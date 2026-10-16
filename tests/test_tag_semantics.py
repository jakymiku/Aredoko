"""Pending-tag index/search contracts; fake vectors are not language accuracy."""
from dataclasses import replace
import json
import threading
import unittest
from unittest.mock import patch
import uuid

from test_tag_suggestions import TagFixture
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch,AIBusy
from ai_process import AIUnavailable
from tag_suggestions import TagProposal
from tag_candidate_search import search_candidates
from tag_semantics import semantic_candidates


class Encoder:
    available=True
    resident=False
    def __init__(self,dimension=8):
        self.profile=replace(DEFAULT_PROFILE,dimension=dimension,modalities=('text',))
        self.calls=[];self.hook=None
    def encode(self,operation,text):
        self.calls.append((operation,text))
        if self.hook:self.hook(operation,text)
        axis=1 if 'blue_hair' in text or '青髪' in text else 2 if 'red_hair' in text else 0
        return [float(i==axis) for i in range(self.profile.dimension)]
    def close(self):pass


class TagSemanticTests(TagFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.adapter.output=[TagProposal('blue_hair','fixture only'),TagProposal('twintails','fixture only')]
        self.blue=self.generate()['batch']
        self.adapter.output=[TagProposal('red_hair','fixture only')]
        self.other=self.ids['fiction.cbz'];self.red=self.generate(self.other)['batch']
        self.scope={'root_ids':[self.root]}

    def build(self):
        self.ai.start(scope=self.scope);self.ai.worker.join(10)
        self.assertFalse(self.ai.worker.is_alive());self.assertEqual(self.ai.status()['state'],'complete')

    def search(self,**kwargs):return semantic_candidates(self.service,self.ai,'青髪',**kwargs)

    def test_missing_index_never_embeds_proposals_or_loads_query_model(self):
        result=self.search()
        self.assertEqual((result['total'],result['pending_total'],result['index_remaining']),(0,2,2))
        self.assertEqual(self.encoder.calls,[])
        self.assertEqual(self.catalog.get(self.item)['tags'],[])

    def test_explicit_build_and_reuse_preserve_raw_labels_and_metadata(self):
        self.catalog.update([self.item],{'tags':['手動'],'shelf':'素材','favorite':True})
        before=(self.path.read_bytes(),self.path.stat().st_mtime_ns)
        self.build();calls=list(self.encoder.calls);self.build();self.assertEqual(self.encoder.calls,calls)
        result=self.search();self.assertEqual(result['search_mode'],'pending-proposals-semantic')
        self.assertEqual(result['items'][0]['id'],self.item)
        match=result['items'][0]['proposal_match']
        self.assertEqual(match['tags'],['blue_hair','twintails']);self.assertEqual(match['state'],'pending')
        self.assertEqual(match['producer'],self.adapter.info.record());self.assertEqual(match['source_state'],'current')
        self.assertEqual(result['index_remaining'],0)
        row=self.catalog.get(self.item);self.assertEqual(row['tags'],['手動']);self.assertEqual(row['shelf'],'素材');self.assertTrue(row['favorite'])
        self.assertEqual(before,(self.path.read_bytes(),self.path.stat().st_mtime_ns))
        self.assertEqual(search_candidates(self.service,'青髪')['total'],0)
        self.assertEqual(self.catalog.search('blue_hair')['total'],0)

    def test_review_invalidates_only_that_pending_document_then_explicit_rebuild(self):
        self.build();self.review(self.blue['proposals'][0])
        result=self.search();self.assertEqual([r['id'] for r in result['items']],[self.other]);self.assertEqual(result['index_remaining'],1)
        self.assertEqual(self.catalog.get(self.item)['tags'],['blue_hair'])
        self.assertEqual(self.ai.coverage(self.scope)['remaining_total'],1)
        self.build();self.assertEqual(self.search()['index_remaining'],0)
        self.review(self.blue['proposals'][1],'reject')
        self.assertNotIn(self.item,[r['id'] for r in self.search()['items']])
        self.assertEqual(self.ai.search('青髪',source='text')['items'][0]['id'],self.item)

    def test_filters_empty_unknown_roots_and_model_are_strict(self):
        self.catalog.update([self.item],{'favorite':True,'shelf':'資料'})
        self.build()
        self.assertEqual(self.search(view='favorites')['total'],1)
        self.assertEqual(self.search(shelf='資料')['total'],1)
        self.assertEqual(self.search(kind='book')['total'],1)
        self.assertEqual(self.search(model='not-this-tagger')['total'],0)
        for kwargs in ({'root_ids':[]},{'root_ids':[self.root,self.root]},{'root_ids':[999]},{'page':True}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.search(**kwargs)
        with self.assertRaises(ValueError):semantic_candidates(self.service,self.ai,'')

    def test_busy_closed_and_missing_runtime_never_fall_back_to_literal(self):
        self.ai.inference.acquire()
        try:
            with self.assertRaises(AIBusy):self.search()
        finally:self.ai.inference.release()
        self.encoder.available=False
        with self.assertRaises(AIUnavailable):self.search()
        self.encoder.available=True;self.ai.close()
        with self.assertRaises(AIUnavailable):self.search()

    def test_cancel_and_review_race_do_not_publish_partial_pending_vectors(self):
        def cancel(operation,text):
            if 'blue_hair' in text:self.ai.cancel.set()
        self.encoder.hook=cancel
        self.ai.start(scope=self.scope);self.ai.worker.join(10)
        with self.ai.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_proposal_vectors WHERE item_id=?',(self.item,)).fetchone()[0],0)
        self.encoder.hook=None;self.build()
        self.review(self.blue['proposals'][0])
        fired=[]
        def race(operation,text):
            if 'twintails' in text and not fired:
                fired.append(True);self.review(self.blue['proposals'][1],'reject')
        self.encoder.hook=race;self.build()
        self.assertTrue(fired);self.assertNotIn(self.item,[r['id'] for r in self.search()['items']])

    def test_new_batch_and_corrupt_cached_vector_require_rebuild(self):
        self.build()
        with self.ai.store.connect() as db:db.execute('UPDATE ai_proposal_vectors SET vector=? WHERE item_id=?',(b'bad',self.item))
        self.assertEqual(self.search()['index_remaining'],1)
        self.build();self.assertEqual(self.search()['index_remaining'],0)
        self.adapter.info=replace(self.adapter.info,version='new')
        self.generate()
        self.assertEqual(self.search()['index_remaining'],1)

    def test_profile_namespace_and_source_revision_are_preserved(self):
        self.build()
        other=AISearch(self.catalog,Encoder(16));self.addCleanup(other.close)
        self.assertNotEqual(self.ai.store.path,other.store.path)
        self.assertEqual(semantic_candidates(self.service,other,'青髪')['index_remaining'],2)
        from create_preview_fixture import png
        self.path.write_bytes(png(color=(210,20,30)));self.scan()
        self.build()
        self.assertEqual(self.ai.coverage(self.scope)['remaining_total'],1)
        result=self.search();self.assertNotIn(self.item,[r['id'] for r in result['items']])
        self.assertEqual(result['index_remaining'],1)


    def test_inactive_root_purge_removes_pending_vectors_from_each_profile(self):
        self.build();second=AISearch(self.catalog,Encoder(16));self.addCleanup(second.close)
        second.start(scope=self.scope);second.worker.join(10)
        for ai in (self.ai,second):
            with ai.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_proposal_vectors').fetchone()[0],2)
        before=self.path.read_bytes(),self.path.stat().st_mtime_ns
        self.catalog.unregister_root(self.root);self.catalog.purge_inactive_root(self.root,consent=True)
        for ai in (self.ai,second):
            with ai.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_proposal_vectors').fetchone()[0],0)
        self.assertEqual(before,(self.path.read_bytes(),self.path.stat().st_mtime_ns))

    def test_http_semantic_flag_empty_input_and_no_silent_literal_fallback(self):
        from http.server import ThreadingHTTPServer
        from production_server import production_handler
        import urllib.request
        import urllib.error
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'tag-token',ai=self.ai,tagger=self.adapter))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda:(server.shutdown(),thread.join(3)))
        origin=f'http://127.0.0.1:{server.server_port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(body):
            req=urllib.request.Request(origin+'/api/library/tag-suggestions/search',data=json.dumps(body).encode(),
                headers={'Origin':origin,'X-Aredoko-Token':'tag-token'})
            try:
                with opener.open(req,timeout=5) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:
                with error:return error.code,json.load(error)
        self.assertEqual(request({'query':'青髪','semantic':True})[1]['index_remaining'],2)
        self.assertEqual(self.encoder.calls,[])
        self.build()
        status,result=request({'query':'青髪','semantic':True})
        self.assertEqual(status,200);self.assertEqual(result['items'][0]['id'],self.item)
        self.assertEqual(request({'query':'blue_hair','semantic':False})[1]['search_mode'],'pending-proposals')
        for body in ({'semantic':True},{'query':'','semantic':True},{'query':'青髪','semantic':1},{'query':'青髪','semantic':'true'},{'query':'青髪','path':'private'}):
            self.assertEqual(request(body)[0],400)


if __name__=='__main__':unittest.main()
