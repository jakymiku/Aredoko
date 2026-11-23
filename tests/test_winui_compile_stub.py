import importlib.util
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('compile_check_winui', ROOT / 'tools' / 'compile_check_winui.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class CompileStubTests(unittest.TestCase):
    def test_every_named_xaml_element_gets_a_typed_field(self):
        for xaml in sorted((ROOT / 'src' / 'Aredoko.WinUI').glob('*.xaml')):
            names = set(re.findall(r'x:Name="([^"]+)"', xaml.read_text(encoding='utf-8')))
            stub = tool.stub_for(xaml)
            self.assertIn('InitializeComponent', stub)
            for name in names:
                self.assertRegex(stub, rf'internal global::[\w.]+ {re.escape(name)} = null!;')

    def test_type_mapping_and_unsupported_namespace(self):
        self.assertEqual(tool.csharp_type('Button'), 'global::Microsoft.UI.Xaml.Controls.Button')
        self.assertEqual(tool.csharp_type('{%s}MicaBackdrop' % tool.PRESENTATION), 'global::Microsoft.UI.Xaml.Media.MicaBackdrop')
        self.assertEqual(tool.csharp_type('{using:Aredoko_WinUI}Thing'), 'global::Aredoko_WinUI.Thing')
        with self.assertRaises(ValueError):
            tool.csharp_type('{http://example.invalid}Thing')

    def test_output_must_stay_in_ignored_data(self):
        import subprocess, sys
        result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'compile_check_winui.py'), '--output', '../outside'],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('inside the ignored data/', result.stderr)


if __name__ == '__main__':
    unittest.main()
