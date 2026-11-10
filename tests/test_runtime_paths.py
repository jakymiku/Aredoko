"""Relocated assets retain profile identity and explicit runtime choices."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import create_ai, create_intent
from runtime_paths import model_directory, worker_python, runtime_root, bind_runtime
from tagger_profile import load_profile
from video_previews import _executable, VideoPreviewUnavailable


class RuntimePathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aredoko-runtime-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.models = self.repo / 'ユーザーデータ models'
        self.models.mkdir()

    def test_legacy_defaults_and_explicit_missing_interpreter_never_fall_back(self):
        self.assertEqual(worker_python(self.repo), self.repo / '.venv-ai/Scripts/python.exe')
        missing = self.repo / 'absent Python/python.exe'
        self.assertEqual(worker_python(self.repo, missing), missing)
        model = DEFAULT_PROFILE.model_path(self.repo, models_root=self.models)
        model.mkdir();(model / 'aredoko-revision.txt').write_text(DEFAULT_PROFILE.revision)
        settings = AIProfileSettings(self.repo, self.repo / 'settings.json', ai_python=missing, models_root=self.models)
        self.assertFalse(settings._candidate('default')['ready'])
        settings = AIProfileSettings(self.repo, self.repo / 'settings.json', ai_python=sys.executable, models_root=self.models)
        self.assertTrue(settings._candidate('default')['ready'])
        self.assertFalse((self.repo / 'settings.json').exists())

    def test_embedding_paths_change_without_new_vector_namespace(self):
        model = DEFAULT_PROFILE.model_path(self.repo, models_root=self.models)
        model.mkdir();(model / 'aredoko-revision.txt').write_text(DEFAULT_PROFILE.revision)
        catalog = ProductionCatalog(self.repo / 'catalog.sqlite');self.addCleanup(catalog.close)
        ai = create_ai(catalog, ai_python=sys.executable, models_root=self.models);self.addCleanup(ai.close)
        self.assertEqual(ai.encoder.python, Path(sys.executable))
        self.assertEqual(ai.encoder.model, model)
        self.assertEqual(ai.profile.key, DEFAULT_PROFILE.key)
        self.assertEqual(DEFAULT_PROFILE.model_path(self.repo), self.repo / 'models/embeddinggemma-2')

    def test_tagger_paths_and_laya_share_explicit_asset_location(self):
        profile = load_profile(ROOT)
        self.assertEqual(profile.directory(self.repo, models_root=self.models), self.models / Path(profile.data()['model_directory']).relative_to('models'))
        with patch('production_server.LayaProcess') as worker, patch('production_server.SearchIntent'):
            create_intent(True, ai_python=sys.executable, models_root=self.models)
        self.assertEqual(worker.call_args.args[0], Path(sys.executable))
        self.assertEqual(worker.call_args.args[1], self.models / 'laya-multilingual')

    def test_model_root_escape_and_links_are_rejected(self):
        with self.assertRaises(ValueError):model_directory(self.repo, '../outside', self.models)
        link = self.repo / 'linked models'
        try:link.symlink_to(self.models, target_is_directory=True)
        except OSError:self.skipTest('Creating symlinks is unavailable')
        with self.assertRaises(ValueError):DEFAULT_PROFILE.model_path(self.repo, models_root=link)
        with self.assertRaises(ValueError):load_profile(ROOT).directory(self.repo, models_root=link)

    def test_explicit_video_tools_never_fall_back_to_path(self):
        media = self.repo / 'media';media.mkdir()
        with patch.dict(os.environ, {'AREDOKO_MEDIA_TOOLS': str(media)}), patch('video_previews.shutil.which') as which:
            with self.assertRaises(VideoPreviewUnavailable):_executable('ffmpeg')
            path = media / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg');path.write_bytes(b'fixture')
            self.assertEqual(_executable('ffmpeg'), str(path))
        which.assert_not_called()

    def test_managed_scripts_binding_cannot_fall_back_when_marker_disappears(self):
        outer=self.repo/'managed';scripts=outer/'Scripts';scripts.mkdir(parents=True)
        python=scripts/'python.exe';marker=outer/'aredoko-ai-runtime.json';marker.write_text('{}')
        self.assertEqual(runtime_root(python),outer)
        bind_runtime(outer,'a'*64);marker.unlink()
        self.assertEqual(runtime_root(python),outer)
        (scripts/'aredoko-ai-runtime.json').write_text('{}')
        self.assertEqual(runtime_root(python),scripts)


if __name__ == '__main__':unittest.main()
