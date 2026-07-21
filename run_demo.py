"""End-to-end demo orchestration for Person A's five modules.

Run with: python run_demo.py
Requires open internet access (this sandbox's does not have it — see README).
Every live call is wrapped in try/except so one failing pipeline (e.g. Overpass
rate-limited) doesn't take down the rest of the demo; failures are logged and
that section is skipped rather than crashing.
"""
from __future__ import annotations

import logging

import pandas as pd

from config import CITIES, COMPARISON_CITIES, FORECAST_HORIZON_DAYS, PRIMARY_CITY, CityConfig
from data_pipelines.aqi_ingestion import fetch_aqi_with_fallback_chain
from data_pipelines.firms_ingestion import fetch_fire_hotspots
from data_pipelines.osm_ingestion import fetch_industrial_zones, fetch_road_network
from data_pipelines.population_ingestion import fetch_population_by_cell
from data_pipelines.reddit_sentiment import fetch_pollution_sentiment
from data_pipelines.trends_ingestion import fetch_search_interest
from data_pipelines.weather_ingestion import fetch_historical_weather, fetch_weather_forecast
from modules.module1_causal_loop import LagCorrelationResult, compute_hci, compute_lag_correlation, render_hci_chart
from modules.module2_attribution import AttributionModelResult, build_feature_table, fit_attribution_model
from modules.module4_pollution_debt import build_leaderboard, compare_two_cities, compute_days_above_threshold
from modules.module5_aqi_forecast import ForecastResult, fit_and_forecast
from modules.pipeline_result import PipelineResult
from modules.zone_drilldown import build_zone_drilldown
from utils.grid import assign_points_to_cells, build_grid

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("run_demo")


def run_module_1(city: CityConfig, aqi_df: pd.DataFrame) -> tuple[pd.DataFrame, LagCorrelationResult]:
    """Module 1: fetch behavior signals, join with AQI, compute lag + HCI + chart.

    Returns:
        `(hci_df, lag_result)` — `api.py` holds both in a city's `PipelineResult`
        so the dashboard endpoint can serve them without recomputing.
    """
    logger.info("[Module 1] %s: pulling search + sentiment signals", city.name)
    trends = fetch_search_interest(city.name)
    sentiment = fetch_pollution_sentiment(city.name)

    daily_aqi = aqi_df.groupby("date", as_index=False)["aqi_estimate"].mean()
    daily_sentiment = sentiment.groupby("date", as_index=False)["neg_share"].mean()

    joined = daily_aqi.merge(trends[["date", "search_interest"]], on="date", how="inner") \
                      .merge(daily_sentiment, on="date", how="inner")
    joined = joined.set_index(pd.to_datetime(joined["date"]))

    lag_result = compute_lag_correlation(joined["aqi_estimate"], joined["search_interest"])
    hci_df = compute_hci(joined.reset_index(drop=True))
    render_hci_chart(hci_df, lag_result, city.name, f"cache/{city.name.lower()}_hci_chart.png")
    logger.info("[Module 1] %s: best lag=%dd r=%.2f, chart saved",
                city.name, lag_result.best_lag_days, lag_result.best_correlation)
    return hci_df, lag_result


def run_module_2(city: CityConfig, aqi_df: pd.DataFrame, weather_history: pd.DataFrame | None):
    """Module 2: build grid, pull spatial + wind layers, fit attribution model."""
    logger.info("[Module 2] %s: building grid + spatial layers", city.name)
    grid = build_grid(city)

    roads = assign_points_to_cells(fetch_road_network(city), grid)
    industrial = assign_points_to_cells(fetch_industrial_zones(city), grid)
    fires = assign_points_to_cells(fetch_fire_hotspots(city), grid)
    aqi_points = assign_points_to_cells(aqi_df, grid)
    aqi_by_cell = aqi_points.groupby("cell_id", as_index=False)["aqi_estimate"].mean()

    feature_table = build_feature_table(grid, roads, industrial, fires, aqi_by_cell, weather=weather_history)
    result = fit_attribution_model(feature_table)
    logger.info("[Module 2] %s: R^2=%.2f, coefficients=%s", city.name, result.r_squared, result.coefficients)
    return result, grid, aqi_points


