# Person B — Air Quality Attribution & Advisory Platform (v2, no Streamlit)

A static HTML/CSS/JS build of every Person B deliverable — no Python
server, no build step, no npm install required to run it. Open it in a
browser or serve the folder with any static file server.

Design direction: an "environmental monitoring instrument" aesthetic —
deep atmosphere-navy chrome, a marigold accent, and every number (AQI,
PM2.5, cost figures) rendered in a mono, tabular-numeral "readout" style —
built to look at home in a government dashboard rather than a consumer
weather app. AQI severity colors (green → maroon) follow the standard
CPCB National AQI category scale and are kept separate from the brand
palette, since that scale is a fixed reference standard, not a design
choice.

## Run it

No install needed — just serve the folder statically:

```bash
# from inside person_b_kit_v2/
python3 -m http.server 8000
# then open http://localhost:8000
```

Or just double-click `index.html` to open it directly in a browser (map
tiles and the Overpass API need `http://`/`https://`, not `file://`, to
load reliably — use the http.server one-liner above for anything beyond
the dashboard page).

Any static host works for a real deployment: GitHub Pages, Netlify,
Vercel, or a plain S3/nginx bucket — there's no server-side code.

## Stack

- Vanilla HTML/CSS/JS — no framework, no build step
- **Leaflet** (via CDN) for the map
- **Chart.js** (via CDN) for all charts
- **Google Fonts**: Newsreader (headings), Inter (body/UI), IBM Plex Mono (every numeric readout)

If you'd rather not depend on CDNs (e.g. for an offline/intranet
deployment), download `chart.js` and `leaflet` via npm and point the
`<script>`/`<link>` tags in each HTML file at local copies — everything
else in the code is unaffected either way.

## File map → day in the plan

| File | Day(s) | What it covers |
|---|---|---|
| `assets/js/grid.js` | Day 1 | City grid definition (2km × 2km cells), bounding box |
| `index.html` / `assets/js/home.js` | Day 1, Day 7 | Dashboard shell, AQI gauge, readout tiles, trend chart |
| `assets/js/osm-roads.js` | Day 2 | OSM road network pull (Overpass API) + density classification, with mock fallback |
| `map.html` / `assets/js/map-page.js` | Day 1, 2, 3, 4 | Map skeleton → grid+road wiring → attribution model readout → AQI bubbles + zone drill-down |
| `assets/js/attribution.js` | Day 3 | Bhuvan/FIRMS mock pulls + linear-regression attribution model (R² + coefficients) |
| `advisory.html` / `assets/js/advisory-page.js` | Day 5 | Citizen chat, language toggle, officer-approval queue, alert-received screen |
| `leaderboard.html` / `assets/js/leaderboard-page.js` | Day 6 | Pollution debt ledger + chart + 2-city comparison |
| `assets/js/mock-data.js` | All days | Shared fallback data so every page runs standalone |
| `assets/js/state.js` | All days | Cross-page state (city, offline mode) via URL query params — no localStorage/cookies |

> **Note on Day 3:** the plan's Module Ownership Matrix assigns Module 2's
> data+model work to Person A, but the Day-3 row of the execution table
> assigns the same OSM/Bhuvan/FIRMS pulls + regression model to Person B.
> `attribution.js` implements it so nothing is blocked either way — drop
> it if Person A ships an equivalent.

## Mock → real swap

Every function Person A will eventually own has a mock stand-in with a
`TODO(Person A)` comment at the call site:

- `mockAdvisory()` → replace with the real Claude API advisory call (`advisory-page.js`)
- `mockZoneSummary()` → replace with real Module 1+2 output (HCI, cause %, trend) (`map-page.js`, `home.js`)
- `mockLeaderboard()` / `mockCityComparison()` → replace with real `estimated_cost` + diff-factor output (`leaderboard-page.js`)
- `classifyDensity(cells, useLive=true)` already hits the real Overpass API; it only falls back to mock if a cell's request fails, or if the offline toggle is on

Because every mock function's return shape matches what the real
pipeline will produce, swapping is a small, localized change — no HTML
or CSS rework needed. If Person A exposes a JSON API instead of a
JS-callable function, wrap the call in `fetch()` and keep the same
return shape; the rendering code doesn't care where the data came from.

## State model (replacing Streamlit's session_state)

Since this is now plain multi-page HTML (no single running process),
shared state — which city is selected, whether offline/mock mode is
on — lives in the URL query string (`?city=Delhi&offline=1`) via
`assets/js/state.js`. This has a nice side effect: every page is a
plain, shareable, bookmarkable link. Deliberately avoids
localStorage/sessionStorage so it works identically from a file share,
an intranet host, or a CDN.

## Demo-day fallback

The offline toggle in the header forces every page onto the mock data
in `mock-data.js` — the same mock layer that lets Person B build without
waiting on Person A doubles as your demo-day fallback if venue wifi (or
the public Overpass API) drops mid-demo. Rehearse once with it ON.

## Verified

Every page was rendered headlessly (Chromium via Playwright) and
click-tested end-to-end during development: zero console/runtime errors,
map bubble click → drill-down panel, advisory form submit → chat history,
and officer approve → alert-received flow all confirmed working.
