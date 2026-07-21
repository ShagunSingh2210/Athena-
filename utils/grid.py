"""Shared 2km x 2km grid definition.

Person B's map layer and Person A's attribution model must agree on identical
cell IDs (this was the explicit Day-2 sync point in the work distribution plan).
This module is the single source of truth for that grid — Person B's frontend
should treat these cell_ids as the join key, not regenerate its own.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import CityConfig, GRID_CELL_KM

EARTH_RADIUS_KM = 6371.0088


def km_per_degree_lat() -> float:
    """Approximate km per degree of latitude (near-constant globally)."""
    return (2 * np.pi * EARTH_RADIUS_KM) / 360.0


def km_per_degree_lon(lat_deg: float) -> float:
    """km per degree of longitude at a given latitude (shrinks toward the poles).

    Public (not `utils.grid`-private) because `data_pipelines.city_geocoding`
    reuses it to derive a searched city's bounding box using the exact same
    km<->degree conversion `build_grid` uses — one definition, not two
    slightly-different copies that could drift apart.
    """
    return km_per_degree_lat() * np.cos(np.radians(lat_deg))


def build_grid(city: CityConfig, cell_km: float = GRID_CELL_KM) -> pd.DataFrame:
    """Build the 2km x 2km grid cell centroid table for a city bounding box.

    Args:
        city: City bounding box config from `config.CITIES`.
        cell_km: Grid cell edge length in kilometers.

    Returns:
        DataFrame with one row per cell: cell_id, lat_center, lon_center,
        lat_min/max, lon_min/max — sorted so cell_id is stable across runs.

    Raises:
        ValueError: If the bounding box is degenerate (min >= max on either axis).
    """
    if city.lat_min >= city.lat_max or city.lon_min >= city.lon_max:
        raise ValueError(f"Degenerate bounding box for city={city.name!r}")

    mid_lat = (city.lat_min + city.lat_max) / 2
    lat_step_deg = cell_km / km_per_degree_lat()
    lon_step_deg = cell_km / km_per_degree_lon(mid_lat)

    lat_edges = np.arange(city.lat_min, city.lat_max + lat_step_deg, lat_step_deg)
    lon_edges = np.arange(city.lon_min, city.lon_max + lon_step_deg, lon_step_deg)

    # Vectorized cross product of all (row, col) cells — no Python-level loop.
    row_idx, col_idx = np.meshgrid(np.arange(len(lat_edges) - 1), np.arange(len(lon_edges) - 1), indexing="ij")
    row_idx, col_idx = row_idx.ravel(), col_idx.ravel()

    lat_min = lat_edges[row_idx]
    lat_max = lat_edges[row_idx + 1]
    lon_min = lon_edges[col_idx]
    lon_max = lon_edges[col_idx + 1]

    grid = pd.DataFrame({
        "cell_id": [f"{city.name[:3].upper()}-R{r:03d}C{c:03d}" for r, c in zip(row_idx, col_idx)],
        "row": row_idx,
        "col": col_idx,
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_min": lon_min,
        "lon_max": lon_max,
        "lat_center": (lat_min + lat_max) / 2,
        "lon_center": (lon_min + lon_max) / 2,
    })
    return grid


def assign_points_to_cells(points: pd.DataFrame, grid: pd.DataFrame,
                            lat_col: str = "lat", lon_col: str = "lon") -> pd.DataFrame:
    """Vectorized spatial join of point observations (fires, stations) onto grid cells.

    Args:
        points: DataFrame with at least `lat_col`, `lon_col`.
        grid: Output of `build_grid`.
        lat_col: Name of the latitude column in `points`.
        lon_col: Name of the longitude column in `points`.

    Returns:
        `points` with a new `cell_id` column (NaN for points outside the grid).
    """
    if points.empty:
        return points.assign(cell_id=pd.Series(dtype="object"))

    lat_step = grid["lat_max"].iloc[0] - grid["lat_min"].iloc[0]
    lon_step = grid["lon_max"].iloc[0] - grid["lon_min"].iloc[0]
    grid_lat0, grid_lon0 = grid["lat_min"].min(), grid["lon_min"].min()

    row = np.floor((points[lat_col].to_numpy() - grid_lat0) / lat_step).astype(int)
    col = np.floor((points[lon_col].to_numpy() - grid_lon0) / lon_step).astype(int)

    max_row, max_col = grid["row"].max(), grid["col"].max()
    in_bounds = (row >= 0) & (row <= max_row) & (col >= 0) & (col <= max_col)

    lookup = grid.set_index(["row", "col"])["cell_id"]
    cell_ids = np.full(len(points), None, dtype=object)
    valid_idx = np.where(in_bounds)[0]
    if len(valid_idx):
        keys = list(zip(row[valid_idx], col[valid_idx]))
        cell_ids[valid_idx] = lookup.reindex(keys).to_numpy()

    return points.assign(cell_id=cell_ids)