def run_module_4(city: CityConfig, aqi_df: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Module 4: population + exceedance -> leaderboard for one city."""
    logger.info("[Module 4] %s: computing pollution debt leaderboard", city.name)
    population = fetch_population_by_cell(grid)

    aqi_points = assign_points_to_cells(aqi_df, grid)
    daily_pm25_by_cell = aqi_points[["cell_id", "date", "pm25"]]
    exceedance = compute_days_above_threshold(daily_pm25_by_cell)

    leaderboard = build_leaderboard(exceedance, population)
    logger.info("[Module 4] %s: top zone by pollution debt = %s", city.name, leaderboard.iloc[0]["cell_id"])
    return leaderboard


def run_module_5(city: CityConfig, aqi_df: pd.DataFrame, weather_history: pd.DataFrame) -> ForecastResult:
    """Module 5: forecast T+1/T+2 AQI using historical + forecast weather."""
    logger.info("[Module 5] %s: forecasting AQI %d day(s) ahead", city.name, FORECAST_HORIZON_DAYS)

    daily_aqi = aqi_df.groupby("date", as_index=False)["aqi_estimate"].mean()
    history = daily_aqi.merge(weather_history[["date", "wind_speed_kmh", "humidity_pct"]], on="date", how="inner")
    weather_forecast = fetch_weather_forecast(city, horizon_days=FORECAST_HORIZON_DAYS)

    forecast = fit_and_forecast(history, weather_forecast, horizon_days=FORECAST_HORIZON_DAYS)
    logger.info("[Module 5] %s: forecast=%s (train R^2=%.2f, n=%d days)",
                city.name, dict(zip(forecast.forecast_dates, forecast.forecast_aqi)),
                forecast.train_r_squared, forecast.n_training_days)
    return forecast


def run_zone_drilldown_demo(attribution_result: AttributionModelResult, aqi_points: pd.DataFrame) -> None:
    """Demonstrate the zone-drilldown contract for one sample cell (Person B integration)."""
    if attribution_result.cell_attribution.empty:
        return
    sample_cell = attribution_result.cell_attribution.iloc[0]
    cell_id = sample_cell["cell_id"]

    recent = aqi_points[aqi_points["cell_id"] == cell_id].sort_values("date")["aqi_estimate"].tail(7)
    if recent.empty:
        return

    drilldown = build_zone_drilldown(cell_id, sample_cell, recent)
    logger.info("[Zone drilldown] sample payload for %s: %s", cell_id, drilldown)


def run_full_pipeline(city: CityConfig) -> PipelineResult | None:
    """Run Modules 1, 2, 4, 5 + the zone-drilldown demo end-to-end for one city.

    Works identically for a statically registered city (`config.CITIES[...]`)
    or an ad-hoc `CityConfig` built by `data_pipelines.city_geocoding` from a
    user's search query — nothing in this function reads `config.CITIES`, so
    a searched city needs no static registration to be runnable here. This is
    also the one function `api.py` calls at startup for each city it serves —
    the API layer holds the returned `PipelineResult` in memory and never
    duplicates this orchestration itself.

    Every step is independently try/excepted (existing demo-day-reliability
    convention): one failing module logs and is skipped rather than aborting
    the rest of the pipeline for this city. That's why every `PipelineResult`
    field except `city` is optional — callers (this module's `main()`, or
    `api.py`'s endpoints) must check for `None` per section rather than assume
    a fully populated result.

    Args:
        city: Fully-populated city config, static or ad hoc.

    Returns:
        A `PipelineResult` with whatever sections succeeded, or `None` only
        if the AQI fetch itself failed — at that point there's nothing
        meaningful to attach to a result at all, so this short-circuits
        before constructing one.
    """
    logger.info("=== Running full pipeline for %s ===", city.name)
    try:
        aqi_df = fetch_aqi_with_fallback_chain(city)
    except Exception:
        logger.exception("[AQI] %s: could not fetch AQI data from any source, aborting this city", city.name)
        return None

    result = PipelineResult(city=city, aqi_df=aqi_df)

    try:
        result.weather_history = fetch_historical_weather(city)
    except Exception:
        logger.exception("[Weather] %s: could not fetch historical weather, continuing without it", city.name)

    try:
        result.hci_df, result.lag_result = run_module_1(city, aqi_df)
    except Exception:
        logger.exception("[Module 1] %s failed, continuing to Module 2", city.name)

    try:
        result.attribution_result, result.grid, result.aqi_points = run_module_2(
            city, aqi_df, result.weather_history)
    except Exception:
        logger.exception("[Module 2] %s failed, continuing to Module 4", city.name)

    try:
        grid = result.grid if result.grid is not None else build_grid(city)
        result.leaderboard = run_module_4(city, aqi_df, grid)
    except Exception:
        logger.exception("[Module 4] %s failed", city.name)

    if result.weather_history is not None:
        try:
            result.forecast_result = run_module_5(city, aqi_df, result.weather_history)
        except Exception:
            logger.exception("[Module 5] %s failed", city.name)

    if result.attribution_result is not None and result.aqi_points is not None:
        try:
            run_zone_drilldown_demo(result.attribution_result, result.aqi_points)
        except Exception:
            logger.exception("[Zone drilldown] %s failed", city.name)

    return result


def main() -> None:
    """Default demo entry point: run PRIMARY_CITY + COMPARISON_CITIES, then compare.

    For an ad-hoc searched city, call `run_full_pipeline()` directly instead of
    going through `main()` — see `data_pipelines/city_geocoding.py`. For an
    HTTP-served version of this same eager-compute-at-startup pattern, see `api.py`.
    """
    pipeline_results: dict[str, PipelineResult] = {}
    for city_key in [PRIMARY_CITY, *COMPARISON_CITIES]:
        result = run_full_pipeline(CITIES[city_key])
        if result is not None:
            pipeline_results[city_key] = result

    primary = pipeline_results.get(PRIMARY_CITY)
    if primary is not None and primary.attribution_result is not None:
        for comparison_key in COMPARISON_CITIES:
            comparison_result = pipeline_results.get(comparison_key)
            if comparison_result is None or comparison_result.attribution_result is None:
                continue
            comparison = compare_two_cities(
                primary.attribution_result.cell_attribution,
                comparison_result.attribution_result.cell_attribution,
                CITIES[PRIMARY_CITY].name, CITIES[comparison_key].name,
            )
            logger.info("[2-city comparison] %s vs %s: %s", PRIMARY_CITY, comparison_key, comparison)


if __name__ == "__main__":
    main()
