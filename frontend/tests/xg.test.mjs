import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,statistics} from '../model.mjs';
import {shotXg,expectedGoalsAt} from '../xg.mjs';
const base=new URL('../../data/examples/xg-match/',import.meta.url);
const metadata=JSON.parse(readFileSync(new URL('metadata.json',base)));
const events=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse);
const summary=JSON.parse(readFileSync(new URL('summary.json',base)));
const match=prepare(metadata,events);
const keys=['xg','non_penalty_xg','xg_per_shot','goals_minus_xg','xg_assisted','shot_conversion_percentage','shot_accuracy_percentage','xg_coverage','xg_model'];
test('every shot calculation matches the Python source fields',()=>{
  for(const e of events.filter(e=>e.type==='shot'))assert.deepEqual(shotXg(e,match.players),e.xg);
});
test('player and team xG statistics match Python, including creation credit',()=>{
  const actual=expectedGoalsAt(match,match.duration),stats=statistics(match,match.duration);
  for(const group of ['players','teams'])for(const [id,row] of Object.entries(actual[group]))for(const key of keys)assert.deepEqual(row[key],summary[group][id][key],`${group}.${id}.${key}`);
  for(const team of ['home','away'])assert.equal(stats.teams[team].xg,summary.teams[team].xg);
  assert.ok(actual.teams.home.xg_assisted>0);
});
test('no future xG, rewind, invalid attacks and missing evidence',()=>{
  const shot=match.events.find(e=>e.type==='shot');
  assert.equal(expectedGoalsAt(match,shot.t-1).teams[shot.team_id].xg,0);
  assert.ok(expectedGoalsAt(match,shot.t).teams[shot.team_id].xg>0);
  assert.equal(expectedGoalsAt(match,0).teams[shot.team_id].xg,0);
  const invalid={...match,events:match.events.map(e=>e.type==='shot'?{...e,valid_for_statistics:false}:e)};
  assert.equal(expectedGoalsAt(invalid,match.duration).teams.home.xg,0);
  const missing={...match,events:match.events.map(e=>e.type==='shot'?{...e,pitch_snapshot:null}:e)};
  assert.equal(expectedGoalsAt(missing,match.duration).teams.home.xg,null);
  assert.equal(expectedGoalsAt(missing,match.duration).teams.home.xg_coverage.complete,false);
});
test('outcome speed and aim cannot change pre-shot quality',()=>{
  const e=events.find(e=>e.type==='shot');
  assert.deepEqual(shotXg({...e,outcome:'goal',shot_speed:{kmh:999},end:{x_m:0,y_m:0}},match.players),shotXg(e,match.players));
});
test('full legacy movement, penalty and offside fixtures match Python player/team goldens',()=>{
  const refs=JSON.parse(readFileSync(new URL('fixtures/xg-legacy-totals.json',import.meta.url)));
  for(const [name,expected] of Object.entries(refs)){
    const base=new URL(`../../data/examples/${name}/`,import.meta.url);
    const m=prepare(JSON.parse(readFileSync(new URL('metadata.json',base))),readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse));
    const a=expectedGoalsAt(m,m.duration);
    for(const group of ['teams','players'])for(const [id,row] of Object.entries(expected[group]))for(const [key,v] of Object.entries(row))assert.deepEqual(a[group][id][key],v,`${name}.${group}.${id}.${key}`);
  }
});
