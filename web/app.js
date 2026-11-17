const $ = id => document.getElementById(id);
const today = new Date();
$('date').value = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
let request = 0;
let period = 7;
const formatDate = value => new Date(`${value}T12:00:00`).toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'});
const duration = seconds => {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor(total % 3600 / 60);
  const rest = total % 60;
  if (hours) return `${hours} h ${minutes} min`;
  return minutes ? `${minutes} min${rest ? ` ${rest} s` : ''}` : `${rest} s`;
};
const extracts = count => `${count} extrait${count === 1 ? '' : 's'} avec aboiements`;
const files = count => `${count} fichier${count === 1 ? '' : 's'} audio`;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function renderDetector(detector) {
  const labels = {
    starting:'Démarrage du détecteur…',
    waiting_audio:'En attente du microphone…',
    listening:'Microphone à l’écoute',
    microphone_unavailable:'Microphone indisponible',
    no_audio:'Aucun signal du microphone',
    stopped:'Détecteur arrêté',
    error:'Détecteur en erreur',
    unresponsive:'Le détecteur ne répond plus',
    unknown:'État du détecteur inconnu'
  };
  const node=$('detector-status');
  node.textContent=`En direct · ${labels[detector.state] || labels.unknown}`;
  node.dataset.state=detector.state;
  node.title=detector.last_audio_at ? `Dernier signal du microphone reçu le ${new Date(detector.last_audio_at*1000).toLocaleString('fr-FR')}` : 'Aucun signal du microphone reçu depuis le début du suivi.';
}

