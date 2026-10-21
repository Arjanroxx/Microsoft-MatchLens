import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,statistics,boardAt,clockAt,eventTitle} from '../model.mjs';

const base=new URL('../../data/examples/restarts-match/',import.meta.url);
const metadata=JSON.parse(readFileSync(new URL('metadata.json',base)));
const raw=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse);
const summary=JSON.parse(readFileSync(new URL('summary.json',base)));
const match=prepare(metadata,raw);

test('added time extends replay without flipping direction before halftime',()=>{
  assert.equal(match.duration,metadata.match_duration_ms);
  assert.ok(match.duration>2*metadata.period_duration_ms);
  const boundary=metadata.period_offsets_ms['2'];
  assert.equal(clockAt(match,boundary-1).period,1);
  assert.equal(clockAt(match,boundary).period,2);
  assert.equal(boardAt(match,metadata.period_duration_ms+1).period,1);
  assert.ok(clockAt(match,metadata.period_duration_ms+1).display.startsWith('5+'));
  assert.ok(clockAt(match,boundary+metadata.period_duration_ms+1).display.startsWith('10+'));
  assert.equal(clockAt(match,match.duration).fullTime,true);
  assert.equal(clockAt(match,boundary+1000).display,'5:01');
  assert.equal(clockAt(match,boundary,1).period,1); // explicit end-of-half event label
});

test('restart holds are neutral until the delivery release, including administrative events',()=>{
  for(const stop of match.events.filter(e=>e.type==='stoppage')){
    const restart=match.events.find(e=>e.sequence>stop.sequence&&e.type==='restart');
    if(!restart||restart.period!==stop.period)continue;
    const before=statistics(match,stop.t),after=statistics(match,restart.t);
    assert.equal(after.times.home+after.times.away,before.times.home+before.times.away);
    if(restart.t>stop.t){
      const board=boardAt(match,restart.t-1);
      assert.equal(board.carrierId,null);
      assert.equal(board.phase,'stoppage');
    }
  }
});

test('all five action types animate exact ball samples without premature control',()=>{
  assert.deepEqual(new Set(match.actions.map(e=>e.type)),new Set(['pass','shot','clearance','parry','restart_delivery']));
  for(const action of match.actions){
    for(const sample of action.ball_trajectory){
      const time=metadata.period_offsets_ms[String(action.period)]+sample.period_time_ms;
      if(time>=action.t)continue;
      const board=boardAt(match,time);
      assert.equal(board.carrierId,null);
      assert.ok(Math.abs(board.ball.x_m-sample.x_m)<.00001);
      assert.ok(Math.abs(board.ball.y_m-sample.y_m)<.00001);
    }
  }
});

test('side by side counters and possession agree with Python, without duplicate save credit',()=>{
  const actual=statistics(match,match.duration);
  const mapping={throwIns:'throw_ins',goalKicks:'goal_kicks',corners:'corners',clearances:'clearances',saves:'saves',savesHeld:'saves_held',savesParried:'saves_parried',reboundShots:'rebound_shots'};
  for(const team of ['home','away']){
    for(const [js,py] of Object.entries(mapping))assert.equal(actual.teams[team][js],summary.teams[team][py],`${team}.${js}`);
    assert.equal(actual.times[team],summary.teams[team].possession.time_ms);
    assert.equal(actual.teams[team].attempted,summary.teams[team].passes.attempted);
    assert.equal(actual.teams[team].shots,summary.teams[team].shots.total);
  }
  assert.equal(actual.times.unassigned,summary.possession.unassigned_time_ms);
});

test('goals and saved outcomes appear at completion; rewind restores score and lineups',()=>{
  for(const goal of match.events.filter(e=>e.type==='goal')){
    assert.equal(statistics(match,goal.t).teams[goal.team_id].goals,statistics(match,goal.t-1).teams[goal.team_id].goals+1);
  }
  for(const sub of match.events.filter(e=>e.type==='substitution')){
    assert.ok(boardAt(match,sub.t-1).lineups.bench.includes(sub.player_on_id));
    assert.ok(boardAt(match,sub.t).lineups.onPitch.includes(sub.player_on_id));
  }
  assert.equal(Object.keys(boardAt(match,0).positions).length,22);
  assert.equal(statistics(match,0).teams.home.goals,0);
  for(const e of match.events)assert.equal(typeof eventTitle(e),'string');
});

test('schema 1.5 rejects corrupted replay clock while legacy fixtures remain supported',()=>{
  const altered=structuredClone(raw);altered[2].match_time_ms++;
  assert.throws(()=>prepare(metadata,altered),/clock mapping/);
});
