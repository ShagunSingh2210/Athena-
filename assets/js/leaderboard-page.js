/**
 * pages/leaderboard.html logic
 * Day 6 deliverable: Pollution Debt Leaderboard (ranked table/bar chart,
 * avg-AQI-this-week, methodology disclaimer) + 2-city comparison UI.
 */
function formatInr(n) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);
}

document.addEventListener('DOMContentLoaded', () => {
  const city = AppState.state.city;
  const otherCity = city === 'Delhi' ? 'Mumbai' : 'Delhi';
  const cells = buildCityGrid(city);
  const cellIds = cells.map((c) => c.cellId);

  const rows = mockLeaderboard(cellIds, 5);
  const tbody = document.getElementById('leaderboardBody');
  tbody.innerHTML = rows
    .map(
      (r, i) => `
      <tr>
        <td class="rank mono-num">${i + 1}</td>
        <td><strong>${r.cellId}</strong></td>
        <td class="mono-num">${r.population.toLocaleString('en-IN')}</td>
        <td class="mono-num">${r.daysAboveThreshold}</td>
        <td class="mono-num">${r.avgAqiThisWeek}</td>
        <td class="mono-num"><strong>${formatInr(r.estimatedCostInr)}</strong></td>
      </tr>`
    )
    .join('');

  new Chart(document.getElementById('leaderboardChart'), {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.cellId),
      datasets: [{
        label: 'Estimated health cost (INR)',
        data: rows.map((r) => r.estimatedCostInr),
        backgroundColor: '#16233B',
        borderRadius: 4,
        maxBarThickness: 40,
      }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { ticks: { font: { family: 'IBM Plex Mono', size: 10 }, callback: (v) => `₹${(v / 1e6).toFixed(1)}M` }, grid: { color: '#E2E8F0' } },
        x: { ticks: { font: { family: 'IBM Plex Mono', size: 10 } }, grid: { display: false } },
      },
    },
  });

  // 2-city comparison
  const comp = mockCityComparison(city, otherCity);
  document.getElementById('cityAName').textContent = comp.cityA.name;
  document.getElementById('cityBName').textContent = comp.cityB.name;
  document.getElementById('cityAAqi').textContent = comp.cityA.avgAqi;
  document.getElementById('cityBAqi').textContent = comp.cityB.avgAqi;

  const causeColors = ['#E08A1E', '#16233B', '#8BC34A', '#B8C2D0', '#5B6B85'];
  function factorChart(canvasId, factors) {
    new Chart(document.getElementById(canvasId), {
      type: 'bar',
      data: {
        labels: Object.keys(factors),
        datasets: [{ data: Object.values(factors), backgroundColor: causeColors }],
      },
      options: {
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { max: 100, ticks: { font: { family: 'IBM Plex Mono', size: 10 } }, grid: { color: '#E2E8F0' } },
          y: { ticks: { font: { size: 11 } }, grid: { display: false } },
        },
      },
    });
  }
  factorChart('cityAFactorChart', comp.cityA.factors);
  factorChart('cityBFactorChart', comp.cityB.factors);
});
