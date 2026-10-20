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
