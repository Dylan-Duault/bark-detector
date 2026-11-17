import {element} from '../shared/format.js';

export class BarkMusic extends HTMLElement {
  update(data) {
    const $ = id => this.querySelector(`#${id}`);
    const music = data.music_events || [];
    $('music-count').textContent = `${music.filter(e=>e.status==='started').length} lancement(s)`;
    $('music-events').replaceChildren(...music.map(event=>{
      const card = element('article', undefined, 'music-event');
      card.append(element('span', event.status === 'started' ? '♫ LECTEUR LANCÉ' : '⚠ ÉCHEC DU LANCEMENT', 'eyebrow'),
        element('strong', `À ${event.time} · ${event.track}`));
      if (event.detail) card.append(element('p', event.detail, 'muted'));
      return card;
    }));
    if (!music.length) $('music-events').append(element('p', 'Aucun lancement de musique enregistré pour cette journée.', 'empty'));

  }
}
customElements.define('bark-music', BarkMusic);
