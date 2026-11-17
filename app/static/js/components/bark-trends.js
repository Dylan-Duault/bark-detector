import {element, duration, extracts, formatDate} from '../shared/format.js';

export class BarkTrends extends HTMLElement {
  update(data) {
    const $ = id => this.querySelector(`#${id}`);
const trends = data;

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
}
customElements.define('bark-trends', BarkTrends);
