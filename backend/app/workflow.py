"""Bounded Analyst -> Story -> Experience orchestration with evidence receipts."""
import asyncio
from collections import OrderedDict
import copy
import json
import threading
import time
import uuid

from .agent_providers import PROMPT_VERSION, DemoAgents
from .contracts import SCHEMA
from .intelligence import build_context, tool_context, render_story
from .match_store import digest


class BusyError(Exception):pass


class IntelligenceWorkflow:
    def __init__(self,provider=None,timeout=120,cache_size=64):
        self.provider=provider or DemoAgents()
        self.timeout=timeout;self.cache_size=cache_size
        self.cache=OrderedDict();self.lock=threading.Lock();self.worker=threading.BoundedSemaphore(1)
        self.ledger=OrderedDict()

    def generate(self,store,t,profile,epoch,*,scope=None,since_ms=None):
        context=build_context(store,t,profile,scope=scope,since_ms=since_ms)
        key=digest([context['state']['snapshot_id'],profile.dictionary(),scope,since_ms,self.provider.name,self.provider.model,PROMPT_VERSION])
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                result=copy.deepcopy(self.cache[key]);result.update(session_epoch=epoch,cached=True)
                return result
        if not self.worker.acquire(blocking=False):raise BusyError('A local inference request is already running; try again shortly')
        try:result=asyncio.run(self._run(context,t,profile,epoch,scope))
        finally:self.worker.release()
        # Provider failures are not cached: recovery can produce real model output.
        with self.lock:
            if result['status']!='fallback':
                self.cache[key]=copy.deepcopy(result)
                while len(self.cache)>self.cache_size:self.cache.popitem(last=False)
            if result['status'] in ('verified','demo'):
                self.ledger[result['insight_id']]=copy.deepcopy(result)
                while len(self.ledger)>256:self.ledger.popitem(last=False)
        return result

    async def _run(self,context,t,profile,epoch,scope):
        started=time.monotonic();state=context['state'];trace=[]
        base={'schema_version':SCHEMA,'match_id':state['match_id'],'snapshot_id':state['snapshot_id'],
              'through_sequence':state['through_sequence'],'as_of_match_time_ms':t,'session_epoch':epoch,
              'profile':profile.dictionary(),'audience_mode':profile.audience_mode,'locale':profile.locale,
              'provider':self.provider.name,'model':self.provider.model,'prompt_version':PROMPT_VERSION,
              'trace_id':uuid.uuid4().hex,'cached':False,'display_from_match_ms':t,
              'display_until_match_ms':t+(300000 if scope else 120000)}
        if not context['candidates']:
            return {**base,'insight_id':digest([state['snapshot_id'],profile.dictionary(),'no_story']),
                    'status':'no_story','headline':'अभी कोई समर्थित कहानी नहीं' if profile.locale=='hi' else 'No supported moment yet',
                    'explanation':'इस पसंद के लिए और घटनाओं की प्रतीक्षा है।' if profile.locale=='hi' else 'Waiting for relevant events or sufficient evidence for this focus.',
                    'claims':[],'evidence_ids':[],'source_event_ids':[],'limitations':[],'trace':[],
                    'latency_ms':0,'usage':None,'real_model':False,'fallback_reason':None}
        selected=context['candidates'][0];frame='context'
        styles=['technical','comparison'] if profile.audience_mode=='analyst' else ['plain','supporter']
        style=styles[0];errors=[];model_stages=0;tool_count=0
        ready=self.provider.health()['ready']

        def lookup(cid):
            nonlocal tool_count
            tool_count+=1
            if tool_count>4:raise ValueError('Tool budget exceeded')
            result=tool_context(context,cid)
            trace.append({'kind':'tool','name':'lookup_context','candidate_id':cid,'snapshot_id':state['snapshot_id'],'status':'ok'})
            # Full source receipts remain on the server; compact model context.
            return {'candidate':result['candidate'],'snapshot_id':result['snapshot_id'],
                    'facts':[{k:f[k] for k in ('evidence_id','metric','value','unit')} for f in result['facts']],
                    'limitations':result['limitations']}

        for role in ('analyst','story','experience'):
            stage_start=time.monotonic();usage=None;failure_detail=None
            try:
                remaining=self.timeout-(stage_start-started)
                if not ready:raise ConnectionError('Local provider is not ready')
                if remaining<=0:raise TimeoutError('Workflow deadline exceeded')
                if role=='analyst':
                    payload={'candidates':context['candidates'],'preferences':profile.dictionary()}
                elif role=='story':
                    payload={'evidence':tool_context(context,selected['candidate_id']),'allowed_frames':['context','numbers']}
                    payload['evidence']['facts']=[{k:f[k] for k in ('evidence_id','metric','value','unit')} for f in payload['evidence']['facts']]
                else:payload={'kind':selected['kind'],'frame':frame,'preferences':profile.dictionary(),'allowed_styles':styles}
                before_tools=tool_count
                decision,usage=await self.provider.run(role,payload,lookup,trace,remaining)
                if role=='analyst':
                    if set(decision)!={'candidate_id'} or tool_count==before_tools:raise ValueError('Analyst must use its evidence tool and select a supplied candidate')
                    selected=next(c for c in context['candidates'] if c['candidate_id']==decision['candidate_id'])
                    if not any(x.get('candidate_id')==selected['candidate_id'] for x in trace if x['kind']=='tool'):
                        raise ValueError('Selected candidate was not inspected')
                elif role=='story':
                    if set(decision)!={'frame'} or decision['frame'] not in ('context','numbers'):raise ValueError('Unsupported story frame')
                    frame=decision['frame']
                else:
                    if set(decision)!={'style'} or decision['style'] not in styles:raise ValueError('Style does not match audience')
                    style=decision['style']
                stage_status='demo' if self.provider.name=='demo' else 'model'
                model_stages+=self.provider.name!='demo'
            except Exception as error:
                stage_status='fallback';errors.append(role+': '+type(error).__name__)
                failure_detail=str(error)[:240]
            trace.append({'kind':'agent','name':role,'status':stage_status,'duration_ms':round((time.monotonic()-stage_start)*1000),
                          'usage':usage,'error':failure_detail,'snapshot_id':state['snapshot_id']})
        claims=[copy.deepcopy(context['facts'][k]) for k in selected['claim_ids']]
        if any(c['snapshot_id']!=state['snapshot_id'] for c in claims):raise ValueError('Evidence crossed snapshots')
        headline,explanation=render_story(context,selected,profile,frame,style)
        source_ids=sorted({i for f in claims for i in f['source_event_ids']}|({selected['event_id']} if selected['event_id'] else set()))
        status='fallback' if errors else 'demo' if self.provider.name=='demo' else 'verified'
        usage_rows=[x['usage'] for x in trace if x.get('usage')]
        usage={k:sum(u[k] for u in usage_rows if isinstance(u.get(k),int)) for k in ('input_token_count','output_token_count','total_token_count')} if usage_rows else None
        return {**base,'insight_id':digest([state['snapshot_id'],selected['candidate_id'],profile.dictionary(),frame,style]),
                'status':status,'headline':headline,'explanation':explanation,'kind':selected['kind'],
                'team_id':selected['team_id'],'player_id':selected['player_id'],'claims':claims,
                'moment_time_ms':selected['event_time_ms'],
                'evidence_ids':[f['evidence_id'] for f in claims],'source_event_ids':source_ids,
                'limitations':['Synthetic football data.','xG and ratings are uncalibrated models.',
                    'AI selects stories and reviewed frames; final text is evidence-rendered, not unrestricted model prose.'],
                'trace':trace,'latency_ms':round((time.monotonic()-started)*1000),'usage':usage,
                'real_model':model_stages==3,'model_stages':model_stages,'fallback_reason':'; '.join(errors) or None,
                'recap_scope':scope,'interval':selected['extra'] if scope else None,
                'verification':{'claims_checked':len(claims),'method':'snapshot_bound_facts_and_reviewed_frames_v1'}}
