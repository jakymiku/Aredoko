"""Read/write/pause ordering on actual generated catalog/vector/settings stores."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import sys,tempfile,threading,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from writer_fence import WriterFence
from production import ProductionCatalog
from ai_search import VectorStore
from ai_profiles import DEFAULT_PROFILE
from ai_settings import AIProfileSettings
from backup_jobs import BackupJobs

class WriterFenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close)
        media=self.base/'media';media.mkdir();(media/'a.png').write_bytes(b'generated-only');root=self.cat.add_root(str(media));self.cat.index.scan(root);self.cat.sync_index();self.item=self.cat.search()['items'][0]['id']
    def test_catalog_vector_and_settings_writes_pause_while_reads_continue(self):
        fence=self.cat.writer_fence;profile=replace(DEFAULT_PROFILE,dimension=3)
        store=VectorStore(self.base/'vectors.sqlite',profile,writer_fence=fence)
        settings=AIProfileSettings(Path(__file__).resolve().parents[1],self.base/'settings.json',profile_directory=self.base/'profiles');settings.writer_fence=fence
        entered=[threading.Event() for _ in range(3)];done=[threading.Event() for _ in range(3)]
        def writer(number,operation):entered[number].set();operation();done[number].set()
        operations=[lambda:self.cat.update([self.item],{'tags':['after']}),lambda:store.save_state({'state':'complete'}),lambda:settings.set_scope({'kind':'image'})]
        threads=[threading.Thread(target=writer,args=(i,operation)) for i,operation in enumerate(operations)]
        with fence.pause():
            for thread in threads:thread.start()
            for event in entered:self.assertTrue(event.wait(2))
            self.assertEqual(self.cat.search()['total'],1);self.assertFalse(any(event.is_set() for event in done))
            self.assertEqual(store.state()['state'],'idle')
        for thread in threads:thread.join(3);self.assertFalse(thread.is_alive())
        self.assertTrue(all(event.is_set() for event in done));self.assertEqual(self.cat.get(self.item)['tags'],['after'])
    def test_pause_waits_for_complete_logical_writer_and_allows_its_nested_work(self):
        fence=WriterFence();entered=threading.Event();finish=threading.Event();paused=threading.Event();release=threading.Event();nested=[]
        def writer():
            with fence.write():
                entered.set();finish.wait(3)
                with fence.write():nested.append(True)
        def pause():
            with fence.pause():paused.set();release.wait(3)
        first=threading.Thread(target=writer);second=threading.Thread(target=pause);first.start();self.assertTrue(entered.wait(2));second.start()
        self.assertFalse(paused.wait(.05));finish.set();self.assertTrue(paused.wait(2));release.set();first.join(3);second.join(3)
        self.assertEqual(nested,[True]);self.assertFalse(first.is_alive() or second.is_alive())
    def test_waiting_pause_cancels_and_unblocks_new_writers(self):
        fence=WriterFence();entered=threading.Event();release=threading.Event();cancelled=threading.Event();errors=[]
        def writer():
            with fence.write():entered.set();release.wait(3)
        def pause():
            try:
                with fence.pause(cancelled=cancelled.is_set):self.fail('pause should be cancelled')
            except InterruptedError:errors.append(True)
        first=threading.Thread(target=writer);first.start();self.assertTrue(entered.wait(2));second=threading.Thread(target=pause);second.start();cancelled.set();second.join(3);release.set();first.join(3)
        self.assertEqual(errors,[True]);self.assertFalse(fence.paused)
        with fence.write():pass
    def test_actual_backup_uses_catalog_guard_before_global_pause(self):
        jobs=BackupJobs(self.cat,quiesce=self.cat.writer_fence.pause);self.addCleanup(jobs.close)
        job=jobs.start({'consent':True,'output':str(self.base/'bundle'),'selection':{'settings':False,'history':True,'reader_progress':True,'vectors':False}});jobs.thread.join(5)
        self.assertEqual(jobs.snapshot(job['job_id'])['state'],'complete');self.assertFalse(self.cat.writer_fence.paused)
    def test_backup_cancel_does_not_wait_for_a_busy_catalog_guard(self):
        jobs=BackupJobs(self.cat,quiesce=self.cat.writer_fence.pause);self.addCleanup(jobs.close)
        waiting=threading.Event();original=jobs._progress
        def report(value):
            original(value)
            if value['stage']=='waiting':waiting.set()
        jobs._progress=report
        with self.cat._guard:
            job=jobs.start({'consent':True,'output':str(self.base/'cancelled-bundle'),'selection':{'settings':False,'history':True,'reader_progress':True,'vectors':False}})
            self.assertTrue(waiting.wait(2));self.assertTrue(jobs.cancel(job['job_id'])['cancel_accepted']);jobs.thread.join(2)
            self.assertFalse(jobs.thread.is_alive(),'Cancellation must finish while the catalog guard is still held')
            self.assertEqual(jobs.snapshot()['state'],'cancelled')
        self.assertFalse((self.base/'cancelled-bundle').exists());self.assertFalse(self.cat.writer_fence.paused)

    def test_runtime_rejects_pause_inside_a_writer(self):
        fence=WriterFence()
        with fence.write():
            with self.assertRaises(RuntimeError):
                with fence.pause():pass
