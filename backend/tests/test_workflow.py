"""Evidence, replay, orchestration and HTTP contract tests; no model download needed."""
import copy
import functools
import json
from pathlib import Path
import threading
import tempfile
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

from backend.app.agent_providers import DemoAgents
from backend.app.contracts import ViewerProfile
from backend.app.intelligence import build_context
from backend.app.match_store import MatchStore
from backend.app.server import Application,Handler
from backend.app.persistence import Journal
from backend.app.workflow import IntelligenceWorkflow
from simulator.statistics import calculate_statistics

BASE=Path(__file__).resolve().parents[2]/'data/examples/xg-match'


class Failing(DemoAgents):
    name='test-failing'
    async def run(self,*args):raise TimeoutError('test outage')


class Inventing(DemoAgents):
    async def run(self,role,payload,lookup,trace,remaining):
        if role=='analyst':
            lookup(payload['candidates'][0]['candidate_id'])
            return {'candidate_id':'invented'},None
        return await super().run(role,payload,lookup,trace,remaining)


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store=MatchStore.load(BASE)
        cls.time=next(e['match_time_ms'] for e in cls.store.events if e['type']=='shot')

    def test_three_role_handoff_has_same_snapshot_and_source_receipts(self):
        r=IntelligenceWorkflow().generate(self.store,self.time,ViewerProfile(),'epoch')
        self.assertEqual(r['status'],'demo')
        self.assertFalse(r['real_model'])
        self.assertEqual([t['name'] for t in r['trace'] if t['kind']=='agent'],['analyst','story','experience'])
        self.assertTrue(all(t['snapshot_id']==r['snapshot_id'] for t in r['trace']))
        allowed={e['event_id'] for e in self.store.prefix(self.time)}
        self.assertTrue(set(r['source_event_ids'])<=allowed)

    def test_snapshot_rewind_is_independent_and_copies_cannot_poison_cache(self):
        full=self.store.snapshot(self.store.metadata['match_duration_ms'])
        first=self.store.snapshot(0)
        first['teams']['home']['goals']=999
        self.assertEqual(self.store.snapshot(0)['teams']['home']['goals'],0)
        self.assertNotEqual(first['snapshot_id'],full['snapshot_id'])
        self.assertEqual(full['teams'],calculate_statistics(self.store.metadata,self.store.events)['teams'])

    def test_personalization_and_translation_keep_claims(self):
        w=IntelligenceWorkflow()
        a=w.generate(self.store,self.time,ViewerProfile(),'a')
        b=w.generate(self.store,self.time,ViewerProfile(audience_mode='analyst',locale='hi'),'b')
        self.assertEqual(a['claims'],b['claims'])
        self.assertNotEqual(a['explanation'],b['explanation'])
        self.assertIn('Evidence:',w.generate(self.store,self.time,ViewerProfile(audience_mode='analyst'),'c')['explanation'])

    def test_cache_rebinds_epoch_and_profile_does_not_collide(self):
        w=IntelligenceWorkflow()
        a=w.generate(self.store,self.time,ViewerProfile(),'a')
        b=w.generate(self.store,self.time,ViewerProfile(),'new')
        self.assertTrue(b['cached']);self.assertEqual(b['session_epoch'],'new')
        self.assertEqual(a['insight_id'],b['insight_id'])
        c=w.generate(self.store,self.time,ViewerProfile(locale='hi'),'new')
        self.assertFalse(c['cached'])

    def test_provider_failure_remains_factual_and_is_not_cached(self):
        w=IntelligenceWorkflow(Failing())
        for _ in range(2):
            r=w.generate(self.store,self.time,ViewerProfile(),'a')
            self.assertEqual(r['status'],'fallback');self.assertFalse(r['cached']);self.assertFalse(r['real_model'])
            self.assertTrue(r['claims']);self.assertIn('TimeoutError',r['fallback_reason'])

    def test_unknown_model_candidate_cannot_escape_evidence(self):
        r=IntelligenceWorkflow(Inventing()).generate(self.store,self.time,ViewerProfile(),'a')
        self.assertEqual(r['status'],'fallback')
        self.assertNotIn('invented',r['source_event_ids'])

    def test_no_story_and_unknown_profiles(self):
        r=IntelligenceWorkflow().generate(self.store,0,ViewerProfile(),'a')
        self.assertEqual(r['status'],'no_story');self.assertEqual(r['claims'],[])
        for p in ({'locale':'xx'},{'player_id':'bad'},{'team_id':'bad'},{'metric_focus':'fake'},{'player_id':'home-01','team_id':'away'}):
            with self.assertRaises(ValueError):ViewerProfile.parse(p,self.store.metadata)

    def test_recap_scope_windows_and_future_cutoffs(self):
        w=IntelligenceWorkflow()
        for scope in ('full','half','catchup'):
            r=w.generate(self.store,self.time,ViewerProfile(),'a',scope=scope)
            self.assertEqual(r['recap_scope'],scope)
            self.assertTrue(all(c['window'] is None or c['window'][1]<=self.time for c in r['claims']))
        for invalid in (-1,float('nan'),float('inf'),self.store.metadata['match_duration_ms']+1):
            with self.assertRaises(ValueError):self.store.snapshot(invalid)

    def test_ingestion_is_ordered_idempotent_atomic_and_prefix_limited(self):
        live=MatchStore(self.store.metadata,replay=False)
        rows=self.store.events[:12]
        with self.assertRaises(ValueError):live.ingest(rows[1])
        for row in rows:live.ingest(row)
        self.assertTrue(live.ingest(rows[-1])['duplicate'])
        corrupt=copy.deepcopy(rows[-1]);corrupt['type']='different'
        with self.assertRaises(ValueError):live.ingest(corrupt)
        with self.assertRaises(ValueError):live.snapshot(self.time)
        t=rows[-1]['match_time_ms']
        self.assertEqual(live.snapshot(t)['teams'],self.store.snapshot(t)['teams'])
        self.assertEqual(len(live.events),12)

    def test_http_routes_and_invalid_requests(self):
        app=Application(self.store,DemoAgents())
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,application=app))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def post(path,body,**headers):
            return urlopen(Request(base+path,json.dumps(body).encode(),{'Content-Type':'application/json',**headers}),timeout=10)
        body={'match_id':self.store.metadata['match_id'],'time_ms':self.time,'session_epoch':'http','profile':{}}
        try:
            with urlopen(base+'/api/health') as r:self.assertFalse(json.load(r)['provider']['real_model'])
            with post('/api/insights',body) as r:self.assertEqual(json.load(r)['status'],'demo')
            with post('/api/recaps',{**body,'scope':'catchup'}) as r:self.assertEqual(json.load(r)['recap_scope'],'catchup')
            with self.assertRaises(HTTPError) as error:post('/api/recaps',{**body,'scope':''})
            self.assertEqual(error.exception.code,400)
            for bad,status in (({**body,'time_ms':-1},400),({**body,'match_id':'wrong'},404)):
                with self.assertRaises(HTTPError) as error:post('/api/insights',bad)
                self.assertEqual(error.exception.code,status)
            with self.assertRaises(HTTPError) as error:post('/api/insights',body,Origin='http://other.invalid')
            self.assertEqual(error.exception.code,403)
        finally:server.shutdown();server.server_close();worker.join()

    def test_durable_live_restart_full_match_and_audit_cutoff(self):
        with tempfile.TemporaryDirectory() as folder:
            journal=Journal(Path(folder)/'events.sqlite3')
            app=Application(MatchStore(self.store.metadata,replay=False),DemoAgents(),journal=journal)
            for event in self.store.events:app.ingest(event)
            self.assertTrue(app.ingest(self.store.events[-1])['duplicate'])
            restored=Application(MatchStore(self.store.metadata,replay=False),DemoAgents(),journal=journal)
            end=self.store.times[-1]
            self.assertEqual(restored.default.events,self.store.events)
            self.assertEqual(restored.default.snapshot(end),self.store.snapshot(end))
            result=restored.insight({'match_id':self.store.metadata['match_id'],'time_ms':self.time,'session_epoch':'audit','profile':{}})
            self.assertEqual(journal.history(self.store.metadata['match_id'],self.time)[0],result)
            self.assertEqual(journal.history(self.store.metadata['match_id'],self.time-1),[])

    def test_complete_recaps_identify_period_and_source_moments(self):
        w=IntelligenceWorkflow()
        for end in (e for e in self.store.events if e['type']=='period_end'):
            r=w.generate(self.store,end['match_time_ms'],ViewerProfile(),'boundary',scope='full')
            self.assertIn('Halftime' if end['period']==1 else 'Full-time',r['headline'])
            self.assertTrue(r['claims'])


    def test_failed_journal_commit_cannot_leak_into_live_state(self):
        store=MatchStore(self.store.metadata,replay=False)
        application=Application(store)
        event=self.store.events[0]
        before=store.snapshot(0)
        class BrokenJournal:
            def event(self,event):raise OSError('disk unavailable')
        application.journal=BrokenJournal()
        with self.assertRaises(OSError):application.ingest(event)
        self.assertEqual(store.events,[])
        self.assertEqual(store.snapshot(0),before)
        application.journal=None
        self.assertTrue(application.ingest(event)['accepted'])
        self.assertTrue(application.ingest(event)['duplicate'])


if __name__=='__main__':unittest.main()
