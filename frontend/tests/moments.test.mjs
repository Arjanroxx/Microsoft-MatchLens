import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,clockAt,statistics} from '../model.mjs';
import {decisionAt} from '../decisions.mjs';
import {momentAt,nextMoment,nextPause,presentationAt,isMoment,isPenaltyResult} from '../moments.mjs';
import {momentView,substitutionRows} from '../moment-ui.mjs';
const base=new URL('../../data/examples/offside-match/',import.meta.url),meta=JSON.parse(readFileSync(new URL('metadata.json',base))),raw=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse),match=prepare(meta,raw),format=(t,p)=>clockAt(match,t,p).display;
test('one substitution popup contains every visible change at the recorded stoppage, with source positions and minute',()=>{
 const event=match.events.find(e=>e.type==='substitution');assert.notEqual(momentAt(match,event.t-1)?.event.event_id,event.event_id);
 const state=momentAt(match,event.t),batch=match.events.filter(e=>e.type==='substitution'&&e.t===event.t&&e.stoppage_event_id===event.stoppage_event_id);
 assert.equal(state.kind,'substitution');assert.deepEqual(state.substitutions.map(e=>e.event_id),batch.map(e=>e.event_id));assert.equal(batch.length,2);
 const markup=momentView(match,state,format);for(const sub of batch){assert.ok(markup.includes(match.players[sub.player_on_id].name.replace(' Player ',' #')));assert.ok(markup.includes(match.players[sub.player_off_id].name.replace(' Player ',' #')));assert.ok(markup.includes(sub.position_group));}
 assert.match(markup,/62:11/);assert.match(markup,/ON/);assert.match(markup,/OFF/);assert.match(markup,/Striker/);assert.match(markup,/Winger/);
});
test('halftime substitutions identify the interval and do not substitute shirt numbers for formation positions',()=>{
 const example={...match.events.find(e=>e.type==='substitution'),halftime:true,formation_slot:10,position_group:'ST'};
 const text=substitutionRows(match,[example],format);assert.match(text,/HALF-TIME/);assert.match(text,/Striker · ST/);
});
test('goal celebration starts only on the goal record and uses its running score and scorer',()=>{
 const goal=match.events.find(e=>e.type==='goal'),shot=match.events.find(e=>e.event_id===goal.shot_event_id);assert.equal(isMoment(shot),false);
 assert.notEqual(momentAt(match,goal.t-1)?.kind,'goal');const state=momentAt(match,goal.t);assert.equal(state.kind,'goal');assert.equal(state.event.event_id,goal.event_id);
 const markup=momentView({...match,metadata:{...meta,final_score:{home:99,away:99}}},state,format);assert.match(markup,/GOALLLLLL/);assert.ok(markup.includes(match.players[goal.player_id].name.replace(' Player ',' #')));assert.ok(markup.includes('1 <em>:</em> 0'));assert.ok(!markup.includes('99'));
 assert.equal(statistics(match,goal.t).teams[goal.team_id].goals,statistics(match,goal.t-1).teams[goal.team_id].goals+1);
});
test('SAVED is shown only at penalty completion, once despite the following save record',()=>{
 const shot=match.events.find(e=>e.set_piece_type==='penalty'&&e.outcome_reason==='saved'),save=match.events.find(e=>e.type==='save'&&e.shot_event_id===shot.event_id);
 assert.notEqual(momentAt(match,shot.t-1)?.event.event_id,shot.event_id);const state=momentAt(match,shot.t);assert.equal(state.kind,'saved');assert.equal(isMoment(save),false);
 assert.match(momentView(match,state,format),/>SAVED</);assert.ok(momentView(match,state,format).includes(match.players[shot.goalkeeper_id].name.replace(' Player ',' #')));
 assert.equal(momentAt(match,save.t).id,shot.event_id);
});
test('MISS classification requires a valid, completed, off-target penalty and excludes offside/no_goal guesses',()=>{
 // Controlled presentation boundary: use documented source fields; no fabricated
 // miss is inserted into the viewer's bundled match.
 const penalty=match.events.find(e=>e.set_piece_type==='penalty');
 const offTarget={...penalty,outcome:'no_goal',outcome_reason:'off_target'};
 assert.equal(isPenaltyResult(offTarget),true);assert.equal(isPenaltyResult({...offTarget,valid_for_statistics:false}),false);assert.equal(isPenaltyResult({...offTarget,outcome_reason:'offside'}),false);assert.equal(isPenaltyResult({...offTarget,set_piece_type:null}),false);assert.equal(isPenaltyResult({...offTarget,outcome_reason:undefined}),false);
 const controlled={...match,events:[offTarget]};const result=momentAt(controlled,offTarget.t);assert.equal(result.kind,'miss');assert.match(momentView(controlled,result,format),/>MISS</);assert.equal(momentAt(controlled,offTarget.t-1),null);
});
test('a goal and substitutions at one timestamp show GOALLLLLL and retain all substitution rows',()=>{
 const goal=match.events.find(e=>e.type==='goal'),sub=match.events.find(e=>e.type==='substitution');
 const sameTime={...sub,t:goal.t,sequence:goal.sequence+2,stoppage_event_id:'goal-window'};
 const controlled={...match,events:[goal,sameTime]};const state=momentAt(controlled,goal.t);assert.equal(state.kind,'goal');assert.equal(state.substitutions.length,1);const text=momentView(controlled,state,format);assert.match(text,/GOALLLLLL/);assert.match(text,/Changes during this stoppage/);
});
test('a substitution attached to a referee stoppage augments rather than hides the referee call',()=>{
 const event=match.events.find(e=>e.type==='offside'),decision=decisionAt(match,event.t),sub=match.events.find(e=>e.type==='substitution');
 const controlled={...match,events:[{...sub,t:event.t,stoppage_event_id:decision.stop.event_id}]};const view=presentationAt(controlled,event.t,decision);assert.equal(view.primary.kind,'offside');assert.equal(view.substitutions.length,1);
});
test('auto pauses include source outcomes and group simultaneous substitutions without changing event order',()=>{
 const sub=match.events.find(e=>e.type==='substitution'),goal=match.events.find(e=>e.type==='goal');assert.equal(nextPause(match,sub.t-1,sub.t).type,'substitution');assert.equal(nextPause(match,goal.t-1,goal.t).type,'goal');
 assert.equal(nextMoment(match,-1,Infinity,'goal').event_id,goal.event_id);assert.equal(nextMoment(match,-1,Infinity,'substitution').event_id,sub.event_id);
 assert.deepEqual(match.events.map(e=>e.event_id),raw.map(e=>e.event_id));assert.equal(momentAt(match,match.duration),null);assert.equal(momentAt(match,0),null);
});
