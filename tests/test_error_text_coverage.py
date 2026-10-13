"""Every fixed English error the production server sends has a Japanese GUI text.

Static check only (reads source files); keeps app/production_server.py and
src/Aredoko.Core/ErrorText.cs from drifting apart.
"""
import re, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


class ErrorTextCoverageTests(unittest.TestCase):
    def test_fixed_server_errors_are_localized(self):
        server = (REPO / 'app/production_server.py').read_text(encoding='utf-8')
        mapped = set(re.findall(r'\["([^"]+)"\] = "', (REPO / 'src/Aredoko.Core/ErrorText.cs').read_text(encoding='utf-8')))
        english = {m for m in re.findall(r"'error':'([^']+)'", server) if re.fullmatch(r'[ -~]+', m)}
        self.assertTrue(english)
        self.assertEqual(sorted(english - mapped), [])


if __name__ == '__main__':
    unittest.main()
