import {element, formatDate, duration} from '../shared/format.js';

export class BarkHistory extends HTMLElement {
  update(data) {
    const $ = id => this.querySelector(`#${id}`);
const date = data.date;
    $('history').replaceChildren(...data.days.map(day=>{
      const button = element('button',undefined,'day');
      button.type='button'; button.setAttribute('aria-pressed',String(day.date===date));
      button.append(element('span',formatDate(day.date)),element('small',`${day.detections} extraits · ${day.recordings} audio${day.listened_seconds === null ? '' : ` · ${duration(day.listened_seconds)} d’écoute`}`));
      button.addEventListener('click',()=>{ this.dispatchEvent(new CustomEvent('select-date', {detail:day.date, bubbles:true})); });
      return button;
    }));
    if (!data.days.length) $('history').append(element('p','Aucune journée enregistrée pour le moment. Les journées apparaîtront lorsque le détecteur aura créé des données.','muted'));

  }
}
customElements.define('bark-history', BarkHistory);
