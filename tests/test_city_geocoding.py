"""Tests for the pure CityConfig-building logic in data_pipelines/city_geocoding.py.

No live network calls: `search_cities()` is exercised by monkeypatching the
private `_fetch_geocode_candidates_raw` fetch layer with synthetic Open-Meteo-
shaped fixtures, exactly like `test_smoke.py` keeps every other pipeline's live
HTTP call out of the unit tests.
"""
from __future__ import annotations

import pandas as pd
import pytest

from config import GRID_CELL_KM, CityConfig
from data_pipelines.city_geocoding import (
    GeocodeCandidate,
    _row_to_candidate,
    build_city_config,
    format_city_config_snippet,
    guess_aqicn_station_slug,
    resolve_trends_geo,
    search_cities,
)
from utils.grid import build_grid

# Shaped exactly like one row of Open-Meteo's /v1/search "results" list.
JAIPUR_ROW = {
    "id": 1269515, "name": "Jaipur", "latitude": 26.91962, "longitude": 75.78781,
    "country": "India", "country_code": "IN", "admin1": "Rajasthan",
    "population": 3046163, "timezone": "Asia/Kolkata",
}
# A result missing optional fields (admin1/population/timezone), as Open-Meteo
# does for smaller/less-documented places — "empty fields are omitted".
SPARSE_ROW = {
    "id": 999, "name": "Nowheresville", "latitude": 10.0, "longitude": 20.0,
    "country": "Testland", "country_code": "TL",
}


def test_row_to_candidate_parses_full_row():
    candidate = _row_to_candidate(pd.Series(JAIPUR_ROW))
    assert candidate.name == "Jaipur"
    assert candidate.admin1 == "Rajasthan"
    assert candidate.country_code == "IN"
    assert candidate.population == 3046163
    assert candidate.latitude == pytest.approx(26.91962)


def test_row_to_candidate_handles_missing_optional_fields():
    candidate = _row_to_candidate(pd.Series(SPARSE_ROW))
    assert candidate.admin1 is None
    assert candidate.population is None
    assert candidate.timezone is None
    assert candidate.display_name == "Nowheresville, Testland"  # admin1 skipped, not "None"


def test_search_cities_returns_ranked_candidates_without_network(monkeypatch):
    raw = pd.DataFrame([JAIPUR_ROW, SPARSE_ROW])
    monkeypatch.setattr(
        "data_pipelines.city_geocoding._fetch_geocode_candidates_raw",
        lambda query, count=8: raw,
    )
    results = search_cities("anything")
    assert [c.name for c in results] == ["Jaipur", "Nowheresville"]  # order preserved, not re-sorted


def test_resolve_trends_geo_maps_known_indian_state():
    assert resolve_trends_geo("Rajasthan", "IN") == "IN-RJ"
    assert resolve_trends_geo("rajasthan", "in") == "IN-RJ"  # case-insensitive on both sides


def test_resolve_trends_geo_falls_back_for_unmapped_state():
    # A real admin1 value this codebase doesn't happen to have a mapping for.
    assert resolve_trends_geo("Some Unlisted District", "IN") == "IN"


def test_resolve_trends_geo_falls_back_for_non_india_country():
    assert resolve_trends_geo("California", "US") == "US"


def test_resolve_trends_geo_defaults_to_in_when_country_code_missing():
    assert resolve_trends_geo(None, "") == "IN"


@pytest.mark.parametrize("name,expected", [
    ("Jaipur", "jaipur"),
    ("New Delhi", "new-delhi"),
    ("São Paulo", "s-o-paulo"),
    ("  Kanpur  ", "kanpur"),
])
def test_guess_aqicn_station_slug(name, expected):
    assert guess_aqicn_station_slug(name) == expected


