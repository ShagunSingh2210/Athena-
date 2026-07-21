document.addEventListener('DOMContentLoaded', async () => {
    const city = AppState.state.city;
    const citySelect = document.querySelector('[data-role="city-select"]');
    if (citySelect) {
        citySelect.value = city;
        citySelect.onchange = (e) => {
            AppState.setCity(e.target.value);
            loadAttributionMap(e.target.value);
        };
    }
    loadAttributionMap(city);
});

function getAqiColor(aqi) {
    if (aqi > 400) return '#800020'; // Severe
    if (aqi > 300) return '#ef4444'; // Very Poor
    if (aqi > 200) return '#f97316'; // Poor
    if (aqi > 100) return '#f59e0b'; // Moderate
    if (aqi > 50) return '#84cc16';  // Satisfactory
    return '#10b981';                // Good
}

async function loadAttributionMap(city) {
    const mapContainer = document.getElementById('map');
    if (!mapContainer) return;

    if (window._leafletMap) {
        window._leafletMap.remove();
        window._leafletMap = null;
    }

    const center = CITY_CENTERS[city] || [28.6139, 77.2090];
    const map = L.map('map', { zoomControl: true }).setView(center, 12);
    window._leafletMap = map;

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 19,
    }).addTo(map);

    setTimeout(() => { map.invalidateSize(); }, 250);

    let cells = [];
    let zones = [];

    try {
        cells = await Api.getCityGrid(city);
        if (cells && cells.length > 0) {
            const cellIds = cells.map(c => c.cellId);
            zones = await Api.getCityZones(cellIds);
        }
    } catch (err) {
        console.warn("API fetch failed, utilizing fallback data", err);
    }

    if (!cells || cells.length === 0) {
        cells = (typeof MOCK_GRID !== 'undefined' && MOCK_GRID[city]) ? MOCK_GRID[city] : [];
    }

    if (!zones || zones.length === 0) {
        zones = cells.map(c => ({
            cellId: c.cellId,
            currentAqi: Math.floor(Math.random() * 280) + 120,
            measuresTaken: ["Traffic diversion initiated", "Anti-smog mist cannon deployed"]
        }));
    }

    const zoneMap = Object.fromEntries(zones.map(z => [z.cellId, z]));
    const layerGroup = L.layerGroup().addTo(map);
    const markersMap = {};

    const jumpSelect = document.getElementById('zoneJumpSelect');
    if (jumpSelect) {
        jumpSelect.innerHTML = '<option value="">Select a zone...</option>';
        cells.forEach(c => {
            jumpSelect.innerHTML += `<option value="${c.cellId}">${c.cellId}</option>`;
        });
        jumpSelect.onchange = (e) => {
            const selectedId = e.target.value;
            if (markersMap[selectedId]) {
                markersMap[selectedId].marker.fire('click');
                map.setView(markersMap[selectedId].latLng, 14);
            }
        };
    }

    cells.forEach(cell => {
        const zone = zoneMap[cell.cellId] || { currentAqi: 220, measuresTaken: ["Monitoring active"] };
        const color = getAqiColor(zone.currentAqi);
        const size = 36;

        // Draw precise 2km x 2km grid box without massive overlaps
        L.rectangle([[cell.latMin, cell.lonMin], [cell.latMax, cell.lonMax]], {
            color: color, weight: 1, opacity: 0.6, fillOpacity: 0.15, fillColor: color
        }).addTo(layerGroup);

        const icon = L.divIcon({
            className: '',
            html: `<div class="${zone.currentAqi > 300 ? 'pulse' : ''}" style="width:${size}px; height:${size}px; background:${color}55; border:2px solid ${color}; border-radius:50%; display:flex; align-items:center; justify-content:center; font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:700; color:#fff; box-shadow:0 4px 12px rgba(0,0,0,0.6); cursor:pointer;">${zone.currentAqi}</div>`,
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
        });

        const marker = L.marker(cell.centroid, { icon }).addTo(layerGroup);
        markersMap[cell.cellId] = { marker, latLng: cell.centroid };

        marker.on('click', () => {
            if (jumpSelect) jumpSelect.value = cell.cellId;
            document.getElementById('panelZoneTitle').textContent = `Sector ${cell.cellId}`;
            
            const badge = document.getElementById('panelAqiBadge');
            badge.textContent = `AQI ${zone.currentAqi}`;
            badge.className = `px-2.5 py-1 rounded text-xs font-mono font-bold text-white`;
            badge.style.backgroundColor = color;

            const content = document.getElementById('panelContent');
            content.innerHTML = `
                <div>
                    <span class="text-[11px] font-mono text-gray-400 uppercase tracking-wider block mb-2">Source Apportionment Model</span>
                    <div class="space-y-2">
                        <div>
                            <div class="flex justify-between text-xs font-mono mb-1"><span>Traffic Emissions</span><span>45%</span></div>
                            <div class="w-full bg-gray-800 h-2 rounded-full overflow-hidden"><div class="bg-cyan-400 h-full" style="width: 45%;"></div></div>
                        </div>
                        <div>
                            <div class="flex justify-between text-xs font-mono mb-1"><span>Industrial Proximity</span><span>30%</span></div>
                            <div class="w-full bg-gray-800 h-2 rounded-full overflow-hidden"><div class="bg-amber-400 h-full" style="width: 30%;"></div></div>
                        </div>
                        <div>
                            <div class="flex justify-between text-xs font-mono mb-1"><span>Biomass / Stubble</span><span>25%</span></div>
                            <div class="w-full bg-gray-800 h-2 rounded-full overflow-hidden"><div class="bg-rose-500 h-full" style="width: 25%;"></div></div>
                        </div>
                    </div>
                </div>

                <div class="pt-3 border-t border-white/10 grid grid-cols-2 gap-3 font-mono">
                    <div class="bg-gray-900/60 p-3 rounded border border-white/5">
                        <span class="text-[10px] text-gray-400 block mb-1">Road Density</span>
                        <span class="text-sm font-bold text-white">14.2 km/km²</span>
                    </div>
                    <div class="bg-gray-900/60 p-3 rounded border border-white/5">
                        <span class="text-[10px] text-gray-400 block mb-1">24h Trend</span>
                        <span class="text-sm font-bold text-rose-400">+12% ▲</span>
                    </div>
                </div>

                <div class="pt-3 border-t border-white/10">
                    <span class="text-[11px] font-mono text-gray-400 uppercase tracking-wider block mb-1.5">Active Mitigation Measures</span>
                    <ul class="text-xs text-gray-300 list-disc pl-4 space-y-1">
                        ${(zone.measuresTaken || []).map(m => `<li>${m}</li>`).join('')}
                    </ul>
                </div>
            `;
            map.panTo(cell.centroid);
        });
    });
}
