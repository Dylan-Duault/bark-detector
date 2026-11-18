import {api} from './shared/http.js';
import './shared/session.js';
import './components/bark-health.js';
import './components/bark-metrics.js';
import './components/bark-activity.js';
import './components/bark-timeline.js';
import './components/bark-trends.js';

/** Coordinates filters and requests; each child owns its rendering and behavior. */
class BarkDashboard extends HTMLElement {
  connectedCallback() {
    this.period = 7;
    this.version = 0;
    this.events = new AbortController();
    const options = {signal: this.events.signal};
    const now = new Date();
    this.querySelector('#date').value = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    this.querySelector('#date').addEventListener('change', () => this.refresh(), options);
    this.querySelector('#refresh').addEventListener('click', () => this.refresh(), options);
    this.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', () => {
      this.period = Number(button.dataset.period);
      this.querySelectorAll('[data-period]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      this.refresh();
    }, options));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) this.refresh(); }, options);
    this.timer = setInterval(() => { if (!document.hidden) this.refresh(); }, 30000);
    this.refresh();
  }

  disconnectedCallback() {
    clearInterval(this.timer);
    this.events.abort();
    this.request?.abort();
  }

  async refresh() {
    const date = this.querySelector('#date').value;
    if (!date) return;
    const version = ++this.version;
    this.request?.abort();
    this.request = new AbortController();
    const status = this.querySelector('#status');
    status.textContent = 'Actualisation des données…';
    this.setAttribute('aria-busy', 'true');
    try {
      const data = await api(`/api/dashboard?date=${encodeURIComponent(date)}&period=${this.period}`, {signal: this.request.signal});
      if (version !== this.version) return;
      for (const name of ['metrics', 'activity', 'timeline']) this.querySelector(`bark-${name}`).update(data);
      this.querySelector('bark-health').update(data.detector);
      this.querySelector('bark-trends').update(data.trends);
      status.textContent = `Mis à jour à ${new Date().toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'})}`;
    } catch {
      if (version !== this.version) return;
      this.querySelector('bark-health').update({state: 'unknown'});
      status.textContent = 'Impossible de charger les données. Vérifiez votre connexion au Pi, puis actualisez.';
    } finally {
      if (version === this.version) this.setAttribute('aria-busy', 'false');
    }
  }
}
customElements.define('bark-dashboard', BarkDashboard);
