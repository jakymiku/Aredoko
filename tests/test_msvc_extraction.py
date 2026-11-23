"""Only synthetic listing validation; no real installer extraction here."""
from pathlib import Path
import hashlib
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from extract_msvc_review import cabinet_members,_pipe,extract_cabinet,extract


class MSVCExtractionTests(unittest.TestCase):
    def test_flat_extraction_and_bundle_inventory_are_bound_to_the_same_source(self):
        import test_burn_containers as fixture
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';source.mkdir();exe=source/'generated.exe';exe.write_bytes(fixture.bundle())
            digest=hashlib.sha256(exe.read_bytes()).hexdigest();size=exe.stat().st_size;reference=root/'reference.json'
            reference.write_text(json.dumps({'format':'aredoko-msvc-source-reference-v1','observed_artifact_url':'https://aka.ms/generated',
                'sha256':digest,'bytes':size,'file_version':'14.1.2.0'}))
            tool=root/'existing-extractor.exe';tool.write_bytes(b'not executed')
            reviewed={'sha256':digest,'bytes':size,'metadata':{'file_version':'14.1.2.0'}}
            def pipe(tool,args,target,limit):
                data=b'Path = 0\nSize = 4\n' if args[0]=='l' else b'data'
                self.assertLessEqual(len(data),limit);target.write(data);return len(data),hashlib.sha256(data).hexdigest()
            with patch('extract_msvc_review.inspect_installer',return_value=reviewed),patch('extract_msvc_review._pipe',side_effect=pipe):
                output=root/'new';value=extract(exe,reference,output,tool)
                self.assertEqual([r['path'] for r in value['entries']],['container-0/0','container-1/0'])
                self.assertTrue(all((output/r['path']).read_bytes()==b'data' for r in value['entries']))
                self.assertFalse(value['source_executed']);self.assertFalse(value['runtime_modified'])
                self.assertEqual(hashlib.sha256(exe.read_bytes()).hexdigest(),digest)
                with self.assertRaises((ValueError,FileExistsError)):extract(exe,reference,output,tool)

    def test_remaining_budget_is_checked_before_creating_member_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);cab=root/'fixture.cab';cab.write_bytes(b'generated');output=root/'new'
            def pipe(tool,args,target,limit):target.write(b'Path = 0\nSize = 4\n')
            with patch('extract_msvc_review._pipe',side_effect=pipe),self.assertRaises(ValueError):
                extract_cabinet(cab,output,'unused',remaining_bytes=3)
            self.assertFalse(output.exists())

    def test_owned_tool_output_is_bounded_while_reading_and_always_released(self):
        class Process:
            def __init__(self,data,code=0):self.stdout=io.BytesIO(data);self.code=code;self.dead=False;self.killed=False
            def poll(self):return self.code if self.dead else None
            def kill(self):self.killed=True;self.dead=True
            def wait(self,timeout=None):self.dead=True;return self.code
        for data,limit,code in ((b'abc',3,0),(b'abcd',3,0),(b'abc',3,2)):
            with self.subTest(data=data,limit=limit,code=code):
                child=Process(data,code);target=io.BytesIO()
                with patch('extract_msvc_review.subprocess.Popen',return_value=child) as launch:
                    if len(data)<=limit and not code:
                        self.assertEqual(_pipe('existing-tool',['l','generated.cab'],target,limit),(3,hashlib.sha256(data).hexdigest()))
                    else:
                        with self.assertRaises((ValueError,RuntimeError)):_pipe('existing-tool',['l','generated.cab'],target,limit)
                self.assertTrue(child.dead and child.stdout.closed);self.assertLessEqual(len(target.getvalue()),limit)
                self.assertFalse(launch.call_args.kwargs['shell'])
                if len(data)>limit:self.assertTrue(child.killed)

    def test_safe_flat_members_keep_exact_names_and_sizes(self):
        value='Path = 0\nSize = 200\nAttributes = A\n\nPath = a1.cab\nSize = 13\nAttributes = A\n'
        self.assertEqual(cabinet_members(value),[{'name':'0','bytes':200},{'name':'a1.cab','bytes':13}])

    def test_paths_devices_case_collisions_directories_and_large_sizes_are_rejected(self):
        for name in ('../bad','C:bad','/bad','bad/x','bad\\x','bad:ads','-switch','a*','x.','NUL','con.txt','COM1.dll','a\nname'):
            with self.subTest(name=name),self.assertRaises(ValueError):cabinet_members('Path = '+name+'\nSize = 1')
        for value in ('Path = a\nSize = -1','Path = a\nSize = 67108865','Path = a\nSize = 1\nFolder = +',
                      'Path = a\nSize = 1\nAttributes = D','Path = a\nSize = 1\nSize = 1',
                      'Path = a\nSize = 1\n\nPath = A\nSize = 1','not a listing',''):
            with self.subTest(value=value),self.assertRaises(ValueError):cabinet_members(value)

    def test_cumulative_limits_bound_expansion_before_any_extraction(self):
        for value in ('\n\n'.join('Path = f'+str(i)+'\nSize = 1' for i in range(513)),
                      '\n\n'.join('Path = f'+str(i)+'\nSize = 67108864' for i in range(5))):
            with self.assertRaises(ValueError):cabinet_members(value)


if __name__=='__main__':unittest.main()
