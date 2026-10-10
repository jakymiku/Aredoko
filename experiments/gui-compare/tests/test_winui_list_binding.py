"""Guard source wiring of the Windows-only WinUI comparison fixture.

These tests are static contracts, not native WinUI render or build tests.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / "winui3"
NS = {"p": "http://schemas.microsoft.com/winfx/2006/xaml/presentation", "x": "http://schemas.microsoft.com/winfx/2006/xaml"}

class WinUIListBindingTests(unittest.TestCase):
    def test_listview_uses_native_rows_and_never_projects_managed_collection(self):
        window = ET.parse(ROOT / "overrides" / "MainWindow.xaml").getroot()
        lists = window.findall(".//p:ListView", NS)
        self.assertEqual(len(lists), 1)
        element = lists[0]
        self.assertEqual(element.get("Grid.Row"), "3")
        self.assertEqual(element.get("{" + NS["x"] + "}Name"), "ItemList")
        self.assertNotIn("ItemsSource", element.attrib, "Explicit source should not be overridden by x:Bind")
        self.assertEqual(len(element.findall(".//p:DataTemplate", NS)), 0)
        self.assertNotIn("x:Bind", ET.tostring(element, encoding="unicode"))
        cs = (ROOT / "overrides" / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        self.assertNotIn("ItemList.ItemsSource = Items;", cs)
        implementation = "\n".join(line.split("//", 1)[0] for line in cs.splitlines())
        self.assertNotIn("ObservableCollection<MediaRow>", implementation)
        self.assertIn("ItemList.Items.Add(CreateNativeRow(item));", cs)
        self.assertIn("new ListViewItem { Content = grid", cs)
        self.assertIn("var row = _visibleRows[index];", cs)
        self.assertIn('BuildTag = "EDITOR-v6"', cs)
        self.assertIn("ItemList.Items.Count", cs)
        self.assertIn("ItemList.ActualHeight", cs)

    def test_editor_change_detection_is_value_based_and_navigation_confirms_only_real_edits(self):
        cs = (ROOT / "overrides" / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        state = (ROOT / "overrides" / "EditorState.cs").read_text(encoding="utf-8")
        self.assertIn("readonly record struct EditorState(", state)
        self.assertIn("saved != current", state)
        self.assertIn("_savedEditor = CaptureEditor();", cs)
        self.assertIn("EditorState.IsDirty(_savedEditor, CaptureEditor())", cs)
        self.assertIn("if (_dirty)", cs)
        self.assertIn("await ConfirmDiscardAsync()", cs)
        self.assertIn("SetSelectedIndex(_selectedIndex);", cs)
        self.assertIn("requestId != _detailRequestVersion", cs)
        self.assertNotIn("_dirty = true;", cs)
        self.assertIn('BuildTag = "EDITOR-v6"', cs)

    def test_updater_copies_xaml_and_cpp_independently_of_json_protocol(self):
        script = (ROOT / "update-winui.ps1").read_text(encoding="utf-8")
        self.assertIn("'MainWindow.xaml.cs', 'MainWindow.xaml', 'BenchJson.cs', 'EditorState.cs'", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("EDITOR-v6", script)

if __name__ == "__main__":
    unittest.main()
