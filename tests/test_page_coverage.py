"""Generated-only CPU page coverage and gap selection; no model downloads."""
from dataclasses import replace
import json
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from test_page_index import PageFixture
from test_page_semantics import Encoder
from ai_search import AISearch
from page_semantics import CONTRACT
from previews import ReaderChanged, PreviewBusyError
from production import ScanBusyError
from production_server import production_handler
from create_preview_fixture import png


class PageCoverageTests(PageFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.encoder=Encoder();self.ai=AISearch(self.catalog,self.encoder);self.addCleanup(self.ai.close)
        self.item=self.ids['comic.cbz'];self.scope={'root_ids':[self.root]}
        self.write_archive([(f'p{n:03}.png',self.first if n%2 else self.second) for n in range(40)])
        self.scan();self.pages.refresh(self.item);self.snapshot=self.pages.list(self.item)
        self.revision=self.snapshot['source_revision']
    def coverage(self):return self.ai.pages.coverage(self.item,self.revision,self.scope)
    def build(self,start,count):
        pages=self.snapshot['pages'][start:start+count]
        self.ai.pages.start(self.item,[p['page_id'] for p in pages],self.revision,self.scope)
        self.ai.worker.join(10);self.assertEqual(self.ai.status()['state'],'complete',self.ai.status())

    def during_decode(self, change):
        """An editor thread must enter the catalog guard before decoding ends."""
        import page_semantics
        original = page_semantics.unpack
        entered = False
        def decode(*args):
            nonlocal entered
            if not entered:
                entered = True
                errors = []
                def edit():
                    if not self.catalog._guard.acquire(timeout=1):
                        errors.append('vector decoding blocked a catalog edit'); return
                    # Public catalog mutations acquire this non-reentrant
                    # lock themselves. Probe availability, then release before
                    # calling them; the decoder waits for this editor thread.
                    self.catalog._guard.release()
                    try: change()
                    except Exception as ex: errors.append(ex)
                worker = threading.Thread(target=edit, daemon=True)
                worker.start(); worker.join(2)
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
            return original(*args)
        with patch('page_semantics.unpack', side_effect=decode):
            return self.coverage()

    def test_catalog_metadata_edit_can_finish_while_vectors_are_decoded(self):
        self.build(0, 16); calls = list(self.encoder.calls)
        before = self.coverage()
        actual = self.during_decode(lambda:self.catalog.update([self.item], {'favorite':True}))
        self.assertEqual(actual, before)
        self.assertTrue(self.catalog.get(self.item)['favorite'])
        self.assertEqual(self.encoder.calls, calls)

    def test_mid_decode_shelf_scope_change_is_not_reported_ready(self):
        self.catalog.update([self.item], {'shelf':'keep'})
        self.scope = {**self.scope, 'shelf':'keep'}; self.build(0, 16)
        with self.assertRaises(KeyError):
            self.during_decode(lambda:self.catalog.update([self.item], {'shelf':'other'}))

    def test_mid_decode_root_exclusion_and_unregister_are_rechecked(self):
        self.build(0, 16)
        with self.assertRaises(KeyError):
            self.during_decode(lambda:self.catalog.set_excludes(self.root, ['*.cbz']))
        self.catalog.set_excludes(self.root, [])
        with self.assertRaises(KeyError):
            self.during_decode(lambda:self.catalog.unregister_root(self.root))

    def test_mid_decode_changed_file_without_rescan_clears_ready(self):
        self.build(0, 16)
        value = self.during_decode(lambda:self.write_archive([('new.png', self.first)]))
        self.assertEqual(value['source_state'], 'stale')
        self.assertEqual(value['indexed_pages'], 0)
        self.assertIsNone(value['next_range'])

    def test_mid_decode_new_page_snapshot_requires_reopen(self):
        self.build(0, 16)
        def replace_snapshot():
            self.write_archive([('new.png', self.first)])
            self.scan(); self.pages.refresh(self.item)
        with self.assertRaises(ReaderChanged): self.during_decode(replace_snapshot)

    def test_scan_started_during_decode_is_rechecked(self):
        self.build(0, 16)
        with patch.object(self.catalog, '_require_idle', side_effect=[None, ScanBusyError('fixture')]):
            with self.assertRaises(ScanBusyError): self.coverage()

    def test_mid_decode_ai_close_is_rechecked(self):
        from ai_process import AIUnavailable
        self.build(0, 16)
        with self.assertRaises(AIUnavailable): self.during_decode(self.ai.close)


    def test_empty_coverage_is_cpu_only_and_never_creates_vectors_or_snapshots(self):
        with self.ai.store.connect() as db:before=db.execute('SELECT count(*) FROM ai_page_vectors').fetchone()[0]
        with patch.object(self.ai.pages.index,'input',side_effect=AssertionError('must not decode')):
            value=self.coverage()
        self.assertEqual((value['page_count'],value['indexed_pages'],value['remaining_pages']),(40,0,40))
        self.assertEqual(value['next_range'],{'start':0,'count':16});self.assertEqual(value['indexed_ranges'],[])
        self.assertEqual(value['profile'],self.ai.profile.key);self.assertEqual(value['source_state'],'current')
        self.assertEqual(self.encoder.calls,[])
        with self.ai.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM ai_page_vectors').fetchone()[0],before)

    def test_partial_disjoint_ranges_next_gap_and_complete_are_exact(self):
        self.build(16,16);value=self.coverage()
        self.assertEqual(value['indexed_ranges'],[{'start':16,'count':16}]);self.assertEqual(value['next_range'],{'start':0,'count':16})
        self.build(4,4);value=self.coverage()
        self.assertEqual(value['next_range'],{'start':0,'count':4})
        self.build(0,4);self.assertEqual(self.coverage()['next_range'],{'start':8,'count':8})
        self.build(8,8);self.assertEqual(self.coverage()['next_range'],{'start':32,'count':8})
        self.build(32,8);value=self.coverage()
        self.assertEqual(value['indexed_ranges'],[{'start':0,'count':40}]);self.assertIsNone(value['next_range'])
        self.assertEqual((value['indexed_pages'],value['remaining_pages']),(40,0))
        calls=list(self.encoder.calls);self.coverage();self.assertEqual(self.encoder.calls,calls)

    def test_corruption_wrong_page_revision_and_contract_do_not_count(self):
        self.build(0,6)
        with self.ai.store.connect() as db:
            db.execute('UPDATE ai_page_vectors SET vector=? WHERE page=0',(b'bad',))
            db.execute('UPDATE ai_page_vectors SET source_revision=? WHERE page=1',('a'*64,))
            db.execute('UPDATE ai_page_vectors SET contract=? WHERE page=2',('old-contract',))
            db.execute('UPDATE ai_page_vectors SET page=9999 WHERE page=3')
        value=self.coverage()
        self.assertEqual(value['indexed_pages'],2);self.assertEqual(value['indexed_ranges'],[{'start':4,'count':2}])
        self.assertEqual(value['next_range'],{'start':0,'count':4})

    def test_physical_change_busy_and_unavailable_never_report_old_vectors_ready(self):
        self.build(0,3)
        with patch.object(self.ai.previews,'tag_source',side_effect=PreviewBusyError()):
            value=self.coverage();self.assertEqual(value['source_state'],'unverified');self.assertEqual(value['indexed_pages'],0);self.assertIsNone(value['next_range'])
        self.write_archive([('p000.png',png(color=(1,2,3)))])
        value=self.coverage();self.assertEqual(value['source_state'],'stale');self.assertEqual(value['indexed_pages'],0);self.assertIsNone(value['next_range'])
        self.scan();self.pages.refresh(self.item)
        with self.assertRaises(ReaderChanged):self.coverage()
        self.revision=self.pages.list(self.item)['source_revision'];self.archive.unlink()
        value=self.coverage();self.assertEqual(value['source_state'],'unavailable');self.assertEqual(value['indexed_pages'],0)

    def test_profile_runtime_and_manual_metadata_are_independent(self):
        self.build(0,5);self.catalog.update([self.item],{'tags':['manual'],'shelf':'keep','favorite':True})
        self.assertEqual(self.coverage()['indexed_pages'],5)
        self.encoder.available=False;value=self.coverage();self.assertEqual(value['indexed_pages'],5);self.assertFalse(value['available'])
        self.ai.inference.acquire()
        try:self.assertEqual(self.coverage()['indexed_pages'],5)
        finally:self.ai.inference.release()
        other=AISearch(self.catalog,Encoder(16));self.addCleanup(other.close)
        value=other.pages.coverage(self.item,self.revision,self.scope);self.assertEqual(value['indexed_pages'],0);self.assertNotEqual(value['profile'],self.ai.profile.key)
        self.ai.profile=replace(self.ai.profile,modalities=('text',));value=self.coverage()
        self.assertFalse(value['supported']);self.assertEqual(value['indexed_pages'],0);self.assertIsNone(value['next_range'])
        self.assertEqual(self.catalog.get(self.item)['tags'],['manual']);self.assertTrue(self.catalog.get(self.item)['favorite'])

    def test_cancelled_and_failed_request_coverage_keeps_previous_ranges(self):
        self.build(0,4);before=self.coverage()['indexed_ranges']
        self.encoder.hook=lambda *args:self.ai.cancel.set()
        self.ai.pages.start(self.item,[p['page_id'] for p in self.snapshot['pages'][4:8]],self.revision,self.scope)
        self.ai.worker.join(10);self.assertEqual(self.ai.status()['state'],'cancelled')
        self.assertEqual(self.coverage()['indexed_ranges'],before)
        self.assertEqual(self.coverage()['next_range'],{'start':4,'count':16})

    def test_folder_book_scope_exclusions_and_scan_are_enforced(self):
        for scope in (None,{'root_ids':[]},{'root_ids':[self.bookroot]}):
            with self.subTest(scope=scope),self.assertRaises((ValueError,KeyError)):
                self.ai.pages.coverage(self.item,self.revision,scope)
        self.catalog.set_excludes(self.root,['*.cbz'])
        with self.assertRaises(KeyError):self.coverage()
        self.item=self.ids['comic/'];self.scope={'root_ids':[self.bookroot]}
        self.pages.refresh(self.item);self.snapshot=self.pages.list(self.item);self.revision=self.snapshot['source_revision']
        self.assertEqual(self.coverage()['next_range'],{'start':0,'count':2})
        with patch.object(self.catalog,'_require_idle',side_effect=ScanBusyError('fixture')):
            with self.assertRaises(ScanBusyError):self.coverage()
        self.catalog.unregister_root(self.bookroot)
        with self.assertRaises(ValueError):self.coverage()

    def test_http_strict_body_auth_and_stale_head(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'test',ai=self.ai))
        threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}';opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body={'item_id':self.item,'revision':self.revision,'scope':self.scope}
        def call(value,token='test',site=origin):
            request=urllib.request.Request(origin+'/api/library/ai/pages/coverage',json.dumps(value).encode(),
                headers={'Origin':site,'X-Aredoko-Token':token,'Content-Type':'application/json'})
            try:response=opener.open(request,timeout=5)
            except urllib.error.HTTPError as ex:response=ex
            with response:return response.code,json.loads(response.read())
        self.assertEqual(call(body)[0],200);self.assertEqual(self.encoder.calls,[])
        self.assertEqual(call(body,'bad')[0],403);self.assertEqual(call(body,site='https://example.invalid')[0],403)
        for changed in ({**body,'path':'anything'},{**body,'item_id':True},{**body,'revision':'bad'},{'item_id':self.item,'revision':self.revision}):
            self.assertEqual(call(changed)[0],400)
        self.assertEqual(call({**body,'revision':'a'*64})[0],409)
        self.assertEqual(call({**body,'scope':{'root_ids':[]}})[0],404)


if __name__=='__main__':unittest.main()
