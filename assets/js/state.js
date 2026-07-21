/**
 * state.js
 * Shared state across pages using URL query params instead of
 * localStorage/sessionStorage — keeps every page a plain, shareable
 * link (?city=Delhi&offline=1) and avoids any browser storage API.
 */
const AppState = (() => {
  const params = new URLSearchParams(window.location.search);

  const state = {
    city: params.get('city') || 'Delhi',
    offline: params.get('offline') === '1', // default true (offline/mock mode)
  };

  function persist() {
    const p = new URLSearchParams(window.location.search);
    p.set('city', state.city);
    p.set('offline', state.offline ? '1' : '0');
    const newUrl = `${window.location.pathname}?${p.toString()}`;
    window.history.replaceState({}, '', newUrl);
  }

  function setCity(city) {
    state.city = city;
    persist();
    window.dispatchEvent(new CustomEvent('appstate:change', { detail: state }));
  }

  function setOffline(offline) {
    state.offline = offline;
    persist();
    window.dispatchEvent(new CustomEvent('appstate:change', { detail: state }));
  }

  function linkTo(page) {
    return `${page}?city=${encodeURIComponent(state.city)}&offline=${state.offline ? 1 : 0}`;
  }

  persist();

  return { state, setCity, setOffline, linkTo };
})();
