// Local intelligence transport and stale-response guard. No model credentials in browser.
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function acceptsInsight(result,context){
  return result?.schema_version==='matchlens-insight-v1'&&result.match_id===context.matchId&&
    result.session_epoch===context.epoch&&result.as_of_match_time_ms===context.requestedTime&&
    Number.isFinite(result.as_of_match_time_ms)&&Number.isFinite(result.display_until_match_ms)&&result.as_of_match_time_ms<=context.currentTime&&result.display_until_match_ms>=context.currentTime&&
    JSON.stringify(result.profile)===JSON.stringify(context.profile)&&
    ['verified','demo','fallback','no_story'].includes(result.status);
}

export function createIntelligence({getContext,onLiveSource,notify}){
  const $=id=>document.getElementById(id);
  let epoch=crypto.randomUUID(),pending=false,serial=0,lastAuto=-Infinity,lastCatchup=null,sourceId=null;
  let controller=null,automatic=false,health=null,followLive=true,liveCursor=0,pollTimer=null,lastRecapSequence=0,shown=null;
  const currentProfile=()=>({audience_mode:$('ai-audience').value,locale:$('ai-locale').value,
    team_id:$('ai-team').value||null,player_id:$('ai-player').value||null,metric_focus:$('ai-metric').value});
  function setState(value){$('ai-panel').setAttribute('data-state',value);$('ai-content').setAttribute('aria-busy',String(value==='thinking'));}
  function setBusy(value){pending=value;for(const id of ['ai-request','ai-recap','catchup'])$(id).disabled=value;}
  const invalidate=()=>{epoch=crypto.randomUUID();serial++;controller?.abort();setBusy(false);shown=null;setState('ready');lastAuto=-Infinity;lastCatchup=null;$('ai-content').innerHTML='<div class="ai-welcome"><span class="commentary-kicker">FROM THE COMMENTARY BOX</span><h4>Let’s look a little closer.</h4><p>Pick a moment on the pitch, and I’ll put the numbers into context.</p></div>';$('ai-request').disabled=false;};
  function profileChanged(){const {match}=getContext();const player=match?.players[$('ai-player').value];if(player)$('ai-team').value=player.team_id;invalidate();}
  for(const id of ['ai-audience','ai-locale','ai-team','ai-player','ai-metric'])$(id).onchange=()=>{
    if(id==='ai-team')$('ai-player').value='';profileChanged();
  };
  function render(result){
    const label={verified:'AI · checked against the match',demo:'Demo commentary · no AI',fallback:'Match facts · AI unavailable',no_story:'Waiting for the next story'}[result.status];
    shown=result;setState(result.status==='fallback'?'offline':'ready');
    const time=`${Math.floor(result.as_of_match_time_ms/60000)}:${String(Math.floor(result.as_of_match_time_ms/1000)%60).padStart(2,'0')}`;
    const receipt={snapshot_id:result.snapshot_id,through_sequence:result.through_sequence,claims:result.claims,evidence_ids:result.evidence_ids,source_event_ids:result.source_event_ids,limitations:result.limitations,verification:result.verification};
    $('ai-content').innerHTML=`<div class="ai-result" lang="${esc(result.locale)}"><div class="ai-result-meta"><span class="ai-state ${esc(result.status)}">${label}</span><span>Replay ${esc(time)}${result.cached?' · cached':''}</span></div><h4>${esc(result.headline)}</h4><p>${esc(result.explanation)}</p><details><summary>Why this? · ${result.claims.length} match facts</summary><pre>${esc(JSON.stringify(receipt,null,2))}</pre></details><details><summary>Model details · ${(result.latency_ms/1000).toFixed(1)} s${result.usage?' · '+result.usage.total_token_count+' tokens':''}</summary><pre>${esc(JSON.stringify({provider:result.provider,model:result.model,real_model:result.real_model,trace_id:result.trace_id,usage:result.usage,fallback_reason:result.fallback_reason,stages:result.trace},null,2))}</pre></details></div>`;
  }
  async function post(path,body,signal){
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
    let result;try{result=await response.json();}catch{throw Error('Start the local intelligence backend to use this feature.');}
    return {response,result};
  }
  async function request(scope=null){
    const {match,time}=getContext();if(!match||pending)return;
    const requestSerial=++serial,requestEpoch=epoch,profile=currentProfile(),requestedTime=Math.floor(time);
    const activeController=new AbortController();controller=activeController;setBusy(true);setState('thinking');
    $('ai-content').innerHTML='<div class="ai-thinking"><span class="commentary-kicker">LEO IS LOOKING AT THE PLAY</span><h4>There’s more to this moment…</h4><p>Checking the play and the numbers behind it. You can keep watching while I work.</p><div class="commentary-pulse" aria-hidden="true"><i></i><i></i><i></i></div></div>';
    const body={match_id:match.metadata.match_id,time_ms:requestedTime,session_epoch:requestEpoch,profile};
    if(scope){body.scope=scope;if(scope==='catchup'&&lastCatchup!==null)body.since_ms=lastCatchup;}
    try{
      let reply=await post(scope?'/api/recaps':'/api/insights',body,activeController.signal);
      if(reply.response.status===404&&reply.result.code==='unknown_match'){
        const registration=await post('/api/matches',{metadata:match.metadata,events:match.events.map(({t,kick,...source})=>source)},activeController.signal);
        if(!registration.response.ok)throw Error(registration.result.error||'Could not register this match');
        reply=await post(scope?'/api/recaps':'/api/insights',body,activeController.signal);
      }
      if(reply.response.status===429)throw Error('I’m finishing another moment. Give me a few seconds, then try again.');
      if(!reply.response.ok)throw Error(reply.result.error||'Intelligence request failed');
      if(requestSerial!==serial)return;
      const now=getContext();
      if(!acceptsInsight(reply.result,{matchId:now.match?.metadata.match_id,epoch,requestedTime,currentTime:now.time,profile:currentProfile()})){
        $('ai-content').innerHTML='<p class="ai-empty">The match has moved on. Ask me about the moment you’re watching now.</p>';return;
      }
      render(reply.result);if(scope==='catchup')lastCatchup=requestedTime;
    }catch(error){if(error.name!=='AbortError'&&requestSerial===serial)$('ai-content').innerHTML=`<p class="ai-error" role="status">${esc(error.message)}</p>`;}
    finally{if(requestSerial===serial){setBusy(false);setState(shown?.status==='fallback'?'offline':'ready');}}
  }
  $('ai-request').onclick=()=>request();
  $('ai-auto').onclick=()=>{automatic=!automatic;$('ai-auto').setAttribute('aria-pressed',String(automatic));$('ai-auto').textContent=automatic?'Auto commentary on':'Auto commentary off';};
  $('ai-recap').onclick=()=>request($('ai-scope').value);
  $('catchup').onclick=()=>{request('catchup');$('ai-panel').scrollIntoView({behavior:globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});};
  $('ai-follow').onclick=()=>{followLive=!followLive;$('ai-follow').setAttribute('aria-pressed',String(followLive));$('ai-follow').textContent=followLive?'Following stream':'Follow stream';};
  async function pollLive(){
    if(health?.mode!=='live')return;
    try{
      const response=await fetch('/api/live?after_sequence='+liveCursor);if(!response.ok)return;
      const update=await response.json();
      // Initial fixture loading can finish after the first poll and reset the
      // replay to kick-off. Reconcile the watermark even when no new rows arrive.
      if(update.events.length||(followLive&&getContext().time<update.time_ms)){
        onLiveSource(update,followLive);liveCursor=update.through_sequence;
      }
    }catch(error){$('ai-provider').title='Live stream: '+error.message;notify('Live feed could not update: '+error.message);}
    finally{pollTimer=setTimeout(pollLive,1500);}
  }
  async function checkHealth(){
    try{
      const response=await fetch('/api/health');if(!response.ok)throw Error('unavailable');health=await response.json();
      $('ai-provider').textContent=health.provider.ready?(health.provider.real_model?'Local AI connected':'Demo mode · no AI'):'Match facts mode · AI offline';
      $('ai-provider').title=health.provider.detail+(health.provider.model?' · '+health.provider.model:'');
      $('ai-follow').hidden=health.mode!=='live';
      if(health.mode==='live'&&!pollTimer){liveCursor=0;pollTimer=setTimeout(pollLive,0);}
    }catch{$('ai-provider').textContent='Commentary disconnected';}
  }
  $('ai-refresh').onclick=checkHealth;checkHealth();
  return {invalidate,request,requestRecap:scope=>request(scope),onTime(t){
    if(shown&&t>shown.display_until_match_ms&&!pending){shown=null;$('ai-content').innerHTML='<div class="ai-welcome"><h4>On to the next chapter.</h4><p>Ask me about the moment you’re watching now.</p></div>';}
    if(automatic&&!pending){
      const {match}=getContext();
      const boundary=match?.events.findLast(e=>e.type==='period_end'&&e.t<=t&&t-e.t<10000);
      if(boundary&&boundary.sequence!==lastRecapSequence){lastRecapSequence=boundary.sequence;lastAuto=t;request('full');}
      else if(t-lastAuto>=30000){lastAuto=t;request();}
    }
  },onMatch(match){
    sourceId=match.metadata.match_id;lastRecapSequence=0;invalidate();
    $('ai-team').innerHTML='<option value="">Both teams</option>'+match.metadata.teams.map(t=>`<option value="${esc(t.team_id)}">${esc(t.name)}</option>`).join('');
    $('ai-player').innerHTML='<option value="">All players</option>'+Object.values(match.players).map(p=>`<option value="${esc(p.player_id)}">${esc(p.name)}</option>`).join('');
  }};
}
