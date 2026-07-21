# Athena — Air Quality Attribution, Health Advisory & Pollution Debt Platform

ET Hackathon build: a causal loop detector, geospatial source attribution,
an LLM-drafted + officer-approved citizen health advisory workflow, and a
pollution-debt leaderboard, for Delhi/Jaipur and (via city search) any city.
See "Repo layout" just below for how the backend and frontend halves fit
together, then jump to "For Person B" for the fastest way to start
integrating.

## Backend detail (Person A — Data & Backend Track, v4: + HTTP API)

5 modules, keyless-real-data-first, Delhi + Jaipur as the default demo/comparison
pair (`config.PRIMARY_CITY` / `config.COMPARISON_CITIES`) — but no longer the
*only* runnable cities. v2 extended v1 with what the handwritten spec added:
wind-based dispersion modeling, a T+1/T+2 AQI forecast, a measures-taken
knowledge base, and the zone-drilldown contract (cause % / trend / measures)
Person B's map click needs. v3 added city search: look up any city by name and
run the full pipeline against it without editing `config.py` — see "City
search" below. **v4 adds `api.py`**, a real HTTP layer over all of the above —
see "For Person B" right below for how to run it and what it exposes.

## Repo layout: this is two halves of one system

This repository holds both sides of the ET Hackathon build:

