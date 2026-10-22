import {fieldMarkings} from './pitch.mjs';
import {offsideAt} from './model.mjs';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=s=>String(s??'').replaceAll('_',' ');
const person=(match,id)=>match.players[id]?.name.replace(' Player ',' #')||'Player';
const team=(match,id)=>match.metadata.teams.find(t=>t.team_id===id)?.name||'Team';
export function offsideReview(frame,match){
  const attacker=frame.positions[frame.offenderId],direction=frame.decision.contact.direction;
  const x=Math.max(0,Math.min(105,frame.lineX)),left=direction===1?x:0,width=direction===1?105-x:x;
  const markers=Object.entries(frame.positions).map(([id,p])=>`<g><circle cx="${p.x_m}" cy="${68-p.y_m}" r="${id===frame.offenderId?2.2:1.3}" fill="${id===frame.offenderId?'#ff769d':match.players[id]?.team_id==='home'?'#d4f77d':'#b7a0ed'}" stroke="${id===frame.offenderId?'#fff1dc':'#193329'}" stroke-width=".25"><title>${esc(person(match,id))}</title></circle>${id===frame.offenderId?`<circle cx="${p.x_m}" cy="${68-p.y_m}" r="3.3" fill="none" stroke="#ff769d" stroke-width=".35"/>`:''}</g>`).join('');
  return `<div class="offside-review"><div class="review-heading"><span>FROZEN AT TEAMMATE CONTACT</span><b>${Number(frame.marginM).toFixed(2)} m beyond limit</b></div><svg viewBox="-3 -3 111 74" role="img" aria-label="Frozen offside evidence at teammate contact"><rect width="105" height="68" fill="#14382f"/><rect x="${left}" width="${width}" height="68" fill="#ff568d" opacity=".13"/>${fieldMarkings()}<line class="offside-limit" x1="${frame.lineX}" x2="${frame.lineX}" y1="0" y2="68" stroke="#ff799e" stroke-width=".65"/><line x1="${frame.secondLastOpponentX}" x2="${frame.secondLastOpponentX}" y1="0" y2="68" stroke="#6ee7ff" stroke-width=".3" stroke-dasharray="1 1"/><line class="margin-line" x1="${frame.lineX}" x2="${attacker.x_m}" y1="${68-attacker.y_m}" y2="${68-attacker.y_m}" stroke="#fff0bb" stroke-width=".65"/>${markers}<circle cx="${frame.ball.x_m}" cy="${68-frame.ball.y_m}" r=".85" fill="white"/></svg><div class="review-legend"><span><i class="coral-key"></i>Offside limit</span><span><i class="cyan-key"></i>Second-last opponent</span></div><p>${esc(person(match,frame.offenderId))} is highlighted. ${esc(person(match,frame.secondLastOpponentId))} is the second-last opponent. ${esc(frame.label)}.</p></div>`;
}
export function decisionView(match,state,formatClock){
  const e=state.event,kind=state.kind,award=state.award,stamp=state.result||state.restart||e;
  let title=kind==='penalty'?'Penalty awarded':kind==='offside'?'Offside':'Foul committed';
  let status=state.stop?'PLAY STOPPED':'REFEREE DECISION';
  if(state.stage==='advantage'){status='PLAY CONTINUES';title=state.advantage.outcome==='played'?'Advantage played':state.advantage.outcome==='recalled'?'Advantage recalled':'Advantage being assessed';}
  if(state.stage==='ready'){status='RESTART READY';title=kind==='penalty'?'One taker. One keeper.':label(award?.type);}
  if(state.stage==='flight'){status='LIVE PENALTY';title='Penalty in flight';}
  if(state.result){status='PENALTY RESULT';title=state.result.outcome==='goal'?'Penalty scored':state.result.outcome_reason==='saved'?'Penalty saved':'Penalty missed';}
  const details=kind==='offside'?`${esc(person(match,e.player_id))} · ${esc(team(match,e.team_id))}<br>Offside involvement: ${esc(label(e.involvement))}.`:`<strong>${esc(person(match,e.player_id))}</strong> fouled ${esc(person(match,e.victim_id))}.`;
  const restart=state.stage==='advantage'?(state.advantage.outcome==='played'?'Advantage taken. No free kick has been given.':'The referee is assessing the continuation.'):`${esc(label(award?.type))} for <strong>${esc(team(match,award?.team_id))}</strong>${state.spot?` at (${Number(state.spot.x_m).toFixed(1)}, ${Number(state.spot.y_m).toFixed(1)}) m`:''}.`;
  const frame=kind==='offside'?offsideAt(match,e.t,{eventId:e.event_id,lifetimeMs:Infinity}):null;
  const cards=match.events.filter(x=>x.t<=state.asOf&&x.foul_event_id===e.event_id&&['card','dismissal'].includes(x.type));
  const discipline=cards.length?`<div class="decision-card-badges">${cards.map(c=>`<span class="sanction ${c.type==='dismissal'||c.card==='red'?'red':'yellow'}">${c.type==='dismissal'?'SENT OFF':esc(label(c.card))+' CARD'}</span>`).join('')}</div>`:'';
  return `<div class="decision-kicker"><span>${kind==='penalty'?'◎':kind==='offside'?'⚑':'!'} ${status}</span><time>${esc(formatClock(stamp.t,stamp.period))}</time></div><h2>${esc(title)}</h2><p class="decision-who">${details}</p>${discipline}<p class="decision-restart">${restart}</p>${kind==='penalty'?`<div class="penalty-callout"><b>11 m</b><span>Penalty spot · ${state.takerId?esc(person(match,state.takerId)):'Taker not yet at the spot'}${state.keeperId?'<br>Keeper: '+esc(person(match,state.keeperId)):''}</span></div>`:''}${frame?offsideReview(frame,match):''}<div class="decision-source">SOURCE ${esc(e.event_id)} · ${kind==='offside'?'WHISTLE TIME':'RECORDED EVENT'}</div>`;
}
export function decisionGraphics(match,state){
  if(!state)return '';
  const at=state.location,spot=state.spot,color=state.kind==='penalty'?'#ff74b8':state.kind==='offside'?'#6ee7ff':'#ffc06b';
  let svg=at?`<g class="offence-marker" transform="translate(${at.x_m} ${68-at.y_m})"><circle r="3.8" fill="${color}" opacity=".12"/><circle r="2.6" fill="none" stroke="${color}" stroke-width=".35"/><path d="M-1 0H1M0-1V1" stroke="${color}" stroke-width=".3"/></g>`:'';
  if(spot&&state.stop&&!state.resume)svg+=`<circle cx="${spot.x_m}" cy="${68-spot.y_m}" r="1.1" fill="${color}"/><circle cx="${spot.x_m}" cy="${68-spot.y_m}" r="9.15" fill="none" stroke="${color}" stroke-opacity=".4" stroke-width=".2" stroke-dasharray="1 1"/>`;
  if(state.kind==='penalty'&&spot&&!state.result){
    const goalX=spot.x_m<52.5?0:105;
    svg+=`<path d="M${spot.x_m} ${68-spot.y_m}L${goalX} 30.34V37.66Z" fill="#ff76bb" opacity=".14"/><rect x="${goalX===0?0:88.5}" y="13.84" width="16.5" height="40.32" fill="#ff76bb" opacity=".045" stroke="#ff91c8" stroke-width=".3"/><line x1="${goalX}" x2="${goalX}" y1="30.34" y2="37.66" stroke="#fff4b6" stroke-width=".7"/>`;
  }
  return svg;
}
