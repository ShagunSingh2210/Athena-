"""Kaggle fallback — the last-resort offline dataset in the fallback chain.

Kaggle's API is free (needs a free account + API token, no payment), but unlike
the other keyless sources in this codebase it requires accepting the dataset's
terms once in a browser before the API token can download it. That one manual
step is why this lives at the *bottom* of the fallback chain rather than being
a primary source — everything above it works with zero manual setup.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import CACHE_DIR, KAGGLE_KEY, KAGGLE_USERNAME

_DATASET_SLUG = "rohanrao/air-quality-data-in-india"  # "India Air Quality Data" on Kaggle


def load_kaggle_india_aqi(city_name: str, force_download: bool = False) -> pd.DataFrame:
    """Load (downloading if needed) the Kaggle India AQI dataset, filtered to one city.

    Args:
        city_name: City to filter rows to (matched against the dataset's
            `City` column, case-insensitively).
        force_download: Re-download even if a cached copy already exists.

    Returns:
        DataFrame: date, location, pm25, aqi_estimate for the requested city.

    Raises:
        ValueError: If `KAGGLE_USERNAME`/`KAGGLE_KEY` aren't set and no cached
            copy exists — this is the bottom of the fallback chain, so failure
            here means falling back to the small bundled sample fixture instead
            (see `tests/fixtures/` for that, not this function).
    """
    local_path = CACHE_DIR / "kaggle_india_aqi.csv"

    if force_download or not local_path.exists():
        if not (KAGGLE_USERNAME and KAGGLE_KEY):
            raise ValueError(
                "No cached Kaggle dataset and KAGGLE_USERNAME/KAGGLE_KEY are not set. "
                "Free account + token at https://www.kaggle.com/settings -> API -> "
                "Create New Token. You must also click 'Download' once on the dataset "
                "page in-browser to accept its terms before the API token can pull it."
            )
        _download_via_kaggle_api(local_path)

    df = pd.read_csv(local_path)
    df.columns = [c.strip().lower() for c in df.columns]
    city_rows = df[df["city"].str.lower() == city_name.lower()].copy()
    if city_rows.empty:
        raise ValueError(f"No Kaggle rows found for city={city_name!r}")

    from data_pipelines.aqi_ingestion import pm25_to_aqi
    city_rows = city_rows.rename(columns={"date": "date", "pm2.5": "pm25"})
    city_rows["pm25"] = pd.to_numeric(city_rows.get("pm25"), errors="coerce")
    city_rows["aqi_estimate"] = city_rows["pm25"].apply(pm25_to_aqi)
    city_rows["location"] = city_name
    return city_rows[["date", "location", "pm25", "aqi_estimate"]].dropna(subset=["pm25"])


def _download_via_kaggle_api(local_path: Path) -> None:
    """Authenticate and download the dataset via the official `kaggle` package."""
    import os
    os.environ["KAGGLE_USERNAME"] = KAGGLE_USERNAME
    os.environ["KAGGLE_KEY"] = KAGGLE_KEY

    from kaggle.api.kaggle_api_extended import KaggleApi  # local import: optional dependency

    api = KaggleApi()
    api.authenticate()
    api.dataset_download_files(_DATASET_SLUG, path=str(local_path.parent), unzip=True)

    # The dataset ships as `city_day.csv` inside the zip; normalize to our expected filename.
    extracted = local_path.parent / "city_day.csv"
    if extracted.exists():
        extracted.rename(local_path)
