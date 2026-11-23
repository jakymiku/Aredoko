"""Range/cancel/publication over two small generated loopback ZIP parts."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tests')]
import test_ai_runtime as fixture
from ai_acquisition import Catalog,acquire,validate_runtime
from ai_runtime import MARKER,inspect_runtime
from ai_download_jobs import AIDownloadJobs


class PartsAcquisitionTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        source=fixture.fixture(self.base/'source');(source/'generated.bin').write_bytes(random.Random(4).randbytes(300000));manifest=fixture.seal(source)
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_STORED) as archive:
            for path in source.rglob('*'):
                if path.is_file():archive.writestr(path.relative_to(source).as_posix(),path.read_bytes())
        data=buffer.getvalue();self.names=['runtime.zip.part001','runtime.zip.part002']
        self.content=dict(zip(self.names,(data[:len(data)//2],data[len(data)//2:])))
        self.requests=[];owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                name=self.path[1:];range_header=self.headers.get('Range');owner.requests.append((name,range_header))
                payload=owner.content[name];offset=int(range_header[6:-1]) if range_header else 0
                self.send_response(206 if range_header else 200);self.send_header('Content-Length',str(len(payload)-offset))
                if range_header:self.send_header('Content-Range',f'bytes {offset}-{len(payload)-1}/{len(payload)}')
                self.end_headers()
                try:self.wfile.write(payload[offset:])
                except (BrokenPipeError,ConnectionResetError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(3)))
        self.value={'format':'aredoko-acquisition-v4','id':'generated-parts','revision':'d'*40,'kind':'runtime',
            'license':'Generated test','license_url':'https://example.org/license','allowed_hosts':['127.0.0.1'],
            'runtime_archive':{'manifest_sha256':hashlib.sha256((source/MARKER).read_bytes()).hexdigest(),
                'unpacked_bytes':manifest['total_bytes'],'unpacked_files':manifest['files_count'],'parts':self.names.copy()},
            'entries':[{'path':name,'url':f'http://127.0.0.1:{server.server_port}/{name}','bytes':len(payload),
                'sha256':hashlib.sha256(payload).hexdigest(),'role':'archive'} for name,payload in self.content.items()]}

    def catalog(self):return Catalog.parse(json.dumps(self.value).encode(),test_loopback=True)
    def fetch(self,**kwargs):return acquire(self.catalog(),self.base/'versions',validate=validate_runtime,publish=lambda op:op(),**kwargs)

    def test_parts_publish_one_verified_root_and_reuse_never_redownloads(self):
        with patch('subprocess.Popen',side_effect=AssertionError('No runtime execution')):result=self.fetch()
        root=Path(result['root']);inspect_runtime(root,verify=True)
        self.assertTrue((root/MARKER).exists());self.assertEqual(set((self.base/'versions').rglob('*.zip')),{root/'python311.zip'})
        self.assertEqual(self.requests,[(name,None) for name in self.names]);self.assertTrue(self.fetch()['reused'])
        self.assertEqual(len(self.requests),2)

    def test_cancel_in_second_part_resumes_only_that_range(self):
        stopped=threading.Event();first_size=len(self.content[self.names[0]])
        def progress(value):
            if value['stage']=='downloading' and value['bytes_received']>=first_size+65536:stopped.set()
        with self.assertRaises(InterruptedError):self.fetch(cancelled=stopped.is_set,progress=progress)
        self.fetch()
        self.assertEqual(self.requests,[(self.names[0],None),(self.names[1],None),(self.names[1],'bytes=65536-')])

    def test_cancel_expansion_keeps_parts_but_never_publishes_partial_root(self):
        stopped=threading.Event();calls=[]
        def progress(value):
            if value['stage']=='extracting':
                calls.append(True)
                if len(calls)>=4:stopped.set()
        with self.assertRaises(InterruptedError):self.fetch(cancelled=stopped.is_set,progress=progress)
        catalog=self.catalog();self.assertFalse((self.base/'versions'/(catalog.key+'-'+catalog.fingerprint[:24])).exists())
        self.fetch();self.assertEqual(len(self.requests),2)

    def test_bad_part_hash_or_manifest_never_publishes(self):
        self.value['entries'][1]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'checksum'):self.fetch()
        self.assertFalse(any(p.is_dir() and not p.name.startswith('.') for p in (self.base/'versions').iterdir()))

    def test_catalog_refuses_wrong_order_format_kind_role_missing_or_oversize(self):
        original=json.loads(json.dumps(self.value))
        operations=[lambda v:v['runtime_archive']['parts'].reverse(),lambda v:v.update(format='aredoko-acquisition-v3'),
            lambda v:v.update(kind='model'),lambda v:v['entries'][0].update(role='runtime'),
            lambda v:v['entries'].pop(),lambda v:v['entries'][0].update(bytes=2*1024**3),
            lambda v:v['runtime_archive'].pop('parts')]
        for operation in operations:
            self.value=json.loads(json.dumps(original));operation(self.value)
            with self.subTest(operation=operation),self.assertRaises(ValueError):self.catalog()
        self.assertEqual(self.requests,[])

    def test_owned_job_keeps_existing_summary_progress_and_publication_contract(self):
        catalog=self.catalog();jobs=AIDownloadJobs(self.base/'owned',specifications=((catalog,validate_runtime),));self.addCleanup(jobs.close)
        summary=jobs.catalogs()['catalogs'][0]
        self.assertEqual(summary['bytes'],sum(len(data) for data in self.content.values()))
        self.assertEqual(summary['unpacked_bytes'],self.value['runtime_archive']['unpacked_bytes'])
        jobs.start({'consent':True,'catalog_id':catalog.fingerprint,'bytes_per_second':None})
        jobs.thread.join(5);self.assertFalse(jobs.thread.is_alive());value=jobs.snapshot()
        self.assertEqual(value['state'],'complete');self.assertTrue(value['published'])
        self.assertEqual(value['bytes_verified'],summary['bytes']);self.assertTrue((Path(value['result']['root'])/MARKER).exists())
        self.assertFalse((self.base/'launch-settings.json').exists())


if __name__=='__main__':unittest.main()
