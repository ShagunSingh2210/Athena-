"""Reddit sentiment ingestion.

Primary path: Reddit's public read-only JSON endpoints (`.json` suffix on any
listing URL) — no OAuth needed for public subreddit search, just a descriptive
User-Agent (Reddit blocks default python-requests UAs). PRAW is wired in as an
optional upgrade for higher rate limits once `REDDIT_CLIENT_ID/SECRET` are set.
"""
from __future__ import annotations

import pandas as pd
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config import DEFAULT_TIMEOUT_S, HTTP_USER_AGENT, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
from utils.caching import cached_fetch

_HEADERS = {"User-Agent": HTTP_USER_AGENT}
_analyzer = SentimentIntensityAnalyzer()

DEFAULT_SUBREDDITS = ["delhi", "india", "indiaspeaks"]


@cached_fetch("reddit_sentiment")
def fetch_pollution_sentiment(city_name: str, subreddits: list[str] | None = None,
                               limit_per_sub: int = 100) -> pd.DataFrame:
    """Search public subreddits for pollution-related posts and score sentiment.

    Args:
        city_name: Used both as a search term and tagged onto output rows.
        subreddits: Subreddits to search; defaults to city/national civic subs.
        limit_per_sub: Max posts pulled per subreddit per call (Reddit JSON caps ~100).

    Returns:
        DataFrame: date, subreddit, title, compound_sentiment, neg_share
        (`neg_share` = VADER negative-lexicon proportion, the raw input the HCI
        formula uses rather than the compound score, since compound conflates
        neutral chatter with genuine relief/positivity).
    """
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        return _fetch_via_praw(city_name, subreddits, limit_per_sub)
    return _fetch_via_public_json(city_name, subreddits, limit_per_sub)


def _fetch_via_public_json(city_name: str, subreddits: list[str] | None,
                            limit_per_sub: int) -> pd.DataFrame:
    subreddits = subreddits or DEFAULT_SUBREDDITS
    rows = []
    for sub in subreddits:
        url = f"https://old.reddit.com/r/{sub}/search.json"
        resp = requests.get(url, params={"q": f"{city_name} pollution OR smog OR AQI",
                                          "restrict_sr": "on", "sort": "new", "limit": limit_per_sub},
                            headers=_HEADERS, timeout=DEFAULT_TIMEOUT_S)
        if resp.status_code != 200:
            continue
        for post in resp.json().get("data", {}).get("children", []):
            p = post["data"]
            rows.append({
                "date": pd.to_datetime(p["created_utc"], unit="s").strftime("%Y-%m-%d"),
                "subreddit": sub,
                "title": p.get("title", ""),
            })

    if not rows:
        raise ValueError(f"No Reddit posts found for {city_name} across {subreddits}")
    return _score_sentiment(pd.DataFrame(rows))


def _fetch_via_praw(city_name: str, subreddits: list[str] | None, limit_per_sub: int) -> pd.DataFrame:
    """PRAW path — only reached if OAuth credentials are configured."""
    import praw  # local import: optional dependency, only needed on this path

    reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID, client_secret=REDDIT_CLIENT_SECRET,
                          user_agent=HTTP_USER_AGENT)
    subreddits = subreddits or DEFAULT_SUBREDDITS
    rows = []
    for sub in subreddits:
        for post in reddit.subreddit(sub).search(f"{city_name} pollution OR smog OR AQI",
                                                   sort="new", limit=limit_per_sub):
            rows.append({
                "date": pd.to_datetime(post.created_utc, unit="s").strftime("%Y-%m-%d"),
                "subreddit": sub,
                "title": post.title,
            })
    if not rows:
        raise ValueError(f"No Reddit posts found for {city_name} across {subreddits}")
    return _score_sentiment(pd.DataFrame(rows))


def _score_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    scores = df["title"].apply(_analyzer.polarity_scores)
    df["compound_sentiment"] = scores.apply(lambda s: s["compound"])
    df["neg_share"] = scores.apply(lambda s: s["neg"])
    return df.drop(columns=["title"])
