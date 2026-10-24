"""Generated metadata/notices only; no Python environment execution."""
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/n) for n in ('app','tools')]
from collect_ai_runtime_notices import collect,write_bundle,validate_bundle,validate_for_source
from prepare_ai_runtime_pack import prepare
import test_ai_runtime as runtime_fixture


class RuntimeNoticeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.base=Path(temp.name)
        self.source=self.base/'source';self.site=self.source/'Lib/site-packages';self.site.mkdir(parents=True)
        (self.source/'LICENSE.txt').write_bytes(b'generated Python license')
    def distribution(self,name='demo',metadata='License-File: LICENSE\n',license=True):
        d=self.site/(name+'-1.0.dist-info');d.mkdir()
        (d/'METADATA').write_text('Metadata-Version: 2.4\nName: '+name+'\nVersion: 1.0\n'+metadata,encoding='utf-8')
        if license:
            (d/'licenses').mkdir();(d/'licenses/LICENSE').write_bytes(b'generated complete license')
        return d
    def test_pep639_text_is_preserved_without_execution_or_source_changes(self):
        self.distribution();before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.source.rglob('*') if p.is_file()}
        with patch('subprocess.Popen',side_effect=AssertionError('No selected Python execution')):
            result=write_bundle(self.source,self.base/'notices')
        self.assertTrue(result['complete_distribution_notices']);self.assertFalse(result['redistribution_approved'])
        self.assertEqual((self.base/'notices/files/Lib/site-packages/demo-1.0.dist-info/licenses/LICENSE').read_bytes(),b'generated complete license')
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.source.rglob('*') if p.is_file()})
        validate_bundle(self.base/'notices',require_complete=True)
    def test_record_locates_package_license_outside_dist_info(self):
        d=self.distribution(metadata='',license=False);package=self.site/'demo';package.mkdir();(package/'LICENSE').write_bytes(b'generated package license')
        (d/'RECORD').write_text('demo/LICENSE,,\ndemo/generated.py,,\n',encoding='utf-8')
        report,_=collect(self.source)
        self.assertTrue(report['complete_distribution_notices'])
        self.assertEqual(report['distributions'][0]['notice_files'],['files/Lib/site-packages/demo/LICENSE'])
    def test_missing_notice_is_reported_and_strict_pack_preparation_is_blocked(self):
        self.distribution(license=False)
        result=write_bundle(self.source,self.base/'notices')
        self.assertFalse(result['complete_distribution_notices']);self.assertEqual(result['missing_distribution_notices'],['demo'])
        with self.assertRaisesRegex(ValueError,'incomplete'):validate_bundle(self.base/'notices',require_complete=True)
    def test_unsafe_declared_and_record_paths_never_read_external_file(self):
        for origin in ('metadata','record'):
            with self.subTest(origin=origin):
                directory=self.distribution(name=origin,metadata='License-File: ../LICENSE\n' if origin=='metadata' else '',license=False)
                if origin=='record':(directory/'RECORD').write_text('../../outside/NOTICE,,\n',encoding='utf-8')
                if origin=='record':
                    with self.assertRaises(ValueError):collect(self.source)
                else:
                    report,_=collect(self.source)
                    self.assertFalse(report['complete_distribution_notices'])
                    self.assertEqual(report['distributions'][0]['missing_declared'],['../LICENSE'])
                for p in directory.iterdir():p.unlink()
                directory.rmdir()
    def test_duplicate_distribution_names_are_rejected(self):
        self.distribution('demo');other=self.distribution('another')
        metadata=other/'METADATA';metadata.write_text(metadata.read_text().replace('Name: another','Name: DEMO'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Duplicate'):collect(self.source)
    def test_output_overlap_existing_output_and_tampering_are_rejected(self):
        self.distribution()
        with self.assertRaisesRegex(ValueError,'overlaps'):write_bundle(self.source,self.source/'notices')
        out=self.base/'notices';write_bundle(self.source,out)
        with self.assertRaises(FileExistsError):write_bundle(self.source,out)
        (out/'NOTICE.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'checksum'):validate_bundle(out)
    def test_hardlinked_notice_is_rejected(self):
        d=self.distribution();original=d/'licenses/LICENSE';linked=self.base/'hardlink';os.link(original,linked)
        with self.assertRaises(ValueError):collect(self.source)

    def test_pack_embeds_bound_notice_inventory_without_running_source(self):
        self.source=runtime_fixture.fixture(self.base/'prepared',source=True)
        self.site=self.source/'Lib/site-packages';self.distribution()
        bundle=self.base/'notices';write_bundle(self.source,bundle)
        with patch('subprocess.Popen',side_effect=AssertionError('No execution')):
            result=prepare(self.source,self.base/'pack',notices=bundle)
        self.assertTrue(result['notices_included'])
        validate_bundle(self.base/'pack/THIRD_PARTY_LICENSES',require_complete=True)

    def test_stale_or_incomplete_bundle_cannot_be_applied_to_runtime(self):
        self.source=runtime_fixture.fixture(self.base/'prepared',source=True)
        self.site=self.source/'Lib/site-packages';d=self.distribution()
        bundle=self.base/'notices';write_bundle(self.source,bundle)
        metadata=d/'METADATA';metadata.write_text(metadata.read_text().replace('Version: 1.0','Version: 2.0'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'source changed'):
            prepare(self.source,self.base/'rejected',notices=bundle)
        self.assertFalse((self.base/'rejected').exists())

    @unittest.skipUnless(os.name=='nt','Native Windows RECORD separator case')
    def test_native_windows_record_paths_are_parsed_without_relaxing_parent_checks(self):
        d=self.distribution(metadata='',license=False)
        (d/'LICENSE').write_bytes(b'generated native license')
        (d/'RECORD').write_text(d.name+'\\LICENSE,,\n',encoding='utf-8')
        result,_=collect(self.source)
        self.assertTrue(result['complete_distribution_notices'])


class SupplementalNoticeTests(unittest.TestCase):
    setUp=RuntimeNoticeTests.setUp
    distribution=RuntimeNoticeTests.distribution
    def review(self,directory,*,declared=None,name='demo'):
        root=self.base/'review';root.mkdir(exist_ok=True)
        text=b'generated upstream complete notice';(root/'LICENSE').write_bytes(text)
        row={'name':name,'version':'1.0','metadata_sha256':hashlib.sha256((directory/'METADATA').read_bytes()).hexdigest(),
             'clears_declared':declared or [],'files':[{'path':'LICENSE','bytes':len(text),'sha256':hashlib.sha256(text).hexdigest(),
             'source':'https://raw.githubusercontent.com/example/project/'+'a'*40+'/LICENSE'}]}
        manifest=root/'reviews.json';manifest.write_text(json.dumps([row]),encoding='utf-8')
        return manifest,row
    def test_supplement_preserves_source_and_binds_exact_metadata(self):
        d=self.distribution(metadata='',license=False);manifest,row=self.review(d)
        before=(d/'METADATA').read_bytes()
        result=write_bundle(self.source,self.base/'notices',supplements=manifest)
        self.assertTrue(result['complete_distribution_notices']);self.assertFalse(result['redistribution_approved'])
        self.assertEqual(result['supplements'],[row]);validate_for_source(self.base/'notices',self.source)
        self.assertEqual(before,(d/'METADATA').read_bytes());self.assertFalse((d/'LICENSE').exists())
    def test_unsafe_legacy_declaration_needs_explicit_matching_review(self):
        d=self.distribution(metadata='License-File: ../LICENSE\n',license=False)
        manifest,row=self.review(d)
        with self.assertRaisesRegex(ValueError,'unresolved'):write_bundle(self.source,self.base/'bad',supplements=manifest)
        self.assertFalse((self.base/'bad').exists())
        row['clears_declared']=['../LICENSE'];manifest.write_text(json.dumps([row]))
        report=write_bundle(self.source,self.base/'good',supplements=manifest)
        self.assertTrue(report['complete_distribution_notices']);validate_for_source(self.base/'good',self.source)
    def test_stale_metadata_and_tampered_supplement_are_rejected_before_output(self):
        d=self.distribution(metadata='',license=False);manifest,row=self.review(d)
        (d/'METADATA').write_text((d/'METADATA').read_text()+'Summary: changed\n')
        with self.assertRaisesRegex(ValueError,'metadata'):write_bundle(self.source,self.base/'stale',supplements=manifest)
        self.assertFalse((self.base/'stale').exists())
        row['metadata_sha256']=hashlib.sha256((d/'METADATA').read_bytes()).hexdigest();manifest.write_text(json.dumps([row]))
        (manifest.parent/'LICENSE').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'checksum'):write_bundle(self.source,self.base/'tampered',supplements=manifest)
    def test_branch_url_parent_paths_and_duplicate_reviews_are_rejected(self):
        d=self.distribution(metadata='',license=False);manifest,row=self.review(d)
        original=json.loads(json.dumps(row))
        for bad in ('https://raw.githubusercontent.com/example/project/main/LICENSE','https://evil.example/'+('a'*40)+'/LICENSE'):
            row=json.loads(json.dumps(original));row['files'][0]['source']=bad;manifest.write_text(json.dumps([row]))
            with self.assertRaises(ValueError):write_bundle(self.source,self.base/'bad',supplements=manifest)
        row=json.loads(json.dumps(original));row['files'][0]['path']='../LICENSE';manifest.write_text(json.dumps([row]))
        with self.assertRaises(ValueError):write_bundle(self.source,self.base/'bad',supplements=manifest)
        manifest.write_text(json.dumps([original,original]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):write_bundle(self.source,self.base/'bad',supplements=manifest)
    def test_changed_source_rejects_complete_supplement_bundle(self):
        d=self.distribution(metadata='',license=False);manifest,row=self.review(d)
        write_bundle(self.source,self.base/'notices',supplements=manifest)
        (d/'METADATA').write_text((d/'METADATA').read_text()+'Summary: changed\n')
        with self.assertRaisesRegex(ValueError,'metadata'):validate_for_source(self.base/'notices',self.source)

    def test_two_supplements_are_preserved_when_pack_is_sealed(self):
        self.source=runtime_fixture.fixture(self.base/'prepared',source=True);self.site=self.source/'Lib/site-packages'
        first=self.distribution(metadata='',license=False);manifest,row=self.review(first)
        second=self.distribution(name='second',metadata='License-File: ../LICENSE\n',license=False)
        other=json.loads(json.dumps(row));other.update(name='second',clears_declared=['../LICENSE'],metadata_sha256=hashlib.sha256((second/'METADATA').read_bytes()).hexdigest())
        manifest.write_text(json.dumps([row,other]))
        bundle=self.base/'notices';write_bundle(self.source,bundle,supplements=manifest)
        with patch('subprocess.Popen',side_effect=AssertionError('No execution')):result=prepare(self.source,self.base/'pack',notices=bundle)
        self.assertTrue(result['notices_included']);validated=validate_for_source(self.base/'pack/THIRD_PARTY_LICENSES',self.base/'pack')
        self.assertEqual(len(validated['supplements']),2)
