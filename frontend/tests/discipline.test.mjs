import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {prepare,statistics,boardAt,lineupsAt,disciplineAt,eventTitle} from '../model.mjs';

const base=new URL('../../data/examples/discipline-match/',import.meta.url);
const metadata=JSON.parse(readFileSync(new URL('metadata.json',base)));
const events=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse);
const summary=JSON.parse(readFileSync(new URL('summary.json',base)));
const match=prepare(metadata,events);

test('second yellow reduces the active lineup, persists after resets, and rewinds cleanly',()=>{
  const dismissal=match.events.find(e=>e.type==='dismissal'&&e.reason==='second_yellow');
  assert.ok(dismissal);
  const before=boardAt(match,dismissal.t-1),after=boardAt(match,dismissal.t);
  assert.ok(before.positions[dismissal.player_id]);
  assert.ok(!after.positions[dismissal.player_id]);
  assert.ok(after.lineups.sentOff.includes(dismissal.player_id));
  assert.equal(after.discipline[dismissal.player_id].yellowCards,2);
  assert.equal(after.discipline[dismissal.player_id].redCards,1);
  assert.ok(!after.lineups.bench.includes(dismissal.player_id));
  assert.ok(!boardAt(match,match.duration).positions[dismissal.player_id]);
  assert.equal(disciplineAt(match,0)[dismissal.player_id].yellowCards,0);
  assert.equal(lineupsAt(match,0).onPitch.length,22);
});

test('cautions retain players and card counts match Python exactly',()=>{
  const snapshot=statistics(match,match.duration);
  for(const team of ['home','away']){
    assert.equal(snapshot.teams[team].yellowCards,summary.teams[team].yellow_cards);
    assert.equal(snapshot.teams[team].redCards,summary.teams[team].red_cards);
  }
  const first=match.events.find(e=>e.type==='card'&&e.card==='yellow');
  assert.ok(lineupsAt(match,first.t).onPitch.includes(first.player_id));
});

test('free kicks, fouls, tackles and penalties are separate per-team counters',()=>{
  const result=statistics(match,match.duration);
  const mapping={secondYellowDismissals:'second_yellow_dismissals',fouls:'fouls_committed',foulsWon:'fouls_won',freeKicks:'free_kicks',directFreeKicks:'direct_free_kicks',indirectFreeKicks:'indirect_free_kicks',penaltiesWon:'penalties_won',penaltiesConceded:'penalties_conceded',penaltiesTaken:'penalties_taken',penaltiesScored:'penalties_scored',penaltiesMissed:'penalties_missed'};
  for(const team of ['home','away']){
    for(const [js,py] of Object.entries(mapping))assert.equal(result.teams[team][js],summary.teams[team][py],`${team}.${js}`);
    assert.equal(result.teams[team].tackles,summary.teams[team].tackles.attempted);
    assert.equal(result.teams[team].tacklesWon,summary.teams[team].tackles.won);
    assert.equal(result.teams[team].tacklesFoul,summary.teams[team].tackles.foul);
    assert.equal(result.teams[team].tacklesMissed,summary.teams[team].tackles.missed);
    assert.equal(result.teams[team].attempted,summary.teams[team].passes.attempted);
    assert.equal(result.teams[team].interceptions,summary.teams[team].interceptions);
    assert.equal(result.times[team],summary.teams[team].possession.time_ms);
  }
});

test('advantage carries show continuous control and do not inflate pass attempts',()=>{
  for(const carry of match.actions.filter(e=>e.type==='carry')){
    const time=(carry.kick+carry.t)/2,board=boardAt(match,time);
    assert.equal(board.carrierId,carry.player_id);
    assert.equal(board.phase,'controlled');
    assert.deepEqual(board.positions[carry.player_id],{x_m:board.ball.x_m,y_m:board.ball.y_m});
    assert.equal(statistics(match,carry.t).teams[carry.team_id].attempted,statistics(match,carry.kick).teams[carry.team_id].attempted);
  }
  for(const e of match.events.filter(e=>['foul','card','dismissal','advantage','tackle'].includes(e.type)))assert.equal(typeof eventTitle(e),'string');
});

test('foul stoppages and card administration do not accrue possession',()=>{
  for(const stop of match.events.filter(e=>e.type==='stoppage'&&e.reason==='foul')){
    const resume=match.events.find(e=>e.sequence>stop.sequence&&e.type==='resume');
    if(!resume||resume.period!==stop.period)continue;
    const a=statistics(match,stop.t),b=statistics(match,resume.t);
    assert.equal(a.times.home+a.times.away,b.times.home+b.times.away);
    assert.equal(boardAt(match,resume.t-1).carrierId,null);
  }
});

test('keeper reassignment uses the event prefix and does not restore the dismissed keeper',()=>{
  const original=boardAt(match,0).positions,after=structuredClone(original);delete after['home-01'];
  const row=(sequence,time,type,fields={})=>({schema_version:'1.6',match_id:metadata.match_id,event_id:`keeper-test-${sequence}`,sequence,period:1,period_time_ms:time,match_time_ms:time,type,team_id:null,player_id:null,...fields});
  const stream=[row(1,0,'period_start',{positions_after:original}),
    row(2,1000,'card',{team_id:'home',player_id:'home-01',card:'red'}),
    row(3,1000,'dismissal',{team_id:'home',player_id:'home-01',reason:'direct_red',positions_after:after}),
    row(4,1000,'goalkeeper_change',{team_id:'home',player_id:'home-03',previous_goalkeeper_id:'home-01',formation_slot:1,positions_after:after}),
    row(5,2000,'restart',{team_id:'away',player_id:'away-07',reason:'kickoff',start:{x_m:52.5,y_m:34},positions_after:after})];
  const prepared=prepare(metadata,stream);
  assert.equal(lineupsAt(prepared,999).goalkeepers.home,'home-01');
  assert.equal(lineupsAt(prepared,1000).goalkeepers.home,'home-03');
  assert.equal(disciplineAt(prepared,1000)['home-03'].role,'GK');
  assert.equal(Object.keys(boardAt(prepared,2000).positions).length,21);
  assert.ok(!boardAt(prepared,2000).positions['home-01']);
  assert.equal(disciplineAt(prepared,999)['home-03'].role,'DF');
});
