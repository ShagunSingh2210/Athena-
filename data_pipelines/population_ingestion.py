"""Population ingestion via WorldPop's public REST statistics API.

Keyless by design: WorldPop's `/v1/services/stats` endpoint accepts an arbitrary
GeoJSON polygon and returns a population sum for it, so per-grid-cell population
is one HTTP call per cell polygon — no raster download/zonal-stats pipeline needed
(avoids a heavy `rasterio`/`rasterstats` dependency for a hackathon timeline).
"""
from __future__ import annotations

import time

import pandas as pd
import requests

from config import DEFAULT_TIMEOUT_S, HTTP_USER_AGENT
from utils.caching import cached_fetch

_STATS_URL = "https://api.worldpop.org/v1/services/stats"
_HEADERS = {"User-Agent": HTTP_USER_AGENT}
_DATASET = "wpgppop"  # WorldPop Global Project Population, most recent year available


def _cell_geojson(lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon_min, lat_min], [lon_max, lat_min],
            [lon_max, lat_max], [lon_min, lat_max], [lon_min, lat_min],
        ]],
    }


@cached_fetch("worldpop_population")
def fetch_population_by_cell(grid: pd.DataFrame, poll_interval_s: float = 1.0,
                              max_polls: int = 15) -> pd.DataFrame:
    """Fetch population estimate per grid cell from WorldPop.

    Args:
        grid: Output of `utils.grid.build_grid` (needs cell_id + bbox columns).
        poll_interval_s: Delay between task-status polls (WorldPop stats jobs
            are async — submit, then poll a task_id until done).
        max_polls: Max polls per cell before giving up on that cell (skipped,
            not fatal — a partial population table still lets Module 4 run).

    Returns:
        DataFrame: cell_id, population. Cells WorldPop couldn't resolve in time
        are simply omitted; Module 4 should treat missing cells as population 0
        with a logged warning rather than crash the leaderboard calc.
    """
    rows = []
    for _, cell in grid.iterrows():
        geojson = _cell_geojson(cell["lat_min"], cell["lat_max"], cell["lon_min"], cell["lon_max"])
        submit = requests.get(_STATS_URL, params={"dataset": _DATASET, "year": 2020,
                                                    "geojson": str(geojson), "runasync": "true"},
                               headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
        if submit.status_code != 200:
            continue
        task_id = submit.json().get("taskid")
        if not task_id:
            continue

        population = None
        for _ in range(max_polls):
            time.sleep(poll_interval_s)
            status = requests.get(f"{_STATS_URL}/{task_id}", headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
            payload = status.json()
            if payload.get("status") == "finished":
                population = payload.get("data", {}).get("total_population")
                break
        if population is not None:
            rows.append({"cell_id": cell["cell_id"], "population": population})

    if not rows:
        raise ValueError("WorldPop returned no resolvable cells — check connectivity/geometry.")
    return pd.DataFrame(rows)
