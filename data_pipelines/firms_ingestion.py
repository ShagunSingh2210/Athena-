"""NASA FIRMS active-fire (stubble-burning proxy) ingestion.

Primary source: FIRMS' public Near-Real-Time CSV feed (no MAP_KEY required —
these regional/global "last 24h/48h/7d" text products are openly published).
The keyed FIRMS API is used instead when `FIRMS_MAP_KEY` is set, since it gives
country-level historical date-range queries rather than just a rolling window.
"""
from __future__ import annotations

import io

import pandas as pd
import requests

from config import DEFAULT_TIMEOUT_S, FIRMS_MAP_KEY, HTTP_USER_AGENT, CityConfig
from utils.caching import cached_fetch

_HEADERS = {"User-Agent": HTTP_USER_AGENT}

# VIIRS S-NPP is the standard active-fire product; 375m resolution is fine-grained
# enough to distinguish stubble-burning fields from a single industrial flare stack.
_KEYLESS_NRT_URL = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_7d.csv"


@cached_fetch("firms_hotspots")
def fetch_fire_hotspots(city: CityConfig, days: int = 7) -> pd.DataFrame:
    """Fetch VIIRS active-fire detections and clip to a city bounding box.

    Args:
        city: Target city config (used to spatially clip the global feed).
        days: Lookback window in days (1, 2, or 7 for the keyless global feed).

    Returns:
        DataFrame: date, lat, lon, frp (fire radiative power, MW — a proxy for
        burn intensity, used as the stubble-burning feature in Module 2).
    """
    if FIRMS_MAP_KEY:
        return _fetch_via_api(city, days)
    return _fetch_via_keyless_csv(city)


def _fetch_via_keyless_csv(city: CityConfig) -> pd.DataFrame:
    resp = requests.get(_KEYLESS_NRT_URL, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df = df.rename(columns={"latitude": "lat", "longitude": "lon", "acq_date": "date"})
    clipped = df[
        (df["lat"].between(city.lat_min, city.lat_max)) &
        (df["lon"].between(city.lon_min, city.lon_max))
    ]
    return clipped[["date", "lat", "lon", "frp"]].reset_index(drop=True)


def _fetch_via_api(city: CityConfig, days: int) -> pd.DataFrame:
    """Keyed FIRMS API — area query by bounding box, wider historical range."""
    bbox = f"{city.lon_min},{city.lat_min},{city.lon_max},{city.lat_max}"
    url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
           f"{FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/{bbox}/{days}")
    resp = requests.get(url, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df = df.rename(columns={"latitude": "lat", "longitude": "lon", "acq_date": "date"})
    return df[["date", "lat", "lon", "frp"]].reset_index(drop=True)
