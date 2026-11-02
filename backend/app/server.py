"""Local portfolio server: replay, ordered ingestion and Ollama agent intelligence.

python -m backend.app.server --input data/examples/movement-match --provider ollama
"""
import argparse
import json
import logging
import math
from pathlib import Path
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from simulator.ui_server import Handler as ReplayHandler
from .agent_providers import DemoAgents,OllamaAgents
from .contracts import request_context
from .match_store import MatchStore
from .persistence import Journal
from .workflow import IntelligenceWorkflow,BusyError

LOG=logging.getLogger('matchlens')


class Application:
    def __init__(self,store,provider=None,timeout=120,journal=None):
        self.default=store
        self.stores={store.metadata['match_id']:store}
        self.lock=threading.RLock()
        self.requests=threading.BoundedSemaphore(2)
        self.workflow=IntelligenceWorkflow(provider,timeout=timeout)
        self.journal=journal
        if journal:journal.restore(store)

    def ingest(self,event):
        # Readers cannot observe an event until its durable commit succeeds.
        with self.default.lock:
            result=self.default.ingest(event)
            try:
                if self.journal:self.journal.event(event)
            except Exception:
                if result['accepted']:self.default.rollback_last(event['event_id'])
                raise
            return result

    def store(self,match_id=None):
        with self.lock:
            key=match_id or self.default.metadata['match_id']
            if key not in self.stores:raise KeyError('Match is not registered with this backend')
            return self.stores[key]

    def register(self,body):
        if not isinstance(body,dict) or set(body)!={'metadata','events'} or not isinstance(body['metadata'],dict) or not isinstance(body['events'],list):
            raise ValueError('Supply metadata and events')
        if not body['events'] or len(body['events'])>30000:raise ValueError('Expected 1–30000 events')
        try:store=MatchStore(body['metadata'],body['events'])
        except (KeyError,TypeError,AttributeError) as error:raise ValueError('Malformed match source') from error
        with self.lock:
            key=store.metadata['match_id']
            if key in self.stores:
                old=self.stores[key]
                if old.metadata!=store.metadata or old.events!=store.events:raise ValueError('Match ID already has different source data')
            else:
                if len(self.stores)>=4:
                    evict=next(k for k in self.stores if k!=self.default.metadata['match_id'])
                    del self.stores[evict]
                self.stores[key]=store
        return {'match_id':key,'event_count':len(store.events)}

    def insight(self,body,recap=False):
        if not isinstance(body,dict):raise ValueError('Request must be an object')
        store=self.store(body.get('match_id'))
        t,profile,epoch=request_context(body,store.metadata)
        if not recap and {'scope','since_ms'}&set(body):raise ValueError('Recap fields belong to /api/recaps')
        scope=body.get('scope','full') if recap else None
        if recap and scope not in ('full','half','catchup'):raise ValueError('Unknown recap scope')
        if body.get('since_ms') is not None and scope!='catchup':raise ValueError('since_ms is only supported for catchup')
        result=self.workflow.generate(store,t,profile,epoch,scope=scope,since_ms=body.get('since_ms'))
        if self.journal:self.journal.insight(result)
        LOG.info(json.dumps({'trace_id':result['trace_id'],'match_id':result['match_id'],'snapshot_id':result['snapshot_id'],
            'status':result['status'],'provider':result['provider'],'latency_ms':result['latency_ms'],
            'cached':result['cached'],'usage':result['usage']},ensure_ascii=False))
        return result


