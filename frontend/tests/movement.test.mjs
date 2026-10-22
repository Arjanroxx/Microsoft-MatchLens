import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,boardAt,statistics,actionTypes} from '../model.mjs';

const base=new URL('../../data/examples/movement-match/',import.meta.url);
const metadata=JSON.parse(readFileSync(new URL('metadata.json',base)));
const events=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse);
const summary=JSON.parse(readFileSync(new URL('summary.json',base)));
const match=prepare(metadata,events);

test('the board consumes generated movement anchors during control and flight',()=>{
  assert.ok(actionTypes.includes('movement'));
  for(const action of match.actions.slice(0,25)){
    for(const sample of action.player_motion??[]){
      const time=(metadata.period_offsets_ms[String(action.period)]??0)+sample.period_time_ms;
      // At shared completion/kick boundaries the next observation may also
      // have an exact anchor; inspect only interior recorded samples here.
      if(time<=action.kick||time>=action.t)continue;
      const board=boardAt(match,time,{smooth:false});
      for(const [pid,pos] of Object.entries(sample.players)){
        if(pid!==board.carrierId)assert.deepEqual(board.positions[pid],pos);
      }
    }
  }
});

test('carried ball and player move together while passing counters wait for completion',()=>{
  const movement=match.actions.find(e=>e.type==='movement'&&e.ball_trajectory.length>2);
  assert.ok(movement);
  const time=(movement.kick+movement.t)/2,board=boardAt(match,time);
  assert.equal(board.carrierId,movement.carrier_id);
  assert.equal(board.phase,'controlled');
  assert.deepEqual(board.positions[board.carrierId],{x_m:board.ball.x_m,y_m:board.ball.y_m});
  const before=statistics(match,movement.kick),during=statistics(match,time);
  assert.equal(before.teams.home.attempted,during.teams.home.attempted);
  assert.equal(before.teams.away.attempted,during.teams.away.attempted);
});

test('moving receivers do not obtain possession or completion credit before arrival',()=>{
  const pass=match.actions.find(e=>e.type==='pass'&&e.outcome==='complete'&&e.intended_end.x_m!==e.receiver_start.x_m);
  assert.ok(pass);
  const mid=boardAt(match,(pass.kick+pass.t)/2);
  assert.equal(mid.carrierId,null);
  assert.equal(mid.phase,'flight');
  assert.equal(boardAt(match,pass.t).carrierId,pass.recipient_id);
  assert.equal(statistics(match,pass.t).teams[pass.team_id].completed,statistics(match,pass.kick).teams[pass.team_id].completed+1);
});

test('new-schema counters and possession still agree with canonical Python',()=>{
  const actual=statistics(match,match.duration);
  for(const team of ['home','away']){
    const expected=summary.teams[team],got=actual.teams[team];
    assert.equal(got.goals,expected.goals);
    assert.equal(got.attempted,expected.passes.attempted);
    assert.equal(got.completed,expected.passes.completed);
    assert.equal(got.shots,expected.shots.total);
    assert.equal(got.offsides,expected.offsides);
    assert.equal(actual.times[team],expected.possession.time_ms);
  }
});

test('recovery and restart runs animate without inventing ball movement or early possession',()=>{
  const paths=match.actions.filter(e=>e.type==='reposition');assert.ok(paths.length);
  for(const action of paths.slice(0,15)){
    const board=boardAt(match,(action.kick+action.t)/2);
    assert.equal(board.carrierId,null);
    assert.equal(board.phase,'repositioning');
    assert.deepEqual(board.ball,action.start);
    assert.deepEqual(action.start,action.end);
    if(action.reason==='restart_setup'||action.reason==='restart_taker'){
      const a=statistics(match,action.kick),b=statistics(match,action.t);
      assert.equal(a.times.home+a.times.away,b.times.home+b.times.away);
    }
  }
});
