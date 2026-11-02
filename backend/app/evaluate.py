"""Repeatable real-model or demo evaluation; exit nonzero on failed contracts."""
import argparse
import json
from pathlib import Path
from .agent_providers import DemoAgents,OllamaAgents
from .contracts import ViewerProfile
from .match_store import MatchStore
from .workflow import IntelligenceWorkflow


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('data/examples/movement-match'))
    parser.add_argument('--provider',choices=('demo','ollama'),default='demo')
    parser.add_argument('--model',default='qwen3:1.7b')
    parser.add_argument('--output',type=Path,default=Path('data/generated/agent-evaluation.json'))
    args=parser.parse_args()
    store=MatchStore.load(args.input)
    provider=DemoAgents() if args.provider=='demo' else OllamaAgents(args.model)
    if not provider.health()['ready']:parser.error('Provider unavailable; start Ollama and pull the configured model')
    workflow=IntelligenceWorkflow(provider)
    shot=next(e for e in store.events if e['type']=='shot')
    goal=next((e for e in store.events if e['type']=='goal'),shot)
    half=next(e for e in store.events if e['type']=='period_end')
    cases=[('opening_shot',shot['match_time_ms'],ViewerProfile(),None),
           ('key_moment_analyst',goal['match_time_ms'],ViewerProfile(audience_mode='analyst'),None),
           ('key_moment_hindi',goal['match_time_ms'],ViewerProfile(locale='hi'),None),
           ('halftime_recap',half['match_time_ms'],ViewerProfile(),'full')]
    results=[]
    for name,t,profile,scope in cases:
        r=workflow.generate(store,t,profile,name,scope=scope)
        available={e['event_id'] for e in store.prefix(t)}
        checks={'expected_status':r['status']==('demo' if args.provider=='demo' else 'verified'),
                'three_roles':len([s for s in r['trace'] if s['kind']=='agent'])==3,
                'same_snapshot':all(s['snapshot_id']==r['snapshot_id'] for s in r['trace']),
                'source_prefix':bool(r['claims']) and set(r['source_event_ids'])<=available,
                'claim_snapshots':all(c['snapshot_id']==r['snapshot_id'] for c in r['claims'])}
        results.append({'case':name,'checks':checks,'result':r})
        print(f"{name}: {r['status']} | {r['latency_ms']} ms | checks={all(checks.values())}",flush=True)
    report={'provider':provider.name,'model':provider.model,'passed':all(all(r['checks'].values()) for r in results),'cases':results}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