class Handler(ReplayHandler):
    protocol_version='HTTP/1.1'
    def payload(self,*args,**kwargs):
        try:super().payload(*args,**kwargs)
        except (BrokenPipeError,ConnectionResetError):pass  # A seek/profile change can abort a browser request.

    def __init__(self,*args,application,**kwargs):
        self.application=application
        super().__init__(*args,view=application.default,**kwargs)

    def do_GET(self):
        parsed=urlsplit(self.path)
        try:
            if parsed.path=='/api/health':
                self.payload({'service':'MatchLens','mode':'replay' if self.application.default.replay else 'live',
                              'provider':self.application.workflow.provider.health()})
            elif parsed.path=='/api/state':
                q=parse_qs(parsed.query)
                if set(q)-{'time_ms','match_id'} or 'time_ms' not in q or any(len(v)!=1 for v in q.values()):
                    raise ValueError('Supply one time_ms and optional match_id')
                self.payload(self.application.store(q.get('match_id',[None])[0]).snapshot(float(q['time_ms'][0])))
            elif parsed.path=='/api/history':
                q=parse_qs(parsed.query)
                if set(q)-{'time_ms','match_id'} or 'time_ms' not in q or any(len(v)!=1 for v in q.values()):
                    raise ValueError('Supply one time_ms and optional match_id')
                store=self.application.store(q.get('match_id',[None])[0])
                snapshot=store.snapshot(float(q['time_ms'][0]))
                results=self.application.journal.history(store.metadata['match_id'],snapshot['as_of_match_time_ms']) if self.application.journal else []
                self.payload({'insights':results})
            elif parsed.path=='/api/live':
                q=parse_qs(parsed.query)
                if set(q)-{'after_sequence'} or any(len(v)!=1 for v in q.values()):raise ValueError('Invalid live cursor')
                after=int(q.get('after_sequence',['0'])[0]);store=self.application.default
                with store.lock:
                    if not 0<=after<=len(store.events):raise ValueError('Invalid live cursor')
                    self.payload({'metadata':store.metadata,'events':store.events[after:],
                                  'through_sequence':len(store.events),'time_ms':store.times[-1] if store.times else 0})
            else:super().do_GET()
        except (ValueError,TypeError) as error:self.payload({'error':str(error)},400)
        except KeyError:self.payload({'error':'Unknown match'},404)

    def do_POST(self):
        # Close after the response: rejected unread bodies must never be parsed
        # as a second request on the same connection.
        self.close_connection=True
        if not self.application.requests.acquire(blocking=False):
            self.payload({'error':'The local server is busy; try again shortly','code':'busy'},429);return
        try:self._post()
        finally:self.application.requests.release()

    def _post(self):
        parsed=urlsplit(self.path)
        if parsed.path not in ('/api/insights','/api/recaps','/api/events','/api/matches'):
            self.payload({'error':'Unknown endpoint'},404);return
        try:
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Use application/json')
            origin=self.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=self.headers.get('Host'):raise ValueError('Cross-origin writes are not supported')
            length=int(self.headers.get('Content-Length','0'))
            limit=64*1024*1024 if parsed.path=='/api/matches' else 2*1024*1024 if parsed.path=='/api/events' else 16*1024
            if not 0<length<=limit:raise ValueError('JSON request body exceeds the endpoint limit')
            def reject_constant(value):raise ValueError('Non-finite JSON numbers are not accepted')
            raw=self.rfile.read(length)
            if len(raw)!=length:raise ValueError('Incomplete request body')
            body=json.loads(raw,parse_constant=reject_constant)
            if parsed.path=='/api/events':self.payload(self.application.ingest(body))
            elif parsed.path=='/api/matches':self.payload(self.application.register(body))
            else:self.payload(self.application.insight(body,recap=parsed.path=='/api/recaps'))
        except BusyError as error:self.payload({'error':str(error),'code':'busy'},429)
        except KeyError:self.payload({'error':'Unknown match; register its source first','code':'unknown_match'},404)
        except (ValueError,TypeError,OverflowError,UnicodeError,RecursionError) as error:self.payload({'error':'Invalid request: '+str(error)[:180]},400)
        except TimeoutError:self.payload({'error':'Request body timed out'},408)
        except Exception:
            LOG.exception('Request failed')
            self.payload({'error':'Request could not be completed'},500)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('data/examples/movement-match'))
    parser.add_argument('--port',type=int,default=8082)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--provider',choices=('ollama','demo'),default='ollama')
    parser.add_argument('--model',default='qwen3:1.7b')
    parser.add_argument('--ollama-host',default='http://127.0.0.1:11434')
    parser.add_argument('--timeout',type=float,default=120)
    parser.add_argument('--database',type=Path,default=Path('data/generated/matchlens.sqlite3'))
    parser.add_argument('--live',action='store_true',help='Start empty; receive ordered source events through POST /api/events')
    args=parser.parse_args()
    if args.host not in ('127.0.0.1','localhost'):parser.error('This local application must bind to 127.0.0.1 or localhost')
    if not math.isfinite(args.timeout) or not 1<=args.timeout<=300:parser.error('Timeout must be 1–300 seconds')
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    try:store=MatchStore.load(args.input,live=args.live)
    except (ValueError,OSError) as error:parser.error(str(error))
    provider=DemoAgents() if args.provider=='demo' else OllamaAgents(args.model,args.ollama_host)
    application=Application(store,provider,args.timeout,Journal(args.database))
    server=ThreadingHTTPServer((args.host,args.port),partial(Handler,application=application))
    print(f'MatchLens: http://{args.host}:{args.port}/ | provider={provider.name}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
