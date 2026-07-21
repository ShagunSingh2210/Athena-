# Athena — Air Quality Attribution & Advisory Platform

A static, dependency-light frontend (plain HTML/CSS/JS + Chart.js + Leaflet)
covering all four modules from the project plan. No build step — open
`index.html` in a browser, or serve the folder with any static file server.

```
python3 -m http.server 8080   # then visit http://localhost:8080
```

(Opening `index.html` directly via `file://` mostly works too, except the
live OSM road-density pull on the Map page needs `http(s)://`, since some
browsers block `fetch()` from `file://` origins.)

## Pages / modules

| Page                | Module                                                              |
|---------------------|----------------------------------------------------------------------|
| `index.html`        | Dashboard — situation report, AQI gauge, 7-day trend, module links   |
| `causal-loop.html`  | **Module 1** — Causal Loop Detector (AQI vs. search/sentiment, HCI)  |
| `map.html`          | **Module 2** — Geospatial Source Attribution (grid, choropleth, drill-down) |
| `advisory.html`     | **Module 3** — Citizen Health Risk Advisory (chat, officer sign-off, alerts) |
| `leaderboard.html`  | **Module 4** — Pollution Debt Leaderboard + two-city comparison      |

City switch (Delhi/Mumbai) and the offline/live toggle live in the shared
header (`nav.js`) and persist across pages via URL query params — no
localStorage, so every page stays a plain shareable link
(`map.html?city=Delhi&offline=1`).

## File map

```
index.html, causal-loop.html, map.html, advisory.html, leaderboard.html
assets/css/style.css        — one shared design system for all pages
assets/js/
  state.js                  — shared city/offline state via URL params
  grid.js                   — 2km×2km city grid definition (JS port of Person A's Day-1 grid math)
  mock-data.js               — deterministic seeded mock data, shaped exactly like the real API responses
  api.js                     — ★ INTEGRATION BOUNDARY — see below
  osm-roads.js               — live Overpass API road-density pull (falls back to mock)
  attribution.js             — OLS regression fallback for source attribution (Person A supersedes via api.js)
  nav.js                     — shared header behaviour (city select, offline toggle, active link)
  home.js, map-page.js, advisory-page.js, leaderboard-page.js, causal-loop-page.js
                              — one script per page, each calling only Api.* for data
```

## Where Person A's code plugs in

Everything funnels through **`assets/js/api.js`**. No other file needs to
change. Every `Api.getX()` function tries a real HTTP call first and falls
back to the matching `mock*()` function (in `mock-data.js`, `grid.js`,
`attribution.js`, `osm-roads.js`) on any failure — network error, timeout,
bad status, bad JSON. That's what makes the "Day 7: pre-cache all live
calls as an offline fallback" requirement automatic: nothing can hard-fail
on demo day even if wifi or an API key misbehaves. The "Offline / fallback
data" toggle in the header forces the fallback path on purpose, so you can
demo it live.

**To plug in:**
1. Stand up a backend (Flask/FastAPI both work) that returns JSON matching
   the shapes below. Each shape is exactly what the matching `mock*()`
   function already returns — read `mock-data.js` / `attribution.js` /
   `osm-roads.js` as your spec if a table row is ever ambiguous.
2. Enable CORS for whatever origin serves this static site
   (`flask-cors` + `CORS(app)` is the one-liner for a hackathon).
3. Open `assets/js/api.js` and set `API_BASE` to your server URL.
4. Toggle "Offline / fallback data" to "Live" in the header (or add
   `?offline=0` to the URL). Every page picks up live data immediately.

| Frontend call | Suggested endpoint | Returns |
|---|---|---|
| `getCityGrid(city)` | `GET /api/grid?city=Delhi` | `[{cellId,row,col,latMin,latMax,lonMin,lonMax,centroid:[lat,lon]}]` |
| `getCityZones(cellIds)` | `POST /api/zones {cellIds}` | `[{cellId,currentAqi,hci,dominantCause,causeBreakdown,trend7day,googleTrend7day,measuresTaken}]` |
| `getCausalLoop(cellId)` | `GET /api/causal-loop/:cellId` | `{cellId,aqiSeries,hciSeries,whoSafeLimit,lagDays,correlationStrength}` |
| `getRedditSentiment(cellId)` | `GET /api/sentiment/:cellId` | `{cellId,label,changePct,keywords:[...]}` |
| `getGoogleTrends(cellId)` | `GET /api/trends/:cellId` | `[{term,changePct}]` |
| `getIndustrialProximity(cellIds)` | `POST /api/industry {cellIds}` | `{[cellId]: 0..1}` |
| `getFireCounts(cellIds)` | `POST /api/fires {cellIds}` | `{[cellId]: int}` |
| `getRoadDensity(cells)` | `POST /api/road-density {cells}` | `{[cellId]: {rawScore,normalized,class}}` |
| `getAttributionModel(t,i,f,aqi)` | `POST /api/attribution-model {traffic,industry,fires,aqi}` | `{method,coefficients,intercept,r2}` |
| `getLeaderboard(cellIds, topN)` | `POST /api/leaderboard {cellIds,topN}` | `[{cellId,population,daysAboveThreshold,estimatedCostInr,avgAqiThisWeek}]` |
| `getCityComparison(cityA, cityB)` | `GET /api/compare?a=Delhi&b=Mumbai` | `{cityA:{name,factors,avgAqi}, cityB:{...}}` |
| `getWeather(city)` | `GET /api/weather?city=Delhi` | `{temp,wind,humidity}` |
| `getOfficerQueue()` | `GET /api/officer-queue` | `[{id,zone,profile,draftMessage,status}]` |
| `getAdvisory(zone,profile,lang)` | `POST /api/advisory {zone,profile,language}` | `{text}` — **the real Claude API call lives on your server, not the browser** |
| `approveAdvisory(id)` | `POST /api/officer-queue/:id/approve` | `{id,status}` |
| `rejectAdvisory(id)` | `POST /api/officer-queue/:id/reject` | `{id,status}` |

Notes:
- **`getAdvisory` should be server-side**, both because that's where the
  Claude API key lives, and because the officer sign-off gate (draft →
  approve → send) needs to be enforced server-side too — a citizen should
  never be able to receive a message that skipped review just because the
  browser called the wrong function.
- `getRoadDensity` already has its own real, working live path — it hits
  the public Overpass API directly from the browser (see `osm-roads.js`)
  and only needs `api.js` if you'd rather proxy/cache Overpass on your own
  server instead.
- `attribution.js`'s `fitAttributionModel()` is a working OLS regression
  (solved via the normal equation) already wired as the fallback — if your
  Python model is more sophisticated, point `/api/attribution-model` at it
  and this becomes dead code you can leave in place or delete.
- You don't have to implement every endpoint before demo day. Any endpoint
  you haven't built yet just falls back to mock data silently — ship
  incrementally.

## Design notes

- AQI severity colors (`--aqi-good` … `--aqi-severe`) follow the standard
  CPCB National AQI breakpoints and are kept separate from the brand
  palette (`--atmosphere`, `--marigold`) — don't restyle the severity scale
  for branding purposes, since it needs to stay legible/official.
- State lives in the URL, not localStorage/sessionStorage, so every page
  stays a plain link you can share or bookmark mid-demo.

## Contributors
* **Nitya** - Lead Developer & Architect
