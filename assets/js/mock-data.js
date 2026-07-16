/**
 * mock-data.js
 * Fallback / sample data so the frontend is never blocked waiting on
 * Person A's live pipelines. Every function's return shape mirrors what
 * the real backend will eventually send — see README "Mock -> real swap".
 */
const CAUSES = ['Traffic', 'Industry', 'Stubble Burning', 'Construction Dust', 'Other'];
const LANGUAGES = { en: 'English', hi: 'Hindi', mr: 'Marathi' };
const HEALTH_PROFILES = ['none', 'asthma', 'elderly', 'outdoor_worker'];

// Deterministic seeded PRNG (mulberry32) keyed by a string seed, so mock
// data doesn't jitter on every re-render — mirrors Python's random.Random(seed).
function seededRandom(seedStr) {
  let h = 1779033703 ^ seedStr.length;
  for (let i = 0; i < seedStr.length; i++) {
    h = Math.imul(h ^ seedStr.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return function () {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}
function randInt(rng, min, max) { return Math.floor(rng() * (max - min + 1)) + min; }
function randFloat(rng, min, max) { return rng() * (max - min) + min; }
function sample(rng, arr, k) {
  const copy = [...arr];
  const out = [];
  for (let i = 0; i < k && copy.length; i++) {
    out.push(copy.splice(Math.floor(rng() * copy.length), 1)[0]);
  }
  return out;
}

// CPCB AQI category breakpoints (standard, used for chips/colors across the app)
function aqiCategory(aqi) {
  if (aqi <= 50) return { label: 'Good', color: 'var(--aqi-good)' };
  if (aqi <= 100) return { label: 'Satisfactory', color: 'var(--aqi-satisfactory)' };
  if (aqi <= 200) return { label: 'Moderate', color: 'var(--aqi-moderate)' };
  if (aqi <= 300) return { label: 'Poor', color: 'var(--aqi-poor)' };
  if (aqi <= 400) return { label: 'Very Poor', color: 'var(--aqi-very-poor)' };
  return { label: 'Severe', color: 'var(--aqi-severe)' };
}

function mockZoneSummary(cellId) {
  const rng = seededRandom(cellId);
  const weights = CAUSES.map(() => rng());
  const total = weights.reduce((a, b) => a + b, 0);
  const causeBreakdown = {};
  CAUSES.forEach((c, i) => { causeBreakdown[c] = Math.round((weights[i] / total) * 1000) / 10; });
  const dominant = Object.entries(causeBreakdown).sort((a, b) => b[1] - a[1])[0][0];

  return {
    cellId,
    currentAqi: randInt(rng, 80, 420),
    hci: Math.round(randFloat(rng, 0.2, 0.95) * 100) / 100,
    dominantCause: dominant,
    causeBreakdown,
    trend7day: Array.from({ length: 7 }, () => randInt(rng, 80, 420)),
    googleTrend7day: Array.from({ length: 7 }, () => randInt(rng, 10, 100)),
    measuresTaken: sample(rng, [
      'Odd-even vehicle scheme active',
      'Construction ban in effect',
      'Stubble-burning fines issued',
      'Water sprinkling on roads',
      'No active measures',
    ], 2),
  };
}

function mockCityZones(cellIds) {
  return cellIds.map(mockZoneSummary);
}

function mockLeaderboard(cellIds, topN = 5) {
  const rows = cellIds.map((cid) => {
    const rng = seededRandom(cid + '-cost');
    const population = randInt(rng, 15000, 120000);
    const daysAbove = randInt(rng, 5, 30);
    const perCapitaCost = 42; // INR/day placeholder — Person A supplies the cited figure
    return {
      cellId: cid,
      population,
      daysAboveThreshold: daysAbove,
      estimatedCostInr: population * daysAbove * perCapitaCost,
      avgAqiThisWeek: randInt(rng, 90, 400),
    };
  });
  rows.sort((a, b) => b.estimatedCostInr - a.estimatedCostInr);
  return rows.slice(0, topN);
}

function mockCityComparison(cityA, cityB) {
  function factors(seed) {
    const rng = seededRandom(seed);
    const w = CAUSES.map(() => rng());
    const t = w.reduce((a, b) => a + b, 0);
    const out = {};
    CAUSES.forEach((c, i) => { out[c] = Math.round((w[i] / t) * 1000) / 10; });
    return out;
  }
  return {
    cityA: { name: cityA, factors: factors(cityA), avgAqi: randInt(seededRandom(cityA + '-aqi'), 100, 350) },
    cityB: { name: cityB, factors: factors(cityB), avgAqi: randInt(seededRandom(cityB + '-aqi'), 100, 350) },
  };
}

// TODO(Person A): replace calls to this with the real Claude API advisory call.
function mockAdvisory(zone, profile, language = 'en') {
  const base = {
    asthma: `AQI in ${zone} is elevated. Avoid outdoor activity 8-11am; keep your inhaler handy.`,
    elderly: `AQI in ${zone} is elevated. Limit outdoor exposure and use an N95 mask if you must go out.`,
    outdoor_worker: `AQI in ${zone} is elevated. Take mask breaks every 90 minutes and stay hydrated.`,
    none: `AQI in ${zone} is moderate. Sensitive individuals should limit prolonged outdoor exertion.`,
  };
  let text = base[profile] || base.none;
  if (language !== 'en') {
    text = `[${LANGUAGES[language] || language} translation placeholder] ${text}`;
  }
  return text;
}

function mockOfficerQueue() {
  return Array.from({ length: 5 }, (_, i) => {
    const n = i + 1;
    const profile = HEALTH_PROFILES[n % HEALTH_PROFILES.length];
    return {
      id: n,
      zone: `Zone ${n}`,
      profile,
      draftMessage: mockAdvisory(`Zone ${n}`, profile),
      status: 'pending',
    };
  });
}
