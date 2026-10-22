import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,statistics,boardAt,offsideAt,eventTitle,actionTypes} from '../model.mjs';

const base=new URL('../../data/examples/offside-match/',import.meta.url);
const metadata=JSON.parse(readFileSync(new URL('metadata.json',base)));
const events=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse);
const summary=JSON.parse(readFileSync(new URL('summary.json',base)));
const match=prepare(metadata,events);

test('offside evidence is withheld until decision and rewind hides it',()=>{
  const decision=match.events.find(e=>e.type==='offside');assert.ok(decision);
  assert.equal(offsideAt(match,decision.t-1,{eventId:decision.event_id}),null);
  const evidence=offsideAt(match,decision.t,{eventId:decision.event_id});assert.ok(evidence);
  const source=match.events.find(e=>e.event_id===decision.source_event_id);
  assert.deepEqual(evidence.positions,source.pitch_snapshot.players);
  assert.deepEqual(evidence.ball,source.start);
  assert.equal(evidence.contactTimeMs,source.kick);
  assert.ok(evidence.contactTimeMs<decision.t);
  assert.equal(evidence.lineX,decision.contact.line_x_m);
  assert.equal(offsideAt(match,decision.t-1,{eventId:decision.event_id}),null);
  assert.equal(offsideAt(match,decision.t+8001,{eventId:decision.event_id}),null);
});

test('evidence is immutable, source-frozen, and uses ball or second-last line in either direction',()=>{
  for(const decision of match.events.filter(e=>e.type==='offside')){
    const frame=offsideAt(match,decision.t,{eventId:decision.event_id});
    const d=decision.contact.direction;
    assert.equal(frame.lineX,d*Math.max(d*frame.ball.x_m,d*frame.secondLastOpponentX));
    assert.ok(d*(frame.positions[frame.offenderId].x_m-frame.lineX)>0);
    frame.positions[frame.offenderId].x_m=-100;
    assert.notEqual(offsideAt(match,decision.t,{eventId:decision.event_id}).positions[frame.offenderId].x_m,-100);
    assert.match(frame.label,/not VAR/);
  }
});

test('P3 counters, control and passing match canonical Python summary',()=>{
  const stats=statistics(match,match.duration);
  for(const team of ['home','away']){
    assert.equal(stats.teams[team].offsides,summary.teams[team].offsides);
    assert.equal(stats.teams[team].interceptions,summary.teams[team].interceptions);
    assert.equal(stats.teams[team].shots,summary.teams[team].shots.total);
    assert.equal(stats.teams[team].onTarget,summary.teams[team].shots.on_target);
    assert.equal(stats.teams[team].completed,summary.teams[team].passes.completed);
    assert.equal(stats.teams[team].attempted,summary.teams[team].passes.attempted);
    assert.equal(stats.times[team],summary.teams[team].possession.time_ms);
  }
  assert.equal(stats.times.unassigned,summary.possession.unassigned_time_ms);
});

test('deflection is continuous flight with no early possession or interception credit',()=>{
  assert.ok(actionTypes.includes('deflection'));
  const deflections=match.actions.filter(e=>e.type==='deflection');assert.ok(deflections.length);
  for(const action of deflections.slice(0,12)){
    const board=boardAt(match,(action.kick+action.t)/2);
    assert.equal(board.carrierId,null);
    assert.equal(board.phase,'flight');
    const source=match.events.find(e=>e.event_id===action.source_event_id);
    assert.deepEqual(action.start,source.end);
    assert.equal(source.interceptor_id,null);
    assert.equal(source.deflector_id,action.player_id);
    assert.equal(eventTitle(action),'Deflected ball');
  }
});

test('offside receipt never transfers control; stoppage and labels reflect the decision',()=>{
  for(const decision of match.events.filter(e=>e.type==='offside')){
    const board=boardAt(match,decision.t);
    // A zero-time restart is not used for an offside IFK in this model.
    assert.equal(board.carrierId,null);
    assert.match(eventTitle(decision),/^Offside/);
    const source=match.events.find(e=>e.event_id===decision.source_event_id);
    if(source.outcome_reason==='offside'&&source.type!=='shot'){
      assert.equal(source.recipient_id,null);
      assert.equal(source.outcome,'incomplete');
    }
  }
});

test('an invalid shot observation cannot inflate UI shots, saves or goals',()=>{
  const original=match.events.find(e=>e.type==='shot');assert.ok(original);
  const invalid={...original,valid_for_statistics:false,outcome:'no_goal',outcome_reason:'offside',save_outcome:null};
  const prepared=prepare(metadata,[invalid]);
  const stats=statistics(prepared,invalid.t);
  assert.equal(stats.teams.home.shots+stats.teams.away.shots,0);
  assert.equal(stats.teams.home.saves+stats.teams.away.saves,0);
  assert.equal(stats.teams.home.goals+stats.teams.away.goals,0);
  assert.match(eventTitle(invalid),/invalid/);
});
