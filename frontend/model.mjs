// Pure simulator adapter. Rendering and future backend transports depend on this contract.
export const elapsed = (e, duration) => e.match_time_ms ?? (e.period - 1) * duration + e.period_time_ms;
export const actionTypes = ['pass','shot','clearance','parry','restart_delivery'];
export const periodOffset = (metadata,period) => metadata.period_offsets_ms?.[String(period)] ?? (period-1)*metadata.period_duration_ms;
export function clockAt(match,time,periodOverride){
  const latest=match.events.filter(e=>e.t<=time).at(-1),period=periodOverride??latest?.period??1;
  const local=Math.max(0,time-periodOffset(match.metadata,period)),regulation=match.metadata.period_duration_ms;
  const stamp=ms=>`${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}`;
  const added=local>=regulation;
  const display=added?`${Math.round(period*regulation/60000)}+${stamp(local-regulation)}`:stamp((period-1)*regulation+local);
  const announcement=match.events.filter(e=>e.t<=time&&e.period===period&&e.type==='added_time').at(-1);
  return {period,periodTimeMs:local,inAddedTime:added,display,announcedMinimumMs:announcement?.minimum_added_ms??null,fullTime:latest?.type==='period_end'&&period===2};
}
export const mean = a => a.length ? a.reduce((s,v)=>s+v,0)/a.length : null;
export function prepare(metadata, rawEvents) {
  if (!metadata?.players?.length || !metadata?.teams?.length || !(metadata.period_duration_ms>0) || !(metadata.pitch?.length_m>0) || !(metadata.pitch?.width_m>0)) throw Error('Invalid metadata: roster, teams, pitch and period duration are required.');
  const seen=new Set(), events=[]; const roster=new Set(metadata.players.map(p=>p.player_id));
  for (const e of rawEvents) {
    if (e.match_id!==metadata.match_id || !e.event_id || ![1,2].includes(e.period) || !Number.isFinite(e.period_time_ms) || e.period_time_ms<0 || e.period_time_ms>(metadata.period_actual_durations_ms?.[String(e.period)]??metadata.period_duration_ms) || !Number.isFinite(e.sequence)) throw Error('Invalid event identity or clock.');
    if(e.player_id && !roster.has(e.player_id)) throw Error('An event references an unknown player.');
    if(metadata.schema_version==='1.5'&&(!Number.isFinite(e.match_time_ms)||e.match_time_ms!==periodOffset(metadata,e.period)+e.period_time_ms))throw Error('Invalid match/period clock mapping.');
    const key=e.match_id+':'+e.event_id; if(seen.has(key))continue;seen.add(key);
    if(actionTypes.includes(e.type)) {
      if(!e.pitch_snapshot?.players || !e.start || !e.end || !e.ball_trajectory?.length)throw Error('An action is missing its snapshot or trajectory.');
      let last=-1;
      for(const point of e.ball_trajectory){if(!Number.isFinite(point.x_m)||!Number.isFinite(point.y_m)||!Number.isFinite(point.period_time_ms)||point.period_time_ms<last||point.period_time_ms>e.period_time_ms)throw Error('Invalid ball trajectory.');last=point.period_time_ms;}
    }
    events.push({...e,t:elapsed(e,metadata.period_duration_ms),kick:e.pitch_snapshot ? periodOffset(metadata,e.period)+e.pitch_snapshot.period_time_ms : undefined});
  }
  events.sort((a,b)=>a.t-b.t||a.sequence-b.sequence);
  if(!events.length)throw Error('No match events found.');
  const match={metadata,events,actions:events.filter(e=>e.kick!==undefined).sort((a,b)=>a.kick-b.kick||a.sequence-b.sequence),duration:metadata.match_duration_ms??metadata.period_duration_ms*2,players:Object.fromEntries(metadata.players.map(p=>[p.player_id,p]))};
  match.visualFrames=visualFrames(match);
  return match;
}
export function statistics(match, time) {
  const counts=Object.fromEntries(['home','away'].map(t=>[t,{goals:0,attempted:0,completed:0,shots:0,onTarget:0,recoveries:0,turnovers:0,pressure:0,interceptions:0,saves:0,throwIns:0,goalKicks:0,corners:0,clearances:0,savesHeld:0,savesParried:0,reboundShots:0,distance:[],difficulty:[],speed:[],shotSpeed:[]} ]));
  let cursor=0,owner=null; const times={home:0,away:0,unassigned:0};
  const advance=t=>{times[owner||'unassigned']+=Math.max(0,t-cursor);cursor=t;};
  for(const e of match.events){
    if(e.t>time)break;
    if(['shot','parry','clearance'].includes(e.type)){advance(Math.max(cursor,periodOffset(match.metadata,e.period)+e.ball_trajectory[0].period_time_ms));owner=null;}
    advance(e.t);
    if(['period_start','period_end','turnover','goal','stoppage','ball_out','loose_ball','save','ball_release'].includes(e.type))owner=null;
    if(e.type==='resume')owner=e.player_id?e.team_id:null;
    if(['restart','recovery'].includes(e.type))owner=e.ball_in_play===false?null:e.team_id;
    const s=counts[e.team_id];if(!s)continue;
    if(e.type==='goal')s.goals++;
    if(e.type==='clearance')s.clearances++;
    if(e.type==='restart'){const key={throw_in:'throwIns',goal_kick:'goalKicks',corner_kick:'corners'}[e.reason];if(key)s[key]++;}
    if(e.type==='restart_delivery'){const defender=match.players[e.interceptor_id]?.team_id;if(defender)counts[defender].interceptions++;}
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
      if(e.is_rebound)s.reboundShots++;s.shots++;if(e.outcome==='goal'||e.outcome_reason==='saved')s.onTarget++;
      if(e.outcome_reason==='saved'){const keeper=counts[e.team_id==='home'?'away':'home'];keeper.saves++;if(e.save_outcome==='hold')keeper.savesHeld++;if(e.save_outcome==='parry')keeper.savesParried++;}
      if(e.shot_speed)s.shotSpeed.push(e.shot_speed.kmh);
    }
  }
  advance(time); const total=times.home+times.away;
  for(const team of ['home','away']){const s=counts[team];s.accuracy=s.attempted?100*s.completed/s.attempted:null;s.possession=total?100*times[team]/total:null;s.time=times[team];}
  return {teams:counts,times};
}

