"""Full-scope CPU integration; deterministic vectors are not AI quality evidence."""
from array import array
from dataclasses import replace
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'app'))
from audit_large_library_boundary import seed,QueryOnlyEncoder
from ai_search import AISearch,AIBusy,revision,source_contract
from ai_process import AIUnavailable
from ai_vectors import normalized
from ai_score_spool import ScoreSpool,ScoreSpoolError
from page_semantics import CONTRACT


def exact(ranked):return [(item,score.hex()) for item,score in ranked]


class StreamingSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/'fixture'
        self.catalog,self.roots,self.controls,self.books,self.paths=seed(self.base,769,10000)
        self.addCleanup(self.catalog.close)
        self.encoder=QueryOnlyEncoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.rows=[]
        for ids in (list(range(n,min(n+256,770))) for n in range(1,770,256)):
            self.rows.extend(self.ai._current_rows(ids).values())
        records=[];contracts=[]
        for row in self.rows:
            item=row['id'];rev=revision(row)
            def packed(score):return array('f',normalized([score,math.sqrt(1-score*score),0.],3)).tobytes()
            for mode,score in (('text',(item%17)/20),('cover',(item%13)/15)):
                records.append((item,rev,mode,packed(score)))
            contract=source_contract(row,self.ai.profile)
            if contract:contracts.append((item,rev,contract))
        with self.ai.store.connect() as db:
            db.executemany('INSERT INTO ai_vectors VALUES(?,?,?,?)',records)
            db.executemany('INSERT INTO ai_source_contracts VALUES(?,?,?)',contracts)
        for item in self.books:
            self.ai.pages.index.refresh(item)
            snapshot=self.ai.pages.index.list(item)
            with self.ai.store.connect() as db:
                db.execute('INSERT INTO ai_page_vectors VALUES(?,?,?,?,?,?)',
                    (item,snapshot['source_revision'],snapshot['pages'][0]['page_id'],0,array('f',[1.,0.,0.]).tobytes(),CONTRACT))

    def test_streamed_api_matches_whole_pool_oracle_and_retains_evidence(self):
        for source,policy in (('text','max'),('cover','max'),('all','max'),('all','mean-rrf')):
            with self.subTest(source=source,policy=policy):
                query=normalized([1.,0.,0.],3)
                pages=self.ai.pages.rank(self.rows,query) if source!='text' else {}
                oracle,video_hits,page_hits=self.ai.store.rank_with_content(self.rows,query,source,policy,pages)
                captured=[];batch_sizes=[]
                finalize=ScoreSpool.finalize;score=self.ai.store.scores_with_content
                def finalized(spool,*args,**kwargs):
                    finalize(spool,*args,**kwargs);captured.extend(spool.ranked())
                def scored(rows,*args,**kwargs):
                    batch_sizes.append(len(rows));return score(rows,*args,**kwargs)
                calls=len(self.encoder.calls)
                with patch.object(ScoreSpool,'finalize',finalized),patch.object(self.ai.store,'scores_with_content',side_effect=scored):
                    result=self.ai.search('boundary',source=source,ranking=policy,limit=120)
                self.assertEqual(exact(captured),exact(oracle))
                self.assertEqual(batch_sizes,[256,256,256,1])
                self.assertEqual(len(self.encoder.calls)-calls,1)
                self.assertEqual((result['total'],result['indexed_total'],result['search_candidate_total']),(769,769,769))
                self.assertTrue(result['search_complete'])
                self.assertEqual([(row['id'],row['semantic_score']) for row in result['items']],
                                 [(item,round(score,6)) for item,score in oracle[:120]])
                if source!='text':
                    hit=next(row for row in result['items'] if row['id'] in self.books)
                    self.assertEqual(hit['ai_page_match'],page_hits[hit['id']])

    def test_scope_omitted_and_explicit_all_have_same_pool_and_deep_page(self):
        omitted=self.ai.search('boundary',source='text',page=6,limit=120)
        explicit=self.ai.search('boundary',source='text',page=6,limit=120,scope={})
        self.assertEqual(omitted['items'],explicit['items'])
        self.assertEqual((omitted['total'],len(omitted['items'])),(769,49))
        self.assertEqual(self.ai.search('boundary',page=10**100)['items'],[])
        literal=self.ai.search('boundary',source='all',literal_only=True)
        self.assertEqual([row['id'] for row in literal['items']],[769])
        self.assertEqual(literal['indexed_total'],769)  # literal filtering follows global fusion.

    def test_annotation_changes_without_epoch_increase_invalidate_whole_result(self):
        original=self.ai.store.scores_with_content
        for field,values in (('tags',['changed']),('shelf','changed'),('favorite',False)):
            before=self.catalog._state_epoch
            fired=[]
            def change(*args,**kwargs):
                result=original(*args,**kwargs)
                if not fired:
                    fired.append(True);self.catalog.update([769],{field:values})
                return result
            with self.subTest(field=field),patch.object(self.ai.store,'scores_with_content',side_effect=change),self.assertRaises(AIBusy):
                self.ai.search('boundary',source='text')
            self.assertEqual(self.catalog._state_epoch,before)

    def test_profile_store_write_during_rank_is_not_published(self):
        original=self.ai.store.scores_with_content;fired=[]
        def change(*args,**kwargs):
            result=original(*args,**kwargs)
            if not fired:
                fired.append(True)
                with self.ai.store.connect() as db:
                    db.execute("UPDATE ai_vectors SET vector=? WHERE item_id=769 AND modality='text'",(array('f',[1.,0.,0.]).tobytes(),))
            return result
        with patch.object(self.ai.store,'scores_with_content',side_effect=change),self.assertRaises(AIBusy):
            self.ai.search('boundary',source='text')

    def test_root_change_during_last_batch_is_not_a_partial_complete_result(self):
        original=self.ai.store.scores_with_content;seen=[]
        def change(rows,*args,**kwargs):
            result=original(rows,*args,**kwargs);seen.append(len(rows))
            if len(seen)==4:self.catalog.unregister_root(self.roots[-1])
            return result
        with patch.object(self.ai.store,'scores_with_content',side_effect=change),self.assertRaises(AIBusy):
            self.ai.search('boundary',source='text')

    def test_returned_page_changed_after_scoring_is_rejected(self):
        original=ScoreSpool.finalize
        book=next(path for path in self.paths if path.suffix=='.cbz')
        def change(spool,*args,**kwargs):
            original(spool,*args,**kwargs);book.write_bytes(b'generated changed book')
        with patch.object(ScoreSpool,'finalize',change),self.assertRaises(AIBusy):
            self.ai.search('boundary',source='cover')

    def test_conflict_and_capacity_error_release_workspace_and_inference(self):
        paths=[];original=ScoreSpool.__enter__
        def entered(spool):
            paths.append(spool.path.parent);return original(spool)
        with patch.object(ScoreSpool,'__enter__',entered),patch.object(ScoreSpool,'finalize',side_effect=ScoreSpoolError('generated full workspace')):
            with self.assertRaises(AIUnavailable):self.ai.search('boundary',source='text')
        self.assertTrue(paths)
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertTrue(self.ai.inference.acquire(blocking=False));self.ai.inference.release()
        self.assertTrue(self.ai.search('boundary',source='text')['search_complete'])


if __name__=='__main__':unittest.main()
