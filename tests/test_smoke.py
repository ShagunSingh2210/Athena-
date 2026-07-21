"""Smoke tests for Person A's modules using synthetic fixtures.

These validate logic correctness (grid math, HCI formula, regression pipeline,
leaderboard formula) without touching any external API — the live pipelines in
`data_pipelines/` need to be smoke-tested separately on a machine with open
internet access, since this sandbox's network is locked to package registries.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import CITIES
from modules.module1_causal_loop import compute_hci, compute_lag_correlation
from modules.module2_attribution import build_feature_table, fit_attribution_model
from modules.module3_health_advisory import HealthProfile, classify_risk_category, officer_review, ApprovalStatus, AdvisoryRequest, draft_advisory
from modules.module4_pollution_debt import build_leaderboard, compute_days_above_threshold
from modules.module5_aqi_forecast import fit_and_forecast
from modules.zone_drilldown import build_zone_drilldown
from data_pipelines.weather_ingestion import add_wind_direction_components
from utils.grid import assign_points_to_cells, build_grid


def test_grid_build_and_assign():
    grid = build_grid(CITIES["delhi"])
    assert len(grid) > 0
    assert grid["cell_id"].is_unique

    points = pd.DataFrame({
        "lat": [grid["lat_center"].iloc[0], 99.0],  # second point is out-of-bounds
        "lon": [grid["lon_center"].iloc[0], 99.0],
    })
    assigned = assign_points_to_cells(points, grid)
    assert assigned["cell_id"].iloc[0] == grid["cell_id"].iloc[0]
    assert pd.isna(assigned["cell_id"].iloc[1])


def test_lag_correlation_detects_known_lag():
    # Construct a signal where behavior is a pure 3-day-lagged copy of AQI.
    n = 60
    dates = pd.date_range("2026-01-01", periods=n)
    aqi = pd.Series(100 + 50 * np.sin(np.arange(n) / 5), index=dates)
    behavior = aqi.shift(3).bfill()

    result = compute_lag_correlation(aqi, behavior, max_lag_days=7)
    assert result.best_lag_days == 3
    assert result.best_correlation > 0.9


def test_hci_weights_must_sum_to_one():
    df = pd.DataFrame({"aqi_estimate": [100, 200], "neg_share": [0.1, 0.2], "search_interest": [10, 20]})
    with pytest.raises(ValueError):
        compute_hci(df, weights={"aqi": 0.5, "sentiment": 0.5, "search": 0.5})

    out = compute_hci(df)
    assert "hci" in out.columns
    assert out["hci"].between(0, 1).all()


def test_attribution_model_recovers_dominant_source():
    # Synthetic cells where AQI is driven almost entirely by traffic.
    rng = np.random.default_rng(0)
    n_cells = 30
    traffic = rng.uniform(0, 10, n_cells)
    industry = rng.uniform(0, 1, n_cells)  # small, low-signal
    fire = rng.uniform(0, 1, n_cells)      # small, low-signal
    aqi = 50 + 20 * traffic + rng.normal(0, 1, n_cells)

    feature_table = pd.DataFrame({
        "cell_id": [f"C{i}" for i in range(n_cells)],
        "traffic_density": traffic, "industrial_area": industry, "fire_count": fire,
        "aqi_estimate": aqi,
    })
    result = fit_attribution_model(feature_table)
    assert result.r_squared > 0.9
    avg_pct_traffic = result.cell_attribution["pct_traffic"].mean()
    assert avg_pct_traffic > 80  # traffic should dominate attribution


def test_attribution_model_rejects_insufficient_rows():
    tiny = pd.DataFrame({
        "cell_id": ["A", "B"], "traffic_density": [1, 2], "industrial_area": [0, 0],
        "fire_count": [0, 0], "aqi_estimate": [100, 110],
    })
    with pytest.raises(ValueError):
        fit_attribution_model(tiny)


def test_risk_classification_boundaries():
    assert classify_risk_category(10) == "Good"
    assert classify_risk_category(75) == "Moderate"
    assert classify_risk_category(500) == "Severe"


def test_officer_review_state_machine_rejects_double_review():
    advisory = AdvisoryRequest(cell_id="DEL-R001C001", pm25=180,
                                profile=HealthProfile(age_group="elderly", has_respiratory_condition=True),
                                risk_category="Poor", draft_text="stub",
                                status=ApprovalStatus.PENDING_REVIEW)
    officer_review(advisory, approve=True)
    assert advisory.status == ApprovalStatus.APPROVED
    with pytest.raises(ValueError):
        officer_review(advisory, approve=True)  # already decided, must raise


def test_draft_advisory_requires_gemini_key(monkeypatch):
    monkeypatch.setattr("modules.module3_health_advisory.GEMINI_API_KEY", None)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        draft_advisory("DEL-R001C001", pm25=200,
                        profile=HealthProfile(age_group="adult"))


def test_attribution_model_with_wind_control():
    rng = np.random.default_rng(1)
    n_cells = 30
    traffic = rng.uniform(0, 10, n_cells)
    industry = rng.uniform(0, 1, n_cells)
    fire = rng.uniform(0, 1, n_cells)
    aqi = 50 + 20 * traffic + rng.normal(0, 1, n_cells)

    feature_table = pd.DataFrame({
        "cell_id": [f"C{i}" for i in range(n_cells)],
        "traffic_density": traffic, "industrial_area": industry, "fire_count": fire,
        "wind_speed_kmh": rng.uniform(5, 25, n_cells),
        "aqi_estimate": aqi,
    })
    result = fit_attribution_model(feature_table)
    assert "wind_speed_kmh" in result.coefficients  # fit as a control
    # Attribution % must still sum to ~100 across the 3 *attributable* sources only.
    pct_cols = [c for c in result.cell_attribution.columns if c.startswith("pct_")]
    assert len(pct_cols) == 3
    totals = result.cell_attribution[pct_cols].sum(axis=1)
    assert np.allclose(totals, 100.0, atol=0.5)


def test_wind_direction_decomposition_is_circular_safe():
    df = pd.DataFrame({"wind_dir_deg": [0, 90, 180, 270, 359]})
    out = add_wind_direction_components(df)
    # 0 and 359 degrees are almost the same direction — sin/cos should be close, not far apart.
    assert abs(out["wind_dir_sin"].iloc[0] - out["wind_dir_sin"].iloc[-1]) < 0.05
    assert abs(out["wind_dir_cos"].iloc[0] - out["wind_dir_cos"].iloc[-1]) < 0.05


def test_forecast_rolls_forward_from_last_known_aqi():
    dates = pd.date_range("2026-01-01", periods=20).strftime("%Y-%m-%d")
    rng = np.random.default_rng(2)
    wind = rng.uniform(5, 30, 20)
    humidity = rng.uniform(30, 90, 20)
    # AQI drops when wind is high — a real, learnable relationship for the model to find.
    aqi = 200 - 3 * wind + rng.normal(0, 2, 20)

    history = pd.DataFrame({"date": dates, "aqi_estimate": aqi, "wind_speed_kmh": wind, "humidity_pct": humidity})
    forecast_dates = pd.date_range("2026-01-21", periods=2).strftime("%Y-%m-%d")
    weather_forecast = pd.DataFrame({
        "date": forecast_dates, "wind_speed_kmh": [25.0, 25.0], "humidity_pct": [50.0, 50.0],
    })

    result = fit_and_forecast(history, weather_forecast, horizon_days=2)
    assert len(result.forecast_aqi) == 2
    assert all(v >= 0 for v in result.forecast_aqi)  # AQI can't go negative


def test_forecast_rejects_insufficient_history():
    tiny_history = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02"], "aqi_estimate": [100, 110],
        "wind_speed_kmh": [10, 12], "humidity_pct": [50, 55],
    })
    weather_forecast = pd.DataFrame({"date": ["2026-01-03"], "wind_speed_kmh": [15.0], "humidity_pct": [50.0]})
    with pytest.raises(ValueError):
        fit_and_forecast(tiny_history, weather_forecast, horizon_days=1)


def test_zone_drilldown_assembles_cause_trend_measures():
    row = pd.Series({
        "cell_id": "DEL-R001C001", "aqi_estimate": 250.0,
        "pct_traffic": 60.0, "pct_industry": 25.0, "pct_stubble_burning": 15.0,
    })
    recent_aqi = pd.Series([150, 170, 190, 220, 250])  # clearly worsening

    drilldown = build_zone_drilldown("DEL-R001C001", row, recent_aqi)
    assert drilldown.dominant_cause == "traffic"
    assert drilldown.trend_direction == "worsening"
    assert len(drilldown.measures_taken) > 0
    assert drilldown.cell_id == "DEL-R001C001"


def test_leaderboard_cost_formula():
    exceedance = pd.DataFrame({
        "cell_id": ["A", "B"], "days_above_threshold": [7, 2], "avg_aqi_this_week": [300, 90],
    })
    population = pd.DataFrame({"cell_id": ["A", "B"], "population": [10000, 5000]})
    board = build_leaderboard(exceedance, population, per_capita_daily_cost=10.0)
    assert board.iloc[0]["cell_id"] == "A"  # highest cost ranked first
    assert board.iloc[0]["estimated_cost_inr"] == 10000 * 7 * 10.0
