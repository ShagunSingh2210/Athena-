/**
 * home.js
 * Day 1 (scaffolding) / Day 7 (polish) deliverable: dashboard home page —
 * situation-report hero with an SVG AQI gauge, instrument-style readout
 * tiles, and a 7-day trend chart.
 */
function polar(cx, cy, r, thetaDeg) {
  const t = (thetaDeg * Math.PI) / 180;
  return [cx + r * Math.cos(t), cy - r * Math.sin(t)];
}
function valueToTheta(v, max = 500) {
  const clamped = Math.max(0, Math.min(v, max));
  return 180 - (clamped / max) * 180;
}
function arcPath(cx, cy, r, vFrom, vTo, max = 500) {
  const thetaStart = valueToTheta(vFrom, max);
  const thetaEnd = valueToTheta(vTo, max);
  const [x1, y1] = polar(cx, cy, r, thetaStart);
  const [x2, y2] = polar(cx, cy, r, thetaEnd);
  const delta = thetaStart - thetaEnd;
  const largeArc = delta >= 179.9 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
}

const GAUGE_BANDS = [
  { from: 0, to: 50, color: 'var(--aqi-good)' },
  { from: 50, to: 100, color: 'var(--aqi-satisfactory)' },
  { from: 100, to: 200, color: 'var(--aqi-moderate)' },
  { from: 200, to: 300, color: 'var(--aqi-poor)' },
  { from: 300, to: 400, color: 'var(--aqi-very-poor)' },
  { from: 400, to: 500, color: 'var(--aqi-severe)' },
];

function renderGauge(container, value) {
  const cx = 150, cy = 150, r = 118, strokeW = 22;
  const bandPaths = GAUGE_BANDS.map(
    (b) => `<path d="${arcPath(cx, cy, r, b.from, b.to)}" stroke="${b.color}" stroke-width="${strokeW}" fill="none" stroke-linecap="butt" />`
  ).join('');

  const needleTheta = valueToTheta(value);
  const [nx, ny] = polar(cx, cy, r - strokeW / 2 - 6, needleTheta);
  const [tx1, ty1] = polar(cx, cy, 12, needleTheta + 90);
  const [tx2, ty2] = polar(cx, cy, 12, needleTheta - 90);

  container.innerHTML = `
    <svg viewBox="0 0 300 175" width="100%" role="img" aria-label="AQI gauge showing ${value}">
      ${bandPaths}
      <polygon points="${tx1},${ty1} ${tx2},${ty2} ${nx},${ny}" fill="var(--ink)" />
      <circle cx="${cx}" cy="${cy}" r="9" fill="var(--ink)" />
    </svg>
  `;
}

document.addEventListener('DOMContentLoaded', () => {
  const city = AppState.state.city;
  const cells = buildCityGrid(city);
  const center = CITY_CENTERS[city];

  // "current location" reading = cell nearest the city center
  let nearest = cells[0];
  let bestDist = Infinity;
  cells.forEach((c) => {
    const d = Math.hypot(c.centroid[0] - center[0], c.centroid[1] - center[1]);
    if (d < bestDist) { bestDist = d; nearest = c; }
  });
  const zone = mockZoneSummary(nearest.cellId);
  const cat = aqiCategory(zone.currentAqi);

  document.getElementById('cityName').textContent = city;
  document.getElementById('zoneLabel').textContent = nearest.cellId;
  document.getElementById('todayDate').textContent = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });

  renderGauge(document.getElementById('aqiGauge'), zone.currentAqi);
  document.getElementById('aqiValue').textContent = zone.currentAqi;
  const chip = document.getElementById('aqiCategoryChip');
  chip.textContent = cat.label;
  chip.dataset.cat = cat.label;

  // Deterministic mock "environmental readout" values (temp/wind/humidity),
  // seeded by city so they don't jitter on refresh — swap for a real
  // weather feed alongside Person A's AQI pipeline when ready.
  const wRng = seededRandom(city + '-weather');
  const pm25 = Math.round(zone.currentAqi * 0.6 * 10) / 10;
  document.getElementById('tilePm25').textContent = pm25;
  document.getElementById('tileTemp').textContent = randInt(wRng, 18, 34);
  document.getElementById('tileWind').textContent = (randFloat(wRng, 1.2, 6.5)).toFixed(1);
  document.getElementById('tileHumidity').textContent = randInt(wRng, 30, 90);

  // 7-day trend chart
  const ctx = document.getElementById('trendChart');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: ['Day -6', 'Day -5', 'Day -4', 'Day -3', 'Day -2', 'Yesterday', 'Today'],
      datasets: [{
        label: 'AQI',
        data: zone.trend7day,
        borderColor: '#16233B',
        backgroundColor: 'rgba(224,138,30,0.12)',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: '#16233B',
        tension: 0.35,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: '#E2E8F0' }, ticks: { font: { family: 'IBM Plex Mono', size: 10 } } },
        x: { grid: { display: false }, ticks: { font: { family: 'IBM Plex Mono', size: 10 } } },
      },
    },
  });

  // Module links
  document.querySelectorAll('[data-module-link]').forEach((a) => {
    a.href = AppState.linkTo(a.dataset.moduleLink);
  });
});
