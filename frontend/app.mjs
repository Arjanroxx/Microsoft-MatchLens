import {prepare,statistics,boardAt,mean,eventTitle,clockAt,actionTypes,disciplineAt,offsideAt} from './model.mjs';
import {decisionAt,nextDecision} from './decisions.mjs';
import {decisionView,decisionGraphics,offsideReview} from './decision-ui.mjs';
import {fieldMarkings} from './pitch.mjs';
import {momentAt,nextMoment,nextPause,presentationAt} from './moments.mjs';
import {momentView,substitutionRows} from './moment-ui.mjs';
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,n=0)=>v==null?'—':Number(v).toFixed(n), clock=t=>`${String(Math.floor(t/60000)).padStart(2,'0')}:${String(Math.floor(t/1000)%60).padStart(2,'0')}`;
let match,time=0,playing=false,speed=4,tab='events',filter='all',selectedEvent=null,selectedPlayer=null,trails=true,names=false,smooth=!(globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches??false),lastFrame=0,lastUI=0,lastPrefix=-1;
let pauseDecisions=true,dismissedDecisionId=null,activeDecision=null,activePresentation=null,decisionKey='',sampleRequest=0;
const teamName=id=>match?.metadata.teams.find(t=>t.team_id===id)?.name||'', playerName=id=>match?.players[id]?.name||'Team event';
const eventPlayer=e=>e.type==='substitution'?playerName(e.player_off_id)+' → '+playerName(e.player_on_id):playerName(e.player_id);
const title=eventTitle;
const displayClock=(t,period)=>['1.5','1.6','1.7','1.8'].includes(match?.metadata.schema_version)?clockAt(match,t,period).display:clock(t);
const symbol=e=>({foul:'!',offside:'⚑',card:'▮',dismissal:'▮',pass:'↗',shot:'◎',goal:'⚽',recovery:'↶',turnover:'⇄',pressure:'⌁',restart:'▶',period_start:'◷',period_end:'◷',substitution:'⇆',stoppage:'Ⅱ',resume:'▶'}[e.type]||'·');
function notify(msg){$('status').textContent=msg;$('status').classList.add('show');clearTimeout(notify.timer);notify.timer=setTimeout(()=>$('status').classList.remove('show'),5500);}
function showModal(titleText,html,label='MATCHLENS STUDIO'){$('modal-label').textContent=label;$('modal-body').innerHTML=`<h2>${esc(titleText)}</h2>${html}`;$('modal').showModal();}
function setTab(next){tab=next;for(const t of ['events','stats','evidence']){$('view-'+t).hidden=t!==tab;$('tab-'+t).classList.toggle('selected',t===tab);$('tab-'+t).setAttribute('aria-selected',String(t===tab));}document.querySelectorAll('.rail-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));}
function setTime(value){if(!match)return;if(value<time)dismissedDecisionId=null;time=Math.max(0,Math.min(match.duration,value));if(time>=match.duration)playing=false;if(selectedEvent&&selectedEvent.t>time)selectedEvent=null;lastPrefix=-1;update(true);}
function install(metadata,events){const next=prepare(metadata,events);match=next;time=0;playing=false;selectedEvent=null;selectedPlayer=null;lastPrefix=-1;dismissedDecisionId=null;decisionKey='';$('field-markings').innerHTML=fieldMarkings();
  $('home-name').textContent=teamName('home');$('away-name').textContent=teamName('away');
  $('home-short').textContent=teamName('home').replace(/ FC$/,'').toUpperCase();$('away-short').textContent=teamName('away').replace(/ FC$/,'').toUpperCase();
  document.querySelector('.crest.home').innerHTML=esc(teamName('home').slice(0,1))+'<span>FC</span>';document.querySelector('.crest.away').innerHTML=esc(teamName('away').slice(0,1))+'<span>FC</span>';
  $('seek').max=match.duration;$('half-duration').textContent=clock(metadata.period_offsets_ms?.['2']??metadata.period_duration_ms)+' · HT';$('full-duration').textContent=clock(match.duration)+' · FT';
  // Begin at kickoff. Schema 1.3 reset positions mirror simulator/PitchState.
  time=0;$('speed').value=String(speed);$('smooth').classList.toggle('active',smooth);$('smooth').setAttribute('aria-pressed',smooth);update(true);
}
function point(p){return `${p.x_m/match.metadata.pitch.length_m*105},${68-p.y_m/match.metadata.pitch.width_m*68}`;}
function xy(p){return {x:p.x_m/match.metadata.pitch.length_m*105,y:68-p.y_m/match.metadata.pitch.width_m*68};}
function renderPitch(){if(!match)return;const board=boardAt(match,time,{smooth}),a=board.action;
  renderDecision(board);
  $('position-note').textContent=match.metadata.schema_version==='1.8'?'Generated movement samples · synthetic, not camera tracking':smooth?'Smoothed snapshots · illustrative movement':'Exact state anchors · no player smoothing';
  const possessionTeam=board.carrierId?match.players[board.carrierId]?.team_id:board.active?a.team_id:null;
  $('pitch').setAttribute('data-possession',possessionTeam||'neutral');
  $('pitch').setAttribute('data-phase',board.phase);
  const pulse=smooth?Math.sin(time/260)*.18:0;
  $('players-layer').innerHTML=Object.entries(board.positions).map(([id,p])=>{
    const roster=match.players[id];if(!roster)return '';
    const booking=board.discipline[id],penalty=activeDecision?.kind==='penalty'&&!!activeDecision.restart&&!activeDecision.result,spot=activeDecision?.spot,goalX=spot?(spot.x_m<52.5?0:105):null;
    const inDuel=penalty&&(id===activeDecision.takerId||(roster.team_id!==activeDecision.award.team_id&&board.lineups.slots[id]===1));
    const {x,y}=xy(p),carrier=id===board.carrierId,color=roster.team_id==='home'?'#d4f77d':'#b7a0ed';
    const halo=carrier?'<circle class="carrier-aura" r="4.8" fill="url(#carrier-halo)"/><circle class="carrier-ring" r="'+(2.9+pulse)+'" fill="none" stroke="#ffbc73" stroke-width=".3"/><circle r="3.55" fill="none" stroke="#ffdcaa" stroke-width=".15" stroke-dasharray="1 2.5" transform="rotate('+(smooth?time/18%360:0)+')"/>':'';
    return '<g class="player '+(penalty?(inDuel?'penalty-duel ':'penalty-support '):'')+(carrier?'carrier ':'')+(selectedPlayer===id?'selected':'')+'" tabindex="0" role="button" aria-label="Inspect '+esc(roster.name)+(carrier?' · In possession':'')+'" data-player="'+esc(id)+'" transform="translate('+x+' '+y+')"><title>'+esc(roster.name)+' · '+esc(roster.role)+(carrier?' · In possession':'')+'</title>'+halo+(booking?.yellowCards?'<rect x="1.2" y="-3.8" width="1.3" height="1.8" rx=".15" fill="#ffe081"/>':'')+(selectedPlayer===id?'<circle r="3.9" fill="none" stroke="#6ee7ff" stroke-width=".25"/>':'')+'<circle class="player-body" r="'+(carrier?2.25:2.05)+'" fill="'+(carrier?'url(#carrier-fill)':color)+'"/><text y=".05">'+esc(roster.shirt_number)+'</text>'+(names?'<text class="name" y="4.6">'+esc(roster.name.replace(' Player ',' #'))+'</text>':'')+'</g>';
  }).join('');
  let lines='';
  if(trails){for(const e of match.actions){
    if(['movement','reposition'].includes(e.type))continue;
    if(e.t>time)break;
    if(time-e.t>12000||e.period!==board.period)continue;
    // Do not carry a previous phase's trails across a simulator kickoff reset.
    const reset=match.events.findLast?.(ev=>ev.t<=time&&ev.type==='restart'&&ev.reason==='kickoff');
    if(reset&&e.t<reset.t)continue;
    const opacity=Math.max(.08,1-(time-e.t)/12000),color=e.type==='shot'?'#ffd195':e.team_id==='home'?'#d4f77d':'#b7a0ed';
    lines+='<line x1="'+xy(e.start).x+'" y1="'+xy(e.start).y+'" x2="'+xy(e.end).x+'" y2="'+xy(e.end).y+'" stroke="'+color+'" stroke-width=".42" opacity="'+opacity+'" marker-end="url(#arrow)"/>';
    if(e.type==='pass'&&e.outcome!=='complete'&&e.intended_end)lines+='<line x1="'+xy(e.end).x+'" y1="'+xy(e.end).y+'" x2="'+xy(e.intended_end).x+'" y2="'+xy(e.intended_end).y+'" stroke="'+color+'" opacity="'+opacity*.4+'" stroke-width=".25" stroke-dasharray="1 1"/>';
  }
  if(board.active&&board.ball&&a){
    // Partial trail ends at the current sampled ball location, never at a future outcome.
    lines+='<line x1="'+xy(a.start).x+'" y1="'+xy(a.start).y+'" x2="'+xy(board.ball).x+'" y2="'+xy(board.ball).y+'" stroke="#ffbc73" stroke-width="1.1" opacity=".12"/><line x1="'+xy(a.start).x+'" y1="'+xy(a.start).y+'" x2="'+xy(board.ball).x+'" y2="'+xy(board.ball).y+'" stroke="#fff1c1" stroke-width=".32" opacity=".85"/>';
  }}
  $('trail-layer').innerHTML=lines;
  if(board.ball){const {x,y}=xy(board.ball);$('ball-layer').innerHTML='<circle cx="'+x+'" cy="'+y+'" r="2" fill="url(#carrier-halo)" opacity=".85"/><circle cx="'+x+'" cy="'+y+'" r=".7" fill="#fffbe8" stroke="#6b512f" stroke-width=".15"/>';}else $('ball-layer').innerHTML='';
  let message='Waiting for the first player snapshot';
  if(activeDecision?.kind==='penalty'&&activeDecision.stage==='ready')message='Penalty setup · paused at recorded kick time';
  else if(board.active&&a.type==='reposition')message='Players repositioning · '+a.reason.replaceAll('_',' ');
  else if(board.active)message=playerName(a.carrier_id||a.player_id).replace(' Player ',' #')+(['carry','movement'].includes(a.type)?' · Carrying the ball':' · Ball in flight');
  else if(board.carrierId)message=playerName(board.carrierId).replace(' Player ',' #')+' · In possession';
  else if(board.lastVisibleEvent)message=title(board.lastVisibleEvent);
  const toast=$('action-toast');
  if(toast.lastElementChild.textContent!==message){
    toast.lastElementChild.textContent=message;
    if(smooth)toast.animate?.([{opacity:.55,translate:'0 3px'},{opacity:1,translate:'0 0'}],{duration:180,easing:'ease-out'});
  }
}
function eventMarkup(e){return `<button class="event ${selectedEvent?.event_id===e.event_id?'selected':''}" data-event="${esc(e.event_id)}"><span class="event-icon ${['foul','offside'].includes(e.type)?'decision-event '+(e.restart?.type==='penalty'?'penalty':e.type):''} ${e.team_id==='away'?'away':''}">${symbol(e)}</span><span class="event-info"><span class="event-title"><span>${esc(title(e))}</span><time>${displayClock(e.t,e.period)}</time></span><p>${esc(eventPlayer(e).replace(' Player ',' #'))}</p>${e.type==='pass'?`<small>${fmt(e.distance_m,1)} m <span>·</span> ${esc(e.pass_difficulty?.rating||'')} difficulty</small>`:e.type==='shot'?`<small>${fmt(e.shot_speed?.kmh,1)} km/h initial speed</small>`:''}</span></button>`;}
function renderFeed(past){const visible=past.filter(e=>!['ball_release','time_lost','ball_placement','movement','reposition'].includes(e.type)).filter(e=>filter==='all'||(filter==='pass'?e.type==='pass':['shot','goal','recovery','turnover','save','parry','clearance','ball_out','restart','substitution','added_time','tackle','foul','card','dismissal','advantage','goalkeeper_change','match_abandoned','offside','deflection','opponent_touch'].includes(e.type))).slice(-80).reverse();$('feed').innerHTML=visible.length?visible.map(eventMarkup).join(''):'<div class="empty-state"><span>◷</span><h4>The story is about to start.</h4><p>Press play to follow the match.<br>Events appear only after they happen.</p></div>';$('event-count').textContent=past.length;}
function renderStats(s){const h=s.teams.home,a=s.teams.away;
  const tiles=[['Pass accuracy',fmt(h.accuracy)+'%',fmt(a.accuracy)+'%','completed / attempted'],['Shots',h.shots,a.shots,'completed shot actions'],['Recoveries',h.recoveries,a.recoveries,'possession won'],['Pass speed',fmt(mean(h.speed),1),fmt(mean(a.speed),1),'mean flight speed · km/h']];
  $('stat-tiles').innerHTML=tiles.map(([name,v1,v2,note])=>`<div class="stat-tile"><span>${name}</span><div class="stat-values"><span class="home-value">${v1==='—%'?'—':v1}</span><em>/</em><span class="away-value">${v2==='—%'?'—':v2}</span></div><small>${note}</small></div>`).join('');
  $('pos-home').textContent=h.possession==null?'—':fmt(h.possession)+'%';$('pos-away').textContent=a.possession==null?'—':fmt(a.possession)+'%';$('pos-bar').style.width=(h.possession??50)+'%';
  const rows=[['Goals',h.goals,a.goals],['Shots / on target',`${h.shots} / ${h.onTarget}`,`${a.shots} / ${a.onTarget}`],['Passes / completed',`${h.attempted} / ${h.completed}`,`${a.attempted} / ${a.completed}`],['Pass accuracy',h.accuracy==null?'—':fmt(h.accuracy)+'%',a.accuracy==null?'—':fmt(a.accuracy)+'%'],['Recoveries',h.recoveries,a.recoveries],['Interceptions',h.interceptions,a.interceptions],['Saves',h.saves,a.saves],['Held / parried',`${h.savesHeld} / ${h.savesParried}`,`${a.savesHeld} / ${a.savesParried}`],['Throw-ins',h.throwIns,a.throwIns],['Goal kicks',h.goalKicks,a.goalKicks],['Corners',h.corners,a.corners],['Clearances',h.clearances,a.clearances],['Rebound shots',h.reboundShots,a.reboundShots],['Tackles / won',`${h.tackles} / ${h.tacklesWon}`,`${a.tackles} / ${a.tacklesWon}`],['Offsides',h.offsides,a.offsides],['Fouls',h.fouls,a.fouls],['Yellow / red cards',`${h.yellowCards} / ${h.redCards}`,`${a.yellowCards} / ${a.redCards}`],['Free kicks',h.freeKicks,a.freeKicks],['Penalties / scored',`${h.penaltiesTaken} / ${h.penaltiesScored}`,`${a.penaltiesTaken} / ${a.penaltiesScored}`],['Pressure observations',h.pressure,a.pressure],['Mean pass distance · m',fmt(mean(h.distance),1),fmt(mean(a.distance),1)],['Mean difficulty / 100',fmt(mean(h.difficulty),1),fmt(mean(a.difficulty),1)],['Mean pass speed · km/h',fmt(mean(h.speed),1),fmt(mean(a.speed),1)],['Mean initial shot speed · km/h',fmt(mean(h.shotSpeed),1),fmt(mean(a.shotSpeed),1)]];
  $('comparison').innerHTML=rows.map(([label,v1,v2])=>`<div class="comparison-row"><div><span>${v1}</span><small>${label}</small><span>${v2}</span></div></div>`).join('');
}
const metric=(value,label)=>`<div class="metric-cell"><b>${value}</b><small>${label}</small></div>`;
function renderEvidence(){if(selectedPlayer){const p=match.players[selectedPlayer],discipline=disciplineAt(match,time)[selectedPlayer],events=match.events.filter(e=>e.t<=time&&e.player_id===selectedPlayer),passes=events.filter(e=>e.type==='pass');$('evidence').innerHTML=`<div class="evidence-card"><div class="evidence-meta">PLAYER FOCUS · ${esc(p.team_id.toUpperCase())}</div><h4>#${p.shirt_number} · ${esc(discipline.role)}</h4><p>${esc(p.name)}<br>${esc(teamName(p.team_id))}</p><div id="player-state"><p>Live ratings available when running the local UI bridge.</p></div><div class="metric-grid">${metric(passes.length,'Pass attempts')}${metric(passes.filter(e=>e.outcome==='complete').length,'Pass completions')}${metric(events.filter(e=>e.type==='shot'&&e.valid_for_statistics!==false).length,'Shots')}${metric(events.filter(e=>e.type==='recovery').length,'Recoveries')}${metric(discipline.fouls,'Fouls committed')}${metric(match.events.filter(e=>e.t<=time&&e.type==='foul'&&e.victim_id===selectedPlayer).length,'Fouls won')}${metric(events.filter(e=>e.type==='offside').length,'Offsides')}</div><p>${discipline.sentOff?'Sent off · '+esc(discipline.dismissalReason):'Yellow cards: '+discipline.yellowCards}. Actions through ${displayClock(time)}. Smooth player movement illustrates source-state anchors; it is not measured tracking.</p></div><div class="player-events"><h4>RECENT ACTIONS</h4>${events.slice(-5).reverse().map(eventMarkup).join('')||'<p class="method-note">No completed actions from this player yet.</p>'}</div>`;loadPlayerState(selectedPlayer,time);return;}
  const e=selectedEvent;if(!e){$('evidence').innerHTML='<div class="empty-state"><span>⌘</span><h4>The proof is in the play.</h4><p>Select a completed event or a player to explore its evidence.</p></div>';return;}
  const action=actionTypes.includes(e.type),decision=['foul','offside'].includes(e.type)?decisionAt(match,e.t):null,offside=offsideAt(match,time,{eventId:e.event_id,lifetimeMs:Infinity}),raw={...e};delete raw.t;delete raw.kick;delete raw.ball_trajectory;delete raw.pitch_snapshot;
  $('evidence').innerHTML=`<div class="evidence-card"><div class="evidence-meta">${esc(e.event_id)} · ${displayClock(e.t,e.period)} · HALF ${e.period}</div><h4>${esc(title(e))}</h4><p>${esc(playerName(e.player_id))}<br>${esc(teamName(e.team_id))}</p>${e.type==='offside'&&offside?offsideDiagram(offside):''}${e.type==='substitution'?substitutionRows(match,[e],displayClock):''}${e.type==='foul'&&decision?'<div class="evidence-decision">'+decisionView(match,{...decision,asOf:time},displayClock)+'</div>':''}${e.valid_for_statistics===false?'<p>Invalid attack: excluded from shot, save, goal, assist and rating credits.</p>':''}${action?`<div class="metric-grid">${metric(fmt(e.distance_m??e.ball_speed?.distance_m,1)+' m','Actual travel')}${metric(fmt(e.ball_speed?.average_kmh,1),'Mean flight · km/h')}${e.type==='pass'?metric(fmt(e.pass_difficulty?.score)+'/100','Difficulty heuristic')+metric(fmt(e.intended_distance_m,1)+' m','Intended travel'):e.type==='shot'?metric(fmt(e.shot_speed?.kmh,1),'Initial speed · km/h')+metric(fmt(e.shot_speed?.window_ms)+' ms','Initial sample window'):metric(fmt(e.ball_speed?.average_kmh,1),'Flight speed · km/h')}</div>`:''}${e.type==='pass'?`<p>Difficulty uses the intended path. Nearest defender: <strong>${fmt(e.difficulty_context?.nearest_defender_m,1)} m</strong>. Defenders in passing lane: <strong>${e.difficulty_context?.defenders_in_lane??'—'}</strong>. It is a heuristic, not a probability.</p>`:''}<details><summary>Inspect source fields ↗</summary><pre>${esc(JSON.stringify(raw,null,2))}</pre></details>${action?'<button class="button secondary" id="replay-action">↶ &nbsp; Replay this action</button>':''}</div>`;
}
function update(force=false){if(!match)return;const past=match.events.filter(e=>e.t<=time),prefix=past.length;
  $('seek').value=time;$('clock').textContent=displayClock(time);$('transport-time').textContent=clock(time)+' / '+clock(match.duration);$('period-label').textContent=clockAt(match,time).abandoned?'ABANDONED':time>=match.duration?'FULL TIME':clockAt(match,time).period===2?'SECOND HALF':'FIRST HALF';$('direction').textContent=clockAt(match,time).period===1?'HOME ATTACKING →':'← HOME ATTACKING';$('play').textContent=playing?'Ⅱ':'▶';$('play').setAttribute('aria-label',playing?'Pause replay':'Play replay');
  const s=statistics(match,time);$('home-score').textContent=s.teams.home.goals;$('away-score').textContent=s.teams.away.goals;renderStats(s);
  if(prefix!==lastPrefix||force){renderFeed(past);renderEvidence();$('timeline-markers').innerHTML=past.filter(e=>e.type==='goal').map(e=>`<i style="left:${e.t/match.duration*100}%" title="Goal ${displayClock(e.t,e.period)}"></i>`).join('');lastPrefix=prefix;}
  renderPitch();
}
function frame(now){const dt=lastFrame?Math.max(0,now-lastFrame):0;lastFrame=now;if(playing&&match){
  const target=Math.min(match.duration,time+dt*speed),decision=pauseDecisions?nextPause(match,time,target):null;
  time=decision?decision.t:target;if(decision){playing=false;dismissedDecisionId=null;}if(time===match.duration)playing=false;
  const pastCount=match.events.filter(e=>e.t<=time).length;if(now-lastUI>120||pastCount!==lastPrefix||time===match.duration||decision){update();lastUI=now;}else renderPitch();
}requestAnimationFrame(frame);}
function inspectEvent(id){const event=match.events.find(e=>e.event_id===id&&e.t<=time);if(!event)return;playing=false;selectedPlayer=null;selectedEvent=event;setTime(event.t);setTab('evidence');}
document.addEventListener('click',e=>{const event=e.target.closest('[data-event]'),player=e.target.closest('[data-player]');if(event)inspectEvent(event.dataset.event);if(player){selectedPlayer=player.dataset.player;selectedEvent=null;playing=false;setTab('evidence');update(true);}if(e.target.id==='replay-action'&&selectedEvent){const start=selectedEvent.kick;selectedEvent=null;setTime(start);playing=true;update(true);}});
$('players-layer').addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();e.target.closest('[data-player]')?.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>setTab(b.dataset.tab)));
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));lastPrefix=-1;update(true);}));
$('play').onclick=()=>{if(!match)return;if(time>=match.duration)setTime(0);playing=!playing;if(playing&&activePresentation)dismissedDecisionId=activePresentation.id;update(true);};$('restart').onclick=()=>{playing=false;setTime(0);};$('back').onclick=()=>setTime(time-10000);$('forward').onclick=()=>setTime(time+10000);$('seek').oninput=e=>setTime(+e.target.value);$('speed').onchange=e=>{speed=+e.target.value;};$('next').onclick=()=>{const next=match?.events.find(e=>e.t>time&&['pass','shot','goal'].includes(e.type));if(next){playing=false;setTime(next.t);}else notify('No more actions in this replay.');};
$('smooth').onclick=()=>{smooth=!smooth;$('smooth').classList.toggle('active',smooth);$('smooth').setAttribute('aria-pressed',smooth);renderPitch();};
$('trails').onclick=()=>{trails=!trails;$('trails').classList.toggle('active',trails);$('trails').setAttribute('aria-pressed',trails);renderPitch();};$('labels').onclick=()=>{names=!names;$('labels').classList.toggle('active',names);$('labels').setAttribute('aria-pressed',names);renderPitch();};
$('catchup').onclick=()=>{if(!match)return;const past=match.events.filter(e=>e.t<=time&&e.t>=Math.max(0,time-60000)),s=statistics(match,time),goals=past.filter(e=>e.type==='goal');const rows=['home','away'].map(team=>{const ev=past.filter(e=>e.team_id===team),passes=ev.filter(e=>e.type==='pass');return `<li><strong>${esc(teamName(team))}</strong>: ${passes.filter(e=>e.outcome==='complete').length} of ${passes.length} passes completed, ${ev.filter(e=>e.type==='shot'&&e.valid_for_statistics!==false).length} shots and ${ev.filter(e=>e.type==='recovery').length} recoveries.</li>`;}).join('');showModal('Back in the game.',`<p>From <strong>${displayClock(Math.max(0,time-60000))}</strong> to <strong>${displayClock(time)}</strong>. Current score: ${s.teams.home.goals}–${s.teams.away.goals}.</p><ul>${rows}</ul><p>${goals.length?goals.map(g=>`Goal for ${esc(teamName(g.team_id))} at ${displayClock(g.t,g.period)} (${esc(g.event_id)}).`).join('<br>'):'No goals in this window.'}</p><details><summary>Source event IDs (${past.length})</summary><pre>${esc(past.map(e=>e.event_id).join(', '))}</pre></details><p>Calculated directly from completed events. This recap uses templates; no AI model is connected.</p>`,'CATCH ME UP · LAST 60 MATCH SECONDS');};
const notes='<p>This is an <strong>original synthetic 2D simulation</strong>. It is not a real match or professional tracking feed.</p><ul><li>Smooth mode illustrates movement between exact kick/arrival state anchors; it is not measured tracking. Disable Smooth to hold player snapshots. Ball movement always follows timestamped trajectory samples.</li><li>Difficulty is a geometry heuristic, not a probability. Ball speeds are simulated pitch-plane measurements.</li><li>Schema 1.5 supports ball-out decisions, restarts, keeper holds/parries, rebounds, natural substitutions and added time. Schema 1.6 also supports challenges, fouls, advantage, free kicks, penalties and dismissals. Schema 1.7 adds contact-time point-player offside, active involvement, restart exceptions and controlled-play/deflection distinctions. Offside replay diagrams use frozen source positions and cannot establish body-part-accurate VAR decisions. xG and measured running distances are not modelled.</li><li>Scores and statistics use only completed events through your playback position. Shot records are not counted as extra goals.</li></ul>';
$('limitations').onclick=()=>showModal('A clear view of the model.',notes,'MODEL NOTES');$('about').onclick=()=>showModal('Explore a match, play by play.',`<p><strong>Play</strong> to follow the ball. Change speed or drag the timeline to inspect a moment. Click a player for their contributions, or a completed event for its evidence.</p><p><strong>Load a match</strong> accepts the simulator’s metadata.json and events.jsonl together. Files are processed locally in your browser.</p>${notes}`);$('close-modal').onclick=()=>$('modal').close();$('modal').addEventListener('click',e=>{if(e.target===$('modal')){const r=$('modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('modal').close();}});
$('import').onclick=()=>$('files').click();$('files').onchange=async e=>{++sampleRequest;try{const files=[...e.target.files],metadata=files.find(f=>f.name==='metadata.json'),events=files.find(f=>f.name==='events.jsonl');if(!metadata||!events)throw Error('Select metadata.json and events.jsonl together.');if(metadata.size+events.size>60*1024*1024)throw Error('Please use match files smaller than 60 MB combined.');install(JSON.parse(await metadata.text()),(await events.text()).split(/\r?\n/).filter(l=>l.trim()).map(l=>JSON.parse(l)));notify('Match loaded. Your files stay in this browser.');}catch(err){notify('Could not load match: '+err.message);}finally{e.target.value='';}};
document.addEventListener('keydown',e=>{if(['INPUT','BUTTON','SELECT','TEXTAREA'].includes(document.activeElement.tagName)||$('modal').open)return;if(e.code==='Space'){e.preventDefault();$('play').click();}if(e.code==='ArrowRight'){e.preventDefault();setTime(time+10000);}if(e.code==='ArrowLeft'){e.preventDefault();setTime(time-10000);}});
async function load(sample='current'){const request=++sampleRequest;const base=['offside-match','discipline-match','short-match'].includes(sample)?'./examples/'+sample:'./data';try{const [mr,er]=await Promise.all([fetch(base+'/metadata.json'),fetch(base+'/events.jsonl')]);if(!mr.ok||!er.ok)throw Error('Match fixture is unavailable.');const metadata=await mr.json(),events=(await er.text()).split(/\r?\n/).filter(l=>l.trim()).map(l=>JSON.parse(l));if(request===sampleRequest)install(metadata,events);}catch(err){notify('Unable to load sample: '+err.message);$('feed').innerHTML='<div class="empty-state"><h4>Load your match to get started.</h4><p>Choose metadata.json and events.jsonl using “Load a match”. Serve this folder over HTTP to load the included fixture.</p></div>';}}
load();requestAnimationFrame(frame);

function offsideDiagram(frame){return offsideReview(frame,match);}

let playerStateRequest=0;
async function loadPlayerState(playerId,requestedTime){
  const request=++playerStateRequest;
  try{
    const response=await fetch(`/api/state?time_ms=${Math.floor(requestedTime)}`);
    if(!response.ok)return;
    const state=await response.json();
    if(request!==playerStateRequest||selectedPlayer!==playerId||Math.floor(time)!==Math.floor(requestedTime)||state.as_of_match_time_ms!==Math.floor(requestedTime)||state.match_id!==match.metadata.match_id)return;
    const p=state.players[playerId],target=$('player-state');if(!p||!target)return;
    target.innerHTML=`<div class="metric-grid">${metric(p.rating.value==null?'NR':fmt(p.rating.value,1),'Match rating')}${metric(fmt(p.minutes_played,1),'Minutes played')}${metric(p.offsides??0,'Offsides')}${metric(p.assists,'Assists')}</div><p>${esc(p.squad_status.replaceAll('_',' '))} · ${p.rating.provisional?'Rating evolving':'Rating finalised'} · ${esc(p.rating.model)}</p><details><summary>Rating calculation and source event IDs</summary><pre>${esc(JSON.stringify(p.rating,null,2))}</pre></details>`;
  }catch{/* Static/file-import mode remains usable without a local API. */}
}

function renderDecision(board){
  activeDecision=decisionAt(match,time);
  activePresentation=presentationAt(match,time,activeDecision);
  const state=activePresentation?.primary,notice=$('decision-notice');
  const show=!!state&&dismissedDecisionId!==activePresentation.id;
  notice.hidden=!show;
  $('pitch').setAttribute('data-decision',state?.kind||'none');
  $('decision-layer').innerHTML=decisionGraphics(match,activeDecision);
  $('penalty-setup').hidden=state?.kind!=='penalty'||!!state?.result;
  if(!show){decisionKey='';return;}
  const cards=match.events.filter(e=>e.t<=time&&e.foul_event_id===state.event.event_id&&['card','dismissal'].includes(e.type)).map(e=>e.event_id).join();
  const key=activePresentation.id+':'+state.stage+':'+state.advantage?.outcome+':'+cards+':'+activePresentation.substitutions.map(e=>e.event_id).join();
  if(key!==decisionKey){
    notice.setAttribute('data-kind',state.kind);
    notice.setAttribute('data-side',(state.location?.x_m??52.5)<52.5?'right':'left');
    const isMoment=['substitution','goal','saved','miss'].includes(state.kind);
    let content=isMoment?momentView(match,state,displayClock):decisionView(match,{...state,asOf:time},displayClock);
    if(!isMoment&&activePresentation.substitutions.length)content+='<div class="attached-subs"><h3>Changes during this stoppage</h3>'+substitutionRows(match,activePresentation.substitutions,displayClock,{compact:true})+'</div>';
    $('decision-content').innerHTML=content;
    if(smooth)notice.animate?.([{opacity:0,translate:'0 8px'},{opacity:1,translate:'0 0'}],{duration:240,easing:'ease-out'});
    decisionKey=key;
  }
  $('continue-decision').textContent=playing?'Dismiss notice →':'Continue replay →';
}
$('continue-decision').onclick=()=>{if(!activePresentation)return;dismissedDecisionId=activePresentation.id;playing=true;update(true);};
$('inspect-decision').onclick=()=>{if(activePresentation)inspectEvent(activePresentation.primary.event.event_id);};
$('pause-decisions').onclick=()=>{pauseDecisions=!pauseDecisions;$('pause-decisions').classList.toggle('active',pauseDecisions);$('pause-decisions').setAttribute('aria-pressed',pauseDecisions);};
for(const kind of ['foul','penalty','offside'])$('jump-'+kind).onclick=()=>{
  if(!match)return;const event=nextDecision(match,time,Infinity,kind)||nextDecision(match,-1,Infinity,kind);
  if(!event){notify('This match has no recorded '+kind+' events. Choose a different example.');return;}
  playing=false;dismissedDecisionId=null;setTime(event.t);
};
$('sample').onchange=()=>load($('sample').value);

$('penalty-setup').onclick=()=>{
  if(activeDecision?.kind!=='penalty')return;
  const restart=match.events.find(e=>e.type==='restart'&&e.source_event_id===activeDecision.event.event_id);
  const action=restart&&match.actions.find(e=>e.restart_event_id===restart.event_id&&e.set_piece_type==='penalty');
  if(!action){notify('No recorded penalty kick follows this award.');return;}
  playing=false;dismissedDecisionId=null;setTime(action.kick);
};

for(const kind of ['substitution','goal'])$('jump-'+kind).onclick=()=>{
  if(!match)return;const event=nextMoment(match,time,Infinity,kind)||nextMoment(match,-1,Infinity,kind);
  if(!event){notify('This match has no recorded '+kind+' events. Choose a different example.');return;}
  playing=false;dismissedDecisionId=null;setTime(event.t);
};
