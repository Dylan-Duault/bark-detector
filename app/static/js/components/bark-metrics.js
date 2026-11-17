import {duration} from '../shared/format.js';

export class BarkMetrics extends HTMLElement {
  update(data) {
    const $ = id => this.querySelector(`#${id}`);
    const s = data.summary;
    const hasStats = s.has_data;
    $('listening-summary').textContent = s.listened_seconds === null ? '· Écoute non mesurée' : `· ${duration(s.listened_seconds)} d’écoute mesurée`;
    $('listening-summary').title = data.detector.tracking_since ? `Durée mesurée depuis le ${new Date(data.detector.tracking_since*1000).toLocaleString('fr-FR')}. Les anciennes périodes ne sont pas estimées.` : 'La durée d’écoute n’était pas mesurée pour cette journée.';
    $('detections').textContent = hasStats ? s.detections : '—';
    $('sessions').textContent = hasStats ? s.sessions : '—';
    $('duration').textContent = hasStats ? duration(s.seconds) : '—';
    $('count').textContent = s.recordings;


  }
}
customElements.define('bark-metrics', BarkMetrics);
