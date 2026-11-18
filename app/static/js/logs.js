import {api} from './shared/http.js';
import './shared/session.js';

const source = document.getElementById('source');
const status = document.getElementById('log-status');
const output = document.getElementById('log-output');
const follow = document.getElementById('follow');
const pause = document.getElementById('pause');
let paused = false;
let request;

function setStatus(state, message) {
  status.dataset.state = state;
  if (status.textContent !== message) status.textContent = message;
}

function scrollToLatest() {
  if (follow.checked) output.scrollTop = output.scrollHeight;
}

async function refresh() {
  request?.abort();
  const controller = request = new AbortController();
  try {
    const data = await api(`/api/logs?source=${encodeURIComponent(source.value)}`, {signal: controller.signal, timeout: 8000});
    if (request !== controller) return;
    const lines = data.entries.map(entry =>
      `${new Date(entry.timestamp * 1000).toLocaleString('fr-FR')}  ${entry.message}`
    ).join('\n') || 'Aucune ligne disponible pour ce service.';
    if (output.textContent !== lines) {
      const previousScroll = output.scrollTop;
      output.textContent = lines;
      output.scrollTop = previousScroll;
      scrollToLatest();
    }
    setStatus(paused ? 'unknown' : 'listening', paused ? 'Actualisation en pause.' : 'Actualisation automatique active');
  } catch {
    if (request === controller) {
      setStatus('error', paused ? 'Journal indisponible. Actualisez pour réessayer.' : 'Journal indisponible. Nouvelle tentative automatique.');
    }
  } finally {
    if (request === controller) request = undefined;
  }
}

pause.addEventListener('click', () => {
  paused = !paused;
  pause.setAttribute('aria-pressed', String(paused));
  if (paused) {
    request?.abort();
    request = undefined;
    setStatus('unknown', 'Actualisation en pause.');
  } else {
    refresh();
  }
});
source.addEventListener('change', () => {
  output.textContent = '';
  setStatus('unknown', 'Chargement…');
  refresh();
});
follow.addEventListener('change', scrollToLatest);
document.getElementById('refresh').addEventListener('click', refresh);
setInterval(() => { if (!paused && !request && !document.hidden) refresh(); }, 2000);
refresh();
