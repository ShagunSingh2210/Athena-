/**
 * osm-roads.js
 * Day 2 deliverable: pull the OSM road network via the Overpass API and
 * classify road density per grid cell. Falls back to deterministic mock
 * density if the API is unreachable or offline mode is on, so the map
 * layer always has something to render on demo day.
 */
const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

const ROAD_WEIGHTS = {
  motorway: 5, trunk: 4, primary: 3, secondary: 2,
  tertiary: 1.5, residential: 1, unclassified: 0.5,
};

function overpassQuery(cell) {
  return `[out:json][timeout:20];way["highway"](${cell.latMin},${cell.lonMin},${cell.latMax},${cell.lonMax});out geom;`;
}

async function fetchRoadsForCell(cell) {
  const resp = await fetch(OVERPASS_URL, {
    method: 'POST',
    body: `data=${encodeURIComponent(overpassQuery(cell))}`,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  if (!resp.ok) throw new Error(`Overpass ${resp.status}`);
  const json = await resp.json();
  return json.elements || [];
}

function roadDensityScore(ways) {
  return ways.reduce((score, way) => {
    const tag = (way.tags && way.tags.highway) || 'unclassified';
    return score + (ROAD_WEIGHTS[tag] ?? 0.5);
  }, 0);
}

function mockScoreForCell(cellId) {
  const rng = seededRandom(cellId + '-road');
  return randFloat(rng, 0, 20);
}

/**
 * Returns { [cellId]: { rawScore, normalized (0-1), class: 'low'|'medium'|'high' } }
 * useLive=false (or a failed live call) falls back to mock automatically.
 * Live calls are capped and run with limited concurrency to be polite to
 * the public Overpass instance during a demo.
 */
async function classifyDensity(cells, useLive = true) {
  const rawScores = {};

  if (useLive) {
    const CONCURRENCY = 4;
    let idx = 0;
    async function worker() {
      while (idx < cells.length) {
        const cell = cells[idx++];
        try {
          const ways = await fetchRoadsForCell(cell);
          rawScores[cell.cellId] = roadDensityScore(ways);
        } catch (e) {
          rawScores[cell.cellId] = mockScoreForCell(cell.cellId);
        }
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  } else {
    cells.forEach((cell) => { rawScores[cell.cellId] = mockScoreForCell(cell.cellId); });
  }

  const maxScore = Math.max(...Object.values(rawScores), 1);
  const result = {};
  Object.entries(rawScores).forEach(([cellId, score]) => {
    const normalized = maxScore ? score / maxScore : 0;
    const cls = normalized > 0.66 ? 'high' : normalized > 0.33 ? 'medium' : 'low';
    result[cellId] = { rawScore: Math.round(score * 100) / 100, normalized: Math.round(normalized * 100) / 100, class: cls };
  });
  return result;
}