const mixPoint=(a,b,u)=>({x_m:a.x_m+(b.x_m-a.x_m)*u,y_m:a.y_m+(b.y_m-a.y_m)*u});
// This is PitchState.FORMATION in simulator/pitch.py, used only for the
// explicit kickoff resets in engine.py. Other versions wait for a snapshot.
export function lineupsAt(match,time) {
  const slots=Object.fromEntries(match.metadata.players.filter(p=>p.is_starter!==false).map(p=>[p.player_id,p.formation_slot||p.shirt_number]));
  const off=new Set();
  for(const event of match.events){
    if(event.t>time)break;
    if(event.type!=='substitution')continue;
    const slot=slots[event.player_off_id];delete slots[event.player_off_id];
    slots[event.player_on_id]=event.formation_slot||slot;off.add(event.player_off_id);
  }
  return {slots,onPitch:Object.keys(slots),substitutedOff:[...off],bench:match.metadata.players.filter(p=>!(p.player_id in slots)&&!off.has(p.player_id)).map(p=>p.player_id)};
}
function kickoffPositions(match, period, owner, ball, time=0) {
  if (!['1.3','1.4','1.5'].includes(match.metadata.schema_version)) return null;
  const formation=[[5,34],[25,8],[25,25],[25,43],[25,60],[48,15],[50,34],[48,53],[72,14],[76,34],[72,54]];
  const positions={};
  const slots=lineupsAt(match,time).slots;
  for(const player of match.metadata.players.filter(p=>p.player_id in slots)){
    const anchor=formation[slots[player.player_id]-1];
    if(!anchor)return null;
    const [x,y]=anchor,positive=(player.team_id==='home')===(period===1);
    positions[player.player_id]={x_m:positive?x:105-x,y_m:y};
  }
  if(owner&&ball)positions[owner]={...ball};
  return positions;
}
function visualFrames(match){
  const frames=[];
  for(const action of match.actions){
    frames.push({t:action.kick,sequence:action.sequence,period:action.period,blend:true,positions:action.pitch_snapshot.players});
    const positions=structuredClone(action.pitch_snapshot.players);
    const recipient=action.recipient_id||action.interceptor_id||
      (action.type==='shot'&&action.outcome_reason==='saved'?action.goalkeeper_id||
        match.metadata.players.find(p=>p.team_id!==action.team_id&&p.role==='GK')?.player_id:null);
    if(recipient)positions[recipient]={...action.end};
    frames.push({t:action.t,sequence:action.sequence,period:action.period,blend:true,positions});
  }
  for(const event of match.events){
    if(event.type!=='restart'||event.reason!=='kickoff')continue;
    const positions=kickoffPositions(match,event.period,event.player_id,event.start,event.t);
    if(positions)frames.push({t:event.t,sequence:event.sequence,period:event.period,blend:false,positions});
  }
  const order=(a,b)=>a.t-b.t||a.sequence-b.sequence;
  for(const event of match.events){
    if(event.positions_after)frames.push({t:event.t,sequence:event.sequence,period:event.period,blend:false,positions:event.positions_after});
  }
  frames.sort(order);
  // engine.py moves a recoverer to the stationary ball before emitting recovery.
  // Anchor that arrival so control never changes early and the gap is continuous.
  for(const event of match.events){
    if(event.type!=='recovery'||!event.start||!event.player_id)continue;
    let previous=null;
    for(const frame of frames){
      if(frame.t<event.t||(frame.t===event.t&&frame.sequence<=event.sequence))previous=frame;
      else break;
    }
    if(!previous||previous.period!==event.period)continue;
    const positions=structuredClone(previous.positions);
    if(positions[event.player_id])positions[event.player_id]={...event.start};
    frames.push({t:event.t,sequence:event.sequence,period:event.period,blend:true,positions});
    frames.sort(order);
  }
  return frames;
}
export function boardAt(match,time,{smooth=true}={}){
  let action=null;
  for(const a of match.actions){if(a.kick<=time)action=a;else break;}
  let previous=null,next=null;
  for(const frame of match.visualFrames){
    if(frame.t<=time)previous=frame;else {next=frame;break;}
  }
  let positions=previous?structuredClone(previous.positions):{};
  // Interpolate only the presentation between exact source-state anchors.
  // A kickoff is a reset in the simulator: never move toward it early.
  if(smooth&&previous&&next&&next.blend&&previous.period===next.period&&next.t>previous.t){
    const u=(time-previous.t)/(next.t-previous.t);
    for(const id of Object.keys(positions)){
      if(next.positions[id])positions[id]=mixPoint(positions[id],next.positions[id],u);
    }
  }
  let ball=null,carrierId=null,latestControl=null,lastEvent=null,lastVisibleEvent=null,stopped=false;
  for(const event of match.events){
    if(event.t>time)break;lastEvent=event;
    if(!['ball_release','time_lost','ball_placement'].includes(event.type))lastVisibleEvent=event;
    if(['period_start','period_end','goal','turnover','stoppage','ball_out','loose_ball','save','ball_release'].includes(event.type)){
      carrierId=null;latestControl=event;
    }
    if(['stoppage','ball_out','period_end'].includes(event.type))stopped=true;
    if(event.type==='resume'||event.type==='recovery'||(event.type==='restart'&&event.ball_in_play!==false))stopped=false;
    if(['restart','recovery','resume'].includes(event.type)){
      carrierId=event.ball_in_play===false?null:event.player_id;latestControl=event;
    }
    if(event.type==='pass'){
      carrierId=event.outcome==='complete'?event.recipient_id:null;
      latestControl=event;
    }
    if(['shot','parry','clearance'].includes(event.type)){carrierId=null;latestControl=event;}
    if(event.type==='restart_delivery'){carrierId=event.recipient_id;latestControl=event;}
    if(['restart','recovery','turnover','resume'].includes(event.type)&&event.start)ball=event.start;
    if(actionTypes.includes(event.type)||event.type==='ball_placement')ball=event.end;
  }
  const active=!!action&&time<action.t;
  if(active){
    carrierId=null; // Flight is not possession by the intended receiver.
    const local=time-periodOffset(match.metadata,action.period);
    const samples=action.ball_trajectory;ball=samples[0];
    for(let i=1;i<samples.length;i++){
      const b=samples[i],a=samples[i-1];
      if(local<b.period_time_ms){ball=mixPoint(a,b,Math.max(0,(local-a.period_time_ms)/(b.period_time_ms-a.period_time_ms)));break;}
      ball=b;
    }
  }
  // The engine keeps the carrier at the ball throughout the decision interval.
  if(carrierId&&ball&&positions[carrierId])positions[carrierId]={x_m:ball.x_m,y_m:ball.y_m};
  const period=clockAt(match,time).period;
  const phase=active?'flight':carrierId?'controlled':lastEvent?.type==='period_end'?'interval':stopped?'stoppage':lastEvent?.type==='goal'?'goal':'loose';
  return {positions,ball,action,active,carrierId,phase,period,clock:clockAt(match,time),lastEvent,lastVisibleEvent,latestControl,lineups:lineupsAt(match,time)};
}

