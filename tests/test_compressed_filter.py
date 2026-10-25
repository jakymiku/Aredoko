"""Derived ZIP/CBZ categories and missing-evidence visibility, generated only."""
import sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from production import ProductionCatalog
from ai_search import AISearch
from ai_scope import validate_scope
from result_sessions import ResultSessions
from create_preview_fixture import png
from test_ai_scope import ScopeEncoder
from test_page_text import TextFixture
from test_tag_suggestions import TagFixture

class CompressedFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.media=self.base/'media';self.media.mkdir()
        for name in ('a.zip','b.CBZ'):
            with zipfile.ZipFile(self.media/name,'w') as archive:archive.writestr('1.png',png())
        for name in ('c.pdf','d.epub','e.png'):(self.media/name).write_bytes(png())
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close);self.root=self.cat.add_root(str(self.media))
        self.cat.start_scan(self.root);self.cat._worker.join(5);self.rows={r['title']:r for r in self.cat.search()['items']}
        self.compressed=[self.rows['a.zip']['id'],self.rows['b.CBZ']['id']]
    def test_unified_filter_preserves_old_storage_and_query_kinds(self):
        self.assertEqual([r['id'] for r in self.cat.search(kind='compressed')['items']],self.compressed)
        self.assertEqual(self.cat.search(kind='archive')['total'],1);self.assertEqual(self.cat.search(kind='book')['total'],3)
        self.assertEqual([self.rows[n]['kind'] for n in ('a.zip','b.CBZ','c.pdf','d.epub','e.png')],['archive','book','book','book','image'])
        self.assertEqual(self.cat.search(kind='compressed',query='b')['total'],1)
    def test_favorite_shelf_history_root_and_exclusion_intersections(self):
        shelf=self.cat.change_shelf('create',name='圧縮棚')['id'];self.cat.update(self.compressed[:1],{'favorite':True,'shelf_ids':[shelf]})
        self.assertEqual(self.cat.search(kind='compressed',view='favorites')['total'],1)
        self.assertEqual(self.cat.search(kind='compressed',shelf_ids=[shelf])['total'],1)
        self.cat.record_view(self.compressed[1]);self.assertEqual(self.cat.search(kind='compressed',view='history')['total'],1)
        self.assertEqual(self.cat.search(kind='compressed',root_ids=[self.root])['total'],2)
        self.cat.set_excludes(self.root,['b.CBZ']);self.assertEqual(self.cat.search(kind='compressed')['total'],1)
        self.cat.unregister_root(self.root);self.assertEqual(self.cat.search(kind='compressed')['total'],0)
    def test_cpu_semantic_search_and_saved_scope_keep_the_same_intersection(self):
        ai=AISearch(self.cat,ScopeEncoder());self.addCleanup(ai.close)
        scope=validate_scope({'root_ids':[self.root],'kind':'compressed'})
        ai.start(100,scope=scope);ai.worker.join(10);self.assertEqual(ai.status()['state'],'complete')
        self.assertEqual(ai.search('生成',kind='compressed',scope=scope)['total'],2)
        self.assertEqual(ai.search('生成',kind='book',scope=scope)['total'],1)
        self.assertEqual(ai.search('生成',kind='image',scope=scope)['total'],0)
        self.assertEqual(ai.search('生成',scope=scope)['total'],2)
    def test_result_session_uses_the_same_category_without_reclassifying_rows(self):
        owner=ResultSessions(self.cat,lambda conditions,consume,cancelled:consume(lambda page:self.cat.search(page=page,**conditions)),parent=self.base);self.addCleanup(owner.close)
        sid='a'*32;owner.create(sid,{'kind':'compressed'})
        result=owner.read(sid,0,120);self.assertEqual([r['id'] for r in result['items']],self.compressed)
        self.assertEqual([r['kind'] for r in result['items']],['archive','book'])
    def test_bad_query_kinds_are_rejected_before_sql(self):
        for kind in (True,[],{},'compressed OR 1=1'):
            with self.assertRaises(ValueError):self.cat.search(kind=kind)
            with self.assertRaises(ValueError):validate_scope({'kind':kind})

class CompressedTextTests(TextFixture,unittest.TestCase):
    def test_compressed_page_text_and_confirmed_missing_filter(self):
        self.item=self.ids['comic.cbz'];self.pages.refresh(self.item);listing=self.pages.list(self.item)
        self.revision=listing['source_revision'];self.page_ids=[p['page_id'] for p in listing['pages']]
        self.generate(page_ids=self.page_ids[:1]);self.assertEqual(self.texts.search('図書室',kind='compressed')['total'],1)
        before=self.text_counts();self.archive.unlink();self.catalog.start_scan(self.root);self.catalog._worker.join(5)
        self.assertEqual(self.texts.search('図書室',kind='compressed')['total'],0);self.assertEqual(self.text_counts(),before)

class CompressedCandidateTests(TagFixture,unittest.TestCase):
    def test_compressed_pending_candidates_and_confirmed_missing_filter(self):
        from tag_candidate_search import search_candidates
        item=self.ids['fiction.cbz'];self.generate(item)
        self.assertEqual(search_candidates(self.service,'生成',kind='compressed')['total'],1)
        before=self.counts();self.book.unlink();self.catalog.start_scan(self.root);self.catalog._worker.join(5)
        self.assertEqual(search_candidates(self.service,'生成',kind='compressed')['total'],0);self.assertEqual(self.counts(),before)

if __name__=='__main__':unittest.main()
