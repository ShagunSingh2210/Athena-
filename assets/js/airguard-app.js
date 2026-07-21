let loopChartInstance = null;
let leafletMap = null;
let mapLayersGroup = null;

function formatInr(n) {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);
}

function getAqiColor(aqi) {
    if (aqi > 350) return '#ef4444'; // critical red
    if (aqi > 200) return '#f5a623'; // warning orange
    return '#00ccbb'; // elevated teal
}

async function renderDashboard() {
    const city = AppState.state.city;
    document.getElementById('clCityName').textContent = city;

    const citySelector = document.getElementById('citySelector');
    citySelector.innerHTML = ['Delhi', 'Mumbai'].map(c => `
        <a href="#" onclick="AppState.setCity('${c}'); window.location.reload();" 
           class="font-label-caps text-[11px] pb-1 transition-colors duration-200 ${c === city ? 'text-secondary border-b-2 border-secondary font-bold' : 'text-on-surface-variant'}">${c}</a>
    `).join('');

    const statusToggle = document.querySelector('[data-role="offline-toggle"]');
    const statusLabel = document.getElementById('statusLabel');
    const statusDot = document.getElementById('statusDot');
    
    statusLabel.textContent = AppState.state.offline ? 'Offline / Mock Data' : 'Live Data (API)';
    statusDot.className = `w-2.5 h-2.5 rounded-full ${AppState.state.offline ? 'bg-danger' : 'bg-success'}`;
    
    statusToggle.onclick = () => {
        AppState.setOffline(!AppState.state.offline);
        window.location.reload();
    };

    // Initialize Leaflet Map once
    if (!leafletMap) {
        leafletMap = L.map('map', { zoomControl: true }).setView(CITY_CENTERS[city], 12);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(leafletMap);
        mapLayersGroup = L.layerGroup().addTo(leafletMap);
    } else {
        leafletMap.setView(CITY_CENTERS[city], 12);
        mapLayersGroup.clearLayers();
    }

    const cells = await Api.getCityGrid(city);
    const cellIds = cells.map(c => c.cellId);
    const zones = await Api.getCityZones(cellIds);
    const zoneMap = Object.fromEntries(zones.map(z => [z.cellId, z]));

    const chatZoneSelect = document.getElementById('chatZone');
    chatZoneSelect.innerHTML = '';

    let totalAqi = 0;

    cells.forEach(cell => {
        const zone = zoneMap[cell.cellId];
        if (!zone) return;
        
        totalAqi += zone.currentAqi;
        chatZoneSelect.innerHTML += `<option value="${cell.cellId}">${cell.cellId}</option>`;

        const color = getAqiColor(zone.currentAqi);
        const isSevere = zone.currentAqi > 350;
        const size = 32 + Math.round((zone.currentAqi / 500) * 16);

        // Draw 2km x 2km grid box on Leaflet map
        L.rectangle([[cell.latMin, cell.lonMin], [cell.latMax, cell.lonMax]], {
            color: color, weight: 1, opacity: 0.4, fillOpacity: 0.12, fillColor: color
        }).addTo(mapLayersGroup);

        // Custom Div marker for AQI value
        const icon = L.divIcon({
            className: '',
            html: `<div class="aqi-bubble ${isSevere ? 'pulse' : ''}" style="width:${size}px; height:${size}px; background:${color}33; border:2px solid ${color}; font-size:11px;">${zone.currentAqi}</div>`,
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
        });

        const marker = L.marker(cell.centroid, { icon }).addTo(mapLayersGroup);
        marker.bindTooltip(`${cell.cellId} — AQI ${zone.currentAqi}`);
        marker.on('click', () => {
            document.getElementById('drilldownCard').style.display = 'block';
            document.getElementById('ddZoneName').textContent = `Sector ${cell.cellId}`;
            document.getElementById('ddAqi').textContent = zone.currentAqi;
            document.getElementById('ddMeasures').innerHTML = zone.measuresTaken.map(m => `<li>${m}</li>`).join('');
            leafletMap.panTo(cell.centroid);
        });
    });

    document.getElementById('clAqiVal').textContent = Math.round(totalAqi / cells.length);

    const centerCell = cells[Math.floor(cells.length / 2)].cellId;
    const [loop, sentiment, trends] = await Promise.all([
        Api.getCausalLoop(centerCell),
        Api.getRedditSentiment(centerCell),
        Api.getGoogleTrends(centerCell)
    ]);

    if (loopChartInstance) loopChartInstance.destroy();
    loopChartInstance = new Chart(document.getElementById('loopChart'), {
        type: 'line',
        data: {
            labels: ['-6d', '-5d', '-4d', '-3d', '-2d', '-1d', 'Now'],
            datasets: [
                { label: 'AQI', data: loop.aqiSeries, borderColor: '#ef4444', yAxisID: 'y', tension: 0.4, pointRadius: 0 },
                { label: 'HCI', data: loop.hciSeries, borderColor: '#00ccbb', borderDash: [4, 4], yAxisID: 'y1', tension: 0.4, pointRadius: 0 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { display: false }, y: { display: false }, y1: { display: false } }
        }
    });

    document.getElementById('sentimentLabel').textContent = sentiment.label;
    document.getElementById('sentimentPct').textContent = `${sentiment.changePct}%`;
    document.getElementById('sentimentKeywords').textContent = `Keywords: ${sentiment.keywords.join(', ')}`;

    document.getElementById('trendsList').innerHTML = trends.map(t => `
        <li class="flex justify-between items-center border-b border-white/5 pb-1">
            <span class="font-body-sm text-[11px] text-on-surface">"${t.term}"</span>
            <span class="font-data-mono text-[11px] ${t.changePct > 200 ? 'text-danger' : 'text-warning'}">+${t.changePct}%</span>
        </li>
    `).join('');

    const lbRows = await Api.getLeaderboard(cellIds, 5);
    document.getElementById('leaderboardList').innerHTML = lbRows.map((r, i) => `
        <div class="bg-surface-container border border-white/5 rounded p-2 flex items-center justify-between">
            <div class="flex items-center gap-2">
                <span class="font-data-mono text-[11px] text-on-surface-variant w-4">${i + 1}</span>
                <div>
                    <p class="font-body-sm text-[11px] text-on-surface font-medium">${r.cellId}</p>
                    <p class="font-data-mono text-[9px] text-warning">Avg AQI ${r.avgAqiThisWeek}</p>
                </div>
            </div>
            <div class="text-right">
                <p class="font-data-mono text-[11px] text-on-surface">${formatInr(r.estimatedCostInr)}</p>
            </div>
        </div>
    `).join('');
}

document.getElementById('chatForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const zone = document.getElementById('chatZone').value;
    const profile = document.getElementById('chatProfile').value;
    const btn = e.target.querySelector('button');
    const history = document.getElementById('chatHistory');
    
    btn.disabled = true;
    btn.innerHTML = '<span class="material-symbols-outlined text-sm animate-spin">sync</span>';

    try {
        const text = await Api.getAdvisory(zone, profile, 'en');
        history.innerHTML += `
            <div class="flex justify-start mb-2">
                <div class="bg-secondary/10 border border-secondary/20 rounded-lg rounded-tl-none px-3 py-2 max-w-[95%]">
                    <p class="font-label-caps text-[9px] text-secondary mb-0.5">${zone} &middot; ${profile}</p>
                    <p class="font-body-sm text-[11px] text-on-surface">${text}</p>
                </div>
            </div>
        `;
        history.scrollTop = history.scrollHeight;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="material-symbols-outlined text-sm">send</span>';
    }
});

document.addEventListener('DOMContentLoaded', renderDashboard);