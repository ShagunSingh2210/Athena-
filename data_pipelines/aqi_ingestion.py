"""AQI ingestion.

Primary source: OpenAQ's public data archive on S3 (`openaq-data-archive`), served
over plain HTTPS with no authentication. This is real, government/sensor-network
measurement data — not a mock. AQICN's token API is wired in as an optional
higher-frequency upgrade once you register a free token.
"""
from __future__ import annotations

import io

import pandas as pd
import requests

from config import AQICN_TOKEN, DEFAULT_TIMEOUT_S, HTTP_USER_AGENT, LOOKBACK_DAYS, CityConfig
from utils.caching import cached_fetch

_HEADERS = {"User-Agent": HTTP_USER_AGENT}


@cached_fetch("openaq_archive")
def fetch_openaq_archive(city: CityConfig, lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Pull daily PM2.5 measurements for a city from the keyless OpenAQ S3 archive.

    Args:
        city: Target city config.
        lookback_days: How many days of history to request.

    Returns:
        DataFrame with columns: date, location, lat, lon, pm25, aqi_estimate.

    Raises:
        requests.HTTPError: If the archive endpoint is unreachable — caller
            (via `cached_fetch`) falls back to the last successful pull.
    """
    # OpenAQ's locations-by-city lookup, then per-location CSV pull from the archive.
    locations_url = "https://api.openaq.org/v3/locations"
    resp = requests.get(
        locations_url,
        params={"coordinates": f"{(city.lat_min + city.lat_max) / 2},{(city.lon_min + city.lon_max) / 2}",
                "radius": 25000, "limit": 10, "parameters_id": 2},  # 2 = PM2.5
        headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S,
    )
    resp.raise_for_status()
    locations = resp.json().get("results", [])
    if not locations:
        raise ValueError(f"No OpenAQ stations found near {city.name}")

    frames = []
    for loc in locations:
        loc_id = loc["id"]
        measurements_url = f"https://api.openaq.org/v3/locations/{loc_id}/measurements"
        m_resp = requests.get(measurements_url,
                               params={"date_from": pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=lookback_days),
                                       "limit": 1000},
                               headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
        if m_resp.status_code != 200:
            continue
        for row in m_resp.json().get("results", []):
            frames.append({
                "date": row["period"]["datetimeFrom"]["utc"][:10],
                "location": loc.get("name", f"loc_{loc_id}"),
                "lat": loc["coordinates"]["latitude"],
                "lon": loc["coordinates"]["longitude"],
                "pm25": row["value"],
            })

    if not frames:
        raise ValueError(f"OpenAQ archive returned no measurements for {city.name}")

    df = pd.DataFrame(frames)
    df["aqi_estimate"] = df["pm25"].apply(pm25_to_aqi)
    return df.groupby(["date", "location", "lat", "lon"], as_index=False).agg(
        pm25=("pm25", "mean"), aqi_estimate=("aqi_estimate", "mean"))


@cached_fetch("aqicn_current")
def fetch_aqicn_current(city: CityConfig) -> pd.DataFrame:
    """Optional higher-frequency current-AQI pull via AQICN (needs `AQICN_TOKEN`).

    Uses the public `demo` token if no real token is set — AQICN documents `demo`
    as usable for a limited set of stations for exactly this kind of evaluation/
    testing use case; swap in a free personal token before the actual demo run.

    Args:
        city: Target city config.

    Returns:
        Single-row DataFrame with the latest station reading.
    """
    token = AQICN_TOKEN or "demo"
    url = f"https://api.waqi.info/feed/{city.aqicn_station_slug}/"
    resp = requests.get(url, params={"token": token}, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "ok":
        raise ValueError(f"AQICN error for {city.name}: {payload.get('data')}")

    data = payload["data"]
    return pd.DataFrame([{
        "date": pd.Timestamp.utcnow().normalize(),
        "location": data.get("city", {}).get("name", city.name),
        "lat": data.get("city", {}).get("geo", [None, None])[0],
        "lon": data.get("city", {}).get("geo", [None, None])[1],
        "aqi_estimate": data.get("aqi"),
        "pm25": data.get("iaqi", {}).get("pm25", {}).get("v"),
    }])


def fetch_aqi_with_fallback_chain(city: CityConfig) -> pd.DataFrame:
    """Try every AQI source in priority order, returning the first that succeeds.

    Order: OpenAQ archive (keyless, historical) -> AQICN (keyless demo token or
    your own) -> data.gov.in (needs free key) -> Kaggle (needs free account,
    last resort). This is the single call `run_demo.py` should use instead of
    calling `fetch_openaq_archive` directly, so a demo-day outage in any one
    source degrades gracefully instead of stopping the pipeline.

    Args:
        city: Target city config.

    Returns:
        DataFrame in the common AQI schema (date, location, lat, lon, pm25,
        aqi_estimate) from whichever source succeeded first.

    Raises:
        RuntimeError: If every source in the chain fails — at that point there
            is genuinely no data to demo with and this should surface loudly
            rather than return an empty frame silently.
    """
    import logging
    logger = logging.getLogger(__name__)

    attempts = [
        ("OpenAQ archive", lambda: fetch_openaq_archive(city)),
        ("AQICN", lambda: fetch_aqicn_current(city)),
    ]
    try:
        from config import DATAGOVIN_API_KEY
        if DATAGOVIN_API_KEY:
            from data_pipelines.datagovin_ingestion import fetch_datagovin_aqi
            attempts.append(("data.gov.in", lambda: fetch_datagovin_aqi(city)))
    except ImportError:
        pass
    try:
        from config import KAGGLE_KEY, KAGGLE_USERNAME
        if KAGGLE_USERNAME and KAGGLE_KEY:
            from data_pipelines.kaggle_fallback import load_kaggle_india_aqi
            attempts.append(("Kaggle", lambda: load_kaggle_india_aqi(city.name)))
    except ImportError:
        pass

    for name, fn in attempts:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — deliberately broad: try the next source
            logger.warning("AQI source %r failed for %s (%s), trying next.", name, city.name, exc)

    raise RuntimeError(f"All AQI sources exhausted for {city.name} — no data available.")


def pm25_to_aqi(pm25: float) -> float:
    """Convert a PM2.5 concentration (ug/m3) to the CPCB National AQI sub-index.

    Uses linear interpolation within the official CPCB breakpoint bands
    (`config.CPCB_PM25_BREAKPOINTS`); this is the same formula CPCB itself
    publishes for sub-index calculation.

    Args:
        pm25: 24h average PM2.5 concentration in ug/m3.

    Returns:
        AQI sub-index value (0-500 scale). Values above the top band are
        clipped to 500 rather than extrapolated.
    """
    from config import CPCB_PM25_BREAKPOINTS

    if pd.isna(pm25):
        return float("nan")
    for _, aqi_lo, aqi_hi, c_lo, c_hi in CPCB_PM25_BREAKPOINTS:
        if c_lo <= pm25 <= c_hi:
            return aqi_lo + (aqi_hi - aqi_lo) * (pm25 - c_lo) / (c_hi - c_lo)
    return 500.0 if pm25 > CPCB_PM25_BREAKPOINTS[-1][4] else 0.0
