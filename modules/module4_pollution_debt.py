"""Module 4 — Pollution Debt Leaderboard (calc) + 2-city comparison backend.

Cost formula:
    Cost_z = P_z * D_z * C_pc
where P_z = zone population (Module, WorldPop), D_z = days in the trailing week
where 24h PM2.5 exceeded the WHO safe threshold (15 ug/m3), and C_pc = per-capita
daily economic cost of exposure above that threshold.

C_pc is *not* fabricated: it's derived from published macro estimates of air
pollution's economic burden in India (~3% of GDP annually per multiple WHO/World
Bank-cited studies) divided down to a daily per-capita figure. This must ship
with the "methodology disclaimer" the plan already calls for in the UI —
`DEFAULT_PER_CAPITA_DAILY_COST_INR` below is a defensible order-of-magnitude
estimate for a hackathon demo, not a peer-reviewed economic model, and the UI
copy should say so explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import WHO_PM25_24H_SAFE_THRESHOLD

# Derived from ~3% of India per-capita GDP/year attributed to air-pollution health
# and productivity burden (published WHO/World Bank order-of-magnitude estimates),
# spread across the ~120 "exceedance days" a typical NCR winter sees.
# Methodology disclaimer: this is a demo-grade approximation, not a validated figure.
DEFAULT_PER_CAPITA_DAILY_COST_INR: float = 45.0


@dataclass
class LeaderboardRow:
    """One zone's row in the pollution debt leaderboard."""

    cell_id: str
    population: float
    days_above_threshold: int
    avg_aqi_this_week: float
    estimated_cost_inr: float


def compute_days_above_threshold(daily_pm25_by_cell: pd.DataFrame) -> pd.DataFrame:
    """Count trailing-week days each cell exceeded the WHO PM2.5 safe threshold.

    Args:
        daily_pm25_by_cell: Long-format DataFrame: cell_id, date, pm25. Should
            already be filtered to the trailing 7 days by the caller.

    Returns:
        DataFrame: cell_id, days_above_threshold, avg_aqi_this_week.
    """
    from data_pipelines.aqi_ingestion import pm25_to_aqi

    df = daily_pm25_by_cell.copy()
    df["exceeds"] = df["pm25"] > WHO_PM25_24H_SAFE_THRESHOLD
    df["aqi_estimate"] = df["pm25"].apply(pm25_to_aqi)

    return df.groupby("cell_id", as_index=False).agg(
        days_above_threshold=("exceeds", "sum"),
        avg_aqi_this_week=("aqi_estimate", "mean"),
    )


def build_leaderboard(exceedance: pd.DataFrame, population: pd.DataFrame,
                       per_capita_daily_cost: float = DEFAULT_PER_CAPITA_DAILY_COST_INR) -> pd.DataFrame:
    """Compute estimated pollution debt cost per zone and rank into a leaderboard.

    Args:
        exceedance: Output of `compute_days_above_threshold`.
        population: cell_id, population (Module, from `population_ingestion`).
        per_capita_daily_cost: INR per person per exceedance day.

    Returns:
        DataFrame sorted descending by `estimated_cost_inr`, with a `rank` column,
        ready for Person B's ranked table/bar chart.

    Raises:
        ValueError: If no cells have both exceedance and population data — a
            leaderboard of zero rows would silently render as an empty UI
            rather than surface the join problem.
    """
    merged = exceedance.merge(population, on="cell_id", how="inner")
    if merged.empty:
        raise ValueError("No overlapping cell_ids between exceedance and population tables")

    merged["estimated_cost_inr"] = (
        merged["population"] * merged["days_above_threshold"] * per_capita_daily_cost
    )
    merged = merged.sort_values("estimated_cost_inr", ascending=False).reset_index(drop=True)
    merged["rank"] = merged.index + 1
    return merged[["rank", "cell_id", "population", "days_above_threshold",
                   "avg_aqi_this_week", "estimated_cost_inr"]]


def compare_two_cities(city_a_attribution: pd.DataFrame, city_b_attribution: pd.DataFrame,
                        city_a_name: str, city_b_name: str) -> dict:
    """Compute the diff-factor + pollutant-dominance comparison for two cities.

    Args:
        city_a_attribution: Output of `module2_attribution.fit_attribution_model
            ().cell_attribution` for city A.
        city_b_attribution: Same, for city B.
        city_a_name: Display name for city A (e.g. "Delhi").
        city_b_name: Display name for city B (e.g. "Jaipur").

    Returns:
        Dict consumed directly by Person B's comparison UI:
            {
              "city_a": {"name", "dominant_source", "avg_pct_by_source"},
              "city_b": {...},
              "diff_factor_by_source": {"traffic": +12.4, "industry": -8.1, ...}
            }
        `diff_factor_by_source` is city_a's average share minus city_b's, in
        percentage points — positive means city A is more dominated by that
        source than city B.
    """
    pct_cols = [c for c in city_a_attribution.columns if c.startswith("pct_")]

    def _summarize(df: pd.DataFrame) -> dict:
        avg = df[pct_cols].mean()
        dominant = avg.idxmax().replace("pct_", "")
        return {"dominant_source": dominant, "avg_pct_by_source": avg.to_dict()}

    summary_a = _summarize(city_a_attribution)
    summary_b = _summarize(city_b_attribution)

    diff = {
        col.replace("pct_", ""): float(city_a_attribution[col].mean() - city_b_attribution[col].mean())
        for col in pct_cols
    }

    return {
        "city_a": {"name": city_a_name, **summary_a},
        "city_b": {"name": city_b_name, **summary_b},
        "diff_factor_by_source": diff,
    }
