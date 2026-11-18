import {api} from './shared/http.js';
import './shared/session.js';

const connect = document.getElementById('direct-connect');
const speak = document.getElementById('direct-talk');
const speakerStatus = document.getElementById('direct-speaker');
const retrySpeaker = document.getElementById('direct-speaker-retry');
const monitor = document.getElementById('direct-monitor');
const status = document.getElementById('direct-status');
const audio = document.getElementById('direct-audio');
const play = document.getElementById('direct-play');
let session;
let press;
let micReady = false;

function show(message, state = 'unknown') {
  status.textContent = message;
  status.dataset.state = state;
}

function showListening() {
  show(micReady ? 'Écoute en direct' : 'En attente du micro du détecteur', micReady ? 'listening' : 'unknown');
}

function release(updateStatus = true) {
  if (!press) return;
  const current = press;
  press = undefined;
  clearInterval(current.heartbeat);
  clearTimeout(current.voiceTimeout);
  if (session?.microphoneTrack) session.microphoneTrack.enabled = false;
  if (session?.channel.readyState === 'open') session.channel.send('release');
  speak.setAttribute('aria-pressed', 'false');
  audio.muted = false;
  if (updateStatus) showListening();
}

function disconnect(message = 'Hors ligne', state = 'unknown') {
  const current = session;
  release(false);
  session = undefined;
  if (current) {
    clearTimeout(current.timeout);
    clearInterval(current.heartbeat);
    current.abort.abort();
    current.microphoneTrack?.stop();
    if (current.channel?.readyState === 'open') current.channel.send('close');
    current.pc?.close();
  }
  audio.srcObject = null;
  play.hidden = true;
  speak.disabled = true;
  speakerStatus.hidden = true;
  retrySpeaker.hidden = true;
  micReady = false;
  connect.textContent = 'Écouter la maison';
  show(message, state);
}

async function playAudio() {
  try {
    await audio.play();
    play.hidden = true;
  } catch {
    play.hidden = !audio.srcObject;
  }
}

function syncMonitor() {
  if (session?.channel.readyState !== 'open') return;
  session.channel.send(monitor.checked ? 'monitor-on' : 'monitor-off');
  audio.muted = Boolean(press) && !monitor.checked;
}

function prepareSpeaker() {
  if (session?.channel.readyState !== 'open') return;
  speak.disabled = true;
  retrySpeaker.hidden = true;
  speakerStatus.hidden = false;
  speakerStatus.textContent = 'Connexion à l’enceinte…';
  session.channel.send('prepare-speaker');
}

function gatherCandidates(pc, signal) {
  if (pc.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve, reject) => {
    // Some networks silently drop STUN or TURN requests. Use the candidates
    // already collected if another transport is still waiting for a reply.
    const timeout = setTimeout(() => finish(), 12000);
    function finish(error) {
      clearTimeout(timeout);
      pc.removeEventListener('icegatheringstatechange', changed);
      signal.removeEventListener('abort', aborted);
      if (error) reject(error);
      else resolve();
    }
    const changed = () => {
      if (pc.iceGatheringState === 'complete') finish();
    };
    const aborted = () => finish(signal.reason);
    if (signal.aborted) {
      aborted();
      return;
    }
    pc.addEventListener('icegatheringstatechange', changed);
    signal.addEventListener('abort', aborted, {once: true});
  });
}

