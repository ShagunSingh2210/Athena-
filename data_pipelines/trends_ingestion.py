"""Google Trends ingestion via `pytrends` — fully keyless, real public search data.

Known limitation: `fetch_search_interest` scopes every query to `geo="IN"`
(country-level), not a per-city region, even though `CityConfig.trends_geo`
carries a best-effort state-level code (see config.py / city_geocoding.py).
Wiring that through is a legitimate follow-up, not done here — untested
against live Trends behavior for arbitrary state codes, and country-level
scoping is safe/known-working for Delhi and Jaipur alike.
"""
from __future__ import annotations

import pandas as pd
from pytrends.request import TrendReq

from config import LOOKBACK_DAYS
from utils.caching import cached_fetch

# Symptom/behavior search terms — proxy for public health-seeking behavior (used in
# the HCI formula alongside AQI and sentiment). Chosen to be India-English/Hindi
# transliteration friendly since that's how most users actually search.
DEFAULT_SEARCH_TERMS = ["pollution mask", "cough medicine", "breathing problem", "air purifier"]


@cached_fetch("google_trends")
def fetch_search_interest(city_name: str, terms: list[str] | None = None,
                           lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Pull daily Google Trends interest-over-time for symptom-related search terms.

    Args:
        city_name: City to geo-restrict the query (Trends resolves this to a region).
        terms: Search terms to pull (max 5 per pytrends batch limit).
        lookback_days: History window; Trends returns daily granularity for <=270 days.

    Returns:
        DataFrame indexed by date with one column per term (0-100 relative interest)
        plus a `search_interest` column = row-wise mean across terms.

    Raises:
        Exception: Any pytrends/network failure — caller falls back to cache.
    """
    terms = terms or DEFAULT_SEARCH_TERMS
    pytrends = TrendReq(hl="en-IN", tz=330)  # IST offset
    pytrends.build_payload(terms[:5], timeframe=f"today {max(lookback_days // 30, 1)}-m", geo="IN")
    df = pytrends.interest_over_time()
    if df.empty:
        raise ValueError(f"pytrends returned no data for terms={terms}")

    df = df.drop(columns=["isPartial"], errors="ignore")
    df["search_interest"] = df.mean(axis=1)
    df = df.reset_index().rename(columns={"date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["city"] = city_name
    return df
