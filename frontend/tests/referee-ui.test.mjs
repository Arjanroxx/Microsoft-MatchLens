import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
test('actual app pauses exactly at decisions; continuation, penalty setup and foul tracker work',async()=>{
 class Element{constructor(){this.innerHTML='';this.textContent='';this.value='0';this.style={};this.hidden=false;this.attrs={};this.lastElementChild={textContent:''};this.classList={add(){},remove(){},toggle(){}};this.open=false;}setAttribute(k,v){this.attrs[k]=v;}addEventListener(){}click(){this.onclick?.();}}
 const els=new Map(),get=id=>{if(!els.has(id))els.set(id,new Element());return els.get(id);},listeners={};
 globalThis.document={getElementById:get,querySelector:get,querySelectorAll:()=>[],activeElement:{tagName:'BODY'},addEventListener:(k,fn)=>listeners[k]=fn};let frame;
 globalThis.requestAnimationFrame=fn=>frame=fn;
 const base=new URL('../../data/examples/offside-match/',import.meta.url),meta=JSON.parse(readFileSync(new URL('metadata.json',base))),text=readFileSync(new URL('events.jsonl',base),'utf8'),events=text.trim().split('\n').map(JSON.parse);
 globalThis.fetch=async path=>path.startsWith('/api/')?{ok:false}:{ok:true,json:async()=>meta,text:async()=>text};
 await import('../app.mjs');await new Promise(setImmediate);assert.equal(get('status').textContent,'');
 const offside=events.find(e=>e.type==='offside');get('seek').oninput({target:{value:offside.match_time_ms-1}});get('play').click();frame(1000);frame(1010);
 assert.equal(get('seek').value,offside.match_time_ms);assert.equal(get('play').textContent,'▶');assert.equal(get('decision-notice').hidden,false);assert.match(get('decision-content').innerHTML,/Frozen offside evidence/);
 get('continue-decision').click();assert.equal(get('play').textContent,'Ⅱ');assert.equal(get('decision-notice').hidden,true);frame(1020);assert.equal(get('play').textContent,'Ⅱ');get('play').click();
 get('jump-penalty').click();assert.equal(get('decision-notice').attrs['data-kind'],'penalty');assert.match(get('decision-content').innerHTML,/Penalty awarded/);assert.equal(get('penalty-setup').hidden,false);
 get('penalty-setup').click();assert.match(get('decision-content').innerHTML,/One taker. One keeper./);assert.ok(get('players-layer').innerHTML.includes('penalty-duel'));assert.doesNotMatch(get('decision-content').innerHTML,/Penalty saved|Penalty scored/);
 get('jump-foul').click();const time=get('seek').value,lastFoul=events.filter(e=>e.type==='foul'&&e.match_time_ms<=time).at(-1),id=lastFoul.player_id;
 listeners.click({target:{closest:s=>s==='[data-player]'?{dataset:{player:id}}:null}});
 assert.match(get('evidence').innerHTML,/Fouls committed/);const n=events.filter(e=>e.type==='foul'&&e.player_id===id&&e.match_time_ms<=time).length;assert.ok(get('evidence').innerHTML.includes('<b>'+n+'</b><small>Fouls committed'));
 get('restart').click();assert.equal(get('decision-notice').hidden,true);assert.ok(get('field-markings').innerHTML.includes('M52.5 0V68'));
});
