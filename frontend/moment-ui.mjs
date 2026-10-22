const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names=(m,id)=>m.players[id]?.name.replace(' Player ',' #')||'Player';
const team=(m,id)=>m.metadata.teams.find(t=>t.team_id===id)?.name||'Team';
const positions={GK:'Goalkeeper',FB:'Full-back',CB:'Centre-back',DM:'Defensive midfielder',CM:'Central midfielder',AM:'Attacking midfielder',W:'Winger',ST:'Striker',DF:'Defender',MF:'Midfielder',FW:'Forward'};
function position(match,event,id){const p=match.players[id];const code=event.position_group||p?.position_group||p?.role;return code?(positions[code]||code)+' · '+code:'Position unavailable';}
export function substitutionRows(match,events,formatClock,{compact=false}={}){
  return `<div class="substitution-list ${compact?'compact':''}">${events.map(e=>{
    const on=match.players[e.player_on_id],off=match.players[e.player_off_id];
    return `<article class="substitution-pair"><div class="substitution-meta"><b>${esc(team(match,e.team_id))}</b><time>${esc(formatClock(e.t,e.period))}${e.halftime?' · HALF-TIME':''}</time></div><div class="substitution-player incoming"><span class="sub-direction">↗<small>ON</small></span><span class="shirt-number">${esc(on?.shirt_number??'—')}</span><div><strong>${esc(names(match,e.player_on_id))}</strong><small>${esc(position(match,e,e.player_on_id))}</small></div></div><div class="substitution-player outgoing"><span class="sub-direction">↙<small>OFF</small></span><span class="shirt-number">${esc(off?.shirt_number??'—')}</span><div><strong>${esc(names(match,e.player_off_id))}</strong><small>${esc(position(match,e,e.player_off_id))}</small></div></div></article>`;
  }).join('')}</div>`;
}
export function momentView(match,state,formatClock){
  const e=state.event,stamp=esc(formatClock(e.t,e.period)),source=`<div class="decision-source">SOURCE ${esc(state.kind==='substitution'?state.substitutions.map(s=>s.event_id).join(' · '):e.event_id)} · RECORDED ${state.kind==='substitution'?'LINEUP CHANGE':'OUTCOME'}</div>`;
  if(state.kind==='substitution')return `<div class="decision-kicker"><span>⇆ SUBSTITUTION${state.substitutions.length>1?'S':''}</span><time>${stamp}</time></div><h2>Fresh legs on the pitch.</h2>${substitutionRows(match,state.substitutions,formatClock)}${source}`;
  const goal=state.kind==='goal',saved=state.kind==='saved',headline=goal?'GOALLLLLL':saved?'SAVED':'MISS';
  const detail=goal?`${esc(names(match,e.player_id))} scores for <strong>${esc(team(match,e.team_id))}</strong>.`:saved?`<strong>${esc(names(match,e.goalkeeper_id))}</strong> saves ${esc(names(match,e.player_id))}’s penalty.`:`${esc(names(match,e.player_id))}’s penalty is off target.`;
  const score=goal&&e.score?`<div class="goal-score"><span>${esc(team(match,'home'))}</span><strong>${Number(e.score.home)} <em>:</em> ${Number(e.score.away)}</strong><span>${esc(team(match,'away'))}</span></div>`:'';
  const stream=goal?'<div class="goal-streamers" aria-hidden="true">'+Array.from({length:12},(_,i)=>`<i style="--n:${i}"></i>`).join('')+'</div>':'';
  const annotation=saved?(e.save_outcome==='parry'?'Parried away · follow the recorded rebound.':e.save_outcome==='hold'?'Held by the goalkeeper.':'Goalkeeper save recorded.'):'Off target · no goal.';
  return `${stream}<div class="decision-kicker"><span>${goal?'⚽ GOAL':saved?'◎ PENALTY SAVE':'↗ PENALTY OFF TARGET'}</span><time>${stamp}</time></div><h2 class="moment-headline">${headline}</h2><p class="decision-who">${detail}</p>${score}${state.substitutions?.length?'<div class="attached-subs"><h3>Changes during this stoppage</h3>'+substitutionRows(match,state.substitutions,formatClock,{compact:true})+'</div>':''}${goal?'':`<p class="moment-detail">${esc(annotation)}</p>`}${source}`;
}
