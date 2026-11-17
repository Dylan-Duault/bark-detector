import {api} from './shared/http.js';

const form=document.getElementById('login-form');
const button=document.getElementById('login-button');
const message=document.getElementById('login-message');
const pin=document.getElementById('pin');
let timer;
if (new URLSearchParams(window.location.search).has('expired')) message.textContent='Votre session a expiré. Saisissez votre code pour vous reconnecter.';
function wait(seconds, reason) {
  const deadline=Date.now()+seconds*1000;
  clearInterval(timer);
  function tick() {
    const left=Math.max(0,Math.ceil((deadline-Date.now())/1000));
    button.disabled=left>0;
    message.textContent=left?`${reason} Réessayez dans ${left} s.`:'Vous pouvez saisir votre code à nouveau.';
    if (!left) { clearInterval(timer); pin.focus(); }
  }
  tick(); timer=setInterval(tick,250);
}
form.addEventListener('submit',async event=>{
  event.preventDefault();
  if (button.disabled) return;
  button.disabled=true; message.textContent='Vérification…';
  try {
    await api('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({pin:pin.value})});
    window.location.replace('/');
    return;
  } catch(error) {
    pin.value='';
    if (error.data?.retry_after) {
      wait(error.data.retry_after, error.status === 401 ? 'Code incorrect.' : 'Veuillez patienter.');
      return;
    }
    message.textContent=error.data?.error || 'Connexion au Pi impossible. Vérifiez votre réseau, puis réessayez.';
  }
  button.disabled=false;
});
