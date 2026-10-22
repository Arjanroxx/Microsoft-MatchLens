// DOM contract smoke test: execute the actual app entrypoint with the real fixture.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
test('app startup draws 22 players; Names, playback, seek and player inspection work',async()=>{
  class Element {
    constructor(){this.innerHTML='';this.textContent='';this.value='0';this.style={};this.hidden=false;this.open=false;this.lastElementChild={textContent:''};this.listeners={};this.classList={add(){},remove(){},toggle(){}};}
    setAttribute(){} addEventListener(type,fn){this.listeners[type]=fn;} click(){this.onclick?.();}showModal(){this.open=true;}close(){this.open=false;}
  }
  const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const listeners={};globalThis.document={getElementById:get,querySelector:get,querySelectorAll:()=>[],activeElement:{tagName:'BODY'},addEventListener:(name,fn)=>listeners[name]=fn};
  globalThis.requestAnimationFrame=()=>{};
  globalThis.fetch=async path=>{const data=readFileSync(new URL('../../data/examples/short-match/'+(path.endsWith('metadata.json')?'metadata.json':'events.jsonl'),import.meta.url),'utf8');return {ok:true,json:async()=>JSON.parse(data),text:async()=>data};};
  const nativeTimeout=globalThis.setTimeout;globalThis.setTimeout=()=>0;
  try {
    await import('../app.mjs');await new Promise(setImmediate);
    assert.equal(get('status').textContent,'','Startup must not trigger the load-error handler');
    assert.equal((get('players-layer').innerHTML.match(/class="player /g)||[]).length,22);
    assert.ok(!get('players-layer').innerHTML.includes('class="name"'));
    assert.ok(get('players-layer').innerHTML.includes('carrier '));
    get('smooth').click();get('smooth').click();
    get('labels').click();assert.equal((get('players-layer').innerHTML.match(/class="name"/g)||[]).length,22);
    get('play').click();assert.equal(get('play').textContent,'Ⅱ');get('play').click();assert.equal(get('play').textContent,'▶');
    get('seek').oninput({target:{value:600000}});assert.equal(String(get('home-score').textContent),'1');assert.equal(String(get('away-score').textContent),'1');
    get('restart').click();assert.equal(String(get('home-score').textContent),'0');assert.equal(String(get('away-score').textContent),'0');
    get('next').click();assert.ok(get('players-layer').innerHTML.includes('home-07'));
    listeners.click({target:{closest:selector=>selector==='[data-player]'?{dataset:{player:'home-07'}}:null}});
    assert.ok(get('evidence').innerHTML.includes('Northbridge Player 07'));
  }finally{globalThis.setTimeout=nativeTimeout;}
});
