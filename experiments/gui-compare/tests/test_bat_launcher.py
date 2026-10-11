"""Guard the Windows batch/PowerShell comparison launcher against easy regressions.

These are source-level checks. GUI input must still be tested on a live Windows desktop.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuiCompareLauncherTests(unittest.TestCase):
    def test_powershell_no_repeated_foregroundcolor(self):
        source = (ROOT / "scripts" / "run-compare.ps1").read_text(encoding="utf-8-sig")
        duplicates = [
            f"{number}: {line.strip()}"
            for number, line in enumerate(source.splitlines(), 1)
            if len(re.findall(r"(?<!\w)-ForegroundColor\b", line, flags=re.I)) > 1
        ]
        self.assertFalse(duplicates, "Duplicate PowerShell parameter: " + repr(duplicates))
        self.assertIn("Build-Benchmarks", source)
        self.assertIn("Run-GuiOperation", source)

    def test_gui_driver_finds_save_only_after_selection(self):
        source = (ROOT / "ui-automation" / "Program.cs").read_text(encoding="utf-8")
        bootstrap, edit = source.split("private static void EditOnce()", 1)
        self.assertNotIn("FindRequired(SaveLabel)", bootstrap)
        self.assertIn("Click(rows[0]);", edit)
        self.assertIn("var save = FindRequired(SaveLabel);", edit)
        self.assertLess(edit.index("Click(rows[0]);"), edit.index("var save = FindRequired(SaveLabel);"))

    def test_text_entry_uses_focusable_edit_not_label(self):
        source = (ROOT / "ui-automation" / "Program.cs").read_text(encoding="utf-8")
        self.assertIn("private static AutomationElement FindEditRequired(", source)
        self.assertIn("c.ControlType == ControlType.Edit", source)
        self.assertIn("c.IsKeyboardFocusable && c.IsEnabled && !c.IsOffscreen", source)
        self.assertIn("new OrCondition(", source)
        self.assertIn("foreach (var child in Descendants(candidate))", source)
        self.assertIn("Type(QueryLabel,", source)
        self.assertIn("Type(TagLabel, after);", source)
        self.assertNotIn("Type(FindRequired(QueryLabel)", source)
        self.assertNotIn("var tag = FindRequired(TagLabel);", source)
        self.assertIn("var target = FindEditRequired(label);", source)

    def test_keyboard_retry_requires_verified_value_and_focus(self):
        source = (ROOT / "ui-automation" / "Program.cs").read_text(encoding="utf-8")
        self.assertIn("private static void Type(string label, string value)", source)
        self.assertIn("attempt <= 3", source)
        self.assertIn("HasEffectiveKeyboardFocus(target)", source)
        self.assertIn("Click(target);", source)
        self.assertIn("var current = FindEditRequired(label);", source)
        self.assertIn("lastValue = ((ValuePattern)pattern).Current.Value;", source)
        self.assertIn("if (string.Equals(value, lastValue, StringComparison.Ordinal))", source)

    def test_search_requires_filtered_and_restored_list(self):
        source = (ROOT / "ui-automation" / "Program.cs").read_text(encoding="utf-8")
        self.assertIn("WaitForSearchState(bool filtered)", source)
        self.assertIn('rows.All(x => x.Contains("雨の街"', source)
        self.assertIn('rows.Any(x => x.Contains("夜の図書館"', source)
        self.assertIn("WaitForSearchState(filtered: true);", source)
        self.assertIn("WaitForSearchState(filtered: false);", source)

    def test_keyboard_native_input_union_handles_mouse_size(self):
        source = (ROOT / "ui-automation" / "Program.cs").read_text(encoding="utf-8")
        self.assertIn("internal MouseInput mouse;", source)
        self.assertIn("Marshal.SizeOf<Input>()", source)
        self.assertIn("Native.InputSizeProbe.Size", source)

    def test_bat_launches_powershell_script(self):
        source = (ROOT / "GUI-Compare.bat").read_text(encoding="utf-8")
        self.assertIn("scripts\\run-compare.ps1", source)
        self.assertIn("exit /b %status%", source)


if __name__ == "__main__":
    unittest.main()