// Event labels must also handle boundaries/restarts, which have no outcome field.
export function eventTitle(event) {
  if (event.type === 'pass') return event.outcome === 'complete' ? 'Pass completed' : event.outcome_reason==='out_of_play'?'Pass out of play':event.outcome_reason==='missed_target'?'Pass missed target':'Pass intercepted';
  if (event.type === 'shot') return 'Shot · ' + String(event.save_outcome?`saved (${event.save_outcome})`:event.outcome_reason || event.outcome || 'resolved').replaceAll('_', ' ');
  if(event.type==='restart'&&event.reason!=='kickoff'&&event.reason)return String(event.reason).replaceAll('_',' ');
  if(event.type==='added_time')return `Added time · minimum ${(event.minimum_added_ms/60000).toFixed(1)} min`;
  return {ball_out:'Ball out of play',ball_placement:'Ball placed for restart',save:'Goalkeeper save',parry:'Keeper parry',loose_ball:'Rebound loose',clearance:'Defender clearance',restart_delivery:'Restart delivery',ball_release:'Ball released',time_lost:'Time allowance recorded',goal:'Goal!', recovery:'Possession recovered', turnover:'Possession lost',
    pressure:'Pressure applied', restart:'Play restarts', period_start:'Half begins',
    period_end:'Half ends',substitution:'Substitution',stoppage:'Play stopped',resume:'Play resumes'}[event.type] || event.type;
}