- **Backend (Person A, this README's subject)** — everything at the repo
  root that isn't HTML/CSS/JS: `api.py`, `run_demo.py`, `config.py`,
  `data_pipelines/`, `modules/`, `utils/`, `tests/`. Python, run via
  `uvicorn api:app` (see "For Person B" below).
- **Frontend (Person B)** — `index.html`, `map.html`, `leaderboard.html`,
  `advisory.html`, and `assets/css/`, `assets/js/`. Static HTML/JS, no
  build step, no server-side code — serve the folder with any static
  file server (`python3 -m http.server`, GitHub Pages, Netlify, ...).
  `assets/js/mock-data.js` currently stands in for every backend call so
  the frontend runs standalone; see the mapping table right below for how
  each mock function lines up with a real endpoint from `api.py`.

### Mock → real endpoint mapping

The frontend's mock layer (`assets/js/mock-data.js`) was built with a
`TODO(Person A)` at each call site, matching the real backend's eventual
response shape. Now that `api.py` exists, here's where each one plugs in:

| Frontend mock function | Called from | Real endpoint |
|---|---|---|
| `mockZoneSummary(cellId)` / `mockZoneSummaries(cellIds)` | `map-page.js`, `home.js` | `GET /zones/{city_key}/{cell_id}` |
| `mockLeaderboard(cellIds, topN)` | `leaderboard-page.js` | `GET /leaderboard/{city_key}` (or `/dashboard`'s `leaderboard_top5` for the home-page excerpt) |
| `mockCityComparison(cityA, cityB)` | `leaderboard-page.js` | `GET /comparison/{city_key}` — **on-demand only** (e.g. a "Compare" button), not on page load; see that endpoint's description in `/docs` |
| `mockAdvisory(zone, profile, language)` | `advisory-page.js` | `POST /advisories/{city_key}/{cell_id}` (body: health profile + language) → then `POST /advisories/{request_id}/review` for the officer-approval step `advisory-page.js` already has a queue UI for |
| *(no mock existed for the home-page AQI gauge/trend chart)* | `home.js` | `GET /dashboard` — call this one on page load, it bundles HCI, attribution, forecast, and the leaderboard top-5 in one response |
| `classifyDensity(cells, useLive=true)` | `osm-roads.js` | Already hits the real Overpass API directly — no `api.py` endpoint needed, this one was never mocked-pending-backend |

Response shapes won't be byte-identical to the mock functions' return
values (they weren't written against a real backend yet) — check
`/docs` for each endpoint's actual schema before wiring up `fetch()`
calls, per this README's normal advice below. The offline/mock toggle in
the frontend's header should stay wired to `mock-data.js` regardless —
it's also everyone's demo-day fallback if venue wifi or a live source
drops mid-demo, same as this backend's own `cache/` fallback story.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY at minimum — see below
python run_demo.py      # standalone batch run — logs everything to console
uvicorn api:app --reload  # HTTP API for Person B — see "For Person B" below
pytest tests/           # logic tests, run offline, no network needed — 51/51 passing
```

## For Person B

`api.py` is the integration point — you shouldn't need to read any other file
in this repo to build against this backend.

**Run it:**

```bash
pip install -r requirements.txt
uvicorn api:app --reload
```

**Base URL:** `http://127.0.0.1:8000`

**Source of truth for exact request/response shapes:** open
**`http://127.0.0.1:8000/docs`** once the server is running. It's
auto-generated from `api.py`'s actual route definitions (FastAPI/OpenAPI), so
it can't drift out of sync with the real API the way a hand-written spec in
this README could — use it to try requests interactively, not this file.

**Design you should know about before integrating:**
- Every city this API can answer for is computed **once at startup**, not per
  request — the server does real network calls (AQICN, Open-Meteo, Reddit,
  FIRMS, ...) for `PRIMARY_CITY` and every `COMPARISON_CITIES` entry before
  it starts accepting traffic, then serves everything from memory. Expect
  a real delay on first boot; expect every response after that to be fast.
- `/dashboard` is the only endpoint meant for page load. `/comparison/{city_key}`
  is meant for an explicit user action (a "Compare" button) — its own
  endpoint description in `/docs` says this too.
- Errors come back as JSON, never a raw Python traceback: `{"error": "..."}`
  for 400s from this codebase's own validation (bad language code, invalid
  officer-review state transition, etc.), `{"detail": "..."}` for 404s
  (unknown city/cell/request id — FastAPI's own convention for `HTTPException`),
  and a generic 500 for anything unexpected, logged server-side for Person A
  to debug rather than exposed to you.

**Endpoints** (one line each — `/docs` has the full request/response schema
for every one of these):

| Method | Path | What it does |
|---|---|---|
| GET | `/dashboard` | Primary-city dashboard: HCI series + lag, attribution, forecast, top-5 leaderboard. Call on page load. |
| GET | `/comparison/{city_key}` | Primary city vs. `city_key` diff-factor comparison. Call on-demand only. |
| GET | `/zones/{city_key}/{cell_id}` | Zone drill-down for a map click: cause %, trend, measures. |
| GET | `/leaderboard/{city_key}` | Full pollution-debt leaderboard for one city. |
| POST | `/advisories/{city_key}/{cell_id}` | Draft a personalized health advisory (body: health profile + language). Returns a `request_id`. |
| POST | `/advisories/{request_id}/review` | Officer approve/reject a pending advisory (body: `approve`, optional `note`). |
| GET | `/cities/search?query=...` | Free-text city search — ranked candidates, not a single guess. |

CORS is wide open (`allow_origins=["*"]`) so your dev server (Streamlit, Vite,
whatever) can call this without extra config — see `api.py`'s comment on that
choice before this goes anywhere beyond a demo.

**This sandbox could not live-test the pipelines** — its network is locked to
package registries only. Every function in `data_pipelines/` imports cleanly
and all 13 unit tests pass against synthetic fixtures, but the actual HTTP
calls need a real smoke-test run on a laptop with open internet before Day 4's
integration checkpoint.

## LLM provider: Gemini, genuinely free

Module 3 uses **Gemini** (`gemini-2.5-flash` by default via the current `google-genai`
SDK), not Claude — Google's Flash/Flash-Lite models carry a real free tier,
no credit card required. Three things worth knowing before demo day:

1. **Rate limits are modest on the free tier** (roughly 10-15 requests/minute,
   low hundreds to ~1,500/day depending on model) — fine for a hackathon demo's
   advisory volume, not for a production citizen base.
2. **Google's free-tier terms allow using your prompts/responses to improve
   their models.** This pipeline sends health-profile fields (age group,
   conditions, pregnancy) into the prompt — disclose that in your deck's
   privacy section rather than let a judge ask about it first.
3. **The free-tier model lineup churns fast.** `GEMINI_MODEL` in `.env` is the
   override point if `gemini-2.5-flash` gets sunset before your demo — check
   https://ai.google.dev/gemini-api/docs/pricing for the current free Flash/
   Flash-Lite list.

Get a key at https://aistudio.google.com/apikey — this is genuinely the only
setup step with a real cost consideration in this whole codebase (zero, in
this case, just rate limits to respect). Every other source below is free
with no caveats.

## Data source map

| Module | Keyless real source (default) | Optional upgrade / fallback tier |
|---|---|---|
| 1 — AQI | OpenAQ v3 API | AQICN token → data.gov.in (free key) → Kaggle (free account, last resort) |
| 1 — Search behavior | `pytrends` | — |
| 1 — Sentiment | Reddit public `.json` search endpoints | PRAW (`REDDIT_CLIENT_ID/SECRET`) |
| 2 — Fire/stubble | FIRMS public NRT CSV | FIRMS API `MAP_KEY` |
| 2 — Traffic/industry | OSM Overpass API | Bhuvan WMS (needs login — swap back only for finer industrial sub-types) |
| 2 — Dispersion (new) | Open-Meteo historical archive (wind/humidity) | — |
| 4 — Population | WorldPop public REST stats API | — |
| 5 — Forecast (new) | Open-Meteo forecast endpoint | — |
| 3 — Advisory generation | Gemini free tier (`gemini-2.5-flash`) — no card required | — |
| City search (new) | Open-Meteo geocoding API | — |

`fetch_aqi_with_fallback_chain(city)` in `data_pipelines/aqi_ingestion.py` is the
one call `run_demo.py` uses — it walks the whole AQI fallback tier automatically.

## Formulas

**Human Cost Index** (Module 1): $HCI_t = 0.5 \cdot \widetilde{AQI}_t + 0.25 \cdot \widetilde{S}_t + 0.25 \cdot \widetilde{H}_t$.

**Attribution** (Module 2), now with a wind control: $AQI_i = \beta_0 + \beta_1 \text{traffic}_i + \beta_2 \text{industry}_i + \beta_3 \text{fire}_i + \beta_4 \text{wind}_i + \varepsilon_i$. Wind is fit but excluded from the attribution-% calc — it modifies dispersion, it doesn't emit anything, so a cell can't be "caused by wind."

**Pollution debt** (Module 4): $\text{Cost}_z = P_z \cdot D_z \cdot C_{pc}$, $C_{pc}$ = ₹45/person/exceedance-day (demo-grade estimate — ship with the methodology disclaimer).

**AQI forecast** (Module 5, new): rather than modeling AQI directly, model the day-over-day *change*: $\Delta \widehat{AQI}_{t+1} = \alpha + \beta_1 \cdot \text{wind\_forecast} + \beta_2 \cdot \text{humidity\_forecast}$, rolled forward cumulatively from the last known reading. Chosen over ARIMA/LSTM because a week of live-gathered history is too little data to fit those without overfitting; persistence-plus-weather is a legitimate, explainable baseline for this data volume.

## City search (any city, not just Delhi/Jaipur)

Every pipeline function and every module takes a `CityConfig`, not a hardcoded
city name — that's what makes this possible without touching `config.py`.
`data_pipelines/city_geocoding.py` adds:

- `search_cities(query)` — free-text city search via Open-Meteo's geocoding API
  (`geocoding-api.open-meteo.com`, keyless, no rate-limit token — same vendor
  family this project already uses for weather). Returns a **ranked list** of
  `GeocodeCandidate`s, not a single best guess: ambiguous names ("Springfield",
  "Jaipur" vs. a village also named Jaipur) are genuinely ambiguous, so the
  caller/UI picks from `candidate.display_name`, e.g. "Jaipur, Rajasthan, India".
- `build_city_config(candidate)` — pure function, no network, turns a picked
  candidate into a real `CityConfig`: a ~40km bounding box centered on the
  candidate (aligned to whole `GRID_CELL_KM` multiples so `build_grid` never
  cuts an undersized edge cell), a best-effort AQICN slug guess, and a
  best-effort Trends `geo` code (state-level like `"IN-RJ"` when the geocoded
  state confidently maps to one of India's states, else just the country code
  — see `resolve_trends_geo`'s docstring and the known-limitation note in
  `trends_ingestion.py`).
- This `CityConfig` is immediately usable — pass it straight into
  `run_demo.run_full_pipeline(city)` for an ad-hoc run. **No entry in
  `config.CITIES`, `PRIMARY_CITY`, or `COMPARISON_CITIES` is required.** Those
  three only control what `run_demo.main()`'s default demo run and the 2-city
  comparison use.
- To make a searched city permanent (a new default primary/comparison city),
  call `format_city_config_snippet(key, city)` and paste its output into
  `config.CITIES`, then optionally point `PRIMARY_CITY`/`COMPARISON_CITIES` at
  the new key. This is deliberately a copy-pasteable snippet, not an
  auto-edit of `config.py` from a live search request — promoting a city is a
  developer decision, not something a search box should silently do to source
  control.

## New pieces this round

- **`data_pipelines/weather_ingestion.py`** — Open-Meteo historical + forecast, fully keyless. Also decomposes wind direction into sin/cos so it's a well-behaved regression feature (0° and 359° are adjacent in reality, not in raw degrees).
- **`data_pipelines/datagovin_ingestion.py`** — free-key fallback tier for AQI, sitting under OpenAQ/AQICN in the chain.
- **`data_pipelines/kaggle_fallback.py`** — last-resort offline dataset; needs a free Kaggle account + one manual "accept terms" click, which is why it's the bottom tier rather than a primary source.
- **`modules/module5_aqi_forecast.py`** — the new T+1/T+2 forecast your handwritten notes called for.
- **`modules/zone_drilldown.py`** — assembles cause %, trend direction, and recommended measures into the exact JSON payload Person B's map-click handler reads. This is the direct implementation of your notes: "click on each zone → shows cause / trend / measures."
- **`config.MEASURES_TAKEN_KB`** — mitigation-action recommendations per dominant cause (traffic/industry/stubble-burning), feeding the "measures" field above.
- **`data_pipelines/city_geocoding.py`** — city search: resolve any free-text city name to a working `CityConfig` via Open-Meteo geocoding, without editing `config.py`. See "City search" above.
- **`config.PRIMARY_CITY` / `config.COMPARISON_CITIES`** — the old hardcoded `["delhi", "jaipur"]` literal in `run_demo.main()`, now named constants so city search's ad-hoc path and the static default-demo path share one definition of "which cities run by default."
- **`run_demo.run_full_pipeline(city)`** — the per-city orchestration that used to live inline in `main()`'s loop, extracted so it takes one `CityConfig` and runs identically whether that config came from `config.CITIES` or from a live search.
- **`api.py`** — the HTTP layer for Person B. See "For Person B" above.
- **`modules/pipeline_result.py`** — the `PipelineResult` dataclass bundling everything one `run_full_pipeline()` call produces (HCI/lag, attribution, grid, leaderboard, forecast). `run_demo.run_full_pipeline()` now returns this instead of just the attribution result, so `api.py` can serve every endpoint from one in-memory object per city without recomputing anything.
- **`modules/dashboard_payload.py`** — `build_dashboard_payload()` / `build_comparison_payload()`, the assembly step behind `/dashboard` and `/comparison/{city_key}`. Same role as `zone_drilldown.py`: join other modules' output once here, not per-caller.
- **`utils/serialization.py`** — `to_jsonable()`, the one place DataFrames/dataclasses/numpy scalars become plain JSON-safe Python. Every `api.py` endpoint calls it once at the return statement instead of hand-rolling its own conversion.

## Engineering decisions worth mentioning to judges

- **Wind as a control, not a source**: prevents the model from confusing "still air" with "strong local emitter" — a methodologically real improvement, not just an extra feature for its own sake.
- **Persistence-plus-weather over ARIMA/LSTM for the forecast**: matched to the data volume a 1-week hackathon can actually gather live.
- **Bhuvan → OSM substitution**: keyless, openly-licensed equivalent for the same semantic (industrial land parcels).
- **Fetch-with-fallback everywhere** (`utils/caching.py`): one decorator, reused by all 8 pipelines now, rather than duplicated per-pipeline reliability logic.
- **Zone-drilldown as a single function call**: Person B never joins Module 1/2/measures-KB output themselves — one call returns the whole payload.
- **City search returns candidates, never guesses one**: same-name cities across states/countries are genuinely ambiguous; forcing a UI pick avoids silently building a wrong-city grid.
- **AQICN slug is a documented guess, not a lookup**: there's no free, keyless "name → AQICN slug" resolver, so a searched city's slug is a lowercase-hyphenated heuristic that can 404 — acceptable because `fetch_aqi_with_fallback_chain` already treats AQICN as one link in a chain, not the only source.
- **Promote-to-static is a pasteable snippet, not a file write**: `format_city_config_snippet` never touches `config.py` on disk — turning a search result into a permanent city is a reviewed, committed decision, not a side effect of a user typing a city name.
- **Eager compute at API startup, reusing `run_full_pipeline()` verbatim**: `api.py` is a second *caller* of the exact function `run_demo.main()` uses, not a second implementation — no business logic lives in the API layer, only lookups into what startup already computed.
- **One shared `to_jsonable()` instead of a serializer per endpoint**: walks dataclass fields directly rather than `dataclasses.asdict()`, specifically so nested Enums (`AdvisoryRequest.status`) get their `.value` instead of leaking a non-JSON-safe Enum member, and so a DataFrame field isn't needlessly deep-copied before conversion.
- **ValueError -> 400 globally, not per-endpoint**: this codebase already raises `ValueError` with genuinely useful messages throughout `modules/`/`data_pipelines/` (bad language code, wrong advisory state, no attribution data to compare); one exception handler forwards that message as a 400 instead of every endpoint re-catching the same thing.
- **Advisory generation gets its own 502, not a blanket 500**: a Gemini SDK/network failure during `draft_advisory` is an upstream dependency problem, not a bug in this codebase — distinguishing it from the generic 500 handler tells Person B (and you, at demo time) where to actually look.
- **Route registration order matters and bit us once**: `POST /advisories/{request_id}/review` and `POST /advisories/{city_key}/{cell_id}` are both two segments under `/advisories/`; Starlette matches routes in registration order, so the wildcard-second-segment route would otherwise swallow every `.../review` call before it's ever tried. Fixed by registering the literal-`review`-suffix route first — see the comment on `post_officer_review` in `api.py`, and `test_officer_review_unknown_request_id_404` in `tests/test_api.py`, which is what actually caught this (it 422'd instead of 404ing) before the fix.

## Hardening checklist (Day 4 onward)

- [ ] Register `GEMINI_API_KEY` (free, https://aistudio.google.com/apikey), run Module 3 end-to-end on a real cell + profile
- [ ] Live-smoke-test all `data_pipelines/*` functions (9, including `city_geocoding.py`) on open internet; commit whatever CSVs land in `cache/` as your offline fallback
- [ ] Confirm Person B's map grid cell IDs match `utils.grid.build_grid()` output exactly
- [ ] Sanity-check Module 5's forecast against a couple of days you can verify by eye before trusting it live
- [ ] Have a native speaker check a few generated Hindi/Rajasthani advisories
- [ ] Run `search_cities("<a real city>")` live at least once and eyeball the AQICN slug guess + `trends_geo` before demoing city search — this is the one new piece with zero unit-test coverage of the actual HTTP response shape
- [ ] Boot `uvicorn api:app` on a machine with real internet and confirm startup actually finishes (it does 2 cities' worth of every live pipeline call before serving) — time it, since that's the real "time to first request" Person B should expect
- [ ] Hit every endpoint in `/docs` once against the live-booted server, not just the synthetic-fixture tests — `tests/test_api.py` never exercises the real `run_full_pipeline`/`draft_advisory`/`search_cities` network paths on purpose
