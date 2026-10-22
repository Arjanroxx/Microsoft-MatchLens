// Key moments come only from completed simulator records. A scoring shot is
// followed by a goal record; never celebrate both or infer a miss from no_goal.
const indexes=new WeakMap();
export const isPenaltyResult=e=>e.type==='shot'&&e.set_piece_type==='penalty'&&e.valid_for_statistics!==false&&['saved','off_target'].includes(e.outcome_reason);
export const isMoment=e=>e.type==='substitution'||(e.type==='goal'&&e.valid_for_statistics!==false)||isPenaltyResult(e);
function index(match){
  if(indexes.has(match))return indexes.get(match);
  const values=match.events.filter(isMoment).map(e=>{
    if(e.type!=='substitution')return {event:e,kind:e.type==='goal'?'goal':e.outcome_reason==='saved'?'saved':'miss',id:e.event_id};
    const group=match.events.filter(x=>x.type==='substitution'&&x.t===e.t&&
      (e.stoppage_event_id?x.stoppage_event_id===e.stoppage_event_id:x.window_id===e.window_id));
    const restart=match.events.find(x=>x.type==='restart'&&x.stoppage_event_id===e.stoppage_event_id&&x.sequence>e.sequence);
    const resume=restart&&match.events.find(x=>x.type==='resume'&&x.sequence>restart.sequence);
    return {event:e,kind:'substitution',id:'subs:'+(e.stoppage_event_id||e.window_id||e.event_id)+':'+e.t,group,resume};
  });indexes.set(match,values);return values;
}
export function momentAt(match,time){
  const visible=index(match).filter(x=>x.event.t<=time);if(!visible.length)return null;
  const stamp=visible.at(-1).event.t,batch=visible.filter(x=>x.event.t===stamp);
  const rank={goal:3,saved:2,miss:2,substitution:1};
  const latest=batch.reduce((a,b)=>rank[b.kind]>rank[a.kind]?b:a);
  const simultaneousSubs=batch.filter(x=>x.kind==='substitution').map(x=>x.event).sort((a,b)=>a.sequence-b.sequence);
  if(latest.kind==='substitution'){
    // Keep the batch visible during the recorded stoppage, then retire it.
    const end=latest.resume?latest.resume.t+2000:latest.event.t+12000;
    if(time>end)return null;
    const substitutions=latest.group.filter(e=>e.t<=time).sort((a,b)=>a.sequence-b.sequence);
    return {...latest,substitutions};
  }
  if(time-latest.event.t>10000)return null;
  return {...latest,substitutions:simultaneousSubs};
}
export function nextMoment(match,from,to=Infinity,kind='all'){
  return index(match).find(x=>x.event.t>from&&x.event.t<=to&&(kind==='all'||x.kind===kind))?.event||null;
}
export function nextPause(match,from,to=Infinity){
  return match.events.find(e=>e.t>from&&e.t<=to&&(e.type==='foul'||e.type==='offside'||isMoment(e)))||null;
}
export function presentationAt(match,time,decision){
  const moment=momentAt(match,time);
  // A batch during a foul/offside stoppage augments the referee notice rather
  // than replacing it or hiding a substitution in the same source timestamp.
  const attached=moment?.kind==='substitution'&&decision?.stop&&
    moment.event.stoppage_event_id===decision.stop.event_id;
  if(attached)return {primary:decision,substitutions:moment.substitutions,id:decision.event.event_id};
  if(moment&&(!decision||moment.event.t>=decision.event.t))return {primary:moment,substitutions:moment.substitutions,id:moment.id};
  if(decision)return {primary:decision,substitutions:[],id:decision.event.event_id};
  return null;
}
