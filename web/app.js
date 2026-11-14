const $ = id => document.getElementById(id);
const today = new Date();
$('date').value = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
let request = 0;
let period = 7;
const formatDate = value => new Date(`${value}T12:00:00`).toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'});
const duration = seconds => seconds < 60 ? `${Math.round(seconds)} s` : `${Math.floor(seconds/60)} min ${Math.round(seconds%60)} s`;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function renderTrends(trends) {
  const logged = trends.days.filter(day=>day.has_log).length;
  $('period-caption').textContent = `Du ${formatDate(trends.start)} au ${formatDate(trends.end)} · ${logged} jours avec un journal sur ${trends.period}. Un journal présent ne garantit pas une journée complète d’écoute.`;
  const maxSeconds = Math.max(1,...trends.days.map(day=>day.seconds));
  $('daily-scale').textContent = `Échelle : 0 → ${duration(maxSeconds)}`;
  $('daily-chart').style.setProperty('--days',trends.period);
  $('daily-chart').replaceChildren(...trends.days.map(day=>{
    const column = element('div',undefined,'daily-column');
    const button = element('button',undefined,`daily-bar${day.has_log?'':' no-data'}`);
    button.type='button';
    button.style.setProperty('--height',`${Math.max(2,day.seconds/maxSeconds*100)}%`);
    const detail = `${formatDate(day.date)} : ${day.has_log?`${duration(day.seconds)} en sessions terminées · ${day.detections} détections`:'aucun journal disponible'}`;
    button.setAttribute('aria-label',detail); button.title=detail;
    button.addEventListener('click',()=>{ $('daily-detail').textContent=detail; });
    const track = element('div',undefined,'daily-track'); track.append(button);
    column.append(track,element('span',day.date.slice(8),'daily-label'));
    return column;
  }));
  const maxCount = Math.max(0,...trends.days.flatMap(day=>day.hours));
  $('heat-max').textContent = `${maxCount} détections / h`;
  const cells = [element('span','Jour','heat-label')];
  for (let hour=0;hour<24;hour++) cells.push(element('span',String(hour).padStart(2,'0'),'heat-hour'));
  for (const day of trends.days) {
    cells.push(element('span',new Date(`${day.date}T12:00:00`).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'}),'heat-label'));
    day.hours.forEach((count,hour)=>{
      const level = count ? Math.max(1,Math.ceil(count/Math.max(1,maxCount)*4)) : 0;
      const cell = element('button',undefined,day.has_log?`heat-cell level-${level}`:'heat-cell no-data');
      const detail = `${formatDate(day.date)}, ${hour} h–${hour+1} h : ${day.has_log?`${count} détections`:'aucun journal disponible'}`;
      cell.type='button'; cell.title=detail; cell.setAttribute('aria-label',detail);
      cell.addEventListener('click',()=>{ $('heat-detail').textContent=detail; });
      cells.push(cell);
    });
  }
  $('heatmap').replaceChildren(...cells);
  const maxHours=Math.max(1,...trends.hours);
  $('period-hours').replaceChildren(...trends.hours.map((count,hour)=>{
    const button=element('button',undefined,'bar hour-bar');
    const detail=`${hour} h–${hour+1} h : ${count} détections sur ${trends.period} jours`;
    button.type='button'; button.style.setProperty('--height',`${count/maxHours*100}%`);
    button.setAttribute('aria-label',detail); button.title=detail;
    button.addEventListener('click',()=>{ $('hours-detail').textContent=detail; });
    return button;
  }));
}

let audioSignature = null;
let renderedDate = null;
async function refresh() {
  const current = ++request;
  const date = $('date').value;
  if (!date) return;
  $('status').textContent = 'Actualisation du journal…';
  try {
    const response = await fetch(`/api/dashboard?date=${encodeURIComponent(date)}&period=${period}`,{cache:'no-store'});
    if (response.status === 401) { window.location.replace('/login'); return; }
    if (!response.ok) throw new Error('HTTP '+response.status);
    const data = await response.json();
    if (current !== request) return;
    renderTrends(data.trends);
    const s = data.summary;
    $('detections').textContent = s.detections;
    $('sessions').textContent = s.sessions;
    $('duration').textContent = duration(s.seconds);
    $('count').textContent = s.recordings;
    $('audio-count').textContent = `${s.recordings} fichier${s.recordings===1?'':'s'}`;
    const max = Math.max(1,...s.hours);
    $('chart').replaceChildren(...s.hours.map((count,hour) => {
      const bar = element('div',undefined,'bar');
      bar.style.setProperty('--height',`${count/max*100}%`);
      bar.tabIndex = 0;
      bar.setAttribute('aria-label',`${hour} h : ${count} détections`);
      bar.append(element('span',`${hour} h · ${count}`));
      return bar;
    }));
    $('chart').setAttribute('aria-label',`Détections par heure : ${s.hours.map((n,h)=>`${h} h : ${n}`).join(', ')}`);
    $('activity-note').textContent = s.detections ? `${s.detections} détections au fil de la journée.` : 'Aucune détection pour cette journée.';
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
        const row = element('article',undefined,'recording');
        row.dataset.name = recording.name;
        const label = element('div');
        label.append(element('strong',recording.time),element('small',`${duration(recording.duration)} d’audio`));
        const audio = document.createElement('audio');
        audio.controls = true; audio.preload = 'none'; audio.src = recording.url;
        audio.setAttribute('aria-label',`Enregistrement de ${recording.time}`);
        audio.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{if(other!==audio) other.pause();}));
        const download = element('a','Télécharger ↓','download');
        download.href = recording.url; download.download = recording.name;
        row.append(label,audio,download); container.prepend(row);
      }
      if (!data.recordings.length) container.append(element('p','Aucun enregistrement ce jour-là. Les prochains apparaîtront ici automatiquement.','empty'));
      audioSignature = signature;
      renderedDate = date;
    }
    $('history').replaceChildren(...data.days.map(day=>{
      const button = element('button',undefined,'day');
      button.type='button'; button.setAttribute('aria-pressed',String(day.date===date));
      button.append(element('span',formatDate(day.date)),element('small',`${day.detections} détections · ${day.recordings} audio`));
      button.addEventListener('click',()=>{ $('date').value=day.date; refresh(); });
      return button;
    }));
    if (!data.days.length) $('history').append(element('p','Votre historique apparaîtra après les premières détections.','muted'));
    $('status').textContent = `Mis à jour à ${new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}`;
  } catch (error) {
    if (current === request) $('status').textContent = 'Journal indisponible. Vérifiez la connexion au serveur, puis actualisez.';
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

$('logout').addEventListener('click',async()=>{const response=await fetch('/api/logout',{method:'POST'});if(response.ok) window.location.replace('/login');});
