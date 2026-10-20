import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,statistics,boardAt,eventTitle} from '../model.mjs';
const meta=JSON.parse(readFileSync(new URL('../data/metadata.json',import.meta.url))), events=readFileSync(new URL('../data/events.jsonl',import.meta.url),'utf8').trim().split('\n').map(JSON.parse),match=prepare(meta,events);
test('duplicate events do not alter counters',()=>{const duplicate=prepare(meta,[...events,...events]);assert.equal(duplicate.events.length,events.length);assert.deepEqual(statistics(duplicate,match.duration),statistics(match,match.duration));});
test('pass completion is hidden until arrival; kick state and ball are available earlier',()=>{const e=match.actions.find(e=>e.type==='pass');assert.equal(statistics(match,e.t-1).teams[e.team_id].attempted,0);assert.equal(statistics(match,e.t).teams[e.team_id].attempted,1);const b=boardAt(match,e.kick);assert.equal(b.active,true);assert.equal(Object.keys(b.positions).length,22);assert.equal(b.ball.x_m,e.start.x_m);assert.equal(boardAt(match,e.t).active,false);});
test('goals counted once and only at goal completion; rewind resets score',()=>{for(const e of match.events.filter(e=>e.type==='goal')){const before=statistics(match,e.t-1).teams[e.team_id].goals;assert.equal(statistics(match,e.t).teams[e.team_id].goals,before+1);}assert.equal(statistics(match,0).teams.home.goals,0);assert.equal(statistics(match,0).teams.away.goals,0);assert.deepEqual(Object.fromEntries(Object.entries(statistics(match,match.duration).teams).map(([k,v])=>[k,v.goals])),meta.final_score);});
test('unknown roster references and mismatched matches are rejected',()=>{assert.throws(()=>prepare(meta,[{...events[0],match_id:'other'}]));assert.throws(()=>prepare(meta,[{...events[0],player_id:'unknown'}]));});

test('every fixture event has a label, including initial restart and period boundaries',()=>{
  for(const event of events){assert.equal(typeof eventTitle(event),'string');assert.ok(eventTitle(event).length);}
  assert.equal(eventTitle({type:'restart'}),'Play restarts');
  assert.equal(eventTitle({type:'period_start'}),'Half begins');
});

test('smooth movement meets exact snapshot anchors without changing ball trajectory',()=>{
  const i=match.visualFrames.findIndex((f,i)=>i>0&&f.blend&&f.period===match.visualFrames[i-1].period&&f.t-match.visualFrames[i-1].t>2000);
  assert.ok(i>0);
  const previous=match.visualFrames[i-1],next=match.visualFrames[i],time=(previous.t+next.t)/2;
  const smooth=boardAt(match,time),held=boardAt(match,time,{smooth:false});
  const id=Object.keys(previous.positions).find(id=>id!==smooth.carrierId&&next.positions[id]&&Math.abs(previous.positions[id].x_m-next.positions[id].x_m)>0.1);
  assert.ok(id);
  assert.ok(Math.abs(smooth.positions[id].x_m-(previous.positions[id].x_m+next.positions[id].x_m)/2)<0.00001);
  assert.equal(held.positions[id].x_m,previous.positions[id].x_m);
  assert.deepEqual(smooth.ball,held.ball);
  assert.equal(boardAt(match,next.t).positions[id].x_m,next.positions[id].x_m);
});
test('carrier highlight transfers at completion, clears in flight and follows recovery events',()=>{
  const pass=match.actions.find(e=>e.type==='pass'&&e.outcome==='complete');
  assert.equal(boardAt(match,pass.kick).carrierId,null);
  assert.equal(boardAt(match,pass.t-1).carrierId,null);
  assert.equal(boardAt(match,pass.t).carrierId,pass.recipient_id);
  for(const event of match.events.filter(e=>e.type==='recovery')){
    const board=boardAt(match,event.t);
    assert.equal(board.carrierId,event.player_id);
    assert.equal(board.positions[event.player_id].x_m,event.start.x_m);
    assert.equal(board.positions[event.player_id].y_m,event.start.y_m);
  }
});
test('every ball observation and source sequence remain unchanged',()=>{
  assert.deepEqual(match.events.map(e=>e.event_id),events.map(e=>e.event_id));
  for(const action of match.actions){
    for(const point of action.ball_trajectory){
      const time=(action.period-1)*meta.period_duration_ms+point.period_time_ms;
      if(time>=action.t)continue;
      const board=boardAt(match,time);
      assert.ok(Math.abs(board.ball.x_m-point.x_m)<0.00001);
      assert.ok(Math.abs(board.ball.y_m-point.y_m)<0.00001);
      assert.equal(board.carrierId,null);
    }
  }
});
test('timestamp ties use simulator sequence even when input is reversed',()=>{
  const prepared=prepare(meta,[events[1],events[0]]);
  assert.deepEqual(prepared.events.map(e=>e.sequence),[events[0].sequence,events[1].sequence]);
});
