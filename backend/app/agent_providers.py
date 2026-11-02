"""Interchangeable three-role runners: honest demo and real local MAF/Ollama."""
import asyncio
import importlib.util
import json
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

PROMPT_VERSION='matchlens-agents-v1'


def require_local_model(details):
    """A local Ollama server can proxy cloud models, including renamed aliases."""
    if not isinstance(details,dict) or details.get('remote_model') or details.get('remote_host'):
        raise ValueError('Cloud-backed Ollama models are disabled; use downloaded local weights')


PROMPTS={
    'analyst': 'You are the MatchLens Analyst. Choose the most relevant supplied candidate. You MUST call lookup_context for your selected candidate before answering. Use only supplied evidence. Return ONLY JSON {"candidate_id":"the selected candidate ID"}. No prose. No other fields. Never invent a candidate.',
    'story': 'You are the MatchLens Story editor. Select a reviewed narrative frame for this evidence. Choose context to explain relevance, or numbers to emphasize measurement. Return ONLY JSON {"frame":"context"} or {"frame":"numbers"}. Final wording and numbers are rendered from verified evidence; do not write prose.',
    'experience': 'You are the MatchLens Experience editor. Select one supplied allowed style for the requested audience and preferences. Return ONLY JSON {"style":"one allowed style"}. You may adapt emphasis, never facts. No other fields.'}


class DemoAgents:
    name='demo'
    model=None
    def health(self):return {'ready':True,'provider':self.name,'real_model':False,'model':None,'detail':'Deterministic demo; no AI inference'}

    async def run(self,role,payload,lookup,trace,remaining):
        if role=='analyst':
            c=payload['candidates'][0]
            lookup(c['candidate_id'])
            return {'candidate_id':c['candidate_id']},None
        if role=='story':return {'frame':'context'},None
        return {'style':payload['allowed_styles'][0]},None


class OllamaAgents:
    name='ollama-maf'
    def __init__(self,model='qwen3:1.7b',host='http://127.0.0.1:11434'):
        endpoint=urlsplit(host)
        if (endpoint.scheme!='http' or endpoint.hostname not in ('127.0.0.1','localhost','::1')
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
                or endpoint.path not in ('','/')):
            raise ValueError('Ollama must use a credential-free local loopback HTTP endpoint')
        if not isinstance(model,str) or not model.strip() or 'cloud' in model.lower():
            raise ValueError('Choose a downloaded local Ollama model; cloud models are disabled')
        self.model=model;self.host=host.rstrip('/')

    def health(self):
        sdk=importlib.util.find_spec('agent_framework') is not None and importlib.util.find_spec('agent_framework_ollama') is not None
        try:
            with urlopen(self.host+'/api/tags',timeout=2) as response:data=json.load(response)
            models=[m.get('name') for m in data.get('models',[])]
            ready=sdk and self.model in models
            detail='Local inference ready' if ready else 'Install the project SDK or pull the configured model'
        except Exception:
            ready=False;models=[];detail='Ollama is unavailable; start Ollama and pull the configured model'
        return {'ready':ready,'provider':self.name,'real_model':True,'model':self.model,'sdk_available':sdk,'models':models,'detail':detail}

    async def run(self,role,payload,lookup,trace,remaining):
        from agent_framework import Agent, tool
        from agent_framework.ollama import OllamaChatClient
        from ollama import AsyncClient
        # Each request owns its HTTP client and event loop; no cross-loop sessions.
        started=time.monotonic()
        native=AsyncClient(host=self.host,timeout=remaining,follow_redirects=False,trust_env=False)
        try:
            response=await native._client.post('/api/show',json={'model':self.model})
            response.raise_for_status()
            require_local_model(response.json())
        except Exception:
            await native._client.aclose()
            raise
        client=OllamaChatClient(client=native,model=self.model,
            function_invocation_configuration={'max_iterations':2,'max_function_calls':2,
                'max_duration_seconds':remaining,'terminate_on_unknown_calls':True,'allow_concurrent_invocation':False})

        @tool(name='lookup_context',approval_mode='never_require',max_invocations=2)
        def lookup_context(candidate_id:str)->str:
            """Read the selected candidate's facts at this immutable snapshot. No future access."""
            return json.dumps(lookup(candidate_id),ensure_ascii=False)

        agent=Agent(client,name='MatchLens_'+role,instructions=PROMPTS[role],
                    tools=[lookup_context] if role=='analyst' else None)
        options={'temperature':0,'max_tokens':180,'think':False,'num_ctx':4096,'keep_alive':'5m'}
        if role!='analyst':options['response_format']='json'
        try:
            result=await asyncio.wait_for(agent.run(json.dumps(payload,ensure_ascii=False),options=options),timeout=remaining)
            text=result.text.strip()
            if text.startswith('```'):
                text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
            decision=json.loads(text)
            if not isinstance(decision,dict):raise ValueError('Agent response is not an object')
            usage=getattr(result,'usage_details',None)
            counts={k:usage.get(k) for k in ('input_token_count','output_token_count','total_token_count')} if usage else None
            # Some small local models emit a structured tool plan as JSON text
            # instead of Ollama's native tool_calls envelope. Normalize ONLY the
            # registered read-only tool, then obtain a separate grounded answer.
            inspected=any(t.get('kind')=='tool' and t.get('candidate_id')==decision.get('candidate_id') for t in trace)
            needs_lookup=role=='analyst' and (set(decision)=={'name','arguments'} or (set(decision)=={'candidate_id'} and not inspected))
            if needs_lookup:
                if set(decision)=={'name','arguments'}:
                    args=decision['arguments']
                    if decision['name']!='lookup_context' or not isinstance(args,dict) or set(args)!={'candidate_id'}:
                        raise ValueError('Unknown structured tool request')
                else:args=decision
                # A small model may prematurely return a candidate without the
                # required lookup. Perform the same allowlisted read, then require
                # a second, grounded model decision. This repair is traceable.
                evidence=lookup(args['candidate_id'])
                trace[-1]['dispatch']='host_normalized_tool_plan_or_missing_lookup'
                remaining-=time.monotonic()-started
                if remaining<=0:raise TimeoutError('Analyst deadline exceeded')
                followup=Agent(client,name='MatchLens_analyst_grounded',instructions=
                    'The registered evidence tool has run. Return ONLY JSON {"candidate_id":"the inspected candidate ID"}. No other fields.')
                final=await asyncio.wait_for(followup.run(json.dumps(evidence,ensure_ascii=False),
                    options={**options,'response_format':'json'}),timeout=remaining)
                decision=json.loads(final.text)
                extra=getattr(final,'usage_details',None)
                if extra:
                    counts={k:(counts or {}).get(k,0)+extra.get(k,0) for k in ('input_token_count','output_token_count','total_token_count')}
            return decision,counts
        finally:
            await native._client.aclose()
