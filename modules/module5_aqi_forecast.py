"""Module 5 — AQI Forecast (T+1 / T+2).

New requirement from the handwritten spec, not in the original 7-day plan:
predict tomorrow's and the day-after's AQI.

Model choice: persistence-plus-weather regression, not ARIMA/Prophet/LSTM.
Reasoning, for the deck:
  - AQI has strong day-to-day autocorrelation (today predicts tomorrow
    reasonably well on its own) — persistence is a legitimately strong
    baseline here, not a strawman.
  - What persistence *misses* is exactly what wind forecasts capture: a
    forecast high-wind day should pull the prediction down from pure
    persistence, a still/humid day should pull it up. Regressing the
    change (AQI_t+1 - AQI_t) on forecast wind/humidity captures that
    correction with 2 features and a handful of training rows — appropriate
    for a hackathon's data volume (weeks, not years, of history).
  - ARIMA/LSTM need far more historical rows than a 1-week build can gather
    live to avoid overfitting; they're a legitimate "next step", not this
    week's model.

    AQI_hat_{t+h} = AQI_t + sum_{k=1}^{h} delta_hat_k
    delta_hat_k = alpha + beta_1 * wind_speed_forecast_k + beta_2 * humidity_forecast_k
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from config import FORECAST_HORIZON_DAYS

_DELTA_FEATURES = ["wind_speed_kmh", "humidity_pct"]


@dataclass
class ForecastResult:
    """T+1..T+horizon AQI forecast with the model's fit diagnostics."""

    forecast_dates: list[str]
    forecast_aqi: list[float]
    train_r_squared: float
    n_training_days: int


def _build_training_rows(history: pd.DataFrame) -> pd.DataFrame:
    """Build (day-over-day AQI delta, same-day weather) training rows.

    Args:
        history: Daily DataFrame with `date`, `aqi_estimate`, `wind_speed_kmh`,
            `humidity_pct` — i.e. AQI history joined with historical weather
            for the *same* dates (see `run_demo.py` for the join).

    Returns:
        DataFrame with `delta_aqi` (AQI_t - AQI_{t-1}) and the weather features
        for day t, one row per day after the first.
    """
    df = history.sort_values("date").reset_index(drop=True)
    df["delta_aqi"] = df["aqi_estimate"].diff()
    return df.dropna(subset=["delta_aqi"] + _DELTA_FEATURES)


def fit_and_forecast(history: pd.DataFrame, weather_forecast: pd.DataFrame,
                      horizon_days: int = FORECAST_HORIZON_DAYS) -> ForecastResult:
    """Fit the delta-regression on history and roll it forward using the forecast.

    Args:
        history: Daily AQI + same-day weather, columns `date`, `aqi_estimate`,
            `wind_speed_kmh`, `humidity_pct`. Needs enough rows to fit a
            2-feature regression meaningfully (>= 14 days recommended).
        weather_forecast: Output of `data_pipelines.weather_ingestion.
            fetch_weather_forecast`, columns `date`, `wind_speed_kmh`,
            `humidity_pct`, covering >= `horizon_days` rows.
        horizon_days: How many days ahead to forecast.

    Returns:
        ForecastResult with forecast dates/values and the training R^2 (report
        this alongside the forecast in the UI — a low R^2 here should visibly
        lower confidence in the forecast, not be hidden).

    Raises:
        ValueError: If fewer than 10 training rows are available, or the
            weather forecast doesn't cover the requested horizon.
    """
    training = _build_training_rows(history)
    if len(training) < 10:
        raise ValueError(f"Need >= 10 days of history to fit the forecast delta model, got {len(training)}")
    if len(weather_forecast) < horizon_days:
        raise ValueError(
            f"weather_forecast has {len(weather_forecast)} rows, need >= {horizon_days} for the requested horizon"
        )

    X_train = training[_DELTA_FEATURES].to_numpy()
    y_train = training["delta_aqi"].to_numpy()

    model = LinearRegression()
    model.fit(X_train, y_train)
    train_r2 = model.score(X_train, y_train)

    last_aqi = history.sort_values("date")["aqi_estimate"].iloc[-1]
    forecast_window = weather_forecast.iloc[:horizon_days]
    predicted_deltas = model.predict(forecast_window[_DELTA_FEATURES].to_numpy())

    # Roll the deltas forward cumulatively: AQI_hat_{t+h} = AQI_t + sum(deltas up to h).
    forecast_aqi = (last_aqi + np.cumsum(predicted_deltas)).clip(min=0).tolist()

    return ForecastResult(
        forecast_dates=forecast_window["date"].tolist(),
        forecast_aqi=[round(v, 1) for v in forecast_aqi],
        train_r_squared=float(train_r2),
        n_training_days=len(training),
    )
