"""City search — resolve a free-text city name to a working CityConfig on the fly.

Lets a user search for any city, not just the ones hardcoded in `config.CITIES`,
and get back a real `CityConfig` (bounding box, AQICN slug guess, Trends geo)
that every existing `data_pipelines/`/`modules/` function already accepts, since
they all take a `CityConfig` rather than a hardcoded city name.

Source: Open-Meteo's geocoding API (https://geocoding-api.open-meteo.com/v1/search),
keyless and free for non-commercial use, no rate-limit token required — verified
against Open-Meteo's own docs (not a third-party blog) before wiring this in. It's
the same Open-Meteo family this project already depends on for weather, so this
adds no new vendor. Underlying data is GeoNames.

Two-layer design, mirroring every other pipeline in this package:
  - `search_cities()` / `_fetch_geocode_candidates_raw()`: the network layer,
    cached via the same `cached_fetch` decorator every other fetch function uses.
  - `build_city_config()`, `resolve_trends_geo()`, `guess_aqicn_station_slug()`:
    pure functions with no network I/O, unit-testable against synthetic
    geocoding responses (see tests/test_city_geocoding.py) without hitting the
    network — the same split `aqi_ingestion.pm25_to_aqi` gets from
    `fetch_openaq_archive`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
import requests

from config import CITY_SEARCH_HALF_WIDTH_KM, DEFAULT_TIMEOUT_S, GRID_CELL_KM, HTTP_USER_AGENT, CityConfig
from utils.caching import cached_fetch
from utils.grid import km_per_degree_lat, km_per_degree_lon

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_HEADERS = {"User-Agent": HTTP_USER_AGENT}

# ISO 3166-2:IN subdivision codes, for the subset of Indian states/UTs Google
# Trends' `geo` parameter is known to recognize as "<country>-<state>" (e.g.
# "IN-RJ"). Only states we're confident about are listed here; anything else
# falls back to the country-level code in resolve_trends_geo() rather than
# guess at a code that might not exist or might not resolve in Trends.
INDIA_STATE_TRENDS_GEO: dict[str, str] = {
    "andhra pradesh": "IN-AP", "arunachal pradesh": "IN-AR", "assam": "IN-AS",
    "bihar": "IN-BR", "chhattisgarh": "IN-CT", "goa": "IN-GA", "gujarat": "IN-GJ",
    "haryana": "IN-HR", "himachal pradesh": "IN-HP", "jharkhand": "IN-JH",
    "karnataka": "IN-KA", "kerala": "IN-KL", "madhya pradesh": "IN-MP",
    "maharashtra": "IN-MH", "manipur": "IN-MN", "meghalaya": "IN-ML",
    "mizoram": "IN-MZ", "nagaland": "IN-NL", "odisha": "IN-OR", "punjab": "IN-PB",
    "rajasthan": "IN-RJ", "sikkim": "IN-SK", "tamil nadu": "IN-TN",
    "telangana": "IN-TG", "tripura": "IN-TR", "uttar pradesh": "IN-UP",
    "uttarakhand": "IN-UT", "west bengal": "IN-WB",
    "delhi": "IN-DL", "nct of delhi": "IN-DL", "jammu and kashmir": "IN-JK",
    "ladakh": "IN-LA", "puducherry": "IN-PY", "chandigarh": "IN-CH",
    "andaman and nicobar islands": "IN-AN",
}


@dataclass(frozen=True)
class GeocodeCandidate:
    """One ranked match from the geocoding search — enough to build a CityConfig."""

    name: str
    country: str
    country_code: str
    latitude: float
    longitude: float
    admin1: str | None = None          # state/region, e.g. "Rajasthan" — None if the API omitted it
    population: int | None = None
    timezone: str | None = None

    @property
    def display_name(self) -> str:
        """Disambiguated label for showing same-name candidates to a caller/UI."""
        parts = [self.name, self.admin1, self.country]
        return ", ".join(p for p in parts if p)


@cached_fetch("city_geocoding_search")
def _fetch_geocode_candidates_raw(query: str, count: int = 8) -> pd.DataFrame:
    """Hit Open-Meteo's geocoding search endpoint for a free-text city query.

    Args:
        query: Free-text search, e.g. "Jaipur" or "Springfield".
        count: Max candidates to request (Open-Meteo allows up to 100).

    Returns:
        Raw results as a DataFrame, one row per candidate, columns as Open-Meteo
        returns them (name, latitude, longitude, country, country_code, admin1, ...).

    Raises:
        requests.HTTPError: Network/HTTP failure — caller falls back to cache.
        ValueError: Query matched no cities. Deliberately raised before
            `cached_fetch` would write anything, so a typo'd search doesn't
            overwrite the cache the next good search would otherwise fall back to.
    """
    resp = requests.get(
        _GEOCODING_URL,
        params={"name": query, "count": count, "language": "en", "format": "json"},
        headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S,
    )
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        raise ValueError(f"No geocoding matches for query={query!r}")
    return pd.DataFrame(results)


def search_cities(query: str, count: int = 8) -> list[GeocodeCandidate]:
    """Search for cities by free-text name; caller picks among ambiguous matches.

    The function a "search for a city" UI box should call directly.

    Args:
        query: Free-text city name, e.g. "Jaipur" or "Springfield".
        count: Max candidates to return.

    Returns:
        Ranked list of `GeocodeCandidate`, in the order Open-Meteo/GeoNames
        ranks them (roughly by population/relevance) — not re-sorted here.
        Multiple entries are expected and normal for ambiguous names (e.g.
        "Springfield" matches many countries): show each candidate's
        `display_name` and let the caller pick, don't assume index 0 is right.

    Raises:
        ValueError: No city matched `query` anywhere.
    """
    raw = _fetch_geocode_candidates_raw(query, count)
    return [_row_to_candidate(row) for _, row in raw.iterrows()]


def _row_to_candidate(row: pd.Series) -> GeocodeCandidate:
    """Convert one raw Open-Meteo result row into a `GeocodeCandidate`."""
    def _get(key: str):
        val = row.get(key)
        return None if pd.isna(val) else val

    population = _get("population")
    return GeocodeCandidate(
        name=row["name"],
        country=row.get("country", "") or "",
        country_code=row.get("country_code", "") or "",
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        admin1=_get("admin1"),
        population=int(population) if population is not None else None,
        timezone=_get("timezone"),
    )


def resolve_trends_geo(admin1: str | None, country_code: str) -> str:
    """Best-effort Google Trends `geo` code for a geocoded state/country.

    Args:
        admin1: State/region name from the geocoding result (e.g. "Rajasthan"),
            or None if the API didn't return one.
        country_code: ISO 3166-1 alpha-2 country code (e.g. "IN").

    Returns:
        A state-level code like "IN-RJ" if `admin1` confidently maps to one of
        the known Indian states in `INDIA_STATE_TRENDS_GEO`; otherwise just the
        country-level `country_code`. This is never worse than the precision
        every pre-existing city in this codebase already had — see the known-
        limitation note in `trends_ingestion.py` — only sometimes better.
        Falls back to "IN" if `country_code` itself is empty, matching
        `CityConfig.trends_geo`'s own default.
    """
    if admin1 and country_code.upper() == "IN":
        code = INDIA_STATE_TRENDS_GEO.get(admin1.strip().lower())
        if code:
            return code
    return country_code.upper() if country_code else "IN"


def guess_aqicn_station_slug(city_name: str) -> str:
    """Best-effort AQICN feed slug from a city's display name.

    Args:
        city_name: The candidate's plain name, e.g. "Kanpur".

    Returns:
        A lowercase, hyphenated guess (e.g. "kanpur", "new-delhi") in the same
        style as the hand-picked "delhi"/"jaipur" slugs already in
        `config.CITIES`. This is only ever a guess — AQICN's real station-slug
        scheme varies (some cities need a "country/state/city" path). It's fine
        for it to occasionally 404: `fetch_aqi_with_fallback_chain` already
        tries OpenAQ first and falls further down the chain past AQICN on any
        single source's failure.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", city_name.strip().lower()).strip("-")
    return slug or "unknown"


