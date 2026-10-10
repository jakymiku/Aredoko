"""Guard source wiring of the Windows-only WinUI comparison fixture.

These tests are static contracts, not native WinUI render or build tests.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / "winui3"
NS = {"p": "http://schemas.microsoft.com/winfx/2006/xaml/presentation", "x": "http://schemas.microsoft.com/winfx/2006/xaml"}

class WinUIListBindingTests(unittest.TestCase):
    def test_listview_binding_is_explicit_and_template_is_present(self):
        window = ET.parse(ROOT / "overrides" / "MainWindow.xaml").getroot()
        lists = window.findall(".//p:ListView", NS)
        self.assertEqual(len(lists), 1)
        element = lists[0]
        self.assertEqual(element.get("Grid.Row"), "3")
        self.assertEqual(element.get("{" + NS["x"] + "}Name"), "ItemList")
        self.assertNotIn("ItemsSource", element.attrib, "Explicit source should not be overridden by x:Bind")
        self.assertEqual(len(element.findall(".//p:DataTemplate", NS)), 1)
        cs = (ROOT / "overrides" / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        self.assertIn("ItemList.ItemsSource = Items;", cs)
        self.assertIn("foreach (var item in result.Items) Items.Add(item);", cs)
        self.assertIn("BuildTag = \"LIST-v4\"", cs)
        self.assertIn("ItemList.Items.Count", cs)
        self.assertIn("ItemList.ActualHeight", cs)

    def test_updater_copies_xaml_and_cpp_independently_of_json_protocol(self):
        script = (ROOT / "update-winui.ps1").read_text(encoding="utf-8")
        self.assertIn("'MainWindow.xaml.cs', 'MainWindow.xaml', 'BenchJson.cs'", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("LIST-v4", script)

if __name__ == "__main__":
    unittest.main()
