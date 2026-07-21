"""Fetch-with-fallback utility.

Demo-day reliability requirement from the work distribution plan: every live pull
writes a cached copy on success, and reads that cache if the live call fails
(rate limit, no internet at venue, expired token, etc.) instead of crashing.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

from config import CACHE_DIR

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=pd.DataFrame)


def cached_fetch(cache_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: cache a DataFrame-returning fetch function to CSV, fall back on error.

    Args:
        cache_name: Filename stem for the cache file (e.g. "delhi_aqi").

    Returns:
        Decorated function. On success, writes `CACHE_DIR/{cache_name}.csv` and
        returns the live result. On any exception, logs a warning and returns the
        last cached CSV if one exists; re-raises only if no cache exists either.
    """
    cache_path = CACHE_DIR / f"{cache_name}.csv"

    def decorator(fetch_fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fetch_fn)
        def wrapper(*args, **kwargs) -> T:
            try:
                df = fetch_fn(*args, **kwargs)
                if df is None or df.empty:
                    raise ValueError(f"{fetch_fn.__name__} returned an empty result")
                df.to_csv(cache_path, index=False)
                return df
            except Exception as exc:  # noqa: BLE001 — deliberately broad: any live-fetch failure falls back
                logger.warning("Live fetch failed for %s (%s). Falling back to cache.",
                                fetch_fn.__name__, exc)
                if cache_path.exists():
                    return pd.read_csv(cache_path)
                logger.error("No cache available at %s — cannot recover.", cache_path)
                raise
        return wrapper
    return decorator
