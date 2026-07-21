"""Zone drill-down — the backend contract behind "click a zone on the map".

Per the handwritten spec: click a zone -> shows cause (% per source), trend
(recent AQI + Google Trends direction), and measures (taken / can be taken).
This module is the single function Person B's map click handler should call;
it assembles output from Modules 1, 2, and the measures knowledge base so the
frontend never has to join those three things itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from config import MEASURES_TAKEN_KB
from modules.module2_attribution import SOURCE_LABELS


@dataclass
class ZoneDrilldown:
    """Exact JSON-serializable payload for one zone's map-click drill-down."""

    cell_id: str
    aqi_estimate: float
    cause_breakdown_pct: dict[str, float]     # e.g. {"traffic": 62.1, "industry": 20.4, "stubble_burning": 17.5}
    dominant_cause: str
    trend_direction: str                      # "worsening" | "improving" | "stable"
    trend_recent_aqi: list[float]             # last N days of AQI for this zone, for a sparkline
    measures_taken: list[str]                 # recommended actions for the dominant cause


def _trend_direction(recent_aqi: pd.Series, flat_threshold: float = 5.0) -> str:
    """Classify a short AQI series as worsening/improving/stable.

    Args:
        recent_aqi: Ascending-date AQI series, ideally 5-7 points.
        flat_threshold: Minimum absolute change (in AQI points) between the
            first and last reading to call it a trend rather than "stable".

    Returns:
        One of "worsening", "improving", "stable".
    """
    if len(recent_aqi) < 2:
        return "stable"
    delta = recent_aqi.iloc[-1] - recent_aqi.iloc[0]
    if abs(delta) < flat_threshold:
        return "stable"
    return "worsening" if delta > 0 else "improving"


def build_zone_drilldown(cell_id: str, cell_attribution_row: pd.Series,
                          recent_aqi_history: pd.Series) -> ZoneDrilldown:
    """Assemble the full drill-down payload for one zone.

    Args:
        cell_id: Grid cell ID (must match Person B's map layer exactly).
        cell_attribution_row: One row from `module2_attribution.
            AttributionModelResult.cell_attribution`, matching this `cell_id`.
        recent_aqi_history: Last 5-7 days of AQI readings for this cell,
            ascending by date — used for both the trend direction and the
            sparkline the UI renders.

    Returns:
        A `ZoneDrilldown` ready to serialize straight to JSON for the frontend
        (`dataclasses.asdict(result)`).

    Raises:
        KeyError: If `cell_attribution_row` doesn't have the expected
            `pct_<source>` columns — signals a Module 2 / drilldown version
            mismatch that should fail loudly rather than render a blank chart.
    """
    pct_columns = {label: f"pct_{label}" for label in SOURCE_LABELS.values()}
    cause_breakdown = {label: float(cell_attribution_row[col]) for label, col in pct_columns.items()}
    dominant_cause = max(cause_breakdown, key=cause_breakdown.get)

    return ZoneDrilldown(
        cell_id=cell_id,
        aqi_estimate=float(cell_attribution_row["aqi_estimate"]),
        cause_breakdown_pct=cause_breakdown,
        dominant_cause=dominant_cause,
        trend_direction=_trend_direction(recent_aqi_history),
        trend_recent_aqi=[round(v, 1) for v in recent_aqi_history.tolist()],
        measures_taken=MEASURES_TAKEN_KB.get(dominant_cause, []),
    )


def to_json_dict(drilldown: ZoneDrilldown) -> dict:
    """Convert a `ZoneDrilldown` to a plain dict for JSON serialization.

    Args:
        drilldown: A `ZoneDrilldown` instance.

    Returns:
        Plain dict, safe for `json.dumps` or returning from a Flask/FastAPI route.
    """
    return asdict(drilldown)
