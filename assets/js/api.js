/**
 * api.js
 * ============================================================================
 * THIS FILE IS THE INTEGRATION BOUNDARY. Person A's backend plugs in here
 * and nowhere else — no other file needs to change.
 *
 * Every Api.getX() function below tries a real HTTP call to API_BASE first,
 * and transparently falls back to the matching mock*() function (from
 * mock-data.js / grid.js / attribution.js / osm-roads.js) on any failure:
 * network error, timeout, non-2xx status, or bad JSON. That fallback is
 * what makes "Day 7: pre-cache all live calls as an offline fallback"
 * automatic — nothing on demo day can hard-fail even if wifi or an API key
 * misbehaves. The "Offline / fallback data" toggle in the header (see
 * state.js / nav.js) short-circuits straight to mock data on purpose, so
 * you can force the fallback path live during a demo.
 *
 * ── PERSON A: HOW TO PLUG IN ────────────────────────────────────────────
 * 1. Stand up a backend (Flask/FastAPI both work fine) that returns JSON
 *    matching the shapes in the table below — each shape is exactly what
 *    the matching mock*() function already returns, so you can literally
 *    read mock-data.js / attribution.js / osm-roads.js as your spec.
 * 2. Enable CORS on your server for whatever origin this static site is
 *    served from (e.g. `flask-cors` with `CORS(app)` for a hackathon).
 * 3. Set API_BASE below to your server URL.
 * 4. Toggle "Offline / fallback data" to "Live" in the header (or add
 *    ?offline=0 to the URL). Every page picks up live data immediately —
 *    no page script needs to change.
 *
 *   Frontend call                     Suggested endpoint                          Returns
 *   --------------------------------  -------------------------------------------  --------------------------------------------------------------
 *   getCityGrid(city)                 GET  /api/grid?city=Delhi                    [{cellId,row,col,latMin,latMax,lonMin,lonMax,centroid:[lat,lon]}]
 *   getCityZones(cellIds)             POST /api/zones            {cellIds}         [{cellId,currentAqi,hci,dominantCause,causeBreakdown,trend7day,googleTrend7day,measuresTaken}]
 *   getCausalLoop(cellId)             GET  /api/causal-loop/:cellId                {cellId,aqiSeries,hciSeries,whoSafeLimit,lagDays,correlationStrength}
 *   getRedditSentiment(cellId)        GET  /api/sentiment/:cellId                  {cellId,label,changePct,keywords:[...]}
 *   getGoogleTrends(cellId)           GET  /api/trends/:cellId                     [{term,changePct}]
 *   getIndustrialProximity(cellIds)   POST /api/industry          {cellIds}         {[cellId]: 0..1}
 *   getFireCounts(cellIds)            POST /api/fires             {cellIds}         {[cellId]: int}
 *   getRoadDensity(cells)             POST /api/road-density      {cells}           {[cellId]: {rawScore,normalized,class}}
 *   getAttributionModel(t,i,f,aqi)    POST /api/attribution-model {traffic,industry,fires,aqi}  {method,coefficients,intercept,r2}
 *   getLeaderboard(cellIds, topN)     POST /api/leaderboard        {cellIds,topN}   [{cellId,population,daysAboveThreshold,estimatedCostInr,avgAqiThisWeek}]
 *   getCityComparison(cityA, cityB)   GET  /api/compare?a=Delhi&b=Mumbai            {cityA:{name,factors,avgAqi}, cityB:{name,factors,avgAqi}}
 *   getWeather(city)                  GET  /api/weather?city=Delhi                 {temp,wind,humidity}
 *   getOfficerQueue()                 GET  /api/officer-queue                      [{id,zone,profile,draftMessage,status}]
 *   getAdvisory(zone,profile,lang)    POST /api/advisory          {zone,profile,language}  {text}   <- real Claude API call lives on your server
 *   approveAdvisory(id)               POST /api/officer-queue/:id/approve          {id,status}
 *   rejectAdvisory(id)                POST /api/officer-queue/:id/reject           {id,status}
 *
 * `getAdvisory` is the one call you should make server-side, not from the
 * browser: it's where the Claude API key lives, and where the officer
 * sign-off gate (draft -> approve -> send) should be enforced server-side
 * too, so a citizen can never receive a message that skipped review.
 * ============================================================================
 */
