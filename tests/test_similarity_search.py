"""Generated-media contract tests; synthetic vectors are not model quality evidence."""
from array import array
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'));sys.path.insert(0,str(REPO/'tools'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, AIBusy, VectorStore, revision
from ai_process import AIUnavailable
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from create_preview_fixture import png

RED=png(20,20,(200,10,10));NEAR=png(20,20,(190,20,10));BLUE=png(20,20,(10,10,200))

class ContractEncoder:
    profile=replace(DEFAULT_PROFILE,dimension=3)
    available=True
    resident=False
    def __init__(self):self.calls=[]
    def encode(self,op,value):
        self.calls.append(op)
        if op=='image':return {RED:[1.,0.,0.],NEAR:[.98,.2,0.],BLUE:[0.,0.,1.]}[value]
        return [0.,1.,0.]  # Text must not affect visual ranking.
    def close(self):pass

class SimilarityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.roots=[];self.folders=[]
        for number in (1,2):
            folder=self.base/str(number);folder.mkdir();self.folders.append(folder)
            for name,data in [('origin.png',RED),('near.png',NEAR),('blue.png',BLUE)]:
                (folder/name).write_bytes(data)
            with zipfile.ZipFile(folder/'cover.cbz','w') as archive:archive.writestr('1.png',NEAR)
            (folder/'song.wav').write_bytes(b'generated metadata only')
            root=self.catalog.add_root(str(folder));self.roots.append(root)
            self.catalog.start_scan(root);self.catalog._worker.join(10)
            self.assertEqual(self.catalog.scan_state()['state'],'complete')
        self.encoder=ContractEncoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.ai.start();self.ai.worker.join(10);self.assertEqual(self.ai.status()['state'],'complete')
        self.rows=self.catalog.search()['items']
        self.origin=self.row('origin.png');self.scope={'root_ids':[self.roots[0]]}
        self.before=self.sources();self.calls=list(self.encoder.calls)

    def row(self,title,root=0):
        return next(r for r in self.rows if r['title']==title and r['root_id']==self.roots[root])
    def sources(self):
        return {str(p.relative_to(self.base)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns)
                for folder in self.folders for p in folder.iterdir()}
    def ids(self,**kwargs):return [r['id'] for r in self.ai.similar(self.origin['id'],scope=self.scope,**kwargs)['items']]

    def test_visual_order_self_exclusion_explanation_and_readonly_without_model(self):
        self.encoder.available=False
        result=self.ai.similar(self.origin['id'],scope=self.scope)
        self.assertEqual(result['similarity_status'],'ready')
        self.assertEqual([r['id'] for r in result['items']],sorted([self.row('near.png')['id'],self.row('cover.cbz')['id']])+[self.row('blue.png')['id']])
        self.assertEqual(result['profile'],self.ai.profile.key)
        self.assertEqual(result['score_kind'],'cosine')
        self.assertTrue(all(r['similarity_evidence']=='cover' and r['similarity_origin_id']==self.origin['id'] for r in result['items']))
        self.assertGreater(result['items'][0]['semantic_score'],.97)
        self.assertEqual(self.encoder.calls,self.calls);self.assertFalse(self.encoder.resident)
        self.assertEqual(self.sources(),self.before)

    def test_result_kind_favorites_reviewed_and_shelf_filters_do_not_filter_origin(self):
        near=self.row('near.png');cover=self.row('cover.cbz')
        self.catalog.update([near['id']],{'favorite':True,'reviewed':True,'shelf':'素材'})
        self.assertEqual(self.ids(view='favorites'),[near['id']])
        self.assertNotIn(near['id'],self.ids(view='unreviewed'))
        self.assertEqual(self.ids(view='shelf'),[near['id']])
        self.assertEqual(self.ids(kind='book'),[cover['id']])
        self.assertEqual(self.ids(kind='audio'),[])  # No text-vector fallback.

    def test_strict_scope_intersection_empty_and_shelf(self):
        for scope in ({'root_ids':[]},{'root_ids':[self.roots[1]]},{'kind':'book'},{'shelf':'outside'}):
            with self.subTest(scope=scope),self.assertRaises(KeyError):self.ai.similar(self.origin['id'],scope=scope)
        self.catalog.update([self.origin['id'],self.row('near.png')['id']],{'shelf':"素材' OR 1=1 --"})
        result=self.ai.similar(self.origin['id'],scope={'shelf':"素材' OR 1=1 --"})
        self.assertEqual([r['id'] for r in result['items']],[self.row('near.png')['id']])
        with self.assertRaises(ValueError):self.ai.similar(self.origin['id'],scope={'root_ids':[99999]})

    def test_profile_revision_dimension_and_preprocessing_namespaces_are_separate(self):
        for profile in (replace(self.ai.profile,revision='a'*40),replace(self.ai.profile,dimension=4),replace(self.ai.profile,model_id='test/other')):
            encoder=ContractEncoder();encoder.profile=profile
            other=AISearch(self.catalog,encoder)
            try:
                result=other.similar(self.origin['id'],scope=self.scope)
                self.assertEqual(result['similarity_status'],'unindexed');self.assertEqual(result['items'],[])
                self.assertNotEqual(other.store.path,self.ai.store.path);self.assertEqual(encoder.calls,[])
            finally:other.close()
        with self.assertRaises(AIUnavailable):VectorStore(self.ai.store.path,replace(self.ai.profile,revision='a'*40))
        with patch('ai_profiles.VECTOR_CONTRACT','generated-other-preprocessing:v2'):
            other=AISearch(self.catalog,ContractEncoder())
            try:
                self.assertNotEqual(other.store.path,self.ai.store.path)
                self.assertEqual(other.similar(self.origin['id'])['similarity_status'],'unindexed')
            finally:other.close()

    def test_unindexed_stale_or_missing_cover_origin_never_infers(self):
        for vectors in ({'text':[1,0,0]}, {'cover':[1,0,0]}):
            # A cover with a stale revision is unusable as well as a text-only row.
            self.ai.store.put(self.origin['id'],'stale' if 'cover' in vectors else revision(self.origin),vectors)
            result=self.ai.similar(self.origin['id'],scope=self.scope)
            self.assertEqual((result['similarity_status'],result['total']),('unindexed',0))
        self.assertEqual(self.encoder.calls,self.calls)

    def test_tag_edit_invalidates_origin_until_explicit_reindex(self):
        self.catalog.update([self.origin['id']],{'tags':['変更']})
        self.assertEqual(self.ai.similar(self.origin['id'],scope=self.scope)['similarity_status'],'unindexed')
        self.assertEqual(self.catalog.search('変更')['total'],1)

    def test_stale_candidates_exclusions_and_unregister(self):
        near=self.row('near.png');self.catalog.update([near['id']],{'tags':['新しいタグ']})
        self.assertNotIn(near['id'],self.ids())
        self.catalog.set_excludes(self.roots[0],['blue.png']);self.assertNotIn(self.row('blue.png')['id'],self.ids())
        self.catalog.set_excludes(self.roots[0],['origin.png'])
        with self.assertRaises(KeyError):self.ids()
        self.catalog.set_excludes(self.roots[0],[]);self.catalog.unregister_root(self.roots[0])
        with self.assertRaises(ValueError):self.ids()

    def test_rescan_invalidates_changed_origin_and_drops_missing_candidates(self):
        (self.folders[0]/'origin.png').write_bytes(BLUE)
        (self.folders[0]/'near.png').unlink()
        self.catalog.start_scan(self.roots[0]);self.catalog._worker.join(10)
        self.assertEqual(self.ai.similar(self.origin['id'],scope=self.scope)['similarity_status'],'unindexed')
        current=self.catalog.get(self.origin['id']);self.ai.store.put(current['id'],revision(current),{'cover':[0,0,1]})
        self.assertNotIn(self.row('near.png')['id'],self.ids())

    def test_unsupported_profile_and_non_visual_origin(self):
        encoder=ContractEncoder();encoder.profile=replace(encoder.profile,modalities=('text',))
        other=AISearch(self.catalog,encoder)
        try:self.assertEqual(other.similar(self.origin['id'])['similarity_status'],'unsupported_profile')
        finally:other.close()
        with self.assertRaises(ValueError):self.ai.similar(self.row('song.wav')['id'])

    def test_paging_stable_ties_and_index_cap_independent_search(self):
        all_ids=self.ids()
        pages=[self.ai.similar(self.origin['id'],page=p,limit=1,scope=self.scope)['items'][0]['id'] for p in range(3)]
        self.assertEqual(all_ids,pages)
        result=self.ai.similar(self.origin['id'],page=99,scope=self.scope)
        self.assertEqual((result['total'],result['items']),(3,[]))
        first=min(r['id'] for r in self.rows if r['root_id']==self.roots[0])
        with patch('ai_search.MAX_ITEMS',1):
            result=self.ai.similar(self.origin['id'],kind='image',scope=self.scope)
            expected=[item for item in all_ids if self.catalog.get(item)['kind']=='image']
            self.assertEqual([r['id'] for r in result['items']],expected)
            self.assertEqual(result['coverage_limit'],1)  # Legacy field is the indexing cap only.
            self.assertTrue(result['search_complete'])
            self.assertEqual(result['search_candidate_total'],len(expected))

    def test_corrupt_origin_vectors_use_unindexed_fallback(self):
        for data in (b'bad',array('f',[0,0,0]).tobytes(),array('f',[float('nan'),0,1]).tobytes(),array('f',[3e30,0,0]).tobytes(),array('f',[1]).tobytes()):
            with self.ai.store.connect() as db:db.execute("UPDATE ai_vectors SET vector=? WHERE item_id=? AND modality='cover'",(data,self.origin['id']))
            self.assertEqual(self.ai.similar(self.origin['id'])['similarity_status'],'unindexed')

    def test_concurrent_changes_do_not_publish_stale_candidates_or_origin(self):
        original=self.ai.store.scores_with_content
        def change_candidates(*args,**kwargs):
            result=original(*args,**kwargs)
            self.catalog.set_excludes(self.roots[0],['near.png','cover.cbz'])
            return result
        with patch.object(self.ai.store,'scores_with_content',side_effect=change_candidates),self.assertRaises(AIBusy):
            self.ids()  # Do not publish a ranking assembled across two catalog states.
        def change_origin(*args,**kwargs):
            result=original(*args,**kwargs);self.catalog.update([self.origin['id']],{'tags':['changed']});return result
        with patch.object(self.ai.store,'scores_with_content',side_effect=change_origin),self.assertRaises(AIBusy):self.ids()

    def test_corrupt_candidate_vector_is_skipped_without_hiding_other_results(self):
        near=self.row('near.png')
        for data in (b'bad',array('f',[3e30,0,0]).tobytes(),array('f',[0,0,0]).tobytes()):
            with self.ai.store.connect() as db:db.execute("UPDATE ai_vectors SET vector=? WHERE item_id=? AND modality='cover'",(data,near['id']))
            self.assertEqual(self.ids(),[self.row('cover.cbz')['id'],self.row('blue.png')['id']])

    def test_cached_cover_on_unsupported_kind_is_never_a_visual_candidate(self):
        song=self.row('song.wav');self.ai.store.put(song['id'],revision(song),{'text':[0,1,0],'cover':[1,0,0]})
        self.assertNotIn(song['id'],self.ids())
        self.assertEqual(self.ids(kind='audio'),[])

    def test_busy_close_and_strict_arguments(self):
        with self.ai.inference,self.assertRaises(AIBusy):self.ids()
        with patch.object(self.catalog,'scan_state',return_value={'state':'running'}),self.assertRaises(AIBusy):self.ids()
        for value in (True,0,-1,2**63,'1',None):
            with self.subTest(value=value),self.assertRaises(ValueError):self.ai.similar(value)
        for args in ({'page':True},{'page':-1},{'limit':True},{'limit':121},{'kind':[]},{'view':'unknown'}):
            with self.subTest(args=args),self.assertRaises(ValueError):self.ai.similar(self.origin['id'],**args)
        self.ai.close()
        with self.assertRaises(AIUnavailable):self.ids()

    def test_http_auth_default_scope_strict_requests_and_fallback(self):
        settings=AIProfileSettings(REPO,self.base/'settings.json');settings.set_scope(self.scope)
        before=settings.path.read_bytes()
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'similar-token',ai=self.ai,profiles=settings))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,5);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        headers={'Origin':origin,'X-Aredoko-Token':'similar-token','Content-Type':'application/json'}
        def post(body,custom=None):
            request=urllib.request.Request(origin+'/api/library/ai/similar',data=json.dumps(body).encode(),headers=headers if custom is None else custom)
            try:
                with urllib.request.urlopen(request) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as ex:
                with ex:return ex.code,json.load(ex)
        body={'item_id':self.origin['id']}
        code,result=post(body);self.assertEqual(code,200)
        self.assertTrue(all(r['root_id']==self.roots[0] for r in result['items']))
        self.assertEqual(post(body,{} )[0],403)
        for custom in ({**headers,'Origin':'http://evil.invalid'},{**headers,'Host':'evil.invalid'},{**headers,'X-Aredoko-Token':'wrong'}):self.assertEqual(post(body,custom)[0],403)
        for bad in ({},{**body,'scope':None},{**body,'scope':{'root_ids':[True]}},{**body,'scope':{'root_ids':[2**63]}},{**body,'profile':'other'},{**body,'source':'text'},{**body,'query':'rain'},{**body,'item_id':2**63}):self.assertEqual(post(bad)[0],400)
        self.assertEqual(post({**body,'scope':{'root_ids':[]}})[0],404)
        with self.ai.inference:self.assertEqual(post(body)[0],409)
        self.catalog.update([self.origin['id']],{'tags':['stale']})
        self.assertEqual(post(body)[1]['similarity_status'],'unindexed')
        self.assertEqual(settings.path.read_bytes(),before)
        self.assertEqual(self.encoder.calls,self.calls)

if __name__=='__main__':unittest.main()
