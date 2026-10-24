"""One-archive acquisition over generated loopback HTTP; never runs a runtime."""
import hashlib,json,random,sys,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/n) for n in ('app','tools')]
import test_ai_acquisition as http_fixture
import test_ai_runtime as runtime_fixture
from ai_acquisition import Catalog,acquire,validate_runtime
from ai_download_jobs import AIDownloadJobs,ACTIVE
from ai_runtime import MARKER,inspect_runtime


class ArchiveAcquisitionTests(unittest.TestCase):
    def setUp(self):
        http_fixture.AcquisitionTests.setUp(self)
        self.source=runtime_fixture.fixture(self.base/'runtime')
        (self.source/'generated-large.bin').write_bytes(random.Random(1).randbytes(300000));manifest=runtime_fixture.seal(self.source)
        archive=self.base/'runtime.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as target:
            for file in self.source.rglob('*'):
                if file.is_file():target.write(file,file.relative_to(self.source).as_posix())
        self.content=archive.read_bytes();url=self.value['entries'][0]['url']
        self.value.update(format='aredoko-acquisition-v3',runtime_archive={'manifest_sha256':hashlib.sha256((self.source/MARKER).read_bytes()).hexdigest(),'unpacked_bytes':manifest['total_bytes'],'unpacked_files':manifest['files_count']},entries=[{'path':'runtime.zip','url':url,'bytes':len(self.content),'sha256':hashlib.sha256(self.content).hexdigest(),'role':'archive'}])
    def catalog(self):return Catalog.parse(json.dumps(self.value).encode(),test_loopback=True)
    def fetch(self,**kwargs):return acquire(self.catalog(),self.base/'versions',validate=validate_runtime,publish=lambda op:op(),**kwargs)
    def test_one_download_yields_runtime_root_and_reuse_never_redownloads(self):
        progress=[]
        with patch('subprocess.Popen',side_effect=AssertionError('No execution')):result=self.fetch(progress=progress.append)
        self.assertEqual(self.requests,[None]);root=Path(result['root']);self.assertTrue((root/MARKER).is_file());self.assertFalse((root/'runtime.zip').exists())
        self.assertIn('extracting',[v['stage'] for v in progress]);inspect_runtime(root,verify=True)
        self.assertTrue(self.fetch()['reused']);self.assertEqual(self.requests,[None])
    def test_transfer_cancel_resumes_range_then_expands(self):
        event=threading.Event()
        def progress(value):
            if value['stage']=='downloading' and value['bytes_received']>=65536:event.set()
        with self.assertRaises(InterruptedError):self.fetch(cancelled=event.is_set,progress=progress)
        self.fetch();self.assertEqual(self.requests,[None,'bytes=65536-'])
    def test_expansion_cancel_retains_archive_and_resumes_without_network(self):
        event=threading.Event();seen=[0]
        def progress(value):
            if value['stage']=='extracting':
                seen[0]+=1
                if seen[0]>=4:event.set()
        with self.assertRaises(InterruptedError):self.fetch(cancelled=event.is_set,progress=progress)
        root=self.base/'versions';catalog=self.catalog();self.assertFalse((root/(catalog.key+'-'+catalog.fingerprint[:24])).exists())
        self.fetch();self.assertEqual(self.requests,[None])
    def test_changed_published_runtime_is_preserved_and_rejected(self):
        result=self.fetch();file=Path(result['root'])/'generated-large.bin';bad=b'x'*file.stat().st_size;file.write_bytes(bad)
        with self.assertRaisesRegex(ValueError,'changed'):self.fetch()
        self.assertEqual(file.read_bytes(),bad);self.assertEqual(self.requests,[None])
    def test_archive_manifest_mismatch_never_publishes(self):
        self.value['runtime_archive']['manifest_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'inventory changed'):self.fetch()
        self.assertFalse(any(p.is_dir() and not p.name.startswith('.') for p in (self.base/'versions').iterdir()))
    def test_v3_cannot_be_model_multi_file_inline_or_unbound_archive(self):
        original=json.loads(json.dumps(self.value))
        for mutate in (lambda v:v.update(kind='model'),lambda v:v['entries'].append(v['entries'][0].copy()),lambda v:v['entries'][0].update(role='runtime'),lambda v:v.update(format='aredoko-acquisition-v2')):
            self.value=json.loads(json.dumps(original));mutate(self.value)
            with self.assertRaises(ValueError):self.catalog()
    def test_job_summary_reports_installed_capacity_and_extraction_is_cancellable(self):
        catalog=self.catalog();owner=AIDownloadJobs(self.base/'jobs',specifications=((catalog,validate_runtime),));self.addCleanup(owner.close)
        row=owner.catalogs()['catalogs'][0];self.assertEqual(row['unpacked_bytes'],self.value['runtime_archive']['unpacked_bytes']);self.assertEqual(row['bytes'],len(self.content))
        self.assertIn('extracting',ACTIVE)
        owner.value.update(job_id='1'*32,state='extracting');self.assertTrue(owner.cancel('1'*32)['cancel_accepted'])
