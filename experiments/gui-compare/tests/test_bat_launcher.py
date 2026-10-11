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
