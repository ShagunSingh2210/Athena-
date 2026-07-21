"""Central configuration for the Air Quality Attribution platform (Person A track).

All credentials are optional. Every pipeline in `data_pipelines/` is designed to run
on keyless public data by default and silently upgrade to a keyed source if the
corresponding environment variable is present. This mirrors the "backup/fallback
dataset for demo-day reliability" requirement from the work distribution plan.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------- #
# Optional credentials (all pipelines degrade gracefully if these are None)
# --------------------------------------------------------------------------- #
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")      # https://aistudio.google.com — free, no card required
# Model name is env-overridable on purpose: Google's free-tier model lineup churns
# faster than this codebase will be maintained (e.g. 2.0 Flash sunset in mid-2026).
# Check https://ai.google.dev/gemini-api/docs/pricing for the current free-tier
# Flash/Flash-Lite model list before demo day and override via .env if needed.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AQICN_TOKEN: str | None = os.getenv("AQICN_TOKEN")            # https://aqicn.org/data-platform/token/ (instant, free)
OPENAQ_API_KEY: str | None = os.getenv("OPENAQ_API_KEY")      # v3 key, optional — S3 archive is keyless
FIRMS_MAP_KEY: str | None = os.getenv("FIRMS_MAP_KEY")        # https://firms.modaps.eosdis.nasa.gov/api/map_key/
REDDIT_CLIENT_ID: str | None = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET: str | None = os.getenv("REDDIT_CLIENT_SECRET")
DATAGOVIN_API_KEY: str | None = os.getenv("DATAGOVIN_API_KEY")  # https://api.data.gov.in — free, usually instant
KAGGLE_USERNAME: str | None = os.getenv("KAGGLE_USERNAME")      # free account, needed only for the offline fallback
KAGGLE_KEY: str | None = os.getenv("KAGGLE_KEY")

HTTP_USER_AGENT = "ETHackathon-AQAttribution/1.0 (contact: team@example.com)"
DEFAULT_TIMEOUT_S = 15


@dataclass(frozen=True)
class CityConfig:
    """Bounding box + metadata needed to build a grid and query APIs for one city."""

    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    aqicn_station_slug: str   # AQICN station path, e.g. "delhi/us-embassy" or "jaipur"
    openaq_country: str = "IN"
    # Google Trends `geo` parameter. Defaults to country-level "IN" because that's
    # what every pre-existing city here has always effectively used (see the known
    # limitation noted in data_pipelines/trends_ingestion.py). city_geocoding.py
    # fills this with a state-level code (e.g. "IN-RJ") on a best-effort basis for
    # searched cities where that mapping is confidently known.
    trends_geo: str = "IN"


# Bounding boxes are intentionally a little larger than the municipal core so grid
# cells at the edge still have full 2km x 2km coverage.
CITIES: dict[str, CityConfig] = {
    "delhi": CityConfig(
        name="Delhi",
        lat_min=28.40, lat_max=28.88,
        lon_min=76.85, lon_max=77.35,
        aqicn_station_slug="delhi",
    ),
    "jaipur": CityConfig(
        name="Jaipur",
        lat_min=26.75, lat_max=27.05,
        lon_min=75.65, lon_max=75.95,
        aqicn_station_slug="jaipur",
    ),
}

GRID_CELL_KM: float = 2.0          # matches Person B's map grid (Day 1 agreement)
MAX_LAG_DAYS: int = 7              # search window for AQI -> search-interest lag correlation
LOOKBACK_DAYS: int = 90            # Day-1 pull window

# --------------------------------------------------------------------------- #
# Which of CITIES.keys() drive the default demo run (run_demo.main()) and the
# 2-city comparison feature. Naming these explicitly (rather than the old
# hardcoded ["delhi", "jaipur"] literal in run_demo.py) is what lets city
# search hand run_full_pipeline() an ad-hoc CityConfig without touching either
# constant — see data_pipelines/city_geocoding.py's "promote to static config"
# helper for making a searched city one of these on purpose.
# --------------------------------------------------------------------------- #
PRIMARY_CITY: str = "delhi"
COMPARISON_CITIES: list[str] = ["jaipur"]

# Half-width (km) of the bounding box city_geocoding.py builds around a
# searched city's lat/lon center — total box is 2x this. Chosen to land in the
# same ~30-50km city-scale ballpark as the hand-picked Delhi/Jaipur boxes above.
CITY_SEARCH_HALF_WIDTH_KM: float = 20.0

# --------------------------------------------------------------------------- #
# CPCB National AQI sub-index breakpoints (official published categories).
# Each entry: (category, AQI_low, AQI_high, PM2.5_low, PM2.5_high) in ug/m3, 24h avg.
# Source: CPCB National Air Quality Index methodology (public standard, 8 pollutants
# defined; PM2.5 shown here since it dominates NCR/Jaipur wintertime attribution).
# --------------------------------------------------------------------------- #
CPCB_PM25_BREAKPOINTS: list[tuple[str, int, int, float, float]] = [
    ("Good", 0, 50, 0.0, 30.0),
    ("Satisfactory", 51, 100, 31.0, 60.0),
    ("Moderate", 101, 200, 61.0, 90.0),
    ("Poor", 201, 300, 91.0, 120.0),
    ("Very Poor", 301, 400, 121.0, 250.0),
    ("Severe", 401, 500, 251.0, 500.0),
]

# WHO 2021 Air Quality Guideline: 24h mean PM2.5 safety threshold (ug/m3).
# Used as the "days above threshold" trigger for Module 4's pollution debt formula.
WHO_PM25_24H_SAFE_THRESHOLD: float = 15.0

# Health-risk copy tone per category, consumed by Module 3's LLM prompt.
HEALTH_ADVISORY_TONE = {
    "Good": "reassuring, no action needed",
    "Satisfactory": "mild caution for sensitive groups",
    "Moderate": "moderate caution, limit prolonged outdoor exertion",
    "Poor": "clear caution, sensitive groups avoid outdoor activity",
    "Very Poor": "urgent caution, general public limit outdoor exposure",
    "Severe": "emergency-level advisory, avoid outdoor exposure entirely",
}

SUPPORTED_LANGUAGES = ["en", "hi", "raj"]  # English, Hindi, Rajasthani (regional, for Jaipur)

FORECAST_HORIZON_DAYS: int = 2  # "tomorrow" + "day after tomorrow", per the handwritten spec

# --------------------------------------------------------------------------- #
# Measures-taken knowledge base — recommended mitigation actions per dominant
# attributed source. This is the data Person B's zone-drilldown "measures" field
# reads directly (see handwritten notes: click zone -> cause % / trend / measures).
# These are real, publicly documented policy levers (GRAP, NCAP, CAQM directives),
# written here as short recommendation strings, not reproduced from any single
# source verbatim.
# --------------------------------------------------------------------------- #
MEASURES_TAKEN_KB: dict[str, list[str]] = {
    "traffic": [
        "Enforce odd-even vehicle rationing during severe-AQI days",
        "Increase public transport frequency on high-traffic corridors",
        "Deploy mechanical road-sweeping/anti-smog guns at major junctions",
        "Fast-track PUC (Pollution Under Control) checks at traffic signals",
    ],
    "industry": [
        "Inspect and enforce emission norms at flagged industrial units",
        "Mandate temporary shutdown of non-essential coal/diesel-based units on Severe days",
        "Push for cleaner fuel (PNG) conversion incentives for local industry",
    ],
    "stubble_burning": [
        "Coordinate with state agri-department on in-situ crop residue management subsidies",
        "Deploy happy-seeder machine access programs for affected farmers",
        "Issue inter-state advisory alerts during peak stubble season (Oct-Nov)",
    ],
}

