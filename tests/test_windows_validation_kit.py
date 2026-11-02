"""Archive/directory identity contracts for the generated validation kit."""
import contextlib,io,json,sys,tempfile,unittest,warnings,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_windows_validation as tool


class WindowsValidationKitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aredoko-validation-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.release=self.root/'dist/basic/Aredoko';self.release.mkdir(parents=True)
        self.out=self.root/'dist/validation';self.zip=self.release.parent/'Aredoko-windows-x64.zip'
        self.manifest={'version':'fixture-v1','created_at':'2026-10-29T18:25:21Z','platform':'windows-x64','models_bundled':False,'ai_runtime_bundled':False,'entries':[{'path':'payload.txt','bytes':7,'sha256':'unused-existing-verifier'}]}
        (self.release/'manifest.json').write_bytes(json.dumps(self.manifest).encode())
        (self.release/'sha256sums.txt').write_bytes(b'sealed sums\n')
        self.members={'Aredoko/manifest.json':(self.release/'manifest.json').read_bytes(),'Aredoko/sha256sums.txt':b'sealed sums\n','Aredoko/payload.txt':b'payload'}

    def write_zip(self,members=None,duplicate=False):
        with zipfile.ZipFile(self.zip,'w') as z:
            for name,value in (self.members if members is None else members).items():z.writestr(name,value)
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning);z.writestr('Aredoko/payload.txt',b'payload')

    def run_tool(self):
        with patch.object(tool,'REPO',self.root),patch.object(tool,'verify_release',return_value=self.manifest),patch.object(sys,'argv',['prepare_windows_validation','--release',str(self.release),'--output',str(self.out)]),contextlib.redirect_stdout(io.StringIO()):
            tool.main()

    def rejected(self):
        with self.assertRaises(ValueError):self.run_tool()
        self.assertFalse(self.out.exists());self.assertFalse(self.out.with_suffix('.zip').exists())

    def test_matching_archive_builds_data_only_kit_without_claiming_acceptance(self):
        self.write_zip();before=self.zip.read_bytes();self.run_tool()
        candidate=json.loads((self.out/'candidate.json').read_text());self.assertTrue(candidate['archive_metadata_matches_release']);self.assertFalse(candidate['clean_windows_verified'])
        result=json.loads((self.out/'result-template.json').read_text());self.assertIsNone(result['normal_exe_start']);self.assertFalse(result['clean_windows_verified'])
        expected={'version':'fixture-v1','created_at':'2026-10-29T18:25:21Z','platform':'windows-x64','source_revision':None}
        self.assertEqual(candidate['release_identity'],expected);self.assertEqual(result['release_identity'],expected)
        self.assertEqual(result['application_zip_sha256'],candidate['zip_sha256']);self.assertEqual(result['manifest_sha256'],candidate['manifest_sha256'])
        self.assertIn('source_revisionがnull', (self.out/'はじめに.txt').read_text(encoding='utf-8-sig'))
        with zipfile.ZipFile(self.out.with_suffix('.zip')) as z:
            self.assertEqual(len(z.namelist()),6);self.assertFalse(any(Path(name).suffix.lower() in ('.exe','.cmd','.ps1','.py') for name in z.namelist()))
        self.assertEqual(self.zip.read_bytes(),before)

    def test_explicit_source_revision_reaches_candidate_and_result(self):
        revision='abcdef0123'*4
        self.manifest['source_revision']=revision
        (self.release/'manifest.json').write_bytes(json.dumps(self.manifest).encode())
        self.members['Aredoko/manifest.json']=(self.release/'manifest.json').read_bytes()
        self.write_zip();self.run_tool()
        for name in ('candidate.json','result-template.json'):
            data=json.loads((self.out/name).read_text())
            self.assertEqual(data['release_identity']['source_revision'],revision)
            self.assertFalse(data['clean_windows_verified'])

    def test_legacy_manifest_omitted_identity_fields_stay_unknown(self):
        for key in ('version','created_at','platform'):self.manifest.pop(key)
        (self.release/'manifest.json').write_bytes(json.dumps(self.manifest).encode())
        self.members['Aredoko/manifest.json']=(self.release/'manifest.json').read_bytes()
        self.write_zip();self.run_tool()
        identity=json.loads((self.out/'candidate.json').read_text())['release_identity']
        self.assertEqual(identity,{'version':None,'created_at':None,'platform':None,'source_revision':None})

    def test_other_build_manifest_is_rejected_before_output(self):
        self.write_zip({**self.members,'Aredoko/manifest.json':b'other build'});self.rejected()

    def test_other_build_sums_are_rejected_before_output(self):
        self.write_zip({**self.members,'Aredoko/sha256sums.txt':b'other sums'});self.rejected()

    def test_duplicate_payload_member_is_rejected(self):
        self.write_zip(duplicate=True);self.rejected()

    def test_changed_member_size_is_rejected(self):
        self.write_zip({**self.members,'Aredoko/payload.txt':b'longer payload'});self.rejected()

    def test_unexpected_member_is_rejected(self):
        self.write_zip({**self.members,'Aredoko/extra.txt':b'extra'});self.rejected()


if __name__=='__main__':unittest.main()