def _aligned_half_width_km(half_width_km: float, cell_km: float) -> float:
    """Round a half-width up to the nearest whole multiple of the grid cell size.

    Ensures the resulting bounding box's full width (2x this) is an exact
    multiple of `cell_km`, so `utils.grid.build_grid`'s edge cells come out
    full-sized instead of clipped slivers at the box boundary.
    """
    cells_per_side = max(round(half_width_km / cell_km), 1)
    return cells_per_side * cell_km


def build_city_config(candidate: GeocodeCandidate,
                       half_width_km: float = CITY_SEARCH_HALF_WIDTH_KM,
                       cell_km: float = GRID_CELL_KM) -> CityConfig:
    """Build a fully-populated, usable CityConfig from one geocoded candidate.

    Pure function — no network calls — so it's directly unit-testable against
    synthetic `GeocodeCandidate` fixtures.

    Args:
        candidate: A single selected result from `search_cities()`.
        half_width_km: Half-width of the bounding box to build around the
            candidate's lat/lon center; total box is `2 * half_width_km`,
            aligned to the nearest whole multiple of `cell_km` first (see
            `_aligned_half_width_km`) so the grid `utils.grid.build_grid` cuts
            from it divides evenly.
        cell_km: Grid cell edge length; should match `config.GRID_CELL_KM` for
            the resulting box to actually align with the rest of the pipeline.

    Returns:
        A `CityConfig` ready to pass directly into any `data_pipelines/` fetch
        function or `run_demo.run_full_pipeline()` — no static registration in
        `config.CITIES` required.

    Raises:
        ValueError: If `half_width_km` or `cell_km` is not positive.
    """
    if half_width_km <= 0 or cell_km <= 0:
        raise ValueError("half_width_km and cell_km must both be positive")

    aligned_half_width_km = _aligned_half_width_km(half_width_km, cell_km)
    lat_half_deg = aligned_half_width_km / km_per_degree_lat()
    lon_half_deg = aligned_half_width_km / km_per_degree_lon(candidate.latitude)

    return CityConfig(
        name=candidate.name,
        lat_min=candidate.latitude - lat_half_deg,
        lat_max=candidate.latitude + lat_half_deg,
        lon_min=candidate.longitude - lon_half_deg,
        lon_max=candidate.longitude + lon_half_deg,
        aqicn_station_slug=guess_aqicn_station_slug(candidate.name),
        openaq_country=candidate.country_code.upper() or "IN",
        trends_geo=resolve_trends_geo(candidate.admin1, candidate.country_code),
    )


def format_city_config_snippet(config_key: str, city: CityConfig) -> str:
    """Render a `config.CITIES` dict-entry snippet for promoting a searched city.

    Deliberately does not write to `config.py` itself — auto-editing the
    project's source file as a side effect of a search request is a bigger,
    riskier operation than this convenience is worth. Instead this hands back
    exactly the text a developer pastes into `config.CITIES` (and, if they
    want it in the default demo run, adds to `PRIMARY_CITY`/`COMPARISON_CITIES`)
    to make a searched city permanent.

    Args:
        config_key: The dict key to register it under, e.g. "mumbai".
        city: The `CityConfig` built by `build_city_config()`.

    Returns:
        A ready-to-paste Python source snippet.
    """
    return (
        f'    "{config_key}": CityConfig(\n'
        f'        name="{city.name}",\n'
        f'        lat_min={city.lat_min:.4f}, lat_max={city.lat_max:.4f},\n'
        f'        lon_min={city.lon_min:.4f}, lon_max={city.lon_max:.4f},\n'
        f'        aqicn_station_slug="{city.aqicn_station_slug}",\n'
        f'        openaq_country="{city.openaq_country}",\n'
        f'        trends_geo="{city.trends_geo}",\n'
        f'    ),'
    )
