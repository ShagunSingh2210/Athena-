"""`PipelineResult` — everything one `run_demo.run_full_pipeline()` call produces
for one city, bundled together.

Introduced for `api.py`: the API computes this once per city at startup (eager
compute, matching `run_demo.py`'s existing design) and every endpoint reads
from the in-memory bundle instead of recomputing. Lives in `modules/` rather
than `run_demo.py` so `modules/dashboard_payload.py` can depend on the shape
without depending on the top-level orchestration script — `run_demo.py`
imports this dataclass, not the other way around.

Every field except `city` is optional because `run_full_pipeline()` already
tolerates any single module failing without aborting the others (see its
docstring) — a partially-populated result is expected, not a bug, and
`modules/dashboard_payload.py` renders each section's absence explicitly
rather than assuming full population.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import CityConfig
from modules.module1_causal_loop import LagCorrelationResult
from modules.module2_attribution import AttributionModelResult
from modules.module5_aqi_forecast import ForecastResult


@dataclass
class PipelineResult:
    """One city's full pipeline output, per-module optional."""

    city: CityConfig
    aqi_df: pd.DataFrame | None = None
    weather_history: pd.DataFrame | None = None
    hci_df: pd.DataFrame | None = None
    lag_result: LagCorrelationResult | None = None
    attribution_result: AttributionModelResult | None = None
    grid: pd.DataFrame | None = None
    aqi_points: pd.DataFrame | None = None
    leaderboard: pd.DataFrame | None = None
    forecast_result: ForecastResult | None = None
