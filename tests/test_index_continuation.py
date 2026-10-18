"""Generated CPU contracts for explicit library continuation; no real AI/GUI."""
from array import array
from dataclasses import replace
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'));sys.path.insert(0,str(REPO/'tools'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, AIBusy, revision
from ai_process import AIUnavailable
from index_continuation import JOB, TTL
from production import ProductionCatalog
from production_server import production_handler
from storage_backup import backup, restore
from create_library_scale_fixture import create


class Encoder:
    profile=replace(DEFAULT_PROFILE,dimension=3,modalities=('text',))
    available=True
    def __init__(self):self.calls=[];self.on_document=None
    def encode(self,operation,value):
        self.calls.append(operation)
        if self.on_document and operation=='document':self.on_document()
        return [1.,0.,0.]
    def close(self):pass


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.media=self.base/'media';self.media.mkdir()
        for i in range(6):(self.media/f'asset-{i}.wav').write_bytes(b'generated metadata')
        self.hashes={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.media.iterdir()}
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media));self.catalog.start_scan(self.root);self.catalog._worker.join(10)
        self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.profile=self.ai.profile.key
        self.scope={'root_ids':[self.root]}

    def plan(self,limit=2,after_id=0,scope=None):
        return self.ai.continuation.prepare(scope or self.scope,self.profile,limit,after_id)

    def start(self,plan):
        state=self.ai.continuation.start(plan['plan_id'],plan['scope'],self.profile)
        self.ai.worker.join(15);self.assertFalse(self.ai.worker.is_alive())
        return state,self.ai.status()

    def cancel(self):
        def event():
            if len(self.encoder.calls)==3:self.ai.cancel_build()
        self.encoder.on_document=event
        initial,done=self.start(self.plan(6))
        self.assertEqual(done['state'],'cancelled')
        self.encoder.on_document=None
        return initial,done

    def test_plan_is_cpu_only_no_state_or_media_writes_and_full_counts(self):
        self.encoder.available=False
        before=self.ai.store.state()
        plan=self.plan()
        self.assertEqual((plan['candidate_total'],plan['fresh_total'],plan['remaining_total'],plan['selected_total']),(6,0,6,2))
        self.assertEqual(self.ai.store.state(),before);self.assertEqual(self.encoder.calls,[])
        self.assertEqual(self.hashes,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.media.iterdir()})
        with self.assertRaises(AIUnavailable):self.start(plan)

    def test_repeated_explicit_ranges_reach_every_item_not_prefix(self):
        totals=[]
        for remaining in (6,4,2):
            plan=self.plan()
            self.assertEqual(plan['remaining_total'],remaining)
            start,done=self.start(plan)
            self.assertEqual((done['state'],done['indexed'],done['skipped']),('complete',2,0))
            self.assertNotIn('continuation',done);self.assertNotIn('_pins',self.ai.store.state())
            totals.append(start['next_after_id'])
        self.assertEqual(totals,[2,4,6]);self.assertEqual(self.encoder.calls,['document']*6)
        self.assertEqual(self.plan()['remaining_total'],0)
        with self.assertRaises(ValueError):self.start(self.plan())

    def test_cancel_restart_and_explicit_resume_reuses_saved_items(self):
        old,done=self.cancel()
        self.assertEqual((done['processed'],done['indexed']),(2,2))
        self.ai.close()
        self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.assertIsNone(self.ai.worker);self.assertEqual(self.encoder.calls,[])
        started=self.ai.continuation.resume(old['job_id'],self.scope,self.profile)
        self.ai.worker.join(10);state=self.ai.status()
        self.assertNotEqual(started['job_id'],old['job_id']);self.assertEqual(started['resumed_from'],old['job_id'])
        self.assertEqual((state['state'],state['indexed'],state['reused']),('complete',6,2))
        self.assertEqual(self.encoder.calls,['document']*4)
        self.assertEqual(self.ai.coverage(self.scope)['fresh_total'],6)

    def test_job_owned_cancellation_semantics(self):
        plan=self.plan(6)
        for bad in ('bad',123,'A'*32,'0'*31,'0'*33,None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.ai.continuation.cancel(bad)
        res=self.ai.continuation.cancel('0'*32)
        self.assertEqual(res,{'cancel_requested':False,'job_id':'0'*32})
        cancelled_calls=[]
        def on_doc():
            if len(self.encoder.calls)==2:
                wrong=self.ai.continuation.cancel('f'*32)
                cancelled_calls.append(('wrong',wrong))
                correct=self.ai.continuation.cancel(self.ai.status()['job_id'])
                cancelled_calls.append(('correct',correct))
        self.encoder.on_document=on_doc
        _,done=self.start(plan)
        self.encoder.on_document=None
        self.assertEqual(done['state'],'cancelled')
        self.assertEqual(cancelled_calls,[('wrong',{'cancel_requested':False,'job_id':'f'*32}),
                                          ('correct',{'cancel_requested':True,'job_id':done['job_id']})])
        after=self.ai.continuation.cancel(done['job_id'])
        self.assertEqual(after,{'cancel_requested':False,'job_id':done['job_id']})

    def test_fixed_upper_bound_excludes_added_items_until_new_plan(self):
        plan=self.plan(6)
        (self.media/'new.wav').write_bytes(b'new generated metadata')
        self.catalog.start_scan(self.root);self.catalog._worker.join(10)
        self.start(plan)
        self.assertEqual(self.ai.status()['total'],6)
        next_plan=self.plan()
        self.assertEqual((next_plan['candidate_total'],next_plan['remaining_total'],next_plan['selected_total']),(7,1,1))
        self.assertGreater(next_plan['next_after_id'],plan['upper_id'])

    def test_scope_and_optional_cursor_do_not_silently_include_other_ranges(self):
        plan=self.plan(2,after_id=3)
        self.assertEqual((plan['remaining_total'],plan['remaining_after_id'],plan['next_after_id']),(6,3,5))
        self.start(plan)
        self.assertEqual(self.ai.store.fresh_ids(self.ai._rows()),{4,5})
        self.assertEqual(self.plan(scope={'root_ids':[]})['selected_total'],0)
        self.assertEqual(self.plan(scope={'root_ids':[self.root],'kind':'image'})['candidate_total'],0)
        self.catalog.update([1],{'shelf':'selected'})
        self.assertEqual(self.plan(scope={**self.scope,'shelf':'selected'})['selected_total'],1)

    def test_expired_replaced_and_consumed_preview_refuse_without_job_replacement(self):
        first=self.plan();second=self.plan()
        with self.assertRaises(ValueError):self.start(first)
        saved=self.ai.store.state()
        with patch('index_continuation.time.monotonic',return_value=self.ai.continuation._plan['expires']+1):
            with self.assertRaises(ValueError):self.start(second)
        self.assertEqual(self.ai.store.state(),saved)
        self.start(self.plan())
        with self.assertRaises(ValueError):self.start(second)

    def test_source_root_scope_or_profile_change_refuses_start_and_resume(self):
        for mutation in ('tags','exclude','unregister','scope','profile'):
            with self.subTest(mutation=mutation):
                # Fresh catalog/AI per branch keeps independent contracts.
                plan=self.plan(1)
                saved=self.ai.store.state()
                scope,profile=plan['scope'],self.profile
                if mutation=='tags':self.catalog.update([1],{'tags':['changed']})
                elif mutation=='exclude':self.catalog.set_excludes(self.root,['asset-5.wav'])
                elif mutation=='unregister':self.catalog.unregister_root(self.root)
                elif mutation=='scope':scope={'root_ids':[]}
                else:profile='different'
                with self.assertRaises(ValueError):self.ai.continuation.start(plan['plan_id'],scope,profile)
                self.assertEqual(self.ai.store.state(),saved)
                if mutation=='tags':self.catalog.update([1],{'tags':[]})
                elif mutation=='exclude':self.catalog.set_excludes(self.root,[])
                elif mutation=='unregister':self.catalog.add_root(str(self.media))

    def test_mid_inference_metadata_change_never_publishes_old_revision(self):
        def changed():self.catalog.update([1],{'tags':['changed during inference']})
        self.encoder.on_document=changed
        _,state=self.start(self.plan(2))
        self.assertEqual(state['state'],'failed')
        with self.ai.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_vectors').fetchone()[0],0)
        with self.assertRaises(ValueError):self.ai.continuation.resume(state['job_id'],self.scope,self.profile)

    def test_interrupted_running_job_preserves_fixed_selection_in_recovery_bundle(self):
        old,_=self.cancel()
        raw=self.ai.store.state();raw['state']='running';self.ai.store.save_state(raw)
        self.ai.close();self.catalog.close()
        backup(self.base/'catalog.sqlite',self.base/'backup')
        restore(self.base/'backup',self.base/'restored')
        catalog=ProductionCatalog(self.base/'restored/catalog.sqlite');self.addCleanup(catalog.close)
        encoder=Encoder();ai=AISearch(catalog,encoder);self.addCleanup(ai.close)
        self.assertEqual(ai.status()['state'],'interrupted');self.assertIsNone(ai.worker)
        self.assertEqual(ai.store.state()['continuation'],raw['continuation'])
        ai.continuation.resume(old['job_id'],self.scope,self.profile);ai.worker.join(10)
        self.assertEqual((ai.status()['state'],ai.status()['reused']),('complete',2))
        self.assertEqual(len(encoder.calls),4)

    def test_corrupt_saved_selection_and_replaced_job_cannot_resume(self):
        old,_=self.cancel();saved=self.ai.store.state()
        for field,value in (('version',True),('entries',[[True,'0'*64,None]]),('root_context','bad'),('upper_id',False)):
            bad=json.loads(json.dumps(saved));bad['continuation'][field]=value;self.ai.store.save_state(bad)
            with self.subTest(field=field),self.assertRaises(ValueError):self.ai.continuation.resume(old['job_id'],self.scope,self.profile)
        self.ai.store.save_state(saved)
        self.ai.start(limit=1);self.ai.worker.join(10)
        with self.assertRaises(ValueError):self.ai.continuation.resume(old['job_id'],self.scope,self.profile)

    def test_strict_arguments_and_busy_scan_checks(self):
        for limit,after in ((True,0),(0,0),(10001,0),(1,True),(1,-1)):
            with self.assertRaises(ValueError):self.plan(limit,after)
        with self.assertRaises(ValueError):self.ai.continuation.prepare(None,self.profile)
        with patch.object(self.catalog,'scan_state',return_value={'state':'running'}):
            with self.assertRaises(AIBusy):self.plan()

    def test_prepare_rejects_concurrent_changes_and_preserves_previous_job(self):
        saved=self.ai.store.state();ready=self.ai.continuation.ready
        def change(rows,pending):
            result=ready(rows,pending);self.catalog.update([6],{'tags':['concurrent']});return result
        with patch.object(self.ai.continuation,'ready',side_effect=change):
            with self.assertRaises(AIBusy):self.plan()
        self.assertEqual(self.ai.store.state(),saved)

    def test_authenticated_http_plan_start_resume_and_unknown_fields(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token',ai=self.ai))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        def post(operation,body,expected=200,auth=True):
            headers={'Content-Type':'application/json'}
            if auth:headers.update(Origin=origin,**{'X-Aredoko-Token':'test-token'})
            request=urllib.request.Request(origin+'/api/library/ai/index/'+operation,json.dumps(body).encode(),headers)
            try:
                with urllib.request.urlopen(request,timeout=20) as response:result,code=json.load(response),response.status
            except urllib.error.HTTPError as error:
                with error:result,code=json.load(error),error.code
            self.assertEqual(code,expected);return result
        fields={'scope':self.scope,'profile':self.profile}
        plan=post('plan',{**fields,'limit':2,'after_id':0})
        post('start',{**fields,'plan_id':plan['plan_id']});self.ai.worker.join(10)
        for operation,body in (('plan',{**fields,'limit':2,'after_id':0}),('start',{**fields,'plan_id':plan['plan_id']}),('resume',{**fields,'job_id':'0'*32}),('cancel',{'job_id':'0'*32})):
            post(operation,body,403,False);post(operation,{**body,'path':'private'},400)
        post('resume',{**fields,'job_id':'0'*32},400)
        cancel_unknown=post('cancel',{'job_id':'0'*32})
        self.assertEqual(cancel_unknown,{'cancel_requested':False,'job_id':'0'*32})
        self.assertEqual(self.ai.status()['state'],'complete')
        plan=post('plan',{**fields,'limit':2,'after_id':0})
        self.encoder.on_document=lambda:post('cancel',{'job_id':self.ai.status()['job_id']})
        started=post('start',{**fields,'plan_id':plan['plan_id']});self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'],'cancelled')
        self.encoder.on_document=None
        resumed=post('resume',{**fields,'job_id':started['job_id']});self.ai.worker.join(10)
        self.assertEqual(resumed['resumed_from'],started['job_id'])
        self.assertEqual(self.ai.status()['state'],'complete')
        cancel_done=post('cancel',{'job_id':resumed['job_id']})
        self.assertEqual(cancel_done,{'cancel_requested':False,'job_id':resumed['job_id']})

    def test_resume_rejects_changed_selected_item_or_context_before_encoding(self):
        old,_=self.cancel();before=len(self.encoder.calls)
        self.catalog.update([1],{'tags':['changed completed item']})
        with self.assertRaises(ValueError):self.ai.continuation.resume(old['job_id'],self.scope,self.profile)
        self.catalog.update([1],{'tags':[]})
        self.catalog.set_excludes(self.root,['asset-5.wav'])
        with self.assertRaises(ValueError):self.ai.continuation.resume(old['job_id'],self.scope,self.profile)
        self.assertEqual(len(self.encoder.calls),before)

    def test_pending_signature_change_never_publishes_stale_selection(self):
        pending={1:{'signature':'a'*64}}
        def snapshots(ids):return {item:dict(pending[item]) for item in ids if item in pending}
        with patch.object(self.ai.pending_tags,'snapshots',side_effect=snapshots):
            with patch.object(self.ai.pending_tags,'ready_ids',return_value=set()):
                plan=self.plan(1)
                self.encoder.on_document=lambda:pending[1].update(signature='b'*64)
                _,state=self.start(plan)
        self.assertEqual(state['state'],'failed')
        with self.ai.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_vectors').fetchone()[0],0)

    def test_unready_pending_remains_missing_and_explicit_cursor_can_move_past(self):
        with patch.object(self.ai.pending_tags,'snapshots',side_effect=lambda ids:{1:{'signature':'a'*64}} if 1 in ids else {}),patch.object(self.ai.pending_tags,'ready_ids',return_value=set()),patch.object(self.ai.pending_tags,'build',return_value=(False,False)):
            _,state=self.start(self.plan(1))
            self.assertEqual((state['state'],state['indexed'],state['unready_total']),('complete',0,1))
            self.assertEqual((self.plan(1)['remaining_total'],self.plan(1)['next_after_id']),(6,1))
            self.assertEqual(self.plan(1,after_id=1)['next_after_id'],2)

    def test_changed_completed_metadata_during_later_item_fails_final_check(self):
        def change():
            if len(self.encoder.calls)==2:self.catalog.update([1],{'tags':['changed earlier item']})
        self.encoder.on_document=change
        _,state=self.start(self.plan(2))
        self.assertEqual(state['state'],'failed')
        self.assertEqual(self.ai.coverage(self.scope)['fresh_total'],1)

    def test_new_preview_does_not_destroy_saved_resumable_job(self):
        old,_=self.cancel();saved=self.ai.store.state()
        plan=self.plan(1)
        self.assertEqual(self.ai.store.state(),saved)
        self.assertNotIn('entries',plan)
        self.ai.continuation.resume(old['job_id'],self.scope,self.profile);self.ai.worker.join(10)
        with self.assertRaises(ValueError):self.start(plan)


class LargeContinuationTests(unittest.TestCase):
    def test_real_10001_metadata_tail_is_selected_after_10000_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'fixture';create(fixture,count=10001,root_count=2)
            catalog=ProductionCatalog(fixture/'catalog.sqlite');encoder=Encoder();ai=AISearch(catalog,encoder)
            try:
                packed=array('f',[1.,0.,0.]).tobytes()
                with ai.store.connect() as db:
                    db.executemany('INSERT INTO ai_vectors VALUES(?,?,?,?)',
                        [(r['id'],revision(r),'text',packed) for r in ai._iter_rows(limit=10000)])
                plan=ai.continuation.prepare({},ai.profile.key,1)
                self.assertEqual((plan['candidate_total'],plan['fresh_total'],plan['remaining_total'],plan['next_after_id']),(10001,10000,1,10001))
                self.assertEqual(encoder.calls,[])
                ai.continuation.start(plan['plan_id'],{},ai.profile.key);ai.worker.join(20)
                self.assertEqual((ai.status()['state'],ai.status()['indexed']),('complete',1))
                self.assertEqual(encoder.calls,['document'])
                self.assertEqual(ai.continuation.prepare({},ai.profile.key,1)['remaining_total'],0)
            finally:ai.close();catalog.close()


if __name__=='__main__':unittest.main()
