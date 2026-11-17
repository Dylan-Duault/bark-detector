import {element, extracts} from '../shared/format.js';

export class BarkActivity extends HTMLElement {
  update(data) {
    const $ = id => this.querySelector(`#${id}`);
const s = data.summary;
const hasStats = s.has_data;
    const max = Math.max(1,...s.hours);
    $('chart').replaceChildren(...s.hours.map((count,hour) => {
      const bar = element('div',undefined,'bar');
      bar.style.setProperty('--height',`${count/max*100}%`);
      bar.tabIndex = 0;
      bar.setAttribute('aria-label',`${hour} h : ${extracts(count)}`);
      bar.append(element('span',`${hour} h · ${count} extrait${count === 1 ? '' : 's'}`));
      return bar;
    }));
    $('chart').setAttribute('aria-label',`Extraits avec aboiements par heure : ${s.hours.map((n,h)=>`${h} h : ${n}`).join(', ')}`);
    $('activity-note').textContent = !hasStats ? 'Aucune donnée d’écoute pour cette journée.' : s.detections ? `${extracts(s.detections)} pour la journée choisie.` : 'Aucun extrait avec aboiements pour la journée choisie.';

  }
}
customElements.define('bark-activity', BarkActivity);
