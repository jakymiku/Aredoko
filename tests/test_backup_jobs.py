"""Owned backup cancellation/publication; generated catalogs, no UI/API activation."""
from contextlib import contextmanager
from pathlib import Path
import sys,tempfile,threading,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from backup_jobs import BackupJobs,BackupBusy
from storage_backup import restore

class BackupJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.cat=ProductionCatalog(self.base/'catalog.sqlite');self.addCleanup(self.cat.close)
        self.body={'consent':True,'output':str(self.base/'bundle'),'selection':{'settings':True,'history':True,'reader_progress':True,'vectors':False}}
    @contextmanager
    def quiesce(self,*,cancelled=None):yield
    def jobs(self,**kwargs):
        value=BackupJobs(self.cat,quiesce=self.quiesce,**kwargs);self.addCleanup(value.close);return value
    def test_real_owned_capture_can_be_restored(self):
        jobs=self.jobs();job=jobs.start(self.body);jobs.thread.join(5)
        value=jobs.snapshot(job['job_id']);self.assertEqual(value['state'],'complete');self.assertTrue(value['published'])
        self.assertFalse(jobs.cancel(job['job_id'])['cancel_accepted'])
        restore(self.base/'bundle',self.base/'restored');self.assertTrue((self.base/'restored/catalog.sqlite').is_file())
        copied=jobs.snapshot();copied['selection']['history']=False;self.assertTrue(jobs.snapshot()['selection']['history'])
    def test_cancel_wins_before_publication_and_rejects_stale_ids(self):
        reached=threading.Event();release=threading.Event();published=[]
        def capture(catalog,output,**kwargs):
            reached.set();release.wait(5);kwargs['publish'](lambda:published.append(True));return {}
        jobs=self.jobs(capture=capture);first=jobs.start(self.body);self.assertTrue(reached.wait(3))
        with self.assertRaises(BackupBusy):jobs.start(self.body)
        self.assertTrue(jobs.cancel(first['job_id'])['cancel_accepted']);release.set();jobs.thread.join(5)
        self.assertEqual(jobs.snapshot()['state'],'cancelled');self.assertEqual(published,[])
        second=jobs.start(self.body);jobs.thread.join(5);self.assertNotEqual(first['job_id'],second['job_id'])
        with self.assertRaises(KeyError):jobs.cancel(first['job_id'])
        self.assertEqual(jobs.snapshot()['state'],'complete')
    def test_closed_owner_cannot_publish_after_blocking_io_returns(self):
        reached=threading.Event();release=threading.Event();published=[]
        def capture(catalog,output,**kwargs):
            reached.set();release.wait(5);kwargs['publish'](lambda:published.append(True));return {}
        jobs=self.jobs(capture=capture);jobs.start(self.body);self.assertTrue(reached.wait(3))
        self.assertFalse(jobs.close(timeout=0));release.set();jobs.thread.join(5)
        self.assertEqual(published,[]);self.assertEqual(jobs.snapshot()['state'],'cancelled')
        with self.assertRaises(BackupBusy):jobs.start(self.body)
    def test_failure_after_publication_does_not_claim_rollback(self):
        def capture(catalog,output,**kwargs):kwargs['publish'](lambda:None);raise OSError('injected cleanup failure')
        jobs=self.jobs(capture=capture);job=jobs.start(self.body);jobs.thread.join(5)
        value=jobs.snapshot();self.assertEqual(value['state'],'complete');self.assertTrue(value['published']);self.assertEqual(value['error_code'],'post_publish_cleanup_failed')
        self.assertFalse(jobs.cancel(job['job_id'])['cancel_accepted'])
    def test_invalid_request_and_unstarted_thread_cleanup(self):
        jobs=self.jobs()
        for value in ({**self.body,'consent':False},{**self.body,'output':'relative'},{**self.body,'selection':{}},{**self.body,'extra':True}):
            with self.assertRaises(ValueError):jobs.start(value)
        with patch.object(threading.Thread,'start',side_effect=RuntimeError('injected')),self.assertRaises(BackupBusy):jobs.start(self.body)
        self.assertEqual(jobs.snapshot()['state'],'failed');self.assertTrue(jobs.close())
