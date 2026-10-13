"""Code/dependency/resource changes must not reuse an old deployment layout."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from winapp_layout import fingerprint

class LayoutTests(unittest.TestCase):
    def test_same_payload_reuses_layout_independently_of_enumeration(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);a=base/'app.dll';b=base/'app.deps.json';a.write_bytes(b'code');b.write_bytes(b'deps')
            self.assertEqual(fingerprint([a,b],base),fingerprint([b,a],base))
    def test_code_dependency_and_resource_changes_get_new_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);paths=[base/name for name in ('app.dll','app.deps.json','resources.pri')]
            for path in paths:path.write_bytes(b'initial')
            previous=fingerprint(paths,base)
            for path in paths:
                path.write_bytes(b'changed');current=fingerprint(paths,base);self.assertNotEqual(previous,current);previous=current
    def test_missing_payload_is_not_treated_as_valid_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'Build the WinUI payload first'):
                fingerprint([Path(tmp)/'missing.dll'],Path(tmp))

if __name__=='__main__':unittest.main()
