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


    def test_tag_suggestion_runtime_errors_are_localized(self):
        adapter = ''.join((REPO / 'app' / file).read_text(encoding='utf-8')
                          for file in ('tag_suggestions.py', 'page_text.py'))
        mapped = set(re.findall(r'\["([^"]+)"\] = "', (REPO / 'src/Aredoko.Core/ErrorText.cs').read_text(encoding='utf-8')))
        errors = set(re.findall(r"raise (?:AIUnavailable|AIBusy|SuggestionConflict)\('([^']+)'\)", adapter))
        self.assertTrue(errors)
        self.assertEqual(sorted(errors - mapped), [])

    def test_public_folder_errors_are_localized_and_raised(self):
        import sys
        sys.path.insert(0, str(REPO / 'app'))
        from production_server import PUBLIC_FOLDER_ERRORS
        mapped = set(re.findall(r'\["([^"]+)"\] = "', (REPO / 'src/Aredoko.Core/ErrorText.cs').read_text(encoding='utf-8')))
        self.assertEqual(sorted(PUBLIC_FOLDER_ERRORS - mapped), [])
        sources = ''.join((REPO / 'app' / name).read_text(encoding='utf-8')
                          for name in ('library_index.py', 'production.py', 'production_server.py'))
        raised = set(re.findall(r"raise ValueError\('([^']+)'\)", sources))
        self.assertEqual(sorted(PUBLIC_FOLDER_ERRORS - raised), [])

    def test_finite_worker_failures_are_localized(self):
        import sys
        sys.path.insert(0,str(REPO/'app'))
        from inference_errors import STARTUP_ERRORS
        mapped=set(re.findall(r'\["([^"]+)"\] = "',(REPO/'src/Aredoko.Core/ErrorText.cs').read_text(encoding='utf-8')))
        self.assertEqual(sorted({message for code,message in STARTUP_ERRORS.values()}-mapped),[])


if __name__ == '__main__':
    unittest.main()
