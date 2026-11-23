"""CPU-only scope/ownership cases; generated roots and in-memory AI spies."""
import sys,threading,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from scan_ai_followup import run_scan_ai


class SpyAI:
    def __init__(self,hold=False):
        self.guard=threading.RLock();self.worker=None;self.scope=None
        self.release=threading.Event();self.started=threading.Event();self.state='idle';self.cancels=0
        if not hold:self.release.set()
    def start(self,scope):
        self.scope=scope;self.state='running'
        def work():
            self.started.set();self.release.wait(5)
            with self.guard:self.state='cancelled' if self.cancels else 'complete'
        self.worker=threading.Thread(target=work);self.worker.start();return self.status()
    def status(self):return {'available':True,'state':self.state,'processed':1,'total':1,'error':''}
    def cancel_build(self):self.cancels+=1;self.release.set()


class ScanFollowupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.catalog=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.catalog.close)
        self.roots=[]
        for index in range(3):
            folder=self.base/str(index);folder.mkdir();(folder/'item.png').write_bytes(b'generated')
            self.roots.append(self.catalog.add_root(str(folder)))
    def run_followup(self,scope,roots,cancelled=lambda:False,ai=None):
        ai=ai or SpyAI();progress=[]
        result=run_scan_ai(ai,SimpleNamespace(scope=lambda:scope),self.catalog,roots,cancelled,progress.append)
        return ai,result,progress
    def test_narrows_all_roots_without_changing_saved_scope(self):
        scope={'root_ids':None,'kind':'image','shelf':'素材'}
        ai,state,_=self.run_followup(scope,self.roots[:1])
        self.assertEqual(ai.scope,{'root_ids':self.roots[:1],'kind':'image','shelf':'素材'})
        self.assertIsNone(scope['root_ids']);self.assertEqual(state['state'],'complete')
    def test_intersects_multi_root_request_and_preserves_shelf_filters(self):
        scope={'root_ids':self.roots[1:],'kind':'book','shelf_ids':[2],'shelf_filter_ids':[3]}
        ai,_,_=self.run_followup(scope,self.roots[:2]);self.assertEqual(ai.scope['root_ids'],[self.roots[1]])
        self.assertEqual(ai.scope['shelf_ids'],[2]);self.assertEqual(ai.scope['shelf_filter_ids'],[3])
    def test_empty_scope_skips_without_starting_model(self):
        ai,state,_=self.run_followup({'root_ids':[]},self.roots)
        self.assertIsNone(ai.worker);self.assertEqual(state['state'],'skipped')
    def test_cancel_before_ai_starts_keeps_model_unloaded(self):
        ai,state,_=self.run_followup({},self.roots,cancelled=lambda:True)
        self.assertIsNone(ai.worker);self.assertEqual(state['state'],'cancelled')
    def test_changed_worker_is_never_cancelled_as_our_scan(self):
        ai=SpyAI(hold=True);other=object()
        def progress(state):
            with ai.guard:ai.worker=other
        result=run_scan_ai(ai,None,self.catalog,self.roots,lambda:False,progress)
        self.assertEqual(result['state'],'failed');self.assertEqual(ai.cancels,0)
        ai.release.set()
    def test_own_worker_can_cancel_while_metadata_remains_editable(self):
        ai=SpyAI(hold=True);self.addCleanup(ai.release.set)
        self.catalog.ai_scan_hook=lambda roots,total,cancelled:run_scan_ai(ai,None,self.catalog,roots,cancelled,self.catalog._scan_ai_progress)
        self.catalog.start_scan(self.roots[0],mode='list_and_ai');self.assertTrue(ai.started.wait(2))
        item=self.catalog.search()['items'][0]
        self.catalog.update([item['id']],{'tags':['編集可能']})
        with self.assertRaises(ValueError):self.catalog.start_scan(self.roots[1])
        self.catalog.cancel_scan();self.catalog._worker.join(3)
        self.assertFalse(self.catalog._worker.is_alive());self.assertEqual(ai.cancels,1)
        self.assertEqual(self.catalog.scan_state()['ai_state'],'cancelled')
        self.assertEqual(self.catalog.get(item['id'])['tags'],['編集可能'])
    def test_successful_root_is_published_even_if_later_root_fails(self):
        scan=self.catalog.index.scan
        def selected(root,**kwargs):
            if root==self.roots[1]:raise PermissionError('private path must not be returned')
            return scan(root,**kwargs)
        with patch.object(self.catalog.index,'scan',side_effect=selected):
            self.catalog.start_scan(root_ids=self.roots[:2]);self.catalog._worker.join(3)
        state=self.catalog.scan_state();self.assertEqual(state['state'],'failed')
        self.assertEqual(state['completed_root_ids'],self.roots[:1]);self.assertEqual(self.catalog.search()['total'],1)
        self.assertNotIn('private',state['error'])
    def test_nested_or_boolean_root_identifiers_are_validation_errors(self):
        for roots in ([[1]],[True],['1'],[1,1]):
            with self.subTest(roots=roots),self.assertRaises(ValueError):self.catalog.start_scan(root_ids=roots)
    def test_real_ai_service_with_cpu_fake_encoder_finishes_owned_scope(self):
        from ai_search import AISearch
        class Encoder:
            available=True;device='generated-test-only'
            def encode(self,operation,value):return [1.0]+[0.0]*767
            def close(self):pass
        self.catalog.start_scan(root_ids=self.roots);self.catalog._worker.join(3)
        ai=AISearch(self.catalog,Encoder());self.addCleanup(ai.close)
        _,state,_=self.run_followup({},self.roots[:1],ai=ai)
        self.assertEqual(state['state'],'complete');self.assertEqual(state['total'],1)
        self.assertEqual(ai.status()['scope']['root_ids'],self.roots[:1])

if __name__=='__main__':unittest.main()
