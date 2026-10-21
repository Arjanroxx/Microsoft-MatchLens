import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,boardAt,lineupsAt,statistics,eventTitle} from '../model.mjs';

const base=new URL('../../data/examples/substitutions-match/',import.meta.url);
const metadata=JSON.parse(readFileSync(new URL('metadata.json',base)));
const events=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse);
const summary=JSON.parse(readFileSync(new URL('summary.json',base)));
const match=prepare(metadata,events);

test('bench players are not drawn at kickoff',()=>{
  assert.equal(metadata.players.length,40);
  assert.equal(Object.keys(boardAt(match,0).positions).length,22);
  assert.equal(lineupsAt(match,0).bench.length,18);
});

test('substitution swaps exactly one marker without leaking incoming players early',()=>{
  const groups=new Map();
  for(const event of match.events.filter(e=>e.type==='substitution'))groups.set(event.t,event);
  for(const [time,last] of groups){
    const atTime=match.events.filter(e=>e.type==='substitution'&&e.t===time);
    const before=lineupsAt(match,time-1),after=lineupsAt(match,time);
    for(const event of atTime){
      assert.ok(before.onPitch.includes(event.player_off_id));
      assert.ok(before.bench.includes(event.player_on_id));
      assert.ok(after.substitutedOff.includes(event.player_off_id));
      assert.ok(after.onPitch.includes(event.player_on_id));
    }
    assert.equal(after.onPitch.length,22);
    assert.deepEqual(Object.keys(boardAt(match,time).positions).sort(),Object.keys(last.positions_after).sort());
    assert.equal(typeof eventTitle(last),'string');
  }
});

test('half-time reset and rewind preserve the correct lineup',()=>{
  assert.ok(match.events.some(e=>e.type==='substitution'&&e.halftime));
  assert.equal(Object.keys(boardAt(match,metadata.period_duration_ms).positions).length,22);
  assert.deepEqual(lineupsAt(match,match.duration).onPitch.sort(),Object.keys(boardAt(match,match.duration).positions).sort());
  assert.equal(lineupsAt(match,0).substitutedOff.length,0);
  assert.equal(Object.keys(boardAt(match,0).positions).length,22);
});

test('substitution stoppages leave no possession attributed during the break',()=>{
  for(const stop of match.events.filter(e=>e.type==='stoppage')){
    const resume=match.events.find(e=>e.sequence>stop.sequence&&e.type==='resume');
    if(!resume||resume.t===stop.t)continue;
    const before=statistics(match,stop.t),after=statistics(match,resume.t);
    assert.equal(after.times.home+after.times.away,before.times.home+before.times.away);
    assert.equal(boardAt(match,stop.t).carrierId,null);
    assert.equal(boardAt(match,stop.t).phase,'stoppage');
  }
});

test('possession matches Python after substitution stoppages',()=>{
  const result=statistics(match,match.duration);
  for(const team of ['home','away'])assert.equal(result.times[team],summary.teams[team].possession.time_ms);
  assert.equal(result.times.unassigned,summary.possession.unassigned_time_ms);
});
