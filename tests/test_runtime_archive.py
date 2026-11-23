"""Generated sealed runtime ZIPs only; selected code is never executed."""
import hashlib,json,os,shutil,stat,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/n) for n in ('app','tools')]
import test_ai_runtime as fixture
from ai_runtime import MARKER,inspect_runtime
from runtime_archive import RuntimeArchive,unpack_runtime


class RuntimeArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.source=fixture.fixture(self.base/'source');raw=(self.source/MARKER).read_bytes();v=json.loads(raw)
        self.spec=RuntimeArchive.parse(dict(manifest_sha256=hashlib.sha256(raw).hexdigest(),unpacked_bytes=v['total_bytes'],unpacked_files=v['files_count']))
    def archive(self,*,replace=None,extra=None,remove=None):
        destination=self.base/'runtime.zip'
        with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for file in self.source.rglob('*'):
                if file.is_file():
                    name=file.relative_to(self.source).as_posix()
                    if name==remove:continue
                    content=file.read_bytes()
                    if replace:content=replace(name,content)
                    archive.writestr(name,content)
            if extra:
                for key,value in extra:archive.writestr(key,value)
        return destination
    def test_full_extract_preserves_bytes_and_never_executes(self):
        zip_path=self.archive();before=zip_path.read_bytes()
        with patch('subprocess.Popen',side_effect=AssertionError('No execution')):result=unpack_runtime(zip_path,self.base/'expanded',self.spec)
        self.assertEqual(result['verification'],'expanded_full');self.assertFalse(result['archive_executed'])
        inspect_runtime(self.base/'expanded',verify=True)
        self.assertEqual(before,zip_path.read_bytes())
        self.assertTrue((self.base/'expanded/DLLs').is_dir())
    def test_bad_inventory_binding_is_rejected_before_output(self):
        path=self.archive();bad=RuntimeArchive('0'*64,self.spec.unpacked_bytes,self.spec.unpacked_files)
        with self.assertRaisesRegex(ValueError,'inventory changed'):unpack_runtime(path,self.base/'expanded',bad)
        self.assertFalse((self.base/'expanded').exists())
    def test_size_and_count_binding_are_not_self_asserted(self):
        path=self.archive()
        for spec in (RuntimeArchive(self.spec.manifest_sha256,self.spec.unpacked_bytes+1,self.spec.unpacked_files),RuntimeArchive(self.spec.manifest_sha256,self.spec.unpacked_bytes,self.spec.unpacked_files+1)):
            with self.assertRaisesRegex(ValueError,'inventory mismatch'):unpack_runtime(path,self.base/'expanded',spec)
    def test_parent_absolute_and_case_aliases_are_rejected(self):
        for name in ('../outside','/absolute','C:/escape','python.exe/child','PYTHON.EXE','Lib/other.txt'):
            with self.subTest(name=name):
                path=self.archive(extra=[(name,b'generated')])
                with self.assertRaises(ValueError):unpack_runtime(path,self.base/'expanded',self.spec)
                self.assertFalse((self.base/'expanded').exists())
    def test_symlink_and_extra_directory_are_rejected(self):
        link=zipfile.ZipInfo('linked');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
        for name in (link,'unexpected/'):
            path=self.archive(extra=[(name,b'')])
            with self.assertRaises(ValueError):unpack_runtime(path,self.base/'expanded',self.spec)
    def test_missing_file_and_member_size_mismatch_are_rejected(self):
        path=self.archive(remove='pythonw.exe')
        with self.assertRaises(ValueError):unpack_runtime(path,self.base/'expanded',self.spec)
        path=self.archive(replace=lambda name,data:data+b'x' if name=='pythonw.exe' else data)
        with self.assertRaises(ValueError):unpack_runtime(path,self.base/'expanded',self.spec)
    def test_same_size_corruption_is_not_published_and_can_resume_only_owned_output(self):
        path=self.archive(replace=lambda name,data:b'x'*len(data) if name=='pythonw.exe' else data)
        output=self.base/'expanded'
        with self.assertRaisesRegex(ValueError,'checksum'):unpack_runtime(path,output,self.spec)
        with self.assertRaises(FileExistsError):unpack_runtime(path,output,self.spec)
        path=self.archive();result=unpack_runtime(path,output,self.spec,resume=True)
        self.assertEqual(result['verification'],'expanded_full')
    def test_cancelled_stage_resumes_and_unlisted_stage_is_preserved(self):
        path=self.archive();out=self.base/'expanded';cancel=[False]
        def progress(value):
            if value['files_done']>=2:cancel[0]=True
        with self.assertRaises(InterruptedError):unpack_runtime(path,out,self.spec,cancelled=lambda:cancel[0],progress=progress)
        unpack_runtime(path,out,self.spec,resume=True)
        (out/'foreign.txt').write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError,'Unlisted'):unpack_runtime(path,out,self.spec,resume=True)
        self.assertEqual((out/'foreign.txt').read_bytes(),b'preserve')
    def test_links_in_source_and_destination_are_rejected(self):
        path=self.archive();os.link(path,self.base/'linked.zip')
        with self.assertRaises(ValueError):unpack_runtime(path,self.base/'expanded',self.spec)
    def test_space_failure_starts_no_extraction(self):
        path=self.archive()
        with patch('runtime_archive.shutil.disk_usage',return_value=shutil._ntuple_diskusage(1,1,0)),self.assertRaises(OSError):unpack_runtime(path,self.base/'expanded',self.spec)
        self.assertEqual(list((self.base/'expanded').iterdir()),[])
    def test_boolean_or_unbounded_archive_metadata_is_rejected(self):
        for field,value in (('unpacked_bytes',True),('unpacked_files',True),('unpacked_files',100001),('unpacked_bytes',65*1024**3)):
            data=self.spec.to_dict();data[field]=value
            with self.assertRaises(ValueError):RuntimeArchive.parse(data)

    def test_publisher_builder_streams_a_reusable_archive_and_pins_catalog(self):
        from prepare_ai_runtime_archive import prepare_archive
        from build_ai_runtime_catalog import build_archive_catalog
        archive=self.base/'published.zip'
        with patch('subprocess.Popen',side_effect=AssertionError('No execution')):
            receipt=prepare_archive(self.source,archive)
            raw,catalog=build_archive_catalog(archive,key='generated-runtime',revision='a'*40,base_url='https://example.org/fixed/',license='MIT',license_url='https://example.org/LICENSE',allowed_hosts=['example.org'])
        self.assertFalse(receipt['uploaded']);self.assertEqual(catalog.runtime_archive,self.spec)
        self.assertEqual(len(catalog.entries),1);self.assertEqual(catalog.entries[0].sha256,receipt['archive_sha256'])
        unpack_runtime(archive,self.base/'expanded',catalog.runtime_archive)
    def test_publisher_rejects_existing_output_and_does_not_write_into_source(self):
        from prepare_ai_runtime_archive import prepare_archive
        with self.assertRaisesRegex(ValueError,'overlaps'):prepare_archive(self.source,self.source/'archive.zip')
        file=self.base/'existing.zip';file.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):prepare_archive(self.source,file)
        self.assertEqual(file.read_bytes(),b'preserve')
    def test_publisher_checks_source_bytes_before_producing_a_complete_archive(self):
        from prepare_ai_runtime_archive import prepare_archive
        (self.source/'pythonw.exe').write_bytes(b'bad content')
        with self.assertRaisesRegex(ValueError,'source changed'):prepare_archive(self.source,self.base/'bad.zip')

    def test_path_depth_and_inconsistent_parent_case_fail_before_output(self):
        for name,reason in ((('part/'*33)+'file','depth'),('lib/other.txt','path case')):
            with self.subTest(name=name):
                path=self.archive(extra=[(name,b'generated')])
                with self.assertRaisesRegex(ValueError,reason):unpack_runtime(path,self.base/'expanded',self.spec)
                self.assertFalse((self.base/'expanded').exists())
