// Execute the actual app against the P3 fixture, including the optional API wiring.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('P3 event inspector renders frozen evidence and player inspector consumes canonical API shape',async()=>{
  class Element {
    constructor(){this.innerHTML='';this.textContent='';this.value='0';this.style={};this.hidden=false;this.open=false;this.lastElementChild={textContent:''};this.listeners={};this.classList={add(){},remove(){},toggle(){}};}
    setAttribute(){} addEventListener(type,fn){this.listeners[type]=fn;}click(){this.onclick?.();}showModal(){this.open=true;}close(){this.open=false;}
  }
  const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const listeners={};
  globalThis.document={getElementById:get,querySelector:get,querySelectorAll:()=>[],activeElement:{tagName:'BODY'},addEventListener:(name,fn)=>listeners[name]=fn};
  globalThis.requestAnimationFrame=()=>{};
  const base=new URL('../../data/examples/offside-match/',import.meta.url);
  const metadata=JSON.parse(readFileSync(new URL('metadata.json',base)));
  const events=readFileSync(new URL('events.jsonl',base),'utf8').trim().split('\n').map(JSON.parse);
  const summary=JSON.parse(readFileSync(new URL('summary.json',base)));
  const requests=[];
  globalThis.fetch=async path=>{
    requests.push(path);
    // This test verifies DOM integration/field mapping. Python API tests check
    // the event-prefix correctness of real state responses independently.
    if(path.startsWith('/api/state'))return {ok:true,json:async()=>({match_id:metadata.match_id,...summary,as_of_match_time_ms:Number(new URL(path,'http://localhost').searchParams.get('time_ms'))})};
    const data=readFileSync(new URL(path.endsWith('metadata.json')?'metadata.json':'events.jsonl',base),'utf8');
    return {ok:true,json:async()=>JSON.parse(data),text:async()=>data};
  };
  const nativeTimeout=globalThis.setTimeout;globalThis.setTimeout=()=>0;
  try{
    await import('../app.mjs');await new Promise(setImmediate);
    assert.equal(get('status').textContent,'');
    const decision=events.find(e=>e.type==='offside');assert.ok(decision);
    get('seek').oninput({target:{value:decision.match_time_ms}});
    listeners.click({target:{closest:s=>s==='[data-event]'?{dataset:{event:decision.event_id}}:null}});
    assert.match(get('evidence').innerHTML,/Frozen offside evidence at teammate contact/);
    assert.match(get('evidence').innerHTML,/2D point-player model, not VAR/);
    assert.match(get('evidence').innerHTML,/second-last opponent/);
    assert.match(get('comparison').innerHTML,/Offsides/);
    listeners.click({target:{closest:s=>s==='[data-player]'?{dataset:{player:decision.player_id}}:null}});
    await new Promise(setImmediate);
    assert.ok(requests.some(r=>r.startsWith('/api/state?time_ms=')));
    assert.match(get('player-state').innerHTML,/Match rating/);
    assert.match(get('player-state').innerHTML,/matchlens-event-rating-v2/);
    assert.match(get('player-state').innerHTML,/Rating calculation and source event IDs/);
  }finally{globalThis.setTimeout=nativeTimeout;}
});