async function open() {
  if (!window.RTCPeerConnection) {
    show('Ce navigateur ne prend pas en charge le direct.', 'error');
    return;
  }
  const current = session = {abort: new AbortController()};
  const signal = current.abort.signal;
  const connectionError = message => {
    const detail = current.hasRelay === false ? ' Aucun relais TURN n’est configuré.' : '';
    disconnect(message + detail, 'error');
  };
  current.timeout = setTimeout(() => {
    connectionError('Connexion audio impossible.');
  }, 40000);
  connect.textContent = 'Arrêter le direct';
  show('Connexion à la maison…');
  try {
    const {iceServers} = await api('/api/live/configuration', {method: 'POST', signal});
    if (session !== current) return;
    current.hasRelay = iceServers.some(({urls}) => [urls].flat().some(url => /^turns?:/i.test(url)));
    show('Recherche d’un chemin pour le son…');
    const pc = current.pc = new RTCPeerConnection({iceServers, bundlePolicy: 'max-bundle'});
    current.sender = pc.addTransceiver('audio', {direction: 'sendrecv'}).sender;
    const channel = current.channel = pc.createDataChannel('direct');
    channel.onopen = () => {
      if (session !== current) return;
      clearTimeout(current.timeout);
      const ping = () => {
        if (channel.readyState === 'open') channel.send('ping');
      };
      ping();
      current.heartbeat = setInterval(ping, 3000);
      showListening();
      syncMonitor();
      prepareSpeaker();
    };
    channel.onclose = () => {
      if (session === current) disconnect('Le direct a pris fin.');
    };
    channel.onmessage = ({data}) => {
      if (session !== current) return;
      if (data === 'mic-ready' || data === 'mic-missing') {
        micReady = data === 'mic-ready';
        if (!press) showListening();
      } else if (data === 'speaker-error') {
        release();
        speak.disabled = true;
        speakerStatus.textContent = 'Enceinte indisponible. Vérifie qu’elle est allumée.';
        retrySpeaker.hidden = false;
      } else if (data === 'speaker-ready') {
        speakerStatus.textContent = 'Enceinte connectée';
        speak.disabled = !navigator.mediaDevices?.getUserMedia;
      } else if (press && current.microphoneTrack && data === 'talking') {
        current.microphoneTrack.enabled = true;
        show('Micro ouvert. Tu peux parler.');
        press.voiceTimeout = setTimeout(() => {
          show('Aucun son reçu du micro de ton appareil.', 'error');
        }, 2200);
      } else if (press && data === 'voice-sent') {
        clearTimeout(press.voiceTimeout);
        show('Son envoyé à l’enceinte', 'listening');
      }
    };
    pc.ontrack = ({track}) => {
      audio.srcObject = new MediaStream([track]);
      playAudio();
    };
    pc.onconnectionstatechange = () => {
      if (session === current && ['failed', 'disconnected', 'closed'].includes(pc.connectionState)) {
        if (channel.readyState === 'connecting') connectionError('Connexion audio impossible.');
        else disconnect('Connexion audio interrompue.', 'error');
      }
    };
    await pc.setLocalDescription(await pc.createOffer());
    await gatherCandidates(pc, signal);
    if (session !== current) return;
    show('Connexion audio à la maison…');
    const answer = await api('/api/live/offer', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(pc.localDescription), signal, timeout: 20000,
    });
    if (session === current) await pc.setRemoteDescription(answer);
  } catch (error) {
    if (session === current) disconnect(error.status ? error.message : 'Impossible de démarrer le direct.', 'error');
  }
}

async function prepareMicrophone(current) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {echoCancellation: true, noiseSuppression: true},
  });
  const [track] = stream.getAudioTracks();
  if (session !== current || document.hidden) {
    track.stop();
    return;
  }
  track.enabled = false;
  try {
    await current.sender.replaceTrack(track);
    if (session === current && !document.hidden) current.microphoneTrack = track;
    else track.stop();
  } catch (error) {
    track.stop();
    throw error;
  }
}

async function hold() {
  const current = session;
  if (speak.disabled || press || current?.channel.readyState !== 'open') return;
  const active = press = {};
  speak.setAttribute('aria-pressed', 'true');
  try {
    if (current.microphoneTrack?.readyState !== 'live') {
      current.microphoneRequest ??= prepareMicrophone(current).finally(() => {
        current.microphoneRequest = undefined;
      });
      await current.microphoneRequest;
    }
    if (press !== active || current.microphoneTrack?.readyState !== 'live') return;
    audio.muted = !monitor.checked;
    current.channel.send('press');
    active.heartbeat = setInterval(() => {
      if (current.channel.readyState === 'open') current.channel.send('hold');
    }, 400);
  } catch {
    if (press === active) {
      release(false);
      show('Impossible d’accéder au micro de ton appareil.', 'error');
    }
  }
}

if (!navigator.mediaDevices?.getUserMedia) {
  document.getElementById('direct-help').textContent = 'Pour parler, ouvre cette page en HTTPS.';
}
connect.addEventListener('click', () => session ? disconnect() : open());
play.addEventListener('click', playAudio);
retrySpeaker.addEventListener('click', prepareSpeaker);
monitor.addEventListener('change', syncMonitor);
speak.addEventListener('pointerdown', event => {
  if (!event.isPrimary || event.button !== 0 || speak.disabled) return;
  event.preventDefault();
  speak.setPointerCapture(event.pointerId);
  hold();
});
for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
  speak.addEventListener(event, pointer => {
    if (pointer.isPrimary) release();
  });
}
speak.addEventListener('blur', () => release());
for (const event of ['contextmenu', 'selectstart', 'dragstart']) {
  speak.addEventListener(event, action => action.preventDefault());
}
speak.addEventListener('keydown', event => {
  if (event.code !== 'Space') return;
  event.preventDefault();
  if (!event.repeat) hold();
});
speak.addEventListener('keyup', event => {
  if (event.code === 'Space') release();
});
window.addEventListener('blur', () => release());
window.addEventListener('pagehide', () => disconnect());
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  release();
  session?.microphoneTrack?.stop();
});
