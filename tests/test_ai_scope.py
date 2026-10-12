"""Generated, CPU-only scope/API tests; no private roots or AI weights."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_settings import AIProfileSettings
from ai_scope import validate_scope
from ai_search import AISearch, AIBusy, VectorStore, revision
from production import ProductionCatalog
from production_server import production_handler


class ScopeEncoder:
    available=True
    device='CPU-contract-only'
    profile=replace(DEFAULT_PROFILE,dimension=8,modalities=('text',))
    def __init__(self):self.calls=[];self.on_document=None
    def encode(self,operation,value):
        self.calls.append(operation)
        if operation=='document' and self.on_document:self.on_document()
        return [1.0]+[0.0]*7
    def close(self):pass


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.folders=[];self.roots=[]
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        for number in (1,2):
            folder=self.base/f'media-{number}';folder.mkdir();self.folders.append(folder)
            for name in ('rain.wav','sun.wav','design.png'):
                (folder/name).write_bytes(b'generated metadata fixture')
            root=self.catalog.add_root(str(folder));self.roots.append(root)
            self.catalog.start_scan(root);self.catalog._worker.join(10)
            self.assertEqual(self.catalog.scan_state()['state'],'complete')
        self.encoder=ScopeEncoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.rows=self.catalog.search()['items']
        self.hashes={str(p.relative_to(self.base)):p.read_bytes() for folder in self.folders for p in folder.iterdir()}

    def build(self,scope,limit=10000):
        self.ai.start(limit,scope=scope);self.ai.worker.join(30)
        self.assertFalse(self.ai.worker.is_alive())
        self.assertEqual(self.ai.status()['state'],'complete')

    def test_strict_scope_validation_and_copy(self):
        value={'root_ids':[2,1],'kind':'image','shelf':"素材' OR 1=1 --"}
        result=validate_scope(value);value['root_ids'].append(3)
        self.assertEqual(result['root_ids'],[1,2])
        self.assertEqual(validate_scope({}),{'root_ids':None,'kind':'','shelf':None})
        for bad in (None,[],{'root_ids':True},{'root_ids':[True]}, {'root_ids':[0]},
                    {'root_ids':[1,1]}, {'root_ids':list(range(1,258))},
                    {'kind':['image']}, {'kind':'unknown'}, {'shelf':True},
                    {'shelf':'x'*81}, {'path':'C:/private'}, {'sql':'SELECT *'}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_scope(bad)
        with self.assertRaises(ValueError):self.ai.coverage({'root_ids':[99999]})

    def test_empty_scope_does_not_fall_back_or_load_encoder(self):
        scope={'root_ids':[]}
        self.assertEqual(self.ai.coverage(scope)['target_total'],0)
        self.build(scope)
        self.assertEqual(self.ai.status()['total'],0)
        self.assertEqual(self.ai.search('雨',scope=scope)['total'],0)
        self.assertEqual(self.encoder.calls,[])

    def test_root_kind_shelf_intersection_and_sql_parameter(self):
        scope={'root_ids':[self.roots[1]],'kind':'image','shelf':"素材' OR 1=1 --"}
        selected=next(row for row in self.rows if row['root_id']==self.roots[1] and row['kind']=='image')
        self.catalog.update([selected['id']],{'shelf':scope['shelf']})
        counts=self.ai.coverage(scope)
        self.assertEqual((counts['candidate_total'],counts['target_total'],counts['fresh_total']),(1,1,0))
        self.assertEqual(self.encoder.calls,[])
        self.build(scope)
        self.assertEqual([row['id'] for row in self.ai.search('雨',scope=scope)['items']],[selected['id']])
        self.assertEqual(self.ai.coverage(scope)['remaining_total'],0)
        self.assertEqual(self.ai.coverage({'shelf':''})['candidate_total'],5)

    def test_scope_switch_reuses_cache_and_keeps_other_vectors(self):
        key,path=self.ai.profile.key,self.ai.store.path
        a,b=({'root_ids':[root]} for root in self.roots)
        self.build(a);self.build(b)
        self.assertEqual(self.encoder.calls.count('document'),6)
        self.build(a)
        self.assertEqual(self.encoder.calls.count('document'),6)
        self.assertEqual((key,path),(self.ai.profile.key,self.ai.store.path))
        self.assertEqual(self.ai.search('雨',scope=b)['total'],3)
        self.assertEqual(self.ai.store.state()['scope'],validate_scope(a))
        reopened=VectorStore(path,self.ai.profile)
        self.assertEqual(reopened.state()['scope'],validate_scope(a))
        self.assertEqual(self.hashes,{str(p.relative_to(self.base)):p.read_bytes() for folder in self.folders for p in folder.iterdir()})

    def test_exclusions_and_missing_do_not_consume_target(self):
        root=self.roots[0];scope={'root_ids':[root]}
        self.catalog.set_excludes(root,['rain.wav'])
        self.assertEqual(self.ai.coverage(scope)['candidate_total'],2)
        (self.folders[0]/'sun.wav').unlink()  # Only the generated fixture.
        self.catalog.start_scan(root);self.catalog._worker.join(10)
        self.assertEqual(self.ai.coverage(scope)['candidate_total'],1)
        self.build(scope)
        self.assertEqual(self.ai.search('雨',scope=scope)['total'],1)

    def test_cap_is_shared_before_search_filters(self):
        self.build({})  # Cache includes both roots before tightening test cap.
        late=self.rows[-1];self.catalog.update([late['id']],{'favorite':True})
        with patch('ai_search.MAX_ITEMS',3):
            self.assertEqual(self.ai.coverage({},limit=3)['candidate_total'],6)
            self.assertEqual(self.ai.coverage({},limit=3)['target_total'],3)
            self.build({},limit=3)
            self.assertEqual(self.ai.search('雨',view='favorites',scope={})['total'],0)
        # Omitted scope preserves legacy filtering-before-cap behavior.
        self.assertEqual(self.ai.search('雨',view='favorites')['items'][0]['id'],late['id'])

    def test_scope_snapshot_and_shelf_recheck_before_publish(self):
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        selected=self.rows[0];self.catalog.update([selected['id']],{'shelf':'対象'})
        scope={'root_ids':[selected['root_id']],'shelf':'対象'}
        def gate():entered.set();release.wait(10)
        self.encoder.on_document=gate
        self.ai.start(scope=scope);self.assertTrue(entered.wait(5))
        scope['root_ids'].clear();scope['shelf']='違う棚'
        self.catalog.update([selected['id']],{'shelf':'範囲外'})
        with self.assertRaises(AIBusy):self.ai.start(scope={})
        release.set();self.ai.worker.join(10)
        state=self.ai.status()
        self.assertEqual(state['scope']['root_ids'],[selected['root_id']])
        self.assertEqual(state['scope']['shelf'],'対象')
        self.assertEqual((state['indexed'],state['skipped']),(0,1))
        self.assertFalse(self.ai.store.fresh(selected['id'],revision(self.catalog.get(selected['id']))))

    def test_counts_and_paging_across_row_batch(self):
        for i in range(260):(self.folders[0]/f'{i:04d}.wav').write_bytes(b'generated')
        self.catalog.start_scan(self.roots[0]);self.catalog._worker.join(15)
        scope={'root_ids':[self.roots[0]]}
        self.build(scope)
        batch_sizes=[];fresh_ids=self.ai.store.fresh_ids
        def counted(rows):
            batch_sizes.append(len(rows));return fresh_ids(rows)
        with patch.object(self.ai.store,'fresh_ids',side_effect=counted):
            counts=self.ai.coverage(scope)
            self.assertEqual((counts['candidate_total'],counts['fresh_total'],counts['remaining_total']),(263,263,0))
            self.assertEqual(batch_sizes,[256,7])
        page=self.ai.search('雨',scope=scope,page=1)
        self.assertEqual((page['total'],len(page['items'])),(263,60))
        changed=self.ai._rows()[0];self.catalog.update([changed['id']],{'tags':['変更']})
        self.assertEqual(self.ai.coverage(scope)['remaining_total'],1)

    def test_deleted_registered_root_is_error_without_fallback(self):
        scope={'root_ids':[self.roots[0]]}
        self.build(scope)
        with self.catalog.connect() as db:db.execute('DELETE FROM library_roots WHERE id=?',(self.roots[0],))
        for operation in (lambda:self.ai.coverage(scope),lambda:self.ai.start(scope=scope),lambda:self.ai.search('雨',scope=scope)):
            with self.assertRaises(ValueError):operation()

    def test_coverage_works_without_available_encoder_and_refuses_scan(self):
        self.encoder.available=False
        self.assertEqual(self.ai.coverage({})['candidate_total'],6)
        self.assertEqual(self.encoder.calls,[])
        with patch.object(self.catalog,'scan_state',return_value={'state':'running'}):
            with self.assertRaises(AIBusy):self.ai.coverage({})

    def test_http_scope_counts_index_search_auth_and_null_rejection(self):
        profiles=AIProfileSettings(Path(__file__).resolve().parents[1],self.base/'settings.json')
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token',self.ai,profiles=profiles))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}'
        headers={'X-Aredoko-Token':'test-token','Origin':url,'Content-Type':'application/json'}
        def request(route,body,custom=None):
            with urllib.request.urlopen(urllib.request.Request(url+route,json.dumps(body).encode(),headers if custom is None else custom)) as response:return json.load(response)
        scope={'root_ids':[self.roots[1]],'kind':'audio'}
        self.assertEqual(request('/api/library/ai/coverage',{'scope':scope})['target_total'],2)
        self.assertEqual(self.encoder.calls,[])
        request('/api/library/ai/index',{'scope':scope});self.ai.worker.join(10)
        self.assertEqual(request('/api/library/ai/search',{'query':'雨','scope':scope})['total'],2)
        for route in ('coverage','index','search'):
            with self.subTest(route=route),self.assertRaises(urllib.error.HTTPError) as error:
                request('/api/library/ai/'+route,{'scope':None,**({'query':'雨'} if route=='search' else {})})
            self.assertEqual(error.exception.code,400);error.exception.close()
        for custom in ({'Origin':url},{'X-Aredoko-Token':'test-token'}):
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/library/ai/coverage',{},custom)
            self.assertEqual(error.exception.code,403);error.exception.close()
