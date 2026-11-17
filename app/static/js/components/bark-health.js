
export class BarkHealth extends HTMLElement {
  update(data) {
    const $ = id => this.querySelector(`#${id}`);
const detector = data;

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
}
customElements.define('bark-health', BarkHealth);
