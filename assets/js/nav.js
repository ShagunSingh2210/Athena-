document.addEventListener('DOMContentLoaded', () => {
    const citySelects = document.querySelectorAll('[data-role="city-select"]');
    const offlineToggles = document.querySelectorAll('[data-role="offline-toggle"]');

    if (citySelects.length > 0) {
        citySelects.forEach(sel => {
            sel.value = window.AppState.city;
            sel.addEventListener('change', (e) => {
                window.AppState.setCity(e.target.value);
            });
        });
    }

    if (offlineToggles.length > 0) {
        const updateUI = () => {
            offlineToggles.forEach(toggle => {
                if (window.AppState.offline) {
                    toggle.innerHTML = `<div class="w-2 h-2 rounded-full bg-slate-400"></div><span class="font-mono text-slate-400">Offline / fallback data</span>`;
                } else {
                    toggle.innerHTML = `<div class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"></div><span class="font-mono text-slate-300">Live data sources</span>`;
                }
            });
        };
        updateUI();
        offlineToggles.forEach(toggle => {
            toggle.addEventListener('click', () => {
                window.AppState.toggleOffline();
                updateUI();
            });
        });
    }
});
