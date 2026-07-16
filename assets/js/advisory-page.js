/**
 * pages/advisory.html logic
 * Day 5 deliverable: citizen chat interface (zone + health profile +
 * language), officer-approval queue, citizen alert-received screen.
 */
let officerQueue = mockOfficerQueue();
let chatHistory = [];

function renderModeTabs(active) {
  document.querySelectorAll('.segmented button').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mode === active);
  });
  document.querySelectorAll('.mode-panel').forEach((panel) => {
    panel.style.display = panel.dataset.panel === active ? 'block' : 'none';
  });
}

function renderChat() {
  const el = document.getElementById('chatHistory');
  if (!chatHistory.length) {
    el.innerHTML = `<p style="color:var(--muted); font-size:0.88rem;">Fill in the form and submit to see a generated advisory here.</p>`;
    return;
  }
  el.innerHTML = chatHistory
    .slice()
    .reverse()
    .map(
      (e) => `
      <div class="chat-bubble">
        <div class="meta">${e.zone} · ${e.profile} · ${LANGUAGES[e.language]}</div>
        ${e.text}
      </div>`
    )
    .join('');
}

function renderQueue() {
  const el = document.getElementById('officerQueue');
  el.innerHTML = officerQueue
    .map(
      (item) => `
      <div class="queue-card">
        <div class="queue-head">
          <strong>${item.zone}</strong>
          <span class="status-pill" data-status="${item.status}">${item.status}</span>
        </div>
        <div class="queue-msg">${item.draftMessage}</div>
        <div class="queue-actions">
          ${item.status === 'pending'
            ? `<button class="btn btn-approve" data-approve="${item.id}">Approve &amp; send</button>
               <button class="btn btn-reject" data-reject="${item.id}">Reject</button>`
            : `<span class="eyebrow">Resolved</span>`}
        </div>
      </div>`
    )
    .join('');

  el.querySelectorAll('[data-approve]').forEach((btn) =>
    btn.addEventListener('click', () => {
      const item = officerQueue.find((i) => i.id === Number(btn.dataset.approve));
      item.status = 'approved';
      renderQueue();
      renderAlerts();
    })
  );
  el.querySelectorAll('[data-reject]').forEach((btn) =>
    btn.addEventListener('click', () => {
      const item = officerQueue.find((i) => i.id === Number(btn.dataset.reject));
      item.status = 'rejected';
      renderQueue();
    })
  );
}

function renderAlerts() {
  const el = document.getElementById('alertList');
  const approved = officerQueue.filter((i) => i.status === 'approved');
  if (!approved.length) {
    el.innerHTML = `<p style="color:var(--muted); font-size:0.88rem;">No alerts have been approved yet. Approve one in the Officer tab to preview it here.</p>`;
    return;
  }
  el.innerHTML = approved
    .map(
      (item) => `
      <div class="card card-pad" style="border-left:4px solid var(--aqi-good); margin-bottom:12px;">
        <div class="eyebrow" style="margin-bottom:6px;">🔔 ALERT DELIVERED — ${item.zone}</div>
        <div style="font-size:0.9rem;">${item.draftMessage}</div>
      </div>`
    )
    .join('');
}

document.addEventListener('DOMContentLoaded', () => {
  const city = AppState.state.city;
  const cells = buildCityGrid(city);
  const zoneSelect = document.getElementById('advisoryZone');
  cells.forEach((c) => {
    const opt = document.createElement('option');
    opt.value = c.cellId;
    opt.textContent = c.cellId;
    zoneSelect.appendChild(opt);
  });

  document.querySelectorAll('.segmented button').forEach((btn) => {
    btn.addEventListener('click', () => renderModeTabs(btn.dataset.mode));
  });
  renderModeTabs('citizen');

  document.getElementById('advisoryForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const zone = zoneSelect.value;
    const profile = document.getElementById('advisoryProfile').value;
    const language = document.getElementById('advisoryLanguage').value;
    // TODO(Person A): replace mockAdvisory() with the real Claude API call, e.g.
    //   const text = await advisoryBackend.generate(zone, profile, language);
    const text = mockAdvisory(zone, profile, language);
    chatHistory.push({ zone, profile, language, text });
    renderChat();
  });

  renderChat();
  renderQueue();
  renderAlerts();
});
