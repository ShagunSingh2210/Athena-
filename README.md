# Athena — Air Quality Attribution, Health Advisory & Pollution Debt Platform

Athena turns raw air-quality signals into four things a
city actually needs: **why** a zone is polluted (traffic vs. industry vs.
stubble-burning), **who's affected and how badly** (a composite Human Cost
Index correlating AQI with public search/sentiment behavior), **what to tell
citizens** (LLM-drafted, officer-approved, multilingual health advisories),
and **what it's costing** (a per-zone pollution-debt leaderboard). It ships
as a working, tested backend plus a full multi-page dashboard UI — for
Delhi and Jaipur out of the box, and for any city by name via live geocoding.

Built with Python, FastAPI, the Gemini API, HTML/CSS/JS.
**Highlights:** Multi-city support • Live public data sources • Offline demo mode • 51/51 backend tests passing

## Repo layout: two halves of one system

- **Backend (Python)** — `api.py`, `run_demo.py`, `config.py`,
  `data_pipelines/`, `modules/`, `utils/`, `tests/`. Run via
  `uvicorn api:app` (see "Run the backend" below).
- **Frontend (static HTML/CSS/JS)** — `index.html`, `map.html`,
  `causal-loop.html`, `advisory.html`, `leaderboard.html`, `assets/css/`,
  `assets/js/`. No build step — serve with any static file server (see
  "Run the frontend" below).

The frontend communicates with the FastAPI backend through `assets/js/api.js`, which serves as the API client for every page. Whenever the backend is available, pages retrieve live data through the corresponding API endpoints. An optional deterministic offline mode is also provided for local development, testing, and reliable demonstrations when network connectivity or external data providers are unavailable. On the backend, `api.py` exposes every analytics module through REST endpoints, with interactive API documentation automatically generated at `/docs`.

## What's inside — backend modules

| # | Module | What it does |
|---|---|---|
| 1 | **Causal Loop Detector** | Correlates AQI against public search interest and sentiment signals with a lagged-correlation scan, producing a composite **Human Cost Index** and detecting how many days behavior trails an AQI spike. |
| 2 | **Geospatial Source Attribution** | Grids a city into 2km×2km cells and fits an OLS regression (traffic density, industrial area, fire/stubble-burning count, wind as a dispersion control) to attribute each cell's pollution to a dominant source, with R² and per-source percentages reported as confidence. |
| 3 | **Citizen Health Risk Advisory** | Classifies risk against official CPCB PM2.5 breakpoints, drafts a personalized multilingual advisory via the Gemini API, and enforces an officer-approval workflow (draft → pending review → approved/rejected → sent) before anything reaches a citizen. |
| 4 | **Pollution Debt Leaderboard** | Combines population, days above the WHO PM2.5 safe threshold, and a per-capita cost estimate into a ranked "who's paying the most" leaderboard, plus a 2-city diff-factor comparison. |
| 5 | **AQI Forecast** | T+1/T+2 AQI forecast via a persistence-plus-weather delta regression, chosen over ARIMA/LSTM specifically because a live-gathered week of data can't support a heavier model without overfitting. |
| — | **City Search** | Resolves any free-text city name to a working grid/config via Open-Meteo geocoding — not limited to the two cities registered by default. |

Every pipeline is **keyless-real-data-first**: OpenAQ, AQICN, Open-Meteo,
OSM Overpass, NASA FIRMS, and WorldPop all work with no signup, with paid/
higher-frequency sources wired in as optional upgrades and a `cache/`-backed
fallback chain so a flaky connection degrades gracefully instead of crashing
mid-demo.

## Backend API

Full interactive reference lives at **`/docs`** once the server is running
(auto-generated from the real route definitions, so it can't drift out of
sync) — treat it as the source of truth over any table here.

| Method | Path | What it does |
|---|---|---|
| GET | `/dashboard` | Primary-city dashboard: HCI series + lag, attribution, forecast, top-5 leaderboard. |
| GET | `/comparison/{city_key}` | Primary city vs. `city_key` diff-factor comparison (on-demand, e.g. a "Compare" button). |
| GET | `/zones/{city_key}/{cell_id}` | Zone drill-down for a map click: cause %, trend, measures. |
| GET | `/leaderboard/{city_key}` | Full pollution-debt leaderboard for one city. |
| POST | `/advisories/{city_key}/{cell_id}` | Draft a personalized health advisory. Returns a `request_id`. |
| POST | `/advisories/{request_id}/review` | Officer approve/reject a pending advisory. |
| GET | `/cities/search?query=...` | Free-text city search — ranked candidates, not a single guess. |

