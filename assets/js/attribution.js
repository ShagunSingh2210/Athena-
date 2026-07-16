/**
 * attribution.js
 * Day 3 deliverable: Bhuvan industrial-zone layer + NASA FIRMS fire
 * hotspots (mocked), and a simple attribution model for
 * AQI_cell ~ traffic_density + industrial_proximity + fire_count,
 * reporting R^2 and per-feature coefficients as the "confidence" figure.
 *
 * NOTE: per the plan's Module Ownership Matrix this modelling work sits
 * with Person A; it's implemented here too because the Day-3 execution
 * table assigns the same task to Person B. Safe to drop if Person A ships
 * an equivalent.
 */
function mockIndustrialProximity(cellIds) {
  const out = {};
  cellIds.forEach((cid) => { out[cid] = Math.round(randFloat(seededRandom(cid + '-industry'), 0, 1) * 1000) / 1000; });
  return out;
}

function mockFireCounts(cellIds) {
  const out = {};
  cellIds.forEach((cid) => { out[cid] = randInt(seededRandom(cid + '-fire'), 0, 12); });
  return out;
}

function mean(arr) { return arr.reduce((a, b) => a + b, 0) / arr.length; }
function variance(arr) {
  const m = mean(arr);
  return mean(arr.map((x) => (x - m) ** 2));
}

/**
 * Ordinary least squares for 3 predictors, solved via the normal equation
 * (no external dependency needed for a 3-feature hackathon-scale fit).
 */
function fitAttributionModel(traffic, industry, fires, aqi) {
  const n = aqi.length;
  if (n < 4) {
    const factors = { traffic, industry, fires };
    const variances = Object.fromEntries(Object.entries(factors).map(([k, v]) => [k, variance(v)]));
    const totalVar = Object.values(variances).reduce((a, b) => a + b, 0) || 1;
    const weights = Object.fromEntries(Object.entries(variances).map(([k, v]) => [k, Math.round((v / totalVar) * 1000) / 1000]));
    return { method: 'heuristic_variance_weighting', coefficients: weights, intercept: null, r2: null };
  }

  // Design matrix X (n x 4 with intercept column), solve beta = (X^T X)^-1 X^T y
  const X = aqi.map((_, i) => [1, traffic[i], industry[i], fires[i]]);
  const y = aqi;

  const XT = transpose(X);
  const XTX = matMul(XT, X);
  const XTy = matVecMul(XT, y);
  const XTXinv = invert4x4(XTX);
  const beta = matVecMul(XTXinv, XTy);

  const yPred = X.map((row) => row.reduce((s, v, j) => s + v * beta[j], 0));
  const yMean = mean(y);
  const ssRes = y.reduce((s, yi, i) => s + (yi - yPred[i]) ** 2, 0);
  const ssTot = y.reduce((s, yi) => s + (yi - yMean) ** 2, 0);
  const r2 = ssTot ? 1 - ssRes / ssTot : 0;

  return {
    method: 'linear_regression',
    coefficients: {
      traffic: Math.round(beta[1] * 1000) / 1000,
      industry: Math.round(beta[2] * 1000) / 1000,
      fires: Math.round(beta[3] * 1000) / 1000,
    },
    intercept: Math.round(beta[0] * 1000) / 1000,
    r2: Math.round(r2 * 1000) / 1000,
  };
}

function attributeDominantSource(traffic, industry, fires) {
  const scores = { Traffic: traffic, Industry: industry, 'Stubble Burning': fires / 12 };
  return Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0];
}

// --- tiny linear-algebra helpers (4x4 max, sized for this 3-feature model) ---
function transpose(m) { return m[0].map((_, c) => m.map((row) => row[c])); }
function matMul(a, b) {
  return a.map((row) => b[0].map((_, j) => row.reduce((s, v, k) => s + v * b[k][j], 0)));
}
function matVecMul(m, v) { return m.map((row) => row.reduce((s, x, i) => s + x * v[i], 0)); }
function invert4x4(m) {
  // Gauss-Jordan elimination
  const n = 4;
  const A = m.map((row, i) => [...row, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
  for (let i = 0; i < n; i++) {
    let pivot = A[i][i];
    if (Math.abs(pivot) < 1e-10) {
      const swapRow = A.slice(i + 1).findIndex((r) => Math.abs(r[i]) > 1e-10);
      if (swapRow === -1) throw new Error('Singular matrix in attribution fit');
      [A[i], A[i + 1 + swapRow]] = [A[i + 1 + swapRow], A[i]];
      pivot = A[i][i];
    }
    for (let j = 0; j < 2 * n; j++) A[i][j] /= pivot;
    for (let k = 0; k < n; k++) {
      if (k === i) continue;
      const factor = A[k][i];
      for (let j = 0; j < 2 * n; j++) A[k][j] -= factor * A[i][j];
    }
  }
  return A.map((row) => row.slice(n));
}
