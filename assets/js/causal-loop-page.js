/**
 * pages/causal-loop.html logic
 * Module 1 — Causal Loop Detector: AQI vs. Human Cost Index (lag
 * correlation), Reddit public sentiment, Google Trends search correlation.
 * Mirrors the Day 2–3 deliverables in the execution plan: lagged
 * cross-correlation, HCI formula + chart, Reddit sentiment score.
 */
let clCharts = { loop: null };

const SENTIMENT_COLOR = {
  Critical: 'var(--aqi-severe)',
  Negative: 'var(--aqi-very-poor)',
  Mixed: 'var(--aqi-moderate)',
  Neutral: 'var(--aqi-satisfactory)',
};

function renderSentimentCard(sentiment) {
  const el = document.getElementById('sentimentCard');
  const color = SENTIMENT_COLOR[sentiment.label] || 'var(--ink)';
  el.innerHTML = `
    <div class="eyebrow" style="margin-bottom:10px;">PUBLIC SENTIMENT · REDDIT</div>
    <div style="display:flex; align-items:baseline; gap:10px; margin-bottom:14px;">
      <span style="font-family:var(--font-display); font-size:1.6rem; font-weight:600; color:${color};">${sentiment.label}</span>
      <span class="badge mono-num" style="background:var(--mist); color:${sentiment.changePct < 0 ? 'var(--aqi-very-poor)' : 'var(--aqi-good)'};">${sentiment.changePct > 0 ? '+' : ''}${sentiment.changePct}%</span>
    </div>
    <div class="eyebrow" style="margin-bottom:8px;">TOP KEYWORDS</div>
    <div style="display:flex; flex-wrap:wrap; gap:8px;">
      ${sentiment.keywords.map((k) => `<span class="badge" style="background:var(--mist); color:var(--muted);">\u201C${k}\u201D</span>`).join('')}
    </div>
  `;
}

function renderTrendsCard(trends) {
  const el = document.getElementById('trendsCard');
  el.innerHTML = `
    <div class="eyebrow" style="margin-bottom:10px;">SEARCH CORRELATION · GOOGLE TRENDS</div>
    <ul style="list-style:none; margin:0; padding:0;">
      ${trends
        .map(
          (t) => `
        <li style="display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid var(--slate-line-soft);">
          <span style="font-size:0.9rem;">\u201C${t.term}\u201D</span>
          <span class="mono-num" style="color:var(--marigold); font-weight:600;">+${t.changePct}%</span>
        </li>`
        )
        .join('')}
    </ul>
  `;
}

async function loadZone(cellId) {
  const [loop, sentiment, trends] = await Promise.all([
    Api.getCausalLoop(cellId),
    Api.getRedditSentiment(cellId),
    Api.getGoogleTrends(cellId),
  ]);

  document.getElementById('lagReadout').textContent = `${loop.lagDays} day${loop.lagDays === 1 ? '' : 's'}`;
  document.getElementById('corrReadout').textContent = loop.correlationStrength;
  document.getElementById('whoReadout').textContent = loop.whoSafeLimit;

  if (clCharts.loop) clCharts.loop.destroy();
  clCharts.loop = new Chart(document.getElementById('loopChart'), {
    type: 'line',
    data: {
      labels: ['Day -6', 'Day -5', 'Day -4', 'Day -3', 'Day -2', 'Yesterday', 'Today'],
      datasets: [
        {
          label: 'AQI',
          data: loop.aqiSeries,
          borderColor: '#16233B',
          backgroundColor: 'rgba(224,138,30,0.10)',
          yAxisID: 'y',
          tension: 0.35,
          pointRadius: 3,
          fill: true,
        },
        {
          label: 'Human Cost Index',
          data: loop.hciSeries,
          borderColor: '#E08A1E',
          backgroundColor: 'transparent',
          borderDash: [5, 3],
          yAxisID: 'y1',
          tension: 0.35,
          pointRadius: 2,
        },
        {
          label: 'WHO safe limit',
          data: Array(7).fill(loop.whoSafeLimit),
          borderColor: '#4CAF50',
          backgroundColor: 'transparent',
          borderDash: [2, 3],
          borderWidth: 1.5,
          pointRadius: 0,
          yAxisID: 'y',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom', labels: { font: { size: 11, family: 'Inter' }, boxWidth: 12 } } },
      scales: {
        y: { position: 'left', beginAtZero: true, title: { display: true, text: 'AQI' }, grid: { color: '#E2E8F0' } },
        y1: { position: 'right', beginAtZero: true, max: 1, title: { display: true, text: 'HCI (0\u20131)' }, grid: { display: false } },
        x: { grid: { display: false } },
      },
    },
  });

  renderSentimentCard(sentiment);
  renderTrendsCard(trends);
}

document.addEventListener('DOMContentLoaded', async () => {
  const city = AppState.state.city;
  const cells = await Api.getCityGrid(city);
  const center = CITY_CENTERS[city];

  const zoneSelect = document.getElementById('clZoneSelect');
  cells.forEach((c) => {
    const opt = document.createElement('option');
    opt.value = c.cellId;
    opt.textContent = c.cellId;
    zoneSelect.appendChild(opt);
  });

  let nearest = cells[0];
  let bestDist = Infinity;
  cells.forEach((c) => {
    const d = Math.hypot(c.centroid[0] - center[0], c.centroid[1] - center[1]);
    if (d < bestDist) { bestDist = d; nearest = c; }
  });
  zoneSelect.value = nearest.cellId;

  zoneSelect.addEventListener('change', () => loadZone(zoneSelect.value));
  await loadZone(nearest.cellId);
});
