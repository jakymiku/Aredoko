import json,sys,tempfile,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'app'));sys.path.insert(0,str(REPO/'tools'))
from production import ProductionCatalog
from ai_search import AISearch,revision
from create_holdout_fixture import create
from test_ai_search import TestEncoder,vector

class EmptyCoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);data=json.loads((REPO/'tests/fixtures/cover-empty-v1.json').read_text(encoding='utf-8'))
        media=create(base/'media',data['items']);self.catalog=ProductionCatalog(base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        root=self.catalog.add_root(str(media));self.catalog.start_scan(root);self.catalog._worker.join(10)
        self.scope={'root_ids':[root],'kind':'','shelf':None};self.encoder=TestEncoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.ai.start(scope=self.scope);self.ai.worker.join(10);self.assertEqual(self.ai.status()['state'],'complete');self.encoder.calls.clear()
    def test_unsupported_cover_kinds_skip_query_and_reject_stray_cover_vector(self):
        row=next(r for r in self.ai._rows('audio','all'))
        self.ai.store.put(row['id'],revision(row),{'text':vector(0),'cover':vector(0)})
        for kind in ['audio','material']:
            result=self.ai.search('午前の市場を歩く足音を探す',kind=kind,source='cover',scope=self.scope)
            self.assertEqual(result['items'],[]);self.assertEqual(result['total'],0);self.assertEqual(result['source'],'cover');self.assertEqual(result['scope'],self.scope)
        self.assertEqual(self.encoder.calls,[])
    def test_scope_kind_empty_pool_and_positive_modes_keep_contract(self):
        scoped={**self.scope,'kind':'audio'}
        self.assertEqual(self.ai.search('川辺で読書するときの音',source='cover',scope=scoped)['items'],[])
        self.assertEqual(self.encoder.calls,[])
        image=self.ai.search('黒い背景の黄色い三角マーク',kind='image',source='cover',scope=self.scope)
        self.assertEqual([r['title'] for r in image['items']],['c7_i01.png']);self.assertEqual(self.encoder.calls,['query'])
        combined=self.ai.search('料理のナレーション',kind='audio',source='all',scope=self.scope)
        self.assertEqual(combined['total'],2);self.assertEqual(self.encoder.calls,['query','query'])

if __name__=='__main__':unittest.main()
