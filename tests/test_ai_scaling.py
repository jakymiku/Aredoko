"""Generated catalogs and deterministic vectors; no GPU/model quality claim."""
from dataclasses import replace
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, AIBusy, MAX_ITEMS, VectorStore, revision
from production import ProductionCatalog

class ScaleEncoder:
    available=True
    device='deterministic-test-only'
    profile=replace(DEFAULT_PROFILE,dimension=8,modalities=('text',))
    def __init__(self):self.documents=[];self.on_document=None
    def encode(self,operation,value):
        if operation=='document':
            self.documents.append(value)
            if self.on_document:self.on_document(len(self.documents))
        axis=0 if operation=='query' or 'late-target' in str(value) else 1
        vector=[0.0]*self.profile.dimension;vector[axis]=1.0
        return vector
    def close(self):pass

class ScalingTests(unittest.TestCase):
    def make(self,count,excluded_prefix=0):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        base=Path(tmp.name);media=base/'media';media.mkdir()
        for i in range(count):
            folder=media/('ignored' if i<excluded_prefix else 'keep')
            folder.mkdir(exist_ok=True)
            (folder/f'{i:05d}.wav').write_bytes(b'generated metadata-only audio fixture')
        catalog=ProductionCatalog(base/'catalog.sqlite');self.addCleanup(catalog.close)
        root=catalog.add_root(str(media));catalog.start_scan(root);catalog._worker.join(30)
        self.assertEqual(catalog.scan_state()['state'],'complete')
        encoder=ScaleEncoder();ai=AISearch(catalog,encoder);self.addCleanup(ai.close)
        return catalog,encoder,ai,media,root
    def build(self,ai,limit=None):
        ai.start() if limit is None else ai.start(limit)
        ai.worker.join(60)
        self.assertFalse(ai.worker.is_alive())
        self.assertEqual(ai.status()['state'],'complete')
    def test_legacy_2000_cache_extends_and_late_item_is_searchable(self):
        catalog,encoder,ai,media,_=self.make(2105)
        hashes={str(p.relative_to(media)):hashlib.sha256(p.read_bytes()).hexdigest() for p in media.rglob('*.wav')}
        late=ai._rows()[-1];catalog.update([late['id']],{'tags':['late-target'],'favorite':True})
        self.build(ai,2000);self.assertEqual(len(encoder.documents),2000)
        original_key=ai.profile.key;original_path=ai.store.path
        self.build(ai,2105)
        self.assertEqual(len(encoder.documents),2105)
        self.assertEqual(ai.store.path,original_path);self.assertEqual(ai.profile.key,original_key)
        result=ai.search('late-target')
        self.assertEqual(result['total'],2105);self.assertEqual(result['items'][0]['id'],late['id'])
        self.assertEqual(result['coverage_limit'],10000)
        self.assertEqual(ai.search('late-target',view='favorites')['items'][0]['id'],late['id'])
        self.assertEqual(len(ai.search('late-target',page=1)['items']),60)
        early=ai._rows()[0];catalog.update([early['id']],{'tags':['updated']})
        self.assertEqual(ai.search('late-target')['total'],2104)
        self.build(ai)
        self.assertEqual(len(encoder.documents),2106)
        ai.store.save_state({**ai.status(),'state':'running'})
        reopened=VectorStore(ai.store.path,ai.profile)
        self.assertEqual(reopened.state()['state'],'interrupted')
        ai.close();fresh_encoder=ScaleEncoder();fresh=AISearch(catalog,fresh_encoder);self.addCleanup(fresh.close)
        self.build(fresh)
        self.assertEqual(fresh_encoder.documents,[])
        self.assertEqual(fresh.search('late-target')['total'],2105)
        self.assertEqual(hashes,{str(p.relative_to(media)):hashlib.sha256(p.read_bytes()).hexdigest() for p in media.rglob('*.wav')})
    def test_early_exclusions_do_not_consume_eligible_limit(self):
        catalog,_,ai,_,root=self.make(308,300)
        catalog.set_excludes(root,['ignored'])
        candidates=ai._rows(limit=5)
        self.assertEqual(len(candidates),5)
        self.assertTrue(all(row['relative_path'].startswith('keep/') for row in candidates))
        self.build(ai,5);self.assertEqual(ai.status()['total'],5)
        self.assertEqual(ai.search('late-target')['total'],5)
    def test_cancel_across_batch_boundary_preserves_checkpoints_and_rechecks_changes(self):
        catalog,encoder,ai,_,_=self.make(300)
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        def pause(count):
            if count==300:entered.set();release.wait(30)
        encoder.on_document=pause
        ai.start();self.assertTrue(entered.wait(30))
        self.assertEqual(ai.status()['processed'],288)
        self.assertEqual(catalog.search()['total'],300)
        with self.assertRaises(AIBusy):ai.search('late-target')
        last=ai._rows()[-1];catalog.update([last['id']],{'tags':['changed while encoding']})
        ai.cancel_build();release.set();ai.worker.join(30)
        state=ai.status();self.assertEqual(state['state'],'cancelled')
        self.assertEqual((state['processed'],state['indexed'],state['skipped']),(300,299,1))
        self.assertFalse(ai.store.fresh(last['id'],revision(catalog.get(last['id']))))
        self.build(ai);self.assertEqual(len(encoder.documents),301)
        self.assertEqual(ai.status()['indexed'],300)
    def test_new_exclusion_during_encoding_cannot_publish_a_vector(self):
        catalog,encoder,ai,_,root=self.make(2)
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        encoder.on_document=lambda count:(entered.set(),release.wait(30)) if count==1 else None
        ai.start();self.assertTrue(entered.wait(30))
        first=ai._rows()[0];catalog.set_excludes(root,[first['title']]);release.set();ai.worker.join(30)
        self.assertEqual(ai.status()['state'],'complete');self.assertEqual(ai.status()['skipped'],1)
        self.assertFalse(ai.store.fresh(first['id'],revision(first)))
        self.assertEqual(ai.search('late-target')['total'],1)
    def test_candidate_bounds_are_strict_and_10000_is_allowed(self):
        _,_,ai,_,_=self.make(1)
        for limit in (0,MAX_ITEMS+1,True,1.5):
            with self.assertRaises(ValueError):ai.start(limit)
        self.build(ai,10000);self.assertEqual(ai.status()['limit'],10000)

class GlobalFusionTests(unittest.TestCase):
    def test_ranks_span_multiple_vector_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile=replace(DEFAULT_PROFILE,dimension=8)
            store=VectorStore(Path(tmp)/'vectors.sqlite',profile)
            rows=[]
            def vec(score):return [score,math.sqrt(1-score*score)]+[0.0]*6
            for i in range(1,271):
                row={'id':i,'root_id':1,'relative_path':str(i),'title':str(i),'tags':[],'size_bytes':1,'mtime_ns':1}
                rows.append(row)
                text,cover=(.99,.5) if i==10 else (.5,.99) if i==265 else (.1,.1)
                store.put(i,revision(row),{'text':vec(text),'cover':vec(cover)})
            query=[1.0]+[0.0]*7
            result=store.rank(rows,query,ranking='mean-rrf')
            self.assertEqual([i for i,_ in result[:2]],[10,265])
            self.assertAlmostEqual(result[0][1],(1/61+1/62)/2)
            self.assertAlmostEqual(result[1][1],result[0][1])
            self.assertEqual(store.rank(rows,query,source='cover')[0][0],265)
            self.assertEqual(store.rank(rows[-2:],query,ranking='mean-rrf')[0][0],269)
