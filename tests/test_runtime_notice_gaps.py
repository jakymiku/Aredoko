"""Gap review rejects stale/tampered evidence and does not approve legal coverage."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_runtime import FORMAT,MARKER
from inspect_runtime_notice_gaps import inspect_gaps


class NoticeGapTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.root=self.base/'runtime';(self.root/'DLLs').mkdir(parents=True)
        self.audit=self.base/'audit.json'
        for name,data in [('python.exe',b'not executable'),('DLLs/libssl-3.dll',b'not executable too'),('msvcp140.dll',b'owned CRT'),('LICENSE.txt',b'Python Software Foundation\nOpenSSL\n')]:
            (self.root/name).write_bytes(data)
        entries=[{'path':p.relative_to(self.root).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(self.root.rglob('*')) if p.is_file()]
        (self.root/MARKER).write_text(json.dumps({'format':FORMAT,'entries':entries}))
        self.review={'format':'aredoko-runtime-native-review-v1','runtime_manifest_sha256':hashlib.sha256((self.root/MARKER).read_bytes()).hexdigest(),
            'unmapped_count':2,'entries':[{'path':e['path'],'bytes':e['bytes'],'declared_sha256':e['sha256'],'distribution_record_owners':[],
            'native_component_owner':'MSVC' if e['path']=='msvcp140.dll' else None} for e in entries if e['path']!='LICENSE.txt']}
        self.save()
    def save(self):self.audit.write_text(json.dumps(self.review))
    def test_only_bound_gaps_and_notice_line_candidates_without_execution_or_approval(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Never run selected code')):v=inspect_gaps(self.root,self.audit)
        self.assertEqual(v['gap_count'],2);self.assertEqual({r['path'] for r in v['entries']},{'python.exe','DLLs/libssl-3.dll'})
        self.assertTrue(v['gap_payload_hashes_verified']);self.assertFalse(v['full_runtime_payload_verified'])
        self.assertEqual(v['notice']['term_line_candidates']['openssl'],[2]);self.assertEqual(v['notice']['term_line_candidates']['sqlite'],[])
        self.assertFalse(v['notice']['term_hits_prove_coverage']);self.assertFalse(v['redistribution_approved']);self.assertFalse(v['source_executed'])
        self.assertTrue(all(not r['owner_verified'] and not r['notice_coverage_verified'] for r in v['entries']))
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_isolated_cli_finds_its_own_helpers_without_site_packages(self):
        result=subprocess.run([sys.executable,'-I','-B',str(ROOT/'tools/inspect_runtime_notice_gaps.py'),
            '--source',str(self.root),'--audit',str(self.audit),'--output',str(self.base/'result.json')],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads((self.base/'result.json').read_text())['gap_count'],2)
    def test_changed_license_or_gap_bytes_rejected(self):
        for name in ('LICENSE.txt','python.exe','DLLs/libssl-3.dll'):
            p=self.root/name;original=p.read_bytes();p.write_bytes(b'x'*len(original))
            with self.subTest(name=name),self.assertRaises(ValueError):inspect_gaps(self.root,self.audit)
            p.write_bytes(original)
    def test_another_inventory_or_forged_count_and_duplicate_path_rejected(self):
        original=json.loads(json.dumps(self.review))
        operations=[lambda v:v.update(runtime_manifest_sha256='0'*64),lambda v:v.update(unmapped_count=1),
            lambda v:v['entries'].append(v['entries'][0].copy()),lambda v:v['entries'][0].update(path='../private.dll'),
            lambda v:v['entries'][0].update(bytes=123)]
        for operation in operations:
            self.review=json.loads(json.dumps(original));operation(self.review);self.save()
            with self.subTest(operation=operation),self.assertRaises(ValueError):inspect_gaps(self.root,self.audit)
    def test_unknown_location_stays_unclassified_instead_of_being_assigned_to_cpython(self):
        self.review['entries'][1]['native_component_owner']=None;self.review['unmapped_count']=3;self.save()
        v=inspect_gaps(self.root,self.audit)
        self.assertEqual(next(x for x in v['entries'] if x['path']=='msvcp140.dll')['review_group'],'unclassified')


if __name__=='__main__':unittest.main()
