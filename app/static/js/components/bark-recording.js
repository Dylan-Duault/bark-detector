import {element, timestamp} from '../shared/format.js';
import {api} from '../shared/http.js';

export class BarkRecording extends HTMLElement {
  connectedCallback() {
    if (this.initialized || !this.recording) return;
    this.initialized = true;
    const recording = this.recording;

  const row = element('article', undefined, 'recording');
  row.dataset.name = recording.name;
  this.append(row);
  const header = element('div', undefined, 'recording-header');
  const download = element('a', 'Télécharger', 'download');
  download.href = recording.url; download.download = recording.name;
  download.setAttribute('aria-label', `Télécharger l’enregistrement de ${recording.time}`);
  header.append(element('h3', 'Enregistrement audio'), download);
  const audio = document.createElement('audio');
  audio.controls = true; audio.preload = 'none'; audio.src = recording.url;
  audio.setAttribute('aria-label', `Écouter l’enregistrement déclenché à ${recording.time}`);
  const transport = element('div', undefined, 'recording-transport');
  const play = element('button', '▶', 'recording-play');
  play.type = 'button'; play.disabled = true;
  const clock = element('span', `0:00 / ${timestamp(recording.duration)}`, 'recording-clock');
  const peak = element('span', 'Analyse du son…', 'recording-peak');
  transport.append(play, clock, peak);
  const graph = element('div', undefined, 'waveform');
  const bars = element('div', undefined, 'waveform-bars');
  const cursor = element('div', undefined, 'waveform-cursor');
  const seek = document.createElement('input');
  seek.type = 'range'; seek.min = 0; seek.max = recording.duration; seek.step = '0.01'; seek.value = 0;
  seek.disabled = true;
  seek.setAttribute('aria-label', `Position de lecture de l’enregistrement de ${recording.time}`);
  graph.append(bars, cursor, seek);
  const axis = element('div', undefined, 'waveform-axis');
  axis.append(element('span', '0:00'), element('span', timestamp(recording.duration)));
  const hint = element('p', 'Chargement de la courbe sonore…', 'recording-hint');
  let length = recording.duration;
  const update = () => {
    const time = audio.currentTime || 0;
    clock.textContent = `${timestamp(time)} / ${timestamp(length)}`;
    seek.value = time;
    seek.setAttribute('aria-valuetext', `${timestamp(time)} sur ${timestamp(length)}`);
    graph.style.setProperty('--progress', `${length ? time / length * 100 : 0}%`);
  };
  const playAudio = () => audio.play().catch(error => {
    if (error.name !== 'AbortError') hint.textContent = 'Lecture impossible. Réessayez ou téléchargez le fichier.';
  });
  play.addEventListener('click', () => audio.paused ? playAudio() : audio.pause());
  seek.addEventListener('input', () => { audio.currentTime = Number(seek.value); update(); });
  const playing = () => {
    play.textContent = audio.paused ? '▶' : 'Ⅱ';
    play.setAttribute('aria-label', audio.paused ? 'Lire l’enregistrement' : 'Mettre en pause');
  };
  playing();
  audio.addEventListener('play', () => {
    document.querySelectorAll('audio').forEach(other => { if (other !== audio) other.pause(); });
    playing();
  });
  audio.addEventListener('pause', playing);
  audio.addEventListener('ended', playing);
  audio.addEventListener('timeupdate', update);
  audio.addEventListener('loadedmetadata', () => {
    if (Number.isFinite(audio.duration)) { length = audio.duration; seek.max = length; update(); }
  });
  row.append(header, transport, graph, axis, hint, audio);
  // Only analyze cards near the viewport; do not download every WAV in the browser.
  const observer = this.observer = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return;
    observer.disconnect();
    this.controller = new AbortController();
    api(`/api/waveform/${encodeURIComponent(recording.name)}`, {signal:this.controller.signal}).then(data => {
      if (!data.levels.length) throw new Error('Audio vide');
      length = data.duration; seek.max = length; seek.disabled = false; play.disabled = false;
      axis.lastChild.textContent = timestamp(length);
      peak.textContent = `Pic : ${data.peak_dbfs <= -60 ? '≤ −60' : data.peak_dbfs} dBFS`;
      bars.replaceChildren(...data.levels.map(level => {
        const bar = element('i', undefined, level >= data.peak_dbfs - 6 && level > -60 ? 'loud' : '');
        bar.style.setProperty('--level', `${Math.max(3, (level + 60) / 60 * 100)}%`);
        return bar;
      }));
      hint.textContent = 'Déplacez le curseur pour choisir un passage. Les pics dorés indiquent les sons les plus forts.';
      audio.hidden = true;
      update();
    }).catch(() => {
      transport.hidden = true; graph.hidden = true; axis.hidden = true;
      hint.textContent = 'Courbe indisponible. Utilisez le lecteur audio ci-dessous.';
    });
  }, {rootMargin:'200px'});
  observer.observe(row);


  }
  disconnectedCallback() {
    this.observer?.disconnect();
    this.controller?.abort();
    this.querySelector('audio')?.pause();
  }
}
customElements.define('bark-recording', BarkRecording);