const API_BASE = 'http://localhost:8000'; // TODO(Person A): e.g. 'http://localhost:8000'. Leave '' to stay mock-only.

async function apiFetch(path, options = {}, timeoutMs = 4000) {
  if (!API_BASE || AppState.state.offline) throw new Error('offline-mode');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

const Api = {
  async getCityGrid(city) {
    try { return await apiFetch(`/api/grid?city=${encodeURIComponent(city)}`); }
    catch { return buildCityGrid(city); }
  },

  async getCityZones(cellIds) {
    try { return await apiFetch('/api/zones', { method: 'POST', body: JSON.stringify({ cellIds }) }); }
    catch { return mockCityZones(cellIds); }
  },

  async getCausalLoop(cellId) {
    try { return await apiFetch(`/api/causal-loop/${encodeURIComponent(cellId)}`); }
    catch { return mockCausalLoop(cellId); }
  },

  async getRedditSentiment(cellId) {
    try { return await apiFetch(`/api/sentiment/${encodeURIComponent(cellId)}`); }
    catch { return mockRedditSentiment(cellId); }
  },

  async getGoogleTrends(cellId) {
    try { return await apiFetch(`/api/trends/${encodeURIComponent(cellId)}`); }
    catch { return mockGoogleTrends(cellId); }
  },

  async getIndustrialProximity(cellIds) {
    try { return await apiFetch('/api/industry', { method: 'POST', body: JSON.stringify({ cellIds }) }); }
    catch { return mockIndustrialProximity(cellIds); }
  },

  async getFireCounts(cellIds) {
    try { return await apiFetch('/api/fires', { method: 'POST', body: JSON.stringify({ cellIds }) }); }
    catch { return mockFireCounts(cellIds); }
  },

  // Road density has its own live path direct to the public Overpass API
  // (see osm-roads.js) — this only routes through Person A's backend if
  // API_BASE is set, e.g. if you'd rather proxy/cache Overpass server-side.
  async getRoadDensity(cells) {
    try { return await apiFetch('/api/road-density', { method: 'POST', body: JSON.stringify({ cells }) }); }
    catch { return classifyDensity(cells, !AppState.state.offline); }
  },

  async getAttributionModel(traffic, industry, fires, aqi) {
    try {
      return await apiFetch('/api/attribution-model', {
        method: 'POST',
        body: JSON.stringify({ traffic, industry, fires, aqi }),
      });
    } catch {
      try { return fitAttributionModel(traffic, industry, fires, aqi); }
      catch { return { method: 'unavailable', coefficients: { traffic: 0, industry: 0, fires: 0 }, intercept: null, r2: null }; }
    }
  },

  async getLeaderboard(cellIds, topN = 5) {
    try { return await apiFetch('/api/leaderboard', { method: 'POST', body: JSON.stringify({ cellIds, topN }) }); }
    catch { return mockLeaderboard(cellIds, topN); }
  },

  async getCityComparison(cityA, cityB) {
    try { return await apiFetch(`/api/compare?a=${encodeURIComponent(cityA)}&b=${encodeURIComponent(cityB)}`); }
    catch { return mockCityComparison(cityA, cityB); }
  },

  async getWeather(city) {
    try { return await apiFetch(`/api/weather?city=${encodeURIComponent(city)}`); }
    catch {
      const wRng = seededRandom(city + '-weather');
      return {
        temp: randInt(wRng, 18, 34),
        wind: Math.round(randFloat(wRng, 1.2, 6.5) * 10) / 10,
        humidity: randInt(wRng, 30, 90),
      };
    }
  },

  async getOfficerQueue() {
    try { return await apiFetch('/api/officer-queue'); }
    catch { return mockOfficerQueue(); }
  },

  async getAdvisory(zone, profile, language) {
    try {
      const r = await apiFetch('/api/advisory', { method: 'POST', body: JSON.stringify({ zone, profile, language }) });
      return r.text;
    } catch { return mockAdvisory(zone, profile, language); }
  },

  async approveAdvisory(id) {
    try { return await apiFetch(`/api/officer-queue/${id}/approve`, { method: 'POST' }); }
    catch { return { id, status: 'approved' }; }
  },

  async rejectAdvisory(id) {
    try { return await apiFetch(`/api/officer-queue/${id}/reject`, { method: 'POST' }); }
    catch { return { id, status: 'rejected' }; }
  },
};
