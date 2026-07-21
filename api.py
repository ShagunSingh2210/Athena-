"""HTTP API for Person B's frontend — a thin wrapper around run_demo.py's pipeline.

Run with: uvicorn api:app --reload
Then open http://127.0.0.1:8000/docs for interactive, auto-generated request/
response documentation — that page, not this docstring, is the source of
truth for exact shapes. See the README's "For Person B" section for the
one-paragraph orientation.

Design, matching run_demo.py's existing conventions rather than introducing new
ones:
  - **Eager compute at startup, not per-request.** On boot, this calls
    `run_demo.run_full_pipeline()` — the exact same function `run_demo.main()`
    uses — once for `PRIMARY_CITY` and once for each of `COMPARISON_CITIES`,
    and holds the results in memory for the process lifetime. No endpoint
    here re-runs any pipeline; they all just read the in-memory bundle.
  - **No duplicated business logic.** Every endpoint is a thin wrapper: look
    up the relevant `PipelineResult`, call the one existing function that
    already does the real work (`build_dashboard_payload`,
    `build_zone_drilldown`, `draft_advisory`, ...), serialize, return.
  - **ValueError -> 400, unknown lookups -> 404, unhandled -> 500.** This
    codebase's existing pattern is "raise ValueError on failure" throughout
    `modules/`/`data_pipelines/`; the exception handlers below are the one
    place that gets translated into HTTP, so no individual endpoint needs its
    own try/except for it.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import CITIES, COMPARISON_CITIES, PRIMARY_CITY, SUPPORTED_LANGUAGES
from data_pipelines.city_geocoding import search_cities
from modules.dashboard_payload import build_comparison_payload, build_dashboard_payload
from modules.module3_health_advisory import AdvisoryRequest, HealthProfile, draft_advisory, officer_review
from modules.pipeline_result import PipelineResult
from modules.zone_drilldown import build_zone_drilldown
from run_demo import run_full_pipeline
from utils.serialization import to_jsonable

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: eager-compute the pipeline for every city this API serves.

    Reuses `run_demo.run_full_pipeline` verbatim — this is not a second
    implementation of the pipeline, just a second *caller* of it, exactly
    like `run_demo.main()` is the first. A city whose AQI fetch fails
    entirely (the one case `run_full_pipeline` returns `None` for) is logged
    and simply absent from `app.state.pipeline_results`; its endpoints then
    404 with a clear message rather than the process failing to boot.
    """
    logger.info("Startup: running full pipeline for %s", [PRIMARY_CITY, *COMPARISON_CITIES])
    pipeline_results: dict[str, PipelineResult] = {}
    for city_key in [PRIMARY_CITY, *COMPARISON_CITIES]:
        result = run_full_pipeline(CITIES[city_key])
        if result is None:
            logger.warning(
                "City %r produced no PipelineResult at startup (AQI fetch failed for every "
                "source) — its endpoints will 404 until the server restarts.", city_key,
            )
            continue
        pipeline_results[city_key] = result
    app.state.pipeline_results = pipeline_results
    app.state.advisory_store = {}  # dict[str, AdvisoryRequest], keyed by request_id
    logger.info("Startup complete: %s ready, %s unavailable",
                sorted(pipeline_results), sorted(set([PRIMARY_CITY, *COMPARISON_CITIES]) - set(pipeline_results)))
    yield


