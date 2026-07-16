/**
 * pages/map.html logic
 * Day 1: map skeleton.
 * Day 2: wire the city grid + OSM road density onto the map.
 * Day 3: attribution model output (dominant cause) feeds bubble color.
 * Day 4: AQI bubbles per cell (image-2-style) + click-to-drill-down panel
 *        (cause %, trend, measures taken).
 */
let charts = { cause: null, trend: null, search: null };

function severityColor(aqi) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(aqiCategory(aqi).color.replace('var(', '').replace(')', ''))
    .trim() || '#888';
}

function destroyCharts() {
  Object.values(charts).forEach((c) => c && c.destroy());
  charts = { cause: null, trend: null, search: null };
}

function renderDrilldown(cellId, zone, density) {
  const panel = document.getElementById('drilldownContent');
  const cat = aqiCategory(zone.currentAqi);
  panel.innerHTML = `
    <div class="eyebrow" style="margin-bottom:8px;">ZONE ${cellId}</div>
    <div style="display:flex; align-items:baseline; gap:10px; margin-bottom:14px;">
      <span class="mono-num" style="font-size:2.1rem; font-weight:500;">${zone.currentAqi}</span>
      <span class="badge aqi-chip" data-cat="${cat.label}">${cat.label}</span>
    </div>
    <div class="grid-2" style="margin-bottom:16px;">
      <div class="readout-tile"><div class="label">Human Cost Index</div><div class="value">${zone.hci}</div></div>
      <div class="readout-tile"><div class="label">Road Density</div><div class="value" style="text-transform:capitalize;">${density.class}</div></div>
    </div>
    <div class="section-title">Cause breakdown</div>
    <div style="height:180px;"><canvas id="causeChart"></canvas></div>
    <div class="section-title" style="margin-top:18px;">7-day AQI trend</div>
    <div style="height:120px;"><canvas id="trendMiniChart"></canvas></div>
    <div class="section-title" style="margin-top:18px;">Measures taken</div>
    <ul style="margin:0; padding-left:18px; font-size:0.86rem; color:var(--muted);">
      ${zone.measuresTaken.map((m) => `<li>${m}</li>`).join('')}
    </ul>
  `;

  destroyCharts();
  const causeColors = ['#E08A1E', '#16233B', '#8BC34A', '#B8C2D0', '#5B6B85'];
  charts.cause = new Chart(document.getElementById('causeChart'), {
    type: 'doughnut',
    data: {
      labels: Object.keys(zone.causeBreakdown),
      datasets: [{ data: Object.values(zone.causeBreakdown), backgroundColor: causeColors, borderWidth: 0 }],
    },
    options: {
      plugins: { legend: { position: 'bottom', labels: { font: { size: 10, family: 'Inter' }, boxWidth: 10 } } },
      cutout: '62%',
    },
  });

  charts.trend = new Chart(document.getElementById('trendMiniChart'), {
    type: 'line',
    data: {
      labels: ['-6', '-5', '-4', '-3', '-2', '-1', '0'],
      datasets: [{ data: zone.trend7day, borderColor: '#16233B', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 2, tension: 0.35 }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: { y: { display: false }, x: { display: false } },
    },
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  const city = AppState.state.city;
  const offline = AppState.state.offline;
  const cells = buildCityGrid(city);
  const zones = Object.fromEntries(cells.map((c) => [c.cellId, mockZoneSummary(c.cellId)]));

  const statusEl = document.getElementById('densityStatus');
  statusEl.textContent = offline ? 'Road density: mock data' : 'Road density: querying Overpass API…';
  const density = await classifyDensity(cells, !offline);
  statusEl.textContent = offline ? 'Road density: mock data' : 'Road density: live OSM pull complete';

  const map = L.map('map', { zoomControl: true }).setView(CITY_CENTERS[city], 12);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);

  const gridLayer = L.layerGroup().addTo(map);
  const bubbleLayer = L.layerGroup().addTo(map);

  cells.forEach((cell) => {
    // subtle grid outline (keeps the "attribution grid" concept visible under the bubbles)
    L.rectangle([[cell.latMin, cell.lonMin], [cell.latMax, cell.lonMax]], {
      color: '#16233B', weight: 0.5, opacity: 0.15, fillOpacity: 0,
    }).addTo(gridLayer);
  });

  cells.forEach((cell) => {
    const zone = zones[cell.cellId];
    const cat = aqiCategory(zone.currentAqi);
    const colorVar = cat.color.match(/--[\w-]+/)[0];
    const color = getComputedStyle(document.documentElement).getPropertyValue(colorVar).trim();
    const size = 26 + Math.round((zone.currentAqi / 500) * 20);

    const icon = L.divIcon({
      className: '',
      html: `<div class="aqi-bubble mono-num" style="width:${size}px;height:${size}px;background:${color};font-size:${size > 38 ? 12 : 10}px;">${zone.currentAqi}</div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });

    const marker = L.marker(cell.centroid, { icon }).addTo(bubbleLayer);
    marker.bindTooltip(`${cell.cellId} — ${cat.label}`);
    marker.on('click', () => {
      renderDrilldown(cell.cellId, zone, density[cell.cellId] || { class: 'n/a' });
      document.getElementById('zoneSelect').value = cell.cellId;
    });
  });

  // Zone dropdown as an alternate way to open the drill-down (accessibility + no-map fallback)
  const zoneSelect = document.getElementById('zoneSelect');
  cells.forEach((c) => {
    const opt = document.createElement('option');
    opt.value = c.cellId;
    opt.textContent = c.cellId;
    zoneSelect.appendChild(opt);
  });
  zoneSelect.addEventListener('change', () => {
    const cellId = zoneSelect.value;
    if (!cellId) return;
    renderDrilldown(cellId, zones[cellId], density[cellId] || { class: 'n/a' });
    const cell = cells.find((c) => c.cellId === cellId);
    map.panTo(cell.centroid);
  });

  // Day 3: attribution model demo readout, shown below the legend
  const trafficArr = cells.map((c) => (density[c.cellId] ? density[c.cellId].rawScore : 0));
  const industryMap = mockIndustrialProximity(cells.map((c) => c.cellId));
  const fireMap = mockFireCounts(cells.map((c) => c.cellId));
  const industryArr = cells.map((c) => industryMap[c.cellId]);
  const fireArr = cells.map((c) => fireMap[c.cellId]);
  const aqiArr = cells.map((c) => zones[c.cellId].currentAqi);
  const fit = fitAttributionModel(trafficArr, industryArr, fireArr, aqiArr);

  document.getElementById('modelReadout').innerHTML = `
    <span class="eyebrow">ATTRIBUTION MODEL — ${fit.method.replace(/_/g, ' ')}</span>
    <div class="grid-3" style="margin-top:10px;">
      <div class="readout-tile"><div class="label">Traffic coef.</div><div class="value">${fit.coefficients.traffic}</div></div>
      <div class="readout-tile"><div class="label">Industry coef.</div><div class="value">${fit.coefficients.industry}</div></div>
      <div class="readout-tile"><div class="label">Fires coef.</div><div class="value">${fit.coefficients.fires}</div></div>
    </div>
    ${fit.r2 !== null ? `<div class="readout-tile" style="margin-top:10px;"><div class="label">R²</div><div class="value">${fit.r2}</div></div>` : ''}
  `;
});
