import './bark-recording.js';
import {element, formatDate} from '../shared/format.js';

function timelineEntry(event, type) {
  const item = element('li', undefined, `timeline-entry timeline-entry--${type}`);
  const time = element('time', event.time);
  time.dateTime = `${event.date}T${event.time}`;
  item.append(time);

  if (type === 'audio') {
    const player = document.createElement('bark-recording');
    player.recording = event;
    item.append(player);
  } else if (type === 'voice') {
    const card = element('article', undefined, 'voice-event');
    card.append(element('h3', 'Parole en direct'));
    item.append(card);
  } else {
    const card = element('article', undefined, 'music-event');
    const failed = event.status === 'failed';
    card.dataset.status = event.status;
    card.append(element('h3', failed ? 'Échec du lancement de la musique' : 'Musique lancée'));
    if (event.track) card.append(element('p', event.track, 'music-track'));
    if (event.detail) card.append(element('p', event.detail, 'muted'));
    item.append(card);
  }
  return item;
}

class BarkTimeline extends HTMLElement {
  update(data) {
    const list = this.querySelector('#timeline');
    const empty = this.querySelector('#timeline-empty');
    const events = data.recordings.map(event => ({event, type: 'audio', key: event.name}));
    const occurrences = new Map();
    for (const event of data.music_events) {
      const signature = JSON.stringify([event.time, event.status, event.track, event.detail]);
      const count = (occurrences.get(signature) || 0) + 1;
      occurrences.set(signature, count);
      events.push({event, type: 'music', key: `${signature}:${count}`});
    }
    for (const event of data.live_voice_events) {
      events.push({event, type: 'voice', key: `voice:${event.id}`});
    }
    events.sort((a, b) => b.event.time.localeCompare(a.event.time));

    if (this.date !== data.date) {
      list.replaceChildren();
      this.date = data.date;
      this.querySelector('#timeline-date').textContent = formatDate(data.date);
    }

    // Keep existing players mounted when new events arrive.
    const existing = new Map([...list.children].map(item => [item.dataset.key, item]));
    const keys = new Set(events.map(({key}) => key));
    for (const [key, item] of existing) {
      if (!keys.has(key)) item.remove();
    }
    let next = null;
    for (const {event, type, key} of events.reverse()) {
      let item = existing.get(key);
      if (!item) {
        item = timelineEntry(event, type);
        item.dataset.key = key;
        list.insertBefore(item, next);
      }
      next = item;
    }
    empty.hidden = events.length > 0;
    empty.textContent = 'Aucun événement pour cette journée.';
  }
}

customElements.define('bark-timeline', BarkTimeline);