function renderTrends(trends) {
  const coverage = trends.listened_seconds === null ? 'durée d’écoute non mesurée' : `${duration(trends.listened_seconds)} d’écoute mesurée`;
  $('period-caption').textContent = `Du ${formatDate(trends.start)} au ${formatDate(trends.end)} · ${coverage}.`;
  const maxSeconds = Math.max(1,...trends.days.map(day=>day.seconds));
  $('daily-scale').textContent = `Échelle : 0 → ${duration(maxSeconds)}`;
  $('daily-chart').style.setProperty('--days',trends.period);
  $('daily-chart').replaceChildren(...trends.days.map(day=>{
    const column = element('div',undefined,'daily-column');
    const button = element('button',undefined,`daily-bar${day.has_data?'':' no-data'}`);
    button.type='button';
    button.style.setProperty('--height',`${Math.max(2,day.seconds/maxSeconds*100)}%`);
    const detail = `${formatDate(day.date)} : ${day.has_data?`${duration(day.seconds)} de séries d’aboiements, pauses comprises · ${extracts(day.detections)}`:'aucune donnée pour ce jour'} · ${day.listened_seconds === null ? 'écoute non mesurée' : `${duration(day.listened_seconds)} d’écoute mesurée`}`;
    button.setAttribute('aria-label',detail); button.title=detail;
    button.addEventListener('click',()=>{ $('daily-detail').textContent=detail; });
    const track = element('div',undefined,'daily-track'); track.append(button);
    column.append(track,element('span',day.date.slice(8),'daily-label'));
    return column;
  }));
  const maxCount = Math.max(0,...trends.days.flatMap(day=>day.hours));
  $('heat-max').textContent = `${maxCount} extraits / h`;
  const cells = [element('span','Jour','heat-label')];
  for (let hour=0;hour<24;hour++) cells.push(element('span',String(hour).padStart(2,'0'),'heat-hour'));
  for (const day of trends.days) {
    cells.push(element('span',new Date(`${day.date}T12:00:00`).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'}),'heat-label'));
    day.hours.forEach((count,hour)=>{
      const level = count ? Math.max(1,Math.ceil(count/Math.max(1,maxCount)*4)) : 0;
      const observed = count > 0 || (day.listened_hours?.[hour] || 0) > 0;
      const cell = element('button',undefined,observed?`heat-cell level-${level}`:'heat-cell no-data');
      const detail = `${formatDate(day.date)}, ${hour} h–${hour+1} h : ${observed?extracts(count):'aucune donnée pour cette heure'}`;
      cell.type='button'; cell.title=detail; cell.setAttribute('aria-label',detail);
      cell.addEventListener('click',()=>{ $('heat-detail').textContent=detail; });
      cells.push(cell);
    });
  }
  $('heatmap').replaceChildren(...cells);
  const maxHours=Math.max(1,...trends.hours);
  $('period-hours').replaceChildren(...trends.hours.map((count,hour)=>{
    const button=element('button',undefined,'bar hour-bar');
    const detail=`${hour} h–${hour+1} h : ${extracts(count)} sur ${trends.period} jours`;
    button.type='button'; button.style.setProperty('--height',`${count/maxHours*100}%`);
    button.setAttribute('aria-label',detail); button.title=detail;
    button.addEventListener('click',()=>{ $('hours-detail').textContent=detail; });
    return button;
  }));
}

const timestamp = seconds => {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};
function recordingCard(recording) {
  const row = element('article', undefined, 'recording');
  row.dataset.name = recording.name;
  const header = element('div', undefined, 'recording-header');
  const label = element('div');
  label.append(element('span', 'ENREGISTREMENT', 'eyebrow'), element('strong', `À ${recording.time}`));
  const download = element('a', 'Télécharger ↓', 'download');
  download.href = recording.url; download.download = recording.name;
  header.append(label, download);
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
  const observer = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return;
    observer.disconnect();
    fetch(`/api/waveform/${encodeURIComponent(recording.name)}`).then(async response => {
      if (response.status === 401) { window.location.replace('/login?expired=1'); throw new Error('Session expirée'); }
      if (!response.ok) throw new Error('Analyse indisponible');
      return response.json();
    }).then(data => {
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
  return row;
}

let audioSignature = null;
let renderedDate = null;
async function refresh() {
  const current = ++request;
  const date = $('date').value;
  if (!date) return;
  $('status').textContent = 'Actualisation des données…';
  const controller = new AbortController();
  const timeout = setTimeout(()=>controller.abort(), 10000);
  try {
    const response = await fetch(`/api/dashboard?date=${encodeURIComponent(date)}&period=${period}`,{cache:'no-store', signal:controller.signal});
    if (response.status === 401) { window.location.replace('/login?expired=1'); return; }
    if (!response.ok) throw new Error('HTTP '+response.status);
    const data = await response.json();
    if (current !== request) return;
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
    renderDetector(data.detector);
    renderTrends(data.trends);
    const s = data.summary;
    const hasStats = data.summary.has_data;
    $('listening-summary').textContent = s.listened_seconds === null ? '· Écoute non mesurée' : `· ${duration(s.listened_seconds)} d’écoute mesurée`;
    $('listening-summary').title = data.detector.tracking_since ? `Durée mesurée depuis le ${new Date(data.detector.tracking_since*1000).toLocaleString('fr-FR')}. Les anciennes périodes ne sont pas estimées.` : 'La durée d’écoute n’était pas mesurée pour cette journée.';
    $('detections').textContent = hasStats ? s.detections : '—';
    $('sessions').textContent = hasStats ? s.sessions : '—';
    $('duration').textContent = hasStats ? duration(s.seconds) : '—';
    $('count').textContent = s.recordings;
    $('audio-count').textContent = files(s.recordings);
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
    const signature = JSON.stringify([date,data.recordings]);
    // Keep existing players intact during automatic refresh, including current playback.
    if (signature !== audioSignature) {
      const container = $('recordings');
      if (renderedDate !== date) container.replaceChildren();
      container.querySelector('.empty')?.remove();
      const existing = new Map([...container.querySelectorAll('.recording')].map(node=>[node.dataset.name,node]));
      const names = new Set(data.recordings.map(r=>r.name));
      for (const [name,node] of existing) if (!names.has(name)) node.remove();
      for (const recording of [...data.recordings].reverse()) {
        if (existing.has(recording.name)) continue;
        container.prepend(recordingCard(recording));
      }
      if (!data.recordings.length) container.append(element('p','Aucun fichier audio pour cette journée. Si un enregistrement est en cours, il apparaîtra après sa fin.','empty'));
      audioSignature = signature;
      renderedDate = date;
    }
    $('history').replaceChildren(...data.days.map(day=>{
      const button = element('button',undefined,'day');
      button.type='button'; button.setAttribute('aria-pressed',String(day.date===date));
      button.append(element('span',formatDate(day.date)),element('small',`${day.detections} extraits · ${day.recordings} audio${day.listened_seconds === null ? '' : ` · ${duration(day.listened_seconds)} d’écoute`}`));
      button.addEventListener('click',()=>{ $('date').value=day.date; refresh(); });
      return button;
    }));
    if (!data.days.length) $('history').append(element('p','Aucune journée enregistrée pour le moment. Les journées apparaîtront lorsque le détecteur aura créé des données.','muted'));
    $('status').textContent = `Mis à jour à ${new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}`;
  } catch (error) {
    if (current === request) {
      $('detector-status').dataset.state='unknown';
      $('detector-status').textContent='État du détecteur indisponible';
      $('detector-status').removeAttribute('title');
      $('status').textContent = 'Impossible de charger les données. Vérifiez votre connexion au réseau du Pi, puis appuyez sur Actualiser.';
    }
  } finally {
    clearTimeout(timeout);
  }
}
document.querySelectorAll('[data-period]').forEach(button=>button.addEventListener('click',()=>{
  period = Number(button.dataset.period);
  document.querySelectorAll('[data-period]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
  refresh();
}));
$('date').addEventListener('change',refresh);
$('refresh').addEventListener('click',refresh);
refresh();
setInterval(refresh,30000);

$('logout').addEventListener('click',async()=>{
  try {
    const response=await fetch('/api/logout',{method:'POST'});
    if (!response.ok) throw new Error('Logout failed');
    window.location.replace('/login');
  } catch (error) {
    $('status').textContent='Déconnexion impossible. Vérifiez votre connexion au réseau du Pi, puis réessayez.';
  }
});
