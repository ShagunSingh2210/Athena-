"""Tests for api.py — the HTTP layer over run_demo.py's pipeline.

No live network calls: `api.run_full_pipeline` is monkeypatched to return
synthetic `PipelineResult`s before the `TestClient` triggers the app's
startup lifespan, and the two other network-touching calls the API makes at
request time (`draft_advisory` via Gemini, `search_cities` via Open-Meteo)
are monkeypatched per-test where exercised. Same synthetic-fixture style as
test_smoke.py / test_city_geocoding.py — nothing here hits a real endpoint.
"""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
from config import CITIES, COMPARISON_CITIES, PRIMARY_CITY
from data_pipelines.city_geocoding import GeocodeCandidate
from modules.module1_causal_loop import LagCorrelationResult
from modules.module2_attribution import AttributionModelResult
from modules.module3_health_advisory import AdvisoryRequest, ApprovalStatus, HealthProfile
from modules.module5_aqi_forecast import ForecastResult
from modules.pipeline_result import PipelineResult

COMPARISON_CITY = COMPARISON_CITIES[0]
UNKNOWN_CITY_KEY = "atlantis"  # never registered in config.CITIES or the synthetic fixture


def _cell_prefix(city_key: str) -> str:
    return CITIES[city_key].name[:3].upper()


def _primary_cell_id() -> str:
    return f"{_cell_prefix(PRIMARY_CITY)}-R000C000"


def _synthetic_pipeline_result(city_key: str) -> PipelineResult:
    """Build a fully-populated PipelineResult with fixture data — no network."""
    city = CITIES[city_key]
    prefix = _cell_prefix(city_key)
    cell_a, cell_b = f"{prefix}-R000C000", f"{prefix}-R000C001"

    hci_df = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "aqi_estimate": [180.0, 200.0, 220.0],
        "hci": [0.4, 0.5, 0.6],
    })
    lag_result = LagCorrelationResult(
        best_lag_days=2, best_correlation=0.85,
        lag_profile=pd.DataFrame({"lag_days": [0, 1, 2], "correlation": [0.5, 0.7, 0.85]}),
    )

    cell_attribution = pd.DataFrame({
        "cell_id": [cell_a, cell_b],
        "aqi_estimate": [220.0, 150.0],
        "pct_traffic": [60.0, 40.0],
        "pct_industry": [25.0, 35.0],
        "pct_stubble_burning": [15.0, 25.0],
    })
    attribution_result = AttributionModelResult(
        r_squared=0.91, coefficients={"traffic_density": 12.0}, intercept=50.0,
        cell_attribution=cell_attribution,
    )

    aqi_points = pd.DataFrame({
        "cell_id": [cell_a] * 5,
        "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
        "aqi_estimate": [150.0, 170.0, 190.0, 210.0, 220.0],
        "pm25": [70.0, 80.0, 90.0, 100.0, 110.0],
    })

    leaderboard = pd.DataFrame({
        "rank": [1, 2], "cell_id": [cell_a, cell_b],
        "population": [10000, 8000], "days_above_threshold": [7, 3],
        "avg_aqi_this_week": [220.0, 150.0], "estimated_cost_inr": [3150000.0, 1080000.0],
    })

    forecast_result = ForecastResult(
        forecast_dates=["2026-01-06", "2026-01-07"], forecast_aqi=[225.0, 230.0],
        train_r_squared=0.7, n_training_days=20,
    )

    return PipelineResult(
        city=city, hci_df=hci_df, lag_result=lag_result,
        attribution_result=attribution_result, aqi_points=aqi_points,
        leaderboard=leaderboard, forecast_result=forecast_result,
    )


@pytest.fixture
def client(monkeypatch):
    """TestClient whose startup lifespan runs against synthetic pipeline data."""
    synthetic_by_name = {
        CITIES[PRIMARY_CITY].name: _synthetic_pipeline_result(PRIMARY_CITY),
        CITIES[COMPARISON_CITY].name: _synthetic_pipeline_result(COMPARISON_CITY),
    }
    monkeypatch.setattr(api, "run_full_pipeline", lambda city: synthetic_by_name.get(city.name))
    with TestClient(api.app) as test_client:
        yield test_client


# --- basic wiring ------------------------------------------------------------

def test_root_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_docs_and_openapi_available(client):
    assert client.get("/docs").status_code == 200
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    for expected in ["/dashboard", "/comparison/{city_key}", "/zones/{city_key}/{cell_id}",
                      "/leaderboard/{city_key}", "/advisories/{city_key}/{cell_id}",
                      "/advisories/{request_id}/review", "/cities/search"]:
        assert expected in paths


# --- dashboard / comparison / zones / leaderboard -----------------------------

