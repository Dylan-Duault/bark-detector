import './bark-recording.js';
import {element, files} from '../shared/format.js';

/** Keyed reconciliation preserves the player and playback position on refresh. */
export class BarkRecordings extends HTMLElement {
  update(data) {
    this.querySelector('#audio-count').textContent = files(data.recordings.length);
    const container = this.querySelector('#recordings');
    if (this.date !== data.date) container.replaceChildren();
    this.date = data.date;
    container.querySelector('.empty')?.remove();
    const existing = new Map([...container.querySelectorAll('bark-recording')].map(node => [node.recording.name, node]));
    const names = new Set(data.recordings.map(recording => recording.name));
    for (const [name, node] of existing) if (!names.has(name)) node.remove();
    for (const recording of [...data.recordings].reverse()) {
      if (existing.has(recording.name)) continue;
      const card = document.createElement('bark-recording');
      card.recording = recording;
      container.prepend(card);
    }
    if (!data.recordings.length) container.append(element('p',
      'Aucun fichier audio pour cette journée. Un enregistrement en cours apparaîtra après sa fin.', 'empty'));
  }
}
customElements.define('bark-recordings', BarkRecordings);