def test_build_city_config_bbox_is_centered_and_grid_ready():
    candidate = GeocodeCandidate(
        name="Jaipur", country="India", country_code="IN",
        latitude=26.91962, longitude=75.78781, admin1="Rajasthan",
    )
    city = build_city_config(candidate, half_width_km=20.0, cell_km=2.0)

    assert isinstance(city, CityConfig)
    assert city.lat_min < candidate.latitude < city.lat_max
    assert city.lon_min < candidate.longitude < city.lon_max
    assert city.aqicn_station_slug == "jaipur"
    assert city.trends_geo == "IN-RJ"
    assert city.openaq_country == "IN"

    # The whole point of the km->cell_km alignment: build_grid must cut this
    # box into evenly-sized cells, not a ragged/undersized cell at the far
    # edge. (build_grid's own np.arange(..., stop=lat_max+step, step) can add
    # one extra edge beyond an exact multiple regardless of alignment — that's
    # a pre-existing float-boundary quirk of build_grid itself, not something
    # city_geocoding's alignment controls, so we tolerate +-1 cell here and
    # assert on uniformity instead, which is what "not malformed" actually means.)
    grid = build_grid(city, cell_km=2.0)
    n_lat_cells = grid["row"].max() + 1
    n_lon_cells = grid["col"].max() + 1
    assert 20 <= n_lat_cells <= 21  # 2 * 20km half-width / 2km cells, +-1 arange edge
    assert 20 <= n_lon_cells <= 21
    lat_cell_widths_km = (grid["lat_max"] - grid["lat_min"]).round(6).unique()
    lon_cell_widths_km = (grid["lon_max"] - grid["lon_min"]).round(6).unique()
    assert len(lat_cell_widths_km) == 1  # every row is exactly one cell size, none clipped
    assert len(lon_cell_widths_km) == 1  # every column is exactly one cell size, none clipped


def test_build_city_config_aligns_uneven_half_width_up_to_next_cell_multiple():
    candidate = GeocodeCandidate(name="X", country="Y", country_code="ZZ", latitude=0.0, longitude=0.0)
    # 15km half-width with 2km cells isn't a whole multiple; should round up to 16km (8 cells/side).
    city = build_city_config(candidate, half_width_km=15.0, cell_km=2.0)
    grid = build_grid(city, cell_km=2.0)
    # +-1 tolerance for build_grid's own arange edge quirk (see the test above) —
    # what matters here is the alignment rounded 15 up to 16, not down to 14 or
    # left un-aligned; a broken alignment would land far outside this window.
    assert 16 <= grid["row"].max() + 1 <= 17
    lat_cell_widths_km = (grid["lat_max"] - grid["lat_min"]).round(6).unique()
    assert len(lat_cell_widths_km) == 1


def test_build_city_config_uses_configured_defaults():
    candidate = GeocodeCandidate(name="X", country="Y", country_code="ZZ", latitude=0.0, longitude=0.0)
    city = build_city_config(candidate)
    assert (city.lat_max - city.lat_min) > 0
    # Default cell_km is config.GRID_CELL_KM — this should never silently drift.
    grid = build_grid(city, cell_km=GRID_CELL_KM)
    assert len(grid) > 0


@pytest.mark.parametrize("half_width_km,cell_km", [(0, 2), (-5, 2), (20, 0), (20, -2)])
def test_build_city_config_rejects_non_positive_params(half_width_km, cell_km):
    candidate = GeocodeCandidate(name="X", country="Y", country_code="ZZ", latitude=0.0, longitude=0.0)
    with pytest.raises(ValueError):
        build_city_config(candidate, half_width_km=half_width_km, cell_km=cell_km)


def test_format_city_config_snippet_is_pasteable_python():
    candidate = GeocodeCandidate(
        name="Jaipur", country="India", country_code="IN",
        latitude=26.91962, longitude=75.78781, admin1="Rajasthan",
    )
    city = build_city_config(candidate)
    snippet = format_city_config_snippet("jaipur", city)
    assert '"jaipur": CityConfig(' in snippet
    assert 'name="Jaipur"' in snippet
    assert 'trends_geo="IN-RJ"' in snippet
