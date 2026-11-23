"""Durable prepared receipts use generated stores; no media/model discovery."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from production import ProductionCatalog
from storage_backup import backup
from restore_jobs import RestoreStagingJobs,RestoreBusy

class PreparedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        catalog=ProductionCatalog(self.base/'catalog.sqlite');catalog.close()
        backup(self.base/'catalog.sqlite',self.base/'bundle',include_vectors=False)
        self.stage=self.base/'restore-staging';self.jobs=RestoreStagingJobs(self.stage);self.addCleanup(self.jobs.close)
        self.value=self.jobs.start({'consent':True,'source':str(self.base/'bundle'),'without_vectors':True})
        self.jobs.manager.wait(self.value['job_id']);self.assertEqual(self.jobs.snapshot()['state'],'completed')
        self.jobs.close()
    def reopen(self):
        value=RestoreStagingJobs(self.stage);self.addCleanup(value.close);return value
    def test_reopen_preserves_exact_job_source_and_policy_without_cutover(self):
        jobs=self.reopen();value=jobs.snapshot()
        self.assertEqual(value['job_id'],self.value['job_id']);self.assertEqual(value['source'],str(self.base/'bundle'))
        self.assertTrue(value['without_vectors']);self.assertEqual(value['state'],'completed')
        self.assertFalse(value['restart_requested']);self.assertFalse((self.base/'launch-settings.json').exists())
        with self.assertRaises(RestoreBusy):jobs.start({'consent':True,'source':str(self.base/'bundle'),'without_vectors':True})
    def test_explicit_discard_of_recovered_job_removes_only_owned_stage(self):
        before=(self.base/'bundle/catalog.sqlite').read_bytes();jobs=self.reopen();stage=jobs.current.staging_path
        jobs.discard({'job_id':self.value['job_id'],'consent':True})
        self.assertFalse(stage.exists());self.assertFalse((self.stage/'prepared.json').exists())
        self.assertEqual((self.base/'bundle/catalog.sqlite').read_bytes(),before)
    def test_corrupt_receipt_blocks_only_restore_and_is_retained(self):
        receipt=self.stage/'prepared.json';receipt.write_text('[]')
        jobs=self.reopen();self.assertFalse(jobs.snapshot()['staging_supported'])
        with self.assertRaises(RestoreBusy):jobs.start({'consent':True,'source':str(self.base/'bundle'),'without_vectors':True})
        self.assertEqual(receipt.read_text(),'[]');self.assertTrue(self.jobs.current.staging_path.exists())
    def test_changed_recovery_metadata_is_not_accepted_or_deleted(self):
        receipt=self.jobs.current.staging_path/'recovery.json';receipt.write_text('{}')
        jobs=self.reopen();self.assertFalse(jobs.snapshot()['staging_supported']);self.assertEqual(receipt.read_text(),'{}')
    def test_loading_receipt_does_not_hash_or_open_catalog_payload(self):
        from unittest.mock import patch
        with patch('storage_backup._database',side_effect=AssertionError('Startup must not open payload DB')):
            self.assertEqual(self.reopen().snapshot()['state'],'completed')

if __name__=='__main__':unittest.main()