def test_dashboard_returns_full_payload(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["city"]["key"] == PRIMARY_CITY
    assert body["human_cost_index"]["best_lag_days"] == 2
    assert body["attribution"]["r_squared"] == pytest.approx(0.91)
    assert len(body["attribution"]["zones"]) == 2
    assert body["forecast"]["forecast_aqi"] == [225.0, 230.0]
    assert len(body["leaderboard_top5"]) == 2


def test_comparison_returns_diff_factor(client):
    resp = client.get(f"/comparison/{COMPARISON_CITY}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["city_a"]["key"] == PRIMARY_CITY
    assert body["city_b"]["key"] == COMPARISON_CITY
    assert "diff_factor_by_source" in body


def test_comparison_unknown_city_404(client):
    resp = client.get(f"/comparison/{UNKNOWN_CITY_KEY}")
    assert resp.status_code == 404


def test_zone_drilldown_ok(client):
    resp = client.get(f"/zones/{PRIMARY_CITY}/{_primary_cell_id()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cell_id"] == _primary_cell_id()
    assert body["dominant_cause"] == "traffic"
    assert body["trend_direction"] == "worsening"


def test_zone_drilldown_unknown_cell_404(client):
    resp = client.get(f"/zones/{PRIMARY_CITY}/NOPE-R999C999")
    assert resp.status_code == 404


def test_zone_drilldown_unknown_city_404(client):
    resp = client.get(f"/zones/{UNKNOWN_CITY_KEY}/{_primary_cell_id()}")
    assert resp.status_code == 404


def test_leaderboard_ok(client):
    resp = client.get(f"/leaderboard/{PRIMARY_CITY}")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_leaderboard_unknown_city_404(client):
    resp = client.get(f"/leaderboard/{UNKNOWN_CITY_KEY}")
    assert resp.status_code == 404


# --- advisories ----------------------------------------------------------------

def _health_profile_body(**overrides):
    body = {"age_group": "elderly", "has_respiratory_condition": True,
            "has_cardiac_condition": False, "is_pregnant": False, "language": "en"}
    body.update(overrides)
    return body


def test_advisory_generation_ok(client, monkeypatch):
    def fake_draft_advisory(cell_id, pm25, profile, language="en"):
        assert cell_id == _primary_cell_id()
        assert pm25 == pytest.approx(90.0)  # mean of [70, 80, 90, 100, 110]
        assert isinstance(profile, HealthProfile)
        return AdvisoryRequest(cell_id=cell_id, pm25=pm25, profile=profile, language=language,
                                risk_category="Poor", draft_text="stub advisory text",
                                status=ApprovalStatus.PENDING_REVIEW)

    monkeypatch.setattr(api, "draft_advisory", fake_draft_advisory)
    resp = client.post(f"/advisories/{PRIMARY_CITY}/{_primary_cell_id()}", json=_health_profile_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending_review"
    assert body["draft_text"] == "stub advisory text"
    assert "request_id" in body and body["request_id"]


def test_advisory_generation_unknown_cell_404(client, monkeypatch):
    monkeypatch.setattr(api, "draft_advisory", lambda *a, **k: pytest.fail("should not be called"))
    resp = client.post(f"/advisories/{PRIMARY_CITY}/NOPE-R999C999", json=_health_profile_body())
    assert resp.status_code == 404


def test_advisory_generation_value_error_becomes_400(client, monkeypatch):
    def raise_value_error(*a, **k):
        raise ValueError("Unsupported language 'xx'")
    monkeypatch.setattr(api, "draft_advisory", raise_value_error)
    resp = client.post(f"/advisories/{PRIMARY_CITY}/{_primary_cell_id()}", json=_health_profile_body(language="xx"))
    assert resp.status_code == 400
    assert "Unsupported language" in resp.json()["error"]


def test_advisory_generation_upstream_failure_becomes_502(client, monkeypatch):
    def raise_upstream_error(*a, **k):
        raise RuntimeError("Gemini 429: rate limited")
    monkeypatch.setattr(api, "draft_advisory", raise_upstream_error)
    resp = client.post(f"/advisories/{PRIMARY_CITY}/{_primary_cell_id()}", json=_health_profile_body())
    assert resp.status_code == 502


def test_officer_review_full_flow(client, monkeypatch):
    def fake_draft_advisory(cell_id, pm25, profile, language="en"):
        return AdvisoryRequest(cell_id=cell_id, pm25=pm25, profile=profile, language=language,
                                risk_category="Poor", draft_text="stub", status=ApprovalStatus.PENDING_REVIEW)
    monkeypatch.setattr(api, "draft_advisory", fake_draft_advisory)

    create_resp = client.post(f"/advisories/{PRIMARY_CITY}/{_primary_cell_id()}", json=_health_profile_body())
    request_id = create_resp.json()["request_id"]

    review_resp = client.post(f"/advisories/{request_id}/review", json={"approve": True, "note": "looks fine"})
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "approved"

    # Reviewing an already-decided advisory must fail, not silently re-apply.
    second_review = client.post(f"/advisories/{request_id}/review", json={"approve": False})
    assert second_review.status_code == 400


def test_officer_review_unknown_request_id_404(client):
    resp = client.post("/advisories/does-not-exist/review", json={"approve": True})
    assert resp.status_code == 404


# --- city search -----------------------------------------------------------

def test_city_search_ok(client, monkeypatch):
    candidates = [
        GeocodeCandidate(name="Jaipur", country="India", country_code="IN",
                          latitude=26.91962, longitude=75.78781, admin1="Rajasthan"),
    ]
    monkeypatch.setattr(api, "search_cities", lambda query, count=8: candidates)
    resp = client.get("/cities/search", params={"query": "Jaipur"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["display_name"] == "Jaipur, Rajasthan, India"


def test_city_search_no_matches_becomes_400(client, monkeypatch):
    def raise_no_matches(query, count=8):
        raise ValueError(f"No geocoding matches for query={query!r}")
    monkeypatch.setattr(api, "search_cities", raise_no_matches)
    resp = client.get("/cities/search", params={"query": "asdfghjkl"})
    assert resp.status_code == 400
