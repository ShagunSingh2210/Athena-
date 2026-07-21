document.addEventListener('DOMContentLoaded', () => {
    const zoneSelect = document.getElementById('zoneSelect');
    const lagVal = document.getElementById('lagVal');
    const corrVal = document.getElementById('corrVal');
    const ctx = document.getElementById('causalChart');

    if (!zoneSelect || !ctx) return;

    let causalChart = null;

    // 1. Populate Zone Dropdown from MockData or AppState grid
    function loadZones() {
        zoneSelect.innerHTML = '<option value="">Select zone...</option>';
        const zones = (typeof MockData !== 'undefined' && MockData.getZones) ? MockData.getZones(window.AppState.city) : ['DEL-R04C04', 'DEL-R04C05', 'DEL-R04C06'];
        
        zones.forEach(z => {
            const opt = document.createElement('option');
            opt.value = typeof z === 'object' ? z.id : z;
            opt.textContent = typeof z === 'object' ? `${z.id} (${z.name || 'Zone'})` : z;
            zoneSelect.appendChild(opt);
        });

        // Default to first zone
        if (zones.length > 0) {
            zoneSelect.value = typeof zones[0] === 'object' ? zones[0].id : zones[0];
            updateChart(zoneSelect.value);
        }
    }

    // 2. Render or Update Chart with Data
    function updateChart(zoneId) {
        // Fallback metrics
        if (lagVal) lagVal.textContent = '2 days';
        if (corrVal) corrVal.textContent = '0.85';

        const days = ['Day -6', 'Day -5', 'Day -4', 'Day -3', 'Day -2', 'Yesterday', 'Today'];
        const aqiData = [130, 210, 115, 320, 300, 185, 190];
        const hciData = [0.35, 0.35, 0.35, 0.36, 0.65, 0.30, 0.70];

        if (causalChart) {
            causalChart.destroy();
        }

        causalChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: days,
                datasets: [
                    {
                        label: 'AQI',
                        data: aqiData,
                        borderColor: '#0f172a',
                        backgroundColor: 'rgba(15, 23, 42, 0.05)',
                        fill: true,
                        tension: 0.3,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Human Cost Index (HCI)',
                        data: hciData,
                        borderColor: '#f59e0b',
                        borderDash: [4, 4],
                        tension: 0.3,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { type: 'linear', display: true, position: 'left', min: 0, max: 400 },
                    y1: { type: 'linear', display: true, position: 'right', min: 0, max: 1, grid: { drawOnChartArea: false } }
                }
            }
        });
    }

    zoneSelect.addEventListener('change', (e) => {
        if (e.target.value) updateChart(e.target.value);
    });

    // Initialize
    loadZones();
});
