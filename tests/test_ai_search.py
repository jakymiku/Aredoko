"""Deterministic protocol tests, not evidence of model retrieval quality."""
import json
import math
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ai_search import AISearch, AIBusy, VectorStore, normalized, revision, MAX_ITEMS
from ai_process import AIUnavailable
from production import ProductionCatalog
from production_server import production_handler, create_ai
from setup_ai import RateGate

def vector(axis):
    data=[0.0]*768
    data[axis]=1.0
    return data

class TestEncoder:
    available=True
    device='test-only'
    def __init__(self): self.calls=[]
    def encode(self,operation,value):
        self.calls.append(operation)
        return vector(0 if '雨' in str(value) or operation=='query' else 1)
    def close(self): pass

class AISearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.media=self.base/'media';self.media.mkdir()
        (self.media/'rain.wav').write_text('generated',encoding='utf-8')
        (self.media/'sun.wav').write_text('generated',encoding='utf-8')
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.root=self.catalog.add_root(str(self.media))
        self.catalog.start_scan(self.root);self.catalog._worker.join(10)
        self.items=self.catalog.search()['items']
        self.rain=next(x for x in self.items if x['title']=='rain.wav')
        self.sun=next(x for x in self.items if x['title']=='sun.wav')
        self.catalog.update([self.rain['id']],{'tags':['雨の夜']})
        self.encoder=TestEncoder()
        self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
    def build(self):
        self.ai.start();self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'],'complete')
    def test_rank_filters_and_sources_unchanged(self):
        before={p.name:p.read_bytes() for p in self.media.iterdir()}
        self.build()
        result=self.ai.search('濡れた夜の街')
        self.assertEqual(result['items'][0]['id'],self.rain['id'])
        self.catalog.update([self.sun['id']],{'favorite':True})
        self.assertEqual(self.ai.search('雨',view='favorites')['items'][0]['id'],self.sun['id'])
        self.assertEqual({p.name:p.read_bytes() for p in self.media.iterdir()},before)
    def test_resumed_build_reuses_saved_revisions(self):
        self.build();count=self.encoder.calls.count('document')
        self.build();self.assertEqual(self.encoder.calls.count('document'),count)
        self.catalog.update([self.rain['id']],{'tags':['雨と霧']})
        self.assertEqual(self.ai.search('雨')['total'],1)
        self.build();self.assertEqual(self.encoder.calls.count('document'),count+1)
    def test_current_excludes_and_missing_never_rank(self):
        self.build()
        self.catalog.set_excludes(self.root,['rain.wav'])
        self.assertEqual(self.ai.search('雨')['total'],1)
        (self.media/'sun.wav').unlink()
        self.catalog.start_scan(self.root);self.catalog._worker.join(10)
        self.assertEqual(self.ai.search('雨')['total'],0)
    def test_cancel_keeps_completed_items_and_can_resume(self):
        entered=threading.Event();release=threading.Event()
        original=self.encoder.encode
        def blocked(op,val):
            if op=='document':
                entered.set();release.wait(5)
            return original(op,val)
        self.encoder.encode=blocked
        self.ai.start();self.assertTrue(entered.wait(3))
        with self.assertRaises(AIBusy): self.ai.start()
        with self.assertRaises(AIBusy): self.ai.search('雨')
        self.ai.cancel_build();release.set();self.ai.worker.join(10)
        self.assertEqual(self.ai.status()['state'],'cancelled')
        self.assertEqual(self.ai.status()['processed'],1)
        self.encoder.encode=original
        self.build();self.assertEqual(self.ai.status()['indexed'],2)
    def test_bad_embeddings_cannot_replace_previous_vector(self):
        self.build()
        row=self.catalog.get(self.rain['id'])
        for bad in ([0.0]*768,[math.nan]*768,[1.0], [math.inf]*768):
            with self.assertRaises(ValueError): self.ai.store.put(row['id'],revision(row),{'text':bad})
        self.assertEqual(self.ai.search('雨')['total'],2)
    def test_profile_mismatch_and_restart_state(self):
        self.ai.store.save_state({'state':'running','processed':1,'total':2,'indexed':1,'skipped':0,'error':''})
        reopened=VectorStore(self.ai.store.path)
        self.assertEqual(reopened.state()['state'],'interrupted')
        with reopened.connect() as db: db.execute("UPDATE ai_profile SET value='other'")
        with self.assertRaises(AIUnavailable): VectorStore(reopened.path)
    def test_corrupt_optional_ai_cache_keeps_literal_catalog_usable(self):
        self.ai.close()
        self.ai.store.path.write_bytes(b'not sqlite')
        disabled=create_ai(self.catalog)
        self.assertFalse(disabled.status()['available'])
        self.assertEqual(self.catalog.search()['total'],2)
        with self.assertRaises(AIUnavailable): disabled.search('雨')
    def test_unavailable_and_invalid_requests(self):
        self.encoder.available=False
        with self.assertRaises(AIUnavailable): self.ai.start()
        with self.assertRaises(AIUnavailable): self.ai.search('雨')
        for limit in (0,MAX_ITEMS+1,True):
            with self.assertRaises(ValueError): self.ai.start(limit)
        with self.assertRaises(ValueError): self.ai.search('')
    def test_visual_source_does_not_use_filename_vector(self):
        # Real image kinds keep this a cover-vs-text contract test. Audio rows
        # must not masquerade as image candidates through manually seeded cache.
        from create_preview_fixture import png
        (self.media/'rain.png').write_bytes(png());(self.media/'sun.png').write_bytes(png())
        self.catalog.start_scan(self.root);self.catalog._worker.join(10)
        self.build()
        images={row['title']:row for row in self.catalog.search(kind='image')['items']}
        rain=images['rain.png'];sun=images['sun.png']
        self.ai.store.put(rain['id'],revision(rain),{'text':vector(0),'cover':vector(1)})
        self.ai.store.put(sun['id'],revision(sun),{'text':vector(1),'cover':vector(0)})
        result=self.ai.search('雨',source='cover')
        self.assertEqual(result['items'][0]['id'],sun['id'])
        self.assertEqual(result['source'],'cover')
        with self.assertRaises(ValueError): self.ai.search('雨',source='invalid')
    def test_ranking_override_score_contract_and_manual_source_precedence(self):
        self.build()
        default=self.ai.search('雨')
        self.assertEqual(default['ranking'],'mean-rrf');self.assertEqual(default['score_kind'],'reciprocal-rank')
        legacy=self.ai.search('雨',ranking='max')
        self.assertEqual(legacy['ranking'],'max');self.assertEqual(legacy['score_kind'],'cosine')
        cover=self.ai.search('雨',source='cover',ranking='mean-rrf')
        self.assertEqual(cover['source'],'cover');self.assertEqual(cover['ranking'],'max')
        text=self.ai.search('雨',source='text',ranking='mean-rrf')
        self.assertEqual(text['ranking'],'max');self.assertEqual(text['score_kind'],'cosine')
        self.assertEqual({r['id'] for r in default['items']},{r['id'] for r in legacy['items']})
        with self.assertRaises(ValueError):self.ai.search('雨',ranking='unknown')

    def test_http_index_default_cap_and_legacy_limit(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token',self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}'
        headers={'X-Aredoko-Token':'test-token','Origin':url,'Content-Type':'application/json'}
        for body,expected in (({},10000),({'limit':2000},2000)):
            with patch.object(self.ai,'start',wraps=self.ai.start) as start:
                with urllib.request.urlopen(urllib.request.Request(url+'/api/library/ai/index',json.dumps(body).encode(),headers)) as response:
                    self.assertEqual(json.load(response)['limit'],10000)
                start.assert_called_once_with(expected)
            self.ai.worker.join(10)
            self.assertEqual(self.ai.status()['state'],'complete')
        for invalid in (10001,True):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(url+'/api/library/ai/index',json.dumps({'limit':invalid}).encode(),headers))
            self.assertEqual(error.exception.code,400);error.exception.close()

    def test_http_token_origin_and_semantic_route(self):
        self.build()
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test-token',self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}'
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(url+'/api/library/ai/status')
        self.assertEqual(error.exception.code,403)
        error.exception.close()
        headers={'X-Aredoko-Token':'test-token','Origin':url,'Content-Type':'application/json'}
        request=urllib.request.Request(url+'/api/library/ai/search',json.dumps({'query':'雨'}).encode(),headers)
        with urllib.request.urlopen(request) as response:
            self.assertEqual(json.load(response)['mode'],'semantic')
        headers.pop('Origin')
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(url+'/api/library/ai/index',b'{}',headers))
        self.assertEqual(error.exception.code,403)
        error.exception.close()

class DownloadCapTests(unittest.TestCase):
    def test_parallel_transfers_share_one_rate_budget(self):
        gate=RateGate(6_000_000)
        start=time.monotonic()
        threads=[threading.Thread(target=gate.wait,args=(120_000,)) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        elapsed=time.monotonic()-start
        self.assertGreaterEqual(elapsed,480_000/6_000_000*0.95)
        self.assertEqual(gate.bytes,480_000)

