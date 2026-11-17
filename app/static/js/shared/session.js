import {api} from './http.js';

document.getElementById('logout')?.addEventListener('click', async () => {
  try {
    await api('/api/logout', {method: 'POST'});
    window.location.replace('/login');
  } catch {
    const status = document.getElementById('status') || document.getElementById('log-status');
    if (status) status.textContent = 'Déconnexion impossible. Vérifiez votre connexion, puis réessayez.';
  }
});
