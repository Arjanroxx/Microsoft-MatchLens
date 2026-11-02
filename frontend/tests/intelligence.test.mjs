import test from 'node:test';
import assert from 'node:assert/strict';
import {acceptsInsight,createIntelligence} from '../intelligence.mjs';
const profile={audience_mode:'casual',locale:'en',team_id:null,player_id:null,metric_focus:'all'};
const context={matchId:'match',epoch:'epoch',requestedTime:100,currentTime:110,profile};
const insight={schema_version:'matchlens-insight-v1',match_id:'match',session_epoch:'epoch',as_of_match_time_ms:100,display_until_match_ms:200,profile,status:'verified'};
test('insight can arrive after playback advances inside its display window',()=>assert.ok(acceptsInsight(insight,context)));
test('rewind, new match, old epoch, wrong profile, expiry and tampered cutoff are rejected',()=>{
  for(const change of [{currentTime:99},{currentTime:201},{epoch:'rewound'},{matchId:'another'},{requestedTime:101},{profile:{...profile,locale:'hi'}}])assert.equal(acceptsInsight(insight,{...context,...change}),false);
  assert.equal(acceptsInsight({...insight,status:'unchecked'},context),false);
});

test('live follow reconciles a late fixture reset even without additional events',async()=>{
  const previous={document:globalThis.document,fetch:globalThis.fetch,setTimeout:globalThis.setTimeout};
  const nodes=new Map(),timers=[];let polls=0,updates=0;const current={time:0};
  globalThis.document={getElementById(id){if(!nodes.has(id))nodes.set(id,{value:'',setAttribute(){}});return nodes.get(id);}};
  globalThis.setTimeout=callback=>{timers.push(callback);return timers.length;};
  globalThis.fetch=async url=>({ok:true,json:async()=>url==='/api/health'
    ?{mode:'live',provider:{ready:true,real_model:false,detail:'test'}}
    :{events:polls++===0?[{sequence:1}]:[],through_sequence:1,time_ms:100,metadata:{}}});
  try{
    createIntelligence({getContext:()=>current,notify:message=>assert.fail(message),onLiveSource(){updates++;current.time=updates===1?0:100;}});
    await new Promise(setImmediate);
    await timers.shift()();
    assert.equal(current.time,0); // A fixture finished loading after the first live update.
    await timers.shift()();
    assert.equal(current.time,100);
    assert.equal(updates,2);
  }finally{Object.assign(globalThis,previous);}
});
