"""Dashboard + comparison payload builders for api.py.

Same role as `modules/zone_drilldown.py`: Person B's frontend should call one
endpoint and get a ready-to-render payload, never join Module 1/2/4/5 output
itself. These two functions are the assembly step behind `/dashboard` and
`/comparison/{city_key}` in `api.py` — they return plain Python structures
(dicts nesting DataFrames/dataclasses freely); `api.py` passes the result
through `utils.serialization.to_jsonable` once at the HTTP boundary, so
nothing here needs to worry about JSON-safety itself.
"""
from __future__ import annotations

from modules.module4_pollution_debt import compare_two_cities
from modules.pipeline_result import PipelineResult


def build_dashboard_payload(city_key: str, result: PipelineResult) -> dict:
    """Assemble the primary-city, page-load dashboard payload.

    Args:
        city_key: This city's key in `config.CITIES` (e.g. "delhi") — included
            so the frontend can label things without a second lookup.
        result: This city's `PipelineResult` from `run_demo.run_full_pipeline`.

    Returns:
        Dict with `city`, `human_cost_index`, `attribution`, `forecast`, and
        `leaderboard_top5` keys. A section is `None` (not omitted) if its
        underlying module failed for this run — `PipelineResult`'s fields are
        individually optional by design (see its docstring) — so the frontend
        can render a fixed layout with per-section empty states rather than
        branching on which keys exist.
    """
    human_cost_index = None
    if result.hci_df is not None and result.lag_result is not None:
        human_cost_index = {
            "best_lag_days": result.lag_result.best_lag_days,
            "best_correlation": result.lag_result.best_correlation,
            "series": result.hci_df[["date", "aqi_estimate", "hci"]],
        }

    attribution = None
    if result.attribution_result is not None:
        attribution = {
            "r_squared": result.attribution_result.r_squared,
            "coefficients": result.attribution_result.coefficients,
            "zones": result.attribution_result.cell_attribution,
        }

    leaderboard_top5 = result.leaderboard.head(5) if result.leaderboard is not None else None

    return {
        "city": {"key": city_key, "name": result.city.name},
        "human_cost_index": human_cost_index,
        "attribution": attribution,
        "forecast": result.forecast_result,
        "leaderboard_top5": leaderboard_top5,
    }


def build_comparison_payload(primary_key: str, primary: PipelineResult,
                              comparison_key: str, comparison: PipelineResult) -> dict:
    """Assemble the on-demand 2-city comparison payload.

    Meant to be called on an explicit user action (e.g. a "Compare" button
    click), not on page load — `/dashboard` is the page-load endpoint. This
    function itself is cheap (it just diffs two already-computed attribution
    results), but keeping the calling *pattern* on-demand matches how this
    backend was designed: comparison is a deliberate second view, not part of
    the default dashboard payload every visitor triggers.

    Args:
        primary_key: The primary city's key, e.g. "delhi".
        primary: The primary city's `PipelineResult`.
        comparison_key: The comparison city's key, e.g. "jaipur".
        comparison: The comparison city's `PipelineResult`.

    Returns:
        `module4_pollution_debt.compare_two_cities`'s output dict, with each
        side's `config.CITIES` key attached alongside its display name.

    Raises:
        ValueError: If either city's Module 2 attribution didn't succeed —
            there is nothing to compare without it.
    """
    if primary.attribution_result is None or comparison.attribution_result is None:
        raise ValueError(
            f"Cannot compare {primary_key!r} and {comparison_key!r}: "
            "both cities need a successful attribution result."
        )

    payload = compare_two_cities(
        primary.attribution_result.cell_attribution,
        comparison.attribution_result.cell_attribution,
        primary.city.name, comparison.city.name,
    )
    payload["city_a"]["key"] = primary_key
    payload["city_b"]["key"] = comparison_key
    return payload
