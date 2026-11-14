const form=document.getElementById('login-form');
const button=document.getElementById('login-button');
const message=document.getElementById('login-message');
const pin=document.getElementById('pin');
let timer;
function wait(seconds) {
  const deadline=Date.now()+seconds*1000;
  clearInterval(timer);
  function tick() {
    const left=Math.max(0,Math.ceil((deadline-Date.now())/1000));
    button.disabled=left>0;
    message.textContent=left?`Nouvelle tentative dans ${left} s.`:'Vous pouvez réessayer.';
    if (!left) { clearInterval(timer); pin.focus(); }
  }
  tick(); timer=setInterval(tick,250);
}
form.addEventListener('submit',async event=>{
  event.preventDefault();
  if (button.disabled) return;
  button.disabled=true; message.textContent='Vérification…';
  try {
    const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:pin.value})});
    const data=await response.json();
    if (response.ok) { window.location.replace('/'); return; }
    pin.value='';
    if (data.retry_after) { wait(data.retry_after); return; }
    message.textContent=data.error || 'Connexion impossible.';
  } catch(error) { message.textContent='Serveur indisponible. Réessayez dans un instant.'; }
  button.disabled=false;
});