## Run the backend

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in GEMINI_API_KEY at minimum
uvicorn api:app --reload    # http://127.0.0.1:8000/docs
pytest tests/                # 51/51 passing, fully offline/synthetic
```

`python run_demo.py` also runs the same 5-module pipeline standalone as a
batch script (console output only, no server) if that's all you need.

## Run the frontend

```bash
python3 -m http.server 8080   # from the repo root, then open http://localhost:8080
```

No build step, no npm install. Opening `index.html` directly via `file://`
mostly works too, except the live OSM road-density pull needs `http(s)://`
(some browsers block `fetch()` from `file://` origins).

| Page | Covers |
|---|---|
| `index.html` | Dashboard — situation report, AQI gauge, 7-day trend |
| `causal-loop.html` | Module 1 — Causal Loop Detector (AQI vs. search/sentiment, HCI) |
| `map.html` | Module 2 — Geospatial Source Attribution (grid, choropleth, drill-down) |
| `advisory.html` | Module 3 — Citizen Health Risk Advisory (chat, officer sign-off, alerts) |
| `leaderboard.html` | Module 4 — Pollution Debt Leaderboard + two-city comparison |

Stack: HTML/CSS/JS (no framework, no build step), **Leaflet** for
the map, **Chart.js** for charts, Google Fonts (Newsreader/Inter/IBM Plex
Mono) for an "environmental monitoring instrument" visual style — AQI
severity colors follow the standard CPCB category scale, kept deliberately
separate from the brand palette since that scale is a fixed reference
standard, not a design choice. City selection and the offline/live toggle
live in the URL query string (`?city=Delhi&offline=1`), not
localStorage, so every page stays a plain, shareable, bookmarkable link.

## Formulas

(Written as plain-text code spans rather than `$...$` LaTeX — verified
against GitHub's actual rendered view that the LaTeX delimiters were
displaying as raw literal backslashes/underscores instead of typeset math;
this notation renders correctly everywhere instead.)

**Human Cost Index** (Module 1): `HCI_t = 0.5 * AQI_norm_t + 0.25 * sentiment_norm_t + 0.25 * search_norm_t`

**Attribution** (Module 2): `AQI_i = b0 + b1*traffic_i + b2*industry_i + b3*fire_i + b4*wind_i + error_i` — wind is fit as a dispersion control, excluded from the attribution-% calc, since it modifies how pollution spreads rather than emitting any itself.

**Pollution debt** (Module 4): `Cost_z = P_z * D_z * C_pc`, shipped with an explicit methodology disclaimer on `C_pc` (a demo-grade per-capita estimate, not a peer-reviewed figure).

**AQI forecast** (Module 5): `delta_AQI_(t+1) = a + b1*wind_forecast + b2*humidity_forecast`, rolled forward cumulatively from the last known reading.

## Engineering decisions worth knowing about

- **Wind as a control, not a source** — prevents the attribution model from confusing "still air" with "a strong local emitter."
- **Persistence-plus-weather over ARIMA/LSTM** for the forecast — matched to the data volume a live, week-long build can actually gather without overfitting.
- **Fetch-with-cache fallback** (`utils/caching.py`) — a shared decorator reused across every data pipeline that automatically serves the most recent successful result whenever a live source is temporarily unavailable or rate-limited, improving reliability during development and demonstrations.
- **City search returns ranked candidates, never a single guess** — same-name cities across states/countries are genuinely ambiguous, so the caller picks.
- **Officer-approval as a real state machine** (`module3_health_advisory.py`) — a drafted advisory can't reach SENT without passing through PENDING_REVIEW → APPROVED first, and an already-decided advisory can't be silently re-decided.
- **Zone-drilldown and dashboard payloads as single function calls** — the frontend never has to join Module 1/2/4/5 output itself; one call returns the whole payload.

## Testing

`pytest tests/` — 51/51 passing, entirely offline against synthetic
fixtures (no live network calls in any test): grid/bounding-box math, the
HCI and lag-correlation formulas, the attribution regression, the officer-
approval state machine, city-search geocoding logic, and every `api.py`
endpoint's happy path plus its 400/404/502 error paths.

## Known limitations / next steps

- WorldPop population lookup and a small number of live data sources may occasionally experience slower responses or temporary rate limits depending on network conditions. The caching layer provides graceful degradation, although a quick live smoke test is recommended before production demonstrations.
- `GEMINI_API_KEY` is the one dependency with no keyless substitute — free tier, no card required, but real rate limits apply (see `.env.example`).
- Google Trends search-interest scoping is currently **country-level (`geo="IN"`) for every city**, not state- or city-level, for Delhi and Jaipur alike — the per-city `trends_geo` field exists on `CityConfig` (state-level where confidently mappable, e.g. Rajasthan for Jaipur) but isn't wired into the live Trends query yet (see the known-limitation note in `data_pipelines/trends_ingestion.py`).
