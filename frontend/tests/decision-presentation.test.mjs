import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,boardAt,statistics,disciplineAt,offsideAt} from '../model.mjs';
import {decisionAt,nextDecision} from '../decisions.mjs';
import {decisionView,offsideReview} from '../decision-ui.mjs';
import {PITCH,fieldMarkings} from '../pitch.mjs';
function fixture(name){const base=new URL('../../data/examples/'+name+'/',import.meta.url);return prepare(JSON.parse(readFileSync(new URL('metadata.json',base))),readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse));}
const match=fixture('offside-match'),discipline=fixture('discipline-match');
test('offside notice starts at whistle, uses original contact evidence and ends at restart release',()=>{
 const event=match.events.find(e=>e.type==='offside');assert.equal(decisionAt(match,event.t-1),null);
 const state=decisionAt(match,event.t);assert.equal(state.event.event_id,event.event_id);assert.equal(state.kind,'offside');assert.equal(state.stage,'stopped');
 const frame=offsideAt(match,event.t);const source=match.events.find(e=>e.event_id===event.source_event_id);assert.deepEqual(frame.positions,source.pitch_snapshot.players);
 const markup=offsideReview(frame,match);assert.match(markup,/Frozen offside evidence/);assert.ok(markup.includes(String(event.contact.line_x_m)));assert.ok(markup.includes(String(event.contact.second_last_opponent_x_m)));
 const restart=match.events.find(e=>e.type==='restart'&&e.source_event_id===event.event_id);const resume=match.events.find(e=>e.type==='resume'&&e.sequence>restart.sequence);assert.equal(decisionAt(match,resume.t),null);
});
test('advantage is shown as continued play and never invents a stoppage',()=>{
 const played=discipline.events.find(e=>e.type==='advantage'&&e.outcome==='played');assert.ok(played);
 const foul=discipline.events.find(e=>e.event_id===played.foul_event_id),state=decisionAt(discipline,played.t);
 assert.equal(state.event.event_id,foul.event_id);assert.equal(state.stage,'advantage');assert.equal(state.stop,null);
 assert.match(decisionView(discipline,state,String),/No free kick has been given/);
});
test('penalty is awarded explicitly, setup matches recorded anchors and result stays hidden until completion',()=>{
 const foul=match.events.find(e=>e.type==='foul'&&e.restart.type==='penalty'),state=decisionAt(match,foul.t);
 assert.equal(state.kind,'penalty');assert.equal(state.result,null);assert.equal(state.takerId,null);assert.deepEqual(state.spot,foul.restart.location);
 const restart=match.events.find(e=>e.type==='restart'&&e.source_event_id===foul.event_id),shot=match.actions.find(e=>e.restart_event_id===restart.event_id);
 const setup=decisionAt(match,shot.kick);assert.equal(setup.stage,'ready');assert.equal(setup.result,null);assert.equal(setup.keeperId,shot.goalkeeper_id);
 const board=boardAt(match,shot.kick);assert.deepEqual(board.positions,shot.pitch_snapshot.players);assert.equal(board.carrierId,null);
 const goalX=foul.restart.location.x_m<52.5?0:105;
 assert.equal(board.positions[shot.player_id].x_m,foul.restart.location.x_m);assert.equal(board.positions[shot.goalkeeper_id].x_m,goalX);
 const unseen=decisionAt(match,shot.t-1);assert.equal(unseen.result,null);assert.equal(unseen.stage,'flight');assert.doesNotMatch(decisionView(match,unseen,String),/Penalty saved|Penalty scored|Penalty missed/);
 const result=decisionAt(match,shot.t);assert.equal(result.result.event_id,shot.event_id);
});
test('jump/pause searches preserve timestamp ties and decision order at any playback speed',()=>{
 const expected=match.events.filter(e=>['foul','offside'].includes(e.type));let time=-1;
 for(const event of expected){const next=nextDecision(match,time,event.t+100000);assert.equal(next.event_id,event.event_id);time=event.t;}
 assert.equal(nextDecision(match,match.duration),null);assert.equal(nextDecision(match,-1,Infinity,'penalty').restart.type,'penalty');
});
test('every foul changes only the named offender counter at its source timestamp and rewinds cleanly',()=>{
 for(const foul of discipline.events.filter(e=>e.type==='foul')){
  const before=disciplineAt(discipline,foul.t-1),after=disciplineAt(discipline,foul.t);
  assert.equal(after[foul.player_id].fouls,before[foul.player_id].fouls+1);
  assert.equal(statistics(discipline,foul.t).teams[foul.team_id].fouls,statistics(discipline,foul.t-1).teams[foul.team_id].fouls+1);
 }
 assert.ok(Object.values(disciplineAt(discipline,0)).every(p=>p.fouls===0));
});
test('pitch proportions use simulator metres, centred boxes, halfway line and penalty arc intersections',()=>{
 assert.equal(PITCH.penaltyDepth,16.5);assert.equal(PITCH.spotDistance,11);assert.equal((PITCH.width-PITCH.penaltyWidth)/2,13.84);
 const svg=fieldMarkings();assert.match(svg,/M52.5 0V68/);assert.ok(svg.includes('width="16.5" height="40.32"'));assert.ok(svg.includes('cx="94"'));assert.ok(svg.includes('width="5.5" height="18.32"'));
});
