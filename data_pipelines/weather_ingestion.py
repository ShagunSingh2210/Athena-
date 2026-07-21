"""Weather ingestion via Open-Meteo — fully keyless, no signup, no rate-limit key.

Two roles in this system:
  1. Historical wind/humidity feed Module 2's attribution regression as a
     dispersion covariate (high wind disperses pollutants; a cell reading high
     AQI on a high-wind day is more likely a *local, strong* source than one
     reading the same AQI on a still day).
  2. Forecast wind/humidity feed Module 5's T+1/T+2 AQI forecast.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import requests

from config import DEFAULT_TIMEOUT_S, HTTP_USER_AGENT, LOOKBACK_DAYS, CityConfig
from utils.caching import cached_fetch

_HEADERS = {"User-Agent": HTTP_USER_AGENT}
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_DAILY_VARS = ["windspeed_10m_max", "winddirection_10m_dominant", "relative_humidity_2m_mean",
               "temperature_2m_mean", "precipitation_sum"]


def _city_center(city: CityConfig) -> tuple[float, float]:
    return (city.lat_min + city.lat_max) / 2, (city.lon_min + city.lon_max) / 2


@cached_fetch("openmeteo_historical")
def fetch_historical_weather(city: CityConfig, lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Pull daily historical weather for a city center point.

    Args:
        city: Target city config.
        lookback_days: History window in days.

    Returns:
        DataFrame: date, wind_speed_kmh, wind_dir_deg, humidity_pct, temp_c, precip_mm.
    """
    lat, lon = _city_center(city)
    end = pd.Timestamp.utcnow().normalize()
    start = end - pd.Timedelta(days=lookback_days)

    resp = requests.get(_ARCHIVE_URL, params={
        "latitude": lat, "longitude": lon,
        "start_date": start.strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d"),
        "daily": ",".join(_DAILY_VARS), "timezone": "Asia/Kolkata",
    }, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    if not daily.get("time"):
        raise ValueError(f"Open-Meteo archive returned no data for {city.name}")

    return pd.DataFrame({
        "date": daily["time"],
        "wind_speed_kmh": daily["windspeed_10m_max"],
        "wind_dir_deg": daily["winddirection_10m_dominant"],
        "humidity_pct": daily["relative_humidity_2m_mean"],
        "temp_c": daily["temperature_2m_mean"],
        "precip_mm": daily["precipitation_sum"],
    })


@cached_fetch("openmeteo_forecast")
def fetch_weather_forecast(city: CityConfig, horizon_days: int = 2) -> pd.DataFrame:
    """Pull the T+1..T+horizon_days weather forecast, used as Module 5's input.

    Args:
        city: Target city config.
        horizon_days: How many days ahead to forecast (Open-Meteo free tier
            supports up to 16 without a key).

    Returns:
        DataFrame: date, wind_speed_kmh, wind_dir_deg, humidity_pct, temp_c, precip_mm.
    """
    lat, lon = _city_center(city)
    resp = requests.get(_FORECAST_URL, params={
        "latitude": lat, "longitude": lon,
        "daily": ",".join(_DAILY_VARS), "forecast_days": horizon_days + 1,
        "timezone": "Asia/Kolkata",
    }, headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    if not daily.get("time"):
        raise ValueError(f"Open-Meteo forecast returned no data for {city.name}")

    df = pd.DataFrame({
        "date": daily["time"],
        "wind_speed_kmh": daily["windspeed_10m_max"],
        "wind_dir_deg": daily["winddirection_10m_dominant"],
        "humidity_pct": daily["relative_humidity_2m_mean"],
        "temp_c": daily["temperature_2m_mean"],
        "precip_mm": daily["precipitation_sum"],
    })
    return df.iloc[1:].reset_index(drop=True)  # drop today, keep T+1..T+horizon


def add_wind_direction_components(df: pd.DataFrame, wind_dir_col: str = "wind_dir_deg") -> pd.DataFrame:
    """Decompose circular wind direction (degrees) into sin/cos components.

    Raw degrees are a bad regression feature (0 deg and 359 deg are adjacent in
    reality but far apart numerically). sin/cos components fix that discontinuity.

    Args:
        df: DataFrame containing `wind_dir_col` in degrees [0, 360).
        wind_dir_col: Column name holding wind direction in degrees.

    Returns:
        `df` with two added columns: wind_dir_sin, wind_dir_cos.
    """
    radians = np.radians(df[wind_dir_col].to_numpy())
    out = df.copy()
    out["wind_dir_sin"] = np.sin(radians)
    out["wind_dir_cos"] = np.cos(radians)
    return out
