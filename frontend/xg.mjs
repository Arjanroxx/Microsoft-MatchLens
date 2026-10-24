// Original uncalibrated pre-shot heuristic. Keep in parity with simulator/xg.py.
export const XG_MODEL='matchlens-preshot-xg-v1';
const round=(n,p=6)=>Math.round(n*10**p)/10**p;
export function shotXg(e,roster,keeperId=null){
  const start=e.start,frame=e.pitch_snapshot?.players,team=e.team_id;
  if(e.type!=='shot'||!start||!frame||!['home','away'].includes(team)||![1,2].includes(e.period))return null;
  const side=id=>typeof roster[id]==='string'?roster[id]:roster[id]?.team_id;
  const keeper=e.goalkeeper_id||keeperId||Object.keys(roster).find(id=>roster[id]?.role==='GK'&&side(id)!==team&&frame[id])||null;
  const d=(team==='home')===(e.period===1)?1:-1,gx=d===1?105:0,dx=d*(gx-start.x_m),dy=start.y_m-34;
  const distance=Math.hypot(dx,dy),angle=dx>=0?Math.atan2(Math.abs(7.32*dx),dx*dx+dy*dy-3.66**2):0;
  const outfield=Object.entries(frame).filter(([id])=>side(id)!=null&&side(id)!==team&&id!==keeper);
  const nearest=outfield.length?Math.min(...outfield.map(([,p])=>Math.hypot(p.x_m-start.x_m,p.y_m-start.y_m))):null;
  const cone=p=>{if(dx<=0)return false;const u=d*(p.x_m-start.x_m)/dx;return u>0&&u<=1&&p.y_m>=start.y_m+(30.34-start.y_m)*u&&p.y_m<=start.y_m+(37.66-start.y_m)*u;};
  const blockers=outfield.filter(([,p])=>cone(p)).map(([id])=>id).sort(),kp=frame[keeper],covered=kp?cone(kp):null,off=kp?Math.abs(gx-kp.x_m):null,situation=e.set_piece_type||'open_play';
  const terms={intercept:-1.3,distance:-.1*distance,angle:1.8*angle,blockers:-.22*blockers.length,pressure:-.35*(nearest===null?0:Math.max(0,3-nearest)/3),uncovered_keeper:covered===false?.7:0,keeper_off_line:covered?-.03*Math.min(off||0,10):0,direct_free_kick:situation==='direct_free_kick'?-.35:0};
  const logit=Object.values(terms).reduce((a,b)=>a+b,0),value=situation==='penalty'?.76:Math.max(.001,Math.min(.95,1/(1+Math.exp(-Math.max(-60,Math.min(60,logit))))));
  return {value:round(value),model:XG_MODEL,calibrated:false,counted:e.valid_for_statistics!==false,features:{distance_m:round(distance),angle_radians:round(angle),blocker_ids:blockers,nearest_defender_m:nearest===null?null:round(nearest),goalkeeper_id:keeper,keeper_in_cone:covered,keeper_off_line_m:off===null?null:round(off),situation,body_part_assumption:'foot'},logit_contributions:Object.fromEntries(Object.entries(terms).map(([k,v])=>[k,round(v)])),method:situation==='penalty'?'selected_penalty_prior':'geometry_logistic_heuristic'};
}
class Accumulator{
  constructor(){this.shots=this.known=this.units=this.npShots=this.npKnown=this.npUnits=this.assisted=this.assistedMissing=this.goals=this.onTarget=0;}
  add(e,x){this.shots++;const np=e.set_piece_type!=='penalty';if(np)this.npShots++;if(x){const u=Math.round(x.value*1e6);this.known++;this.units+=u;if(np){this.npKnown++;this.npUnits+=u;}}if(e.outcome==='goal'||e.outcome_reason==='saved')this.onTarget++;}
  summary(){const xg=this.shots===this.known?this.units/1e6:null;return {xg,non_penalty_xg:this.npShots===this.npKnown?this.npUnits/1e6:null,xg_per_shot:this.shots&&xg!==null?Math.round(this.units/this.shots)/1e6:null,goals_minus_xg:xg===null?null:round(this.goals-xg),xg_assisted:this.assistedMissing?null:this.assisted/1e6,shot_conversion_percentage:this.shots?Math.round(10000*this.goals/this.shots)/100:null,shot_accuracy_percentage:this.shots?Math.round(10000*this.onTarget/this.shots)/100:null,xg_coverage:{shots_with_xg:this.known,shots_without_xg:this.shots-this.known,complete:this.shots===this.known},xg_model:XG_MODEL};}
}
export function expectedGoalsAt(match,time){
  const teams={home:new Accumulator(),away:new Accumulator()},players=Object.fromEntries(Object.keys(match.players).map(id=>[id,new Accumulator()])),last=new Map(),keepers=Object.fromEntries(['home','away'].map(t=>[t,Object.keys(match.players).find(id=>match.players[id].team_id===t&&match.players[id].role==='GK')]));
  const shots=[];
  for(const e of match.events){if(e.t>time)break;if(e.valid_for_statistics===false){last.clear();continue;}
    if(['period_start','period_end','stoppage','ball_out','loose_ball','save','offside','opponent_touch','substitution','dismissal','match_abandoned'].includes(e.type))last.clear();
    if(e.type==='goalkeeper_change')keepers[e.team_id]=e.player_id;
    if(e.type==='pass'){if(e.outcome==='complete')last.set(e.possession_id,e);else last.delete(e.possession_id);}
    if(['turnover','recovery','restart'].includes(e.type))last.delete(e.possession_id);
    if(e.type==='goal'){if(teams[e.team_id])teams[e.team_id].goals++;if(players[e.player_id])players[e.player_id].goals++;}
    if(e.type!=='shot'||!teams[e.team_id])continue;
    const x=shotXg(e,match.players,keepers[e.team_id==='home'?'away':'home']);teams[e.team_id].add(e,x);players[e.player_id]?.add(e,x);shots.push({event:e,xg:x});
    const prior=last.get(e.possession_id);last.delete(e.possession_id);
    const delta=e.ball_trajectory?.[0]?.period_time_ms-prior?.period_time_ms;
    if(prior&&prior.team_id===e.team_id&&prior.period===e.period&&prior.recipient_id===e.player_id&&prior.player_id!==e.player_id&&delta>=0&&delta<=10000){const p=players[prior.player_id];if(p){if(x){p.assisted+=Math.round(x.value*1e6);teams[e.team_id].assisted+=Math.round(x.value*1e6);}else{p.assistedMissing++;teams[e.team_id].assistedMissing++;}}}
  }
  return {teams:Object.fromEntries(Object.entries(teams).map(([id,a])=>[id,a.summary()])),players:Object.fromEntries(Object.entries(players).map(([id,a])=>[id,a.summary()])),shots};
}
