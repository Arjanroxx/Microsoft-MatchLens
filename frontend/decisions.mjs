// Decision presentation follows source records, never infers an offence from proximity.
const cache=new WeakMap();
export const isDecision=e=>e.type==='foul'||e.type==='offside';
function index(match){
  if(cache.has(match))return cache.get(match);
  const entries=match.events.filter(isDecision).map(event=>{
    const stop=match.events.find(e=>e.type==='stoppage'&&e.source_event_id===event.event_id);
    const restart=match.events.find(e=>e.type==='restart'&&e.source_event_id===event.event_id);
    const placement=stop&&match.events.find(e=>e.type==='ball_placement'&&e.stoppage_event_id===stop.event_id);
    const resume=restart&&match.events.find(e=>e.sequence>restart.sequence&&e.type==='resume');
    const penalty=event.restart?.type==='penalty';
    const action=penalty&&restart&&match.actions.find(e=>e.restart_event_id===restart.event_id&&e.set_piece_type==='penalty');
    const advantage=match.events.filter(e=>e.type==='advantage'&&e.foul_event_id===event.event_id);
    return {event,stop,restart,placement,resume,penalty,action,advantage};
  });cache.set(match,entries);return entries;
}
export function nextDecision(match,from,to=Infinity,kind='all'){
  return index(match).find(x=>x.event.t>from&&x.event.t<=to&&(kind==='all'||(kind==='penalty'?x.penalty:kind==='foul'?x.event.type==='foul'&&!x.penalty:x.event.type===kind)))?.event||null;
}
export function decisionAt(match,time){
  const entry=index(match).filter(x=>x.event.t<=time).at(-1);if(!entry)return null;
  const {event}=entry,visible=e=>e&&e.t<=time?e:null;
  const stop=visible(entry.stop),restart=visible(entry.restart),placement=visible(entry.placement),resume=visible(entry.resume);
  const advantage=entry.advantage.filter(e=>e.t<=time).at(-1)||null;
  if(!stop&&time-event.t>8000)return null;
  if(resume&&!entry.penalty)return null;
  if(entry.penalty&&entry.action&&time>entry.action.t+2500)return null;
  if(!entry.action&&resume&&time>resume.t+2000)return null;
  const released=entry.action&&entry.action.kick<=time;
  const completed=entry.action&&entry.action.t<=time;
  const stage=completed?'result':released?(time===entry.action.kick?'ready':'flight'):restart?'ready':placement?'positioning':stop?'stopped':advantage?'advantage':'decision';
  return {event,kind:entry.penalty?'penalty':event.type,stage,stop,restart,placement,resume,advantage,
    location:event.location,award:event.restart,spot:event.restart?.location,
    // Future shot outcomes never leave this boundary before completion.
    result:completed?entry.action:null,actionId:released?entry.action.event_id:null,
    takerId:restart?.player_id||null,keeperId:released?(entry.action.goalkeeper_id||null):null};
}
