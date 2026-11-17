const $ = id => document.getElementById(id);
let paused = false;
let current = 0;
async function refresh() {
  const version = ++current;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`/api/logs?source=${encodeURIComponent($('source').value)}`, {cache:'no-store', signal:controller.signal});
    if (response.status === 401) { window.location.replace('/login?expired=1'); return; }
    if (!response.ok) throw new Error();
    const data = await response.json();
    if (version !== current) return;
    $('log-output').textContent = data.entries.map(entry => `${new Date(entry.timestamp * 1000).toLocaleString('fr-FR')}  ${entry.message}`).join('\n') || 'Aucune ligne disponible pour ce service.';
    if ($('follow').checked) $('log-output').scrollTop = $('log-output').scrollHeight;
    $('log-status').textContent = `${paused ? 'En pause · ' : 'En direct · '}Mis à jour à ${new Date().toLocaleTimeString('fr-FR')}`;
  } catch {
    if (version === current) $('log-status').textContent = 'Logs indisponibles. Nouvelle tentative à la prochaine actualisation.';
  } finally { clearTimeout(timeout); }
}
$('pause').addEventListener('click', () => {
  paused = !paused;
  ++current;
  $('pause').textContent = paused ? 'Reprendre' : 'Mettre en pause';
  $('pause').setAttribute('aria-pressed', String(paused));
  $('log-status').textContent = paused ? 'Actualisation en pause.' : 'Reprise…';
  if (!paused) refresh();
});
$('source').addEventListener('change', refresh);
$('refresh').addEventListener('click', refresh);
setInterval(() => { if (!paused && !document.hidden) refresh(); }, 2000);
refresh();
