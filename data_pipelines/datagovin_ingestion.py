"""data.gov.in ingestion — free API layer over the government open-data catalog.

Registration is free and typically instant approval (unlike CPCB CCR's own portal,
which has no clean API and needs scraping — data.gov.in re-publishes the same
CPCB real-time AQI feed through a proper REST endpoint, so we go through this
instead of scraping app.cpcbccr.com directly).
"""
from __future__ import annotations

import pandas as pd
import requests

from config import DATAGOVIN_API_KEY, DEFAULT_TIMEOUT_S, HTTP_USER_AGENT, CityConfig
from utils.caching import cached_fetch

_HEADERS = {"User-Agent": HTTP_USER_AGENT}
# Resource ID for "Real Time Air Quality Index from Various Locations" — confirm
# this against the dataset's own API tab on data.gov.in before demo day; resource
# IDs occasionally change when CPCB republishes the feed.
_RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
_BASE_URL = f"https://api.data.gov.in/resource/{_RESOURCE_ID}"


@cached_fetch("datagovin_aqi")
def fetch_datagovin_aqi(city: CityConfig, limit: int = 500) -> pd.DataFrame:
    """Pull the latest CPCB real-time AQI snapshot for a city via data.gov.in.

    Args:
        city: Target city config (filtered by `city.name` matching the
            dataset's "city" field, case-insensitively).
        limit: Max records to request per call.

    Returns:
        DataFrame: date, location, lat, lon, pm25, aqi_estimate — same shape
        as `aqi_ingestion.fetch_openaq_archive` so it's a drop-in fallback.

    Raises:
        ValueError: If `DATAGOVIN_API_KEY` isn't set — this pipeline has no
            keyless path (unlike most others), since data.gov.in requires the
            free key on every call.
    """
    if not DATAGOVIN_API_KEY:
        raise ValueError(
            "DATAGOVIN_API_KEY is not set. Registration is free and instant at "
            "https://api.data.gov.in — this pipeline is only reached as a fallback "
            "tier under OpenAQ/AQICN, so it's fine to skip until you need the backup."
        )

    resp = requests.get(_BASE_URL, params={
        "api-key": DATAGOVIN_API_KEY, "format": "json", "limit": limit,
        "filters[city]": city.name,
    }, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()
    records = resp.json().get("records", [])
    if not records:
        raise ValueError(f"data.gov.in returned no records for city={city.name}")

    df = pd.DataFrame(records)
    # Field names vary by resource version; normalize the common CPCB schema.
    rename_map = {
        "last_update": "date", "station": "location",
        "latitude": "lat", "longitude": "lon", "pollutant_avg": "pm25",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["pm25"] = pd.to_numeric(df.get("pm25"), errors="coerce")

    from data_pipelines.aqi_ingestion import pm25_to_aqi
    df["aqi_estimate"] = df["pm25"].apply(pm25_to_aqi)

    keep = [c for c in ["date", "location", "lat", "lon", "pm25", "aqi_estimate"] if c in df.columns]
    return df[keep].dropna(subset=["pm25"])