app = FastAPI(
    title="Air Quality Attribution API",
    description=(
        "HTTP layer over the 5-module air-quality-attribution backend. "
        "Every city this API can answer for is computed once at startup "
        "(see PRIMARY_CITY/COMPARISON_CITIES in config.py) and served from "
        "memory — there is no per-request recomputation."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Permissive by design: this is a hackathon dev setup where Person B's frontend
# (Streamlit/Vite/whatever) runs on its own dev-server port, not a deployed
# origin known in advance. Tighten `allow_origins` before shipping this beyond
# a demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Every `ValueError` raised anywhere in the call chain below an endpoint
    becomes a 400 with the exception's own message — this codebase already
    writes clear, user-facing `ValueError` messages (see e.g.
    `module3_health_advisory.draft_advisory`'s docstring), so there's real
    information to forward, not just a generic string.
    """
    return _json_error(400, str(exc))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort handler: log the real exception server-side, return a
    generic message to the client. No raw Python traceback ever reaches
    Person B's frontend from here.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _json_error(500, "Internal server error.")


def _json_error(status_code: int, message: str):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status_code, content={"error": message})


def _require_pipeline_result(request: Request, city_key: str) -> PipelineResult:
    """Look up a city's in-memory `PipelineResult` or raise a clear 404."""
    results: dict[str, PipelineResult] = request.app.state.pipeline_results
    if city_key not in results:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown or unavailable city_key {city_key!r}. Computed at startup: {sorted(results)}.",
        )
    return results[city_key]


class HealthProfileRequest(BaseModel):
    """Request body for POST /advisories/{city_key}/{cell_id}."""

    age_group: str = Field(..., description='One of "child", "adult", "elderly".')
    has_respiratory_condition: bool = False
    has_cardiac_condition: bool = False
    is_pregnant: bool = False
    language: str = Field("en", description=f"One of {SUPPORTED_LANGUAGES}.")


class OfficerReviewRequest(BaseModel):
    """Request body for POST /advisories/{request_id}/review."""

    approve: bool
    note: str = Field("", description="Optional officer note (e.g. reason for rejection).")


@app.get("/", include_in_schema=False)
def root():
    return {"message": "Air Quality Attribution API — see /docs for interactive documentation."}


@app.get("/dashboard", summary="Primary-city dashboard (call on page load)", tags=["dashboard"])
def get_dashboard(request: Request):
    """Everything the default landing view needs for `PRIMARY_CITY`: the Human
    Cost Index series + detected lag, the source-attribution breakdown, the
    T+1/T+2 AQI forecast, and the top-5 pollution-debt leaderboard rows.

    This is the one endpoint intended for every page load. `/comparison` is
    deliberately separate and on-demand — see its own description.
    """
    result = _require_pipeline_result(request, PRIMARY_CITY)
    return to_jsonable(build_dashboard_payload(PRIMARY_CITY, result))


@app.get("/comparison/{city_key}", summary="Compare PRIMARY_CITY against another city", tags=["dashboard"])
def get_comparison(city_key: str, request: Request):
    """Diff-factor + pollutant-dominance comparison between `PRIMARY_CITY` and
    `city_key`.

    **Call this on an explicit user action only** (e.g. a "Compare" button),
    not on page load — this backend's dashboard/comparison split assumes the
    default view is `/dashboard` alone, with comparison as a deliberate
    second step the citizen opts into. `city_key` must be one of the cities
    computed at startup (`PRIMARY_CITY` or a `COMPARISON_CITIES` entry).
    """
    primary_result = _require_pipeline_result(request, PRIMARY_CITY)
    comparison_result = _require_pipeline_result(request, city_key)
    payload = build_comparison_payload(PRIMARY_CITY, primary_result, city_key, comparison_result)
    return to_jsonable(payload)


@app.get("/zones/{city_key}/{cell_id}", summary="Zone drill-down (map click)", tags=["dashboard"])
def get_zone_drilldown(city_key: str, cell_id: str, request: Request):
    """Cause %, trend direction, and recommended measures for one grid cell —
    the payload behind a map click on `city_key`'s attribution choropleth.
    """
    result = _require_pipeline_result(request, city_key)
    if result.attribution_result is None or result.aqi_points is None:
        raise HTTPException(
            status_code=404,
            detail=f"No attribution data available for city_key {city_key!r} "
                   "(Module 2 did not succeed for this city at startup).",
        )
    matches = result.attribution_result.cell_attribution
    matching_rows = matches[matches["cell_id"] == cell_id]
    if matching_rows.empty:
        raise HTTPException(status_code=404, detail=f"Unknown cell_id {cell_id!r} for city_key {city_key!r}.")

    recent_aqi = (result.aqi_points[result.aqi_points["cell_id"] == cell_id]
                  .sort_values("date")["aqi_estimate"].tail(7))
    drilldown = build_zone_drilldown(cell_id, matching_rows.iloc[0], recent_aqi)
    return to_jsonable(drilldown)


@app.get("/leaderboard/{city_key}", summary="Pollution debt leaderboard", tags=["dashboard"])
def get_leaderboard(city_key: str, request: Request):
    """Full ranked pollution-debt leaderboard for `city_key` (all zones, not
    just the dashboard's top-5 excerpt).
    """
    result = _require_pipeline_result(request, city_key)
    if result.leaderboard is None:
        raise HTTPException(
            status_code=404,
            detail=f"No leaderboard available for city_key {city_key!r} "
                   "(Module 4 did not succeed for this city at startup).",
        )
    return to_jsonable(result.leaderboard)


@app.post("/advisories/{request_id}/review", summary="Officer approve/reject", tags=["advisories"])
def post_officer_review(request_id: str, body: OfficerReviewRequest, request: Request):
    """Apply an officer's approve/reject decision to a PENDING_REVIEW advisory.

    Rejects (400) if `request_id` isn't currently PENDING_REVIEW — including
    if it was already decided once — matching `officer_review`'s existing
    audit-trail guarantee that a decision can't be silently overwritten.

    Registered *before* `POST /advisories/{city_key}/{cell_id}` below on
    purpose: Starlette matches routes in registration order, and both paths
    are two path-segments under `/advisories/`. Putting this one first means
    its literal trailing `review` segment is checked before the other
    route's fully-wildcard `{cell_id}` would otherwise swallow every
    `/advisories/<x>/<y>` request, `.../review` included. (Caught by
    `tests/test_api.py::test_officer_review_unknown_request_id_404` during
    development — it 422'd against the wrong route's body schema instead of
    404ing until this ordering was fixed.)
    """
    store: dict[str, AdvisoryRequest] = request.app.state.advisory_store
    advisory = store.get(request_id)
    if advisory is None:
        raise HTTPException(status_code=404, detail=f"Unknown advisory request_id {request_id!r}.")

    officer_review(advisory, approve=body.approve, note=body.note)  # ValueError -> 400 if not PENDING_REVIEW
    return to_jsonable(advisory)


@app.post("/advisories/{city_key}/{cell_id}", status_code=201,
          summary="Draft a personalized health advisory", tags=["advisories"])
def post_advisory(city_key: str, cell_id: str, body: HealthProfileRequest, request: Request):
    """Generate a draft advisory for a citizen at `cell_id` and place it in
    PENDING_REVIEW for an officer to approve/reject.

    The current PM2.5 reading for `cell_id` is resolved server-side from this
    city's already-computed pipeline data — callers supply only `cell_id` and
    the citizen's health profile, never a raw pollutant value. The returned
    `request_id` is what `/advisories/{request_id}/review` needs next.
    """
    result = _require_pipeline_result(request, city_key)
    if result.aqi_points is None:
        raise HTTPException(status_code=404, detail=f"No AQI data available for city_key {city_key!r} yet.")

    cell_pm25 = result.aqi_points.loc[result.aqi_points["cell_id"] == cell_id, "pm25"].dropna()
    if cell_pm25.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No PM2.5 readings available for cell_id {cell_id!r} in city_key {city_key!r}.",
        )

    profile = HealthProfile(
        age_group=body.age_group,
        has_respiratory_condition=body.has_respiratory_condition,
        has_cardiac_condition=body.has_cardiac_condition,
        is_pregnant=body.is_pregnant,
    )
    try:
        advisory = draft_advisory(cell_id, float(cell_pm25.mean()), profile, language=body.language)
    except ValueError:
        raise  # bad language / missing GEMINI_API_KEY -> 400 via the global ValueError handler
    except Exception as exc:  # noqa: BLE001 — deliberately broad: any Gemini SDK/network failure
        logger.exception("Advisory generation failed calling Gemini for cell_id=%s", cell_id)
        raise HTTPException(
            status_code=502,
            detail=f"Advisory generation failed (upstream LLM provider error): {exc}",
        ) from exc

    request.app.state.advisory_store[advisory.request_id] = advisory
    return to_jsonable(advisory)


@app.get("/cities/search", summary="Search for a city by free-text name", tags=["city-search"])
def get_city_search(query: str, count: int = 8):
    """Free-text city search (any city, not just `PRIMARY_CITY`/`COMPARISON_CITIES`).

    Returns ranked candidates for the caller/UI to disambiguate — see
    `data_pipelines.city_geocoding.search_cities`'s docstring on why this
    never collapses to a single best guess. Note this endpoint only searches;
    it does not run the pipeline for whatever the caller picks (this API only
    serves pipelines computed at startup) — that's a natural next step for a
    background-job version of this API, not something the current
    eager-compute-at-startup design supports synchronously over HTTP.
    """
    candidates = search_cities(query, count=count)  # ValueError (no matches) -> 400
    return [{**to_jsonable(c), "display_name": c.display_name} for c in candidates]
