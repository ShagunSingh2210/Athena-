"""Module 1 — Causal Loop Detector.

Question this answers: does a spike in AQI *lead* public search/sentiment
behavior, and by how many days? That lag is the "causal loop" — high AQI drives
health anxiety, which shows up in search/Reddit activity days later.

HCI (Human Cost Index) definition:
    HCI_t = w1 * AQI_norm_t + w2 * negsent_norm_t + w3 * search_norm_t
with w1=0.5, w2=0.25, w3=0.25 (weights sum to 1). AQI gets the highest weight
because it is the objective driver being validated; sentiment and search are
behavioral *responses* used to corroborate it, not independent risk signals.
All three series are min-max normalized to [0, 1] before weighting so the
index isn't dominated by whichever raw series happens to have larger units.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {"aqi": 0.5, "sentiment": 0.25, "search": 0.25}


@dataclass
class LagCorrelationResult:
    """Result of the AQI -> behavior lag scan."""

    best_lag_days: int
    best_correlation: float
    lag_profile: pd.DataFrame  # columns: lag_days, correlation


def _min_max_normalize(series: pd.Series) -> pd.Series:
    """Vectorized min-max scaling to [0, 1]; constant series map to 0.5 (no signal)."""
    lo, hi = series.min(), series.max()
    if np.isclose(hi, lo):
        return pd.Series(0.5, index=series.index)
    return (series - lo) / (hi - lo)


def compute_lag_correlation(aqi: pd.Series, behavior_signal: pd.Series,
                             max_lag_days: int = 7) -> LagCorrelationResult:
    """Scan lags 0..max_lag_days and find where AQI most strongly leads behavior.

    Args:
        aqi: Daily AQI series, indexed by date (ascending, no gaps ideally).
        behavior_signal: Daily search-interest or negative-sentiment series,
            same date index as `aqi`.
        max_lag_days: Maximum lag (in days) to test.

    Returns:
        LagCorrelationResult with the best lag, its Pearson r, and the full
        lag -> correlation profile (useful for Person B's chart annotation).

    Raises:
        ValueError: If the two series don't overlap enough to correlate
            (fewer than 5 overlapping points after shifting).
    """
    aqi, behavior_signal = aqi.align(behavior_signal, join="inner")
    if len(aqi) < 5 + max_lag_days:
        raise ValueError(
            f"Insufficient overlapping data ({len(aqi)} points) for a "
            f"{max_lag_days}-day lag scan; need at least {5 + max_lag_days}."
        )

    lags = np.arange(0, max_lag_days + 1)
    correlations = np.array([
        aqi.iloc[:len(aqi) - lag].corr(behavior_signal.shift(-lag).iloc[:len(aqi) - lag])
        if lag > 0 else aqi.corr(behavior_signal)
        for lag in lags
    ])

    profile = pd.DataFrame({"lag_days": lags, "correlation": correlations})
    best_idx = int(np.nanargmax(correlations))
    return LagCorrelationResult(
        best_lag_days=int(lags[best_idx]),
        best_correlation=float(correlations[best_idx]),
        lag_profile=profile,
    )


def compute_hci(df: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Compute the Human Cost Index time series.

    Args:
        df: DataFrame indexed/sorted by date with columns `aqi_estimate`,
            `neg_share` (Reddit), and `search_interest` (Trends) already
            joined on date (see `run_demo.py` for the join).
        weights: Override for `DEFAULT_WEIGHTS`; must sum to 1.0.

    Returns:
        `df` with an added `hci` column (0-1 scale, higher = worse).

    Raises:
        ValueError: If weights don't sum to ~1.0, or required columns are missing.
    """
    weights = weights or DEFAULT_WEIGHTS
    if not np.isclose(sum(weights.values()), 1.0):
        raise ValueError(f"HCI weights must sum to 1.0, got {sum(weights.values())}")
    required = {"aqi_estimate", "neg_share", "search_interest"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"compute_hci missing required columns: {missing}")

    out = df.copy()
    out["hci"] = (
        weights["aqi"] * _min_max_normalize(out["aqi_estimate"]) +
        weights["sentiment"] * _min_max_normalize(out["neg_share"]) +
        weights["search"] * _min_max_normalize(out["search_interest"])
    )
    return out


def render_hci_chart(df: pd.DataFrame, lag_result: LagCorrelationResult, city_name: str,
                      output_path: str) -> str:
    """Render the AQI-vs-HCI line chart with the detected lag annotated.

    Args:
        df: Output of `compute_hci` (needs `date`, `aqi_estimate`, `hci`).
        lag_result: Output of `compute_lag_correlation`, for the annotation text.
        city_name: Used in the chart title.
        output_path: Where to save the PNG.

    Returns:
        The `output_path` that was written to (for chaining into a report/UI).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(pd.to_datetime(df["date"]), df["aqi_estimate"], color="tab:red", label="AQI")
    ax1.set_ylabel("AQI", color="tab:red")
    ax1.tick_params(axis="y", labelcolor="tab:red")

    ax2 = ax1.twinx()
    ax2.plot(pd.to_datetime(df["date"]), df["hci"], color="tab:blue", label="HCI")
    ax2.set_ylabel("Human Cost Index (0-1)", color="tab:blue")
    ax2.tick_params(axis="y", labelcolor="tab:blue")

    ax1.set_title(
        f"{city_name}: AQI vs. Human Cost Index "
        f"(behavior lags AQI by {lag_result.best_lag_days}d, r={lag_result.best_correlation:.2f})"
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
