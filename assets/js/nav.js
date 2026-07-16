/**
 * nav.js
 * Wires up the shared header present on every page: city selector,
 * offline/live toggle, and active-link highlighting. The header markup
 * itself is duplicated per page (no templating layer) but this script
 * keeps its behavior identical everywhere.
 */
document.addEventListener('DOMContentLoaded', () => {
  const citySelect = document.querySelector('[data-role="city-select"]');
  const offlineToggle = document.querySelector('[data-role="offline-toggle"]');
  const navLinks = document.querySelectorAll('.main-nav a');

  if (citySelect) {
    citySelect.value = AppState.state.city;
    citySelect.addEventListener('change', () => {
      AppState.setCity(citySelect.value);
      window.location.reload();
    });
  }

  if (offlineToggle) {
    offlineToggle.dataset.offline = String(AppState.state.offline);
    offlineToggle.querySelector('.status-label').textContent = AppState.state.offline
      ? 'Offline / fallback data'
      : 'Live data sources';
    offlineToggle.addEventListener('click', () => {
      AppState.setOffline(!AppState.state.offline);
      window.location.reload();
    });
  }

  const current = window.location.pathname.split('/').pop() || 'index.html';
  navLinks.forEach((a) => {
    const href = a.getAttribute('href').split('?')[0];
    a.classList.toggle('active', href === current);
    a.setAttribute('href', AppState.linkTo(href));
  });
});
