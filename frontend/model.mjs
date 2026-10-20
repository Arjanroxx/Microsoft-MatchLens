// Pure simulator adapter. Rendering and future backend transports depend on this contract.
export const elapsed = (e, duration) => (e.period - 1) * duration + e.period_time_ms;
export const mean = a => a.length ? a.reduce((s,v)=>s+v,0)/a.length : null;
export function prepare(metadata, rawEvents) {
  if (!metadata?.players?.length || !metadata?.teams?.length || !(metadata.period_duration_ms>0) || !(metadata.pitch?.length_m>0) || !(metadata.pitch?.width_m>0)) throw Error('Invalid metadata: roster, teams, pitch and period duration are required.');
  const seen=new Set(), events=[]; const roster=new Set(metadata.players.map(p=>p.player_id));
  for (const e of rawEvents) {
    if (e.match_id!==metadata.match_id || !e.event_id || ![1,2].includes(e.period) || !Number.isFinite(e.period_time_ms) || e.period_time_ms<0 || e.period_time_ms>metadata.period_duration_ms || !Number.isFinite(e.sequence)) throw Error('Invalid event identity or clock.');
    if(e.player_id && !roster.has(e.player_id)) throw Error('An event references an unknown player.');
    const key=e.match_id+':'+e.event_id; if(seen.has(key))continue;seen.add(key);
    if(['pass','shot'].includes(e.type)) {
      if(!e.pitch_snapshot?.players || !e.start || !e.end || !e.ball_trajectory?.length)throw Error('An action is missing its snapshot or trajectory.');
      let last=-1;
      for(const point of e.ball_trajectory){if(!Number.isFinite(point.x_m)||!Number.isFinite(point.y_m)||!Number.isFinite(point.period_time_ms)||point.period_time_ms<last||point.period_time_ms>e.period_time_ms)throw Error('Invalid ball trajectory.');last=point.period_time_ms;}
    }
    events.push({...e,t:elapsed(e,metadata.period_duration_ms),kick:e.pitch_snapshot ? (e.period-1)*metadata.period_duration_ms+e.pitch_snapshot.period_time_ms : undefined});
  }
  events.sort((a,b)=>a.t-b.t||a.sequence-b.sequence);
  if(!events.length)throw Error('No match events found.');
  return {metadata,events,actions:events.filter(e=>e.kick!==undefined),duration:metadata.period_duration_ms*2,players:Object.fromEntries(metadata.players.map(p=>[p.player_id,p]))};
}
export function statistics(match, time) {
  const counts=Object.fromEntries(['home','away'].map(t=>[t,{goals:0,attempted:0,completed:0,shots:0,onTarget:0,recoveries:0,turnovers:0,pressure:0,interceptions:0,saves:0,distance:[],difficulty:[],speed:[],shotSpeed:[]} ]));
  let cursor=0,owner=null; const times={home:0,away:0,unassigned:0};
  const advance=t=>{times[owner||'unassigned']+=Math.max(0,t-cursor);cursor=t;};
  for(const e of match.events){
    if(e.t>time)break;
    if(e.type==='shot'){advance((e.period-1)*match.metadata.period_duration_ms+e.ball_trajectory[0].period_time_ms);owner=null;}
    advance(e.t);
    if(['period_start','period_end','turnover','goal'].includes(e.type))owner=null;
    if(['restart','recovery'].includes(e.type))owner=e.team_id;
    const s=counts[e.team_id];if(!s)continue;
    if(e.type==='goal')s.goals++;
    if(e.type==='recovery')s.recoveries++;
    if(e.type==='turnover')s.turnovers++;
    if(e.type==='pressure')s.pressure++;
    if(e.type==='pass'){
      s.attempted++;if(e.outcome==='complete')s.completed++;
      if(e.distance_m!=null)s.distance.push(e.distance_m);
      if(e.pass_difficulty)s.difficulty.push(e.pass_difficulty.score);
      if(e.ball_speed)s.speed.push(e.ball_speed.average_kmh);
      const defender=match.players[e.interceptor_id]?.team_id;if(defender)counts[defender].interceptions++;
    }
    if(e.type==='shot'){
      s.shots++;if(e.outcome==='goal'||e.outcome_reason==='saved')s.onTarget++;
      if(e.outcome_reason==='saved')counts[e.team_id==='home'?'away':'home'].saves++;
      if(e.shot_speed)s.shotSpeed.push(e.shot_speed.kmh);
    }
  }
  advance(time); const total=times.home+times.away;
  for(const team of ['home','away']){const s=counts[team];s.accuracy=s.attempted?100*s.completed/s.attempted:null;s.possession=total?100*times[team]/total:null;s.time=times[team];}
  return {teams:counts,times};
}
export function boardAt(match,time){
  let action=null;for(const a of match.actions){if(a.kick<=time)action=a;else break;}
  if(!action)return {positions:{},ball:null,action:null,active:false};
  const positions=structuredClone(action.pitch_snapshot.players),local=time-(action.period-1)*match.metadata.period_duration_ms,samples=action.ball_trajectory;
  let ball=samples[0];
  for(let i=1;i<samples.length;i++){const b=samples[i],a=samples[i-1];if(local<b.period_time_ms){const u=Math.max(0,(local-a.period_time_ms)/(b.period_time_ms-a.period_time_ms));ball={x_m:a.x_m+(b.x_m-a.x_m)*u,y_m:a.y_m+(b.y_m-a.y_m)*u};break;}ball=b;}
  if(time>=action.t){const recipient=action.recipient_id||action.interceptor_id;if(recipient)positions[recipient]=action.end;}
  // A restart/recovery after this action may move the ball before the next kick.
  for(const e of match.events){if(e.t>time)break;if(e.t>=action.t&&e.start&&['restart','recovery'].includes(e.type))ball=e.start;}
  return {positions,ball,action,active:time<action.t};
}

// Event labels must also handle boundaries/restarts, which have no outcome field.
export function eventTitle(event) {
  if (event.type === 'pass') return event.outcome === 'complete' ? 'Pass completed' : 'Pass intercepted';
  if (event.type === 'shot') return 'Shot · ' + String(event.outcome_reason || event.outcome || 'resolved').replaceAll('_', ' ');
  return {goal:'Goal!', recovery:'Possession recovered', turnover:'Possession lost',
    pressure:'Pressure applied', restart:'Play restarts', period_start:'Half begins',
    period_end:'Half ends'}[event.type] || event.type;
}
