"""Restart-only AI profile preferences and production HTTP security tests."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from ai_profiles import DEFAULT_PROFILE
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import DisabledAI, production_handler
from http.server import ThreadingHTTPServer

class AISettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.folder = self.repo / "data" / "ai-profiles"
        self.folder.mkdir(parents=True)
        self.settings = self.repo / "settings" / "settings.json"

    def custom(self, filename="custom.json", **kw):
        data = DEFAULT_PROFILE.to_dict()
        data.update({"label": "Local Test", "directory": "custom-weights", **kw})
        file = self.folder / filename
        file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return file

    def controller(self, override=None):
        return AIProfileSettings(self.repo, self.settings, override)

    def test_profile_and_resource_writes_do_not_lose_each_other(self):
        self.custom()
        ctrl=self.controller()
        entered=threading.Event(); finish=threading.Event(); second_started=threading.Event()
        errors=[]; original=ctrl._save_settings
        def save(payload):
            if payload.get("resource",{}).get("index_pause_ms")==50 and payload["profile"]=="default":
                entered.set()
                if not finish.wait(5): raise RuntimeError("bounded test gate")
            original(payload)
        def task(operation):
            try: operation()
            except Exception as error: errors.append(error)
        def choose():
            second_started.set(); ctrl.choose("local:custom.json")
        first=threading.Thread(target=task,args=(lambda:ctrl.set_resource({"idle_release_seconds":60,"index_pause_ms":50}),))
        second=threading.Thread(target=task,args=(choose,))
        with patch.object(ctrl,"_save_settings",side_effect=save):
            try:
                first.start(); self.assertTrue(entered.wait(5))
                second.start(); self.assertTrue(second_started.wait(5))
            finally:
                finish.set(); first.join(5)
                if second.ident is not None: second.join(5)
        self.assertFalse(first.is_alive()); self.assertFalse(second.is_alive())
        self.assertFalse(errors,errors)
        self.assertEqual(ctrl.selected(),"local:custom.json")
        self.assertEqual(ctrl.resource(),{"idle_release_seconds":60,"index_pause_ms":50})

    def test_default_and_persisted_switch_only_on_restart(self):
        ctrl = self.controller()
        self.assertEqual(ctrl.active, "default")
        self.assertEqual(ctrl.snapshot()["selected"], "default")
        self.custom()
        choice = ctrl.choose("local:custom.json")
        self.assertTrue(choice["restart_required"])
        self.assertEqual(choice["active"], "default")
        self.assertEqual(choice["selected"], "local:custom.json")
        self.assertFalse(next(p for p in choice["profiles"] if p["id"] == "local:custom.json")["ready"])
        restarted = self.controller()
        self.assertEqual(restarted.active, "local:custom.json")
        self.assertEqual(restarted.startup_path, (self.folder / "custom.json").resolve())
        self.assertFalse(restarted.snapshot()["restart_required"])
        restarted.choose("default")
        self.assertEqual(restarted.active, "local:custom.json")
        self.assertTrue(restarted.snapshot()["restart_required"])
        self.assertEqual(self.controller().active, "default")

    def test_override_wins_even_if_saved_settings_are_broken(self):
        manual = self.custom("manual.json")
        self.settings.parent.mkdir()
        self.settings.write_text("{invalid json", encoding="utf-8")
        ctrl = self.controller(manual)
        self.assertEqual(ctrl.active, "command-line")
        self.assertEqual(ctrl.startup_path, manual.resolve())
        self.assertEqual(ctrl.startup_error, "")
        self.assertTrue(ctrl.snapshot()["command_line_override"])
        self.assertEqual(ctrl.snapshot()["selected"], "invalid")
        ctrl.choose("default")
        self.assertEqual(ctrl.active, "command-line")
        self.assertIsNone(self.controller().startup_path)
        self.assertEqual(self.controller().active, "default")

    def test_legacy_profile_only_preferences_and_resource_policy(self):
        from ai_settings import RESOURCE_DEFAULT
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"version":1,"profile":"default"}',encoding="utf-8")
        controller=self.controller()
        self.assertEqual(controller.resource(),RESOURCE_DEFAULT)
        self.assertEqual(controller.snapshot()["selected"],"default")
        self.assertEqual(controller.set_resource({"idle_release_seconds":60,"index_pause_ms":200}),
                         {"idle_release_seconds":60,"index_pause_ms":200})
        self.custom()
        controller.choose("local:custom.json")
        after=self.controller()
        self.assertEqual(after.selected(),"local:custom.json")
        self.assertEqual(after.resource(),{"idle_release_seconds":60,"index_pause_ms":200})
        self.assertEqual(after.startup_path,(self.folder/"custom.json").resolve())
        self.assertEqual(after.resource(),controller.resource())
        self.assertEqual(after.snapshot()["selected"],"local:custom.json")

    def test_resource_rejects_out_of_range_and_unknown_fields_without_persisting(self):
        ctrl=self.controller()
        for bad in ({"idle_release_seconds":True,"index_pause_ms":0},
                    {"idle_release_seconds":-1,"index_pause_ms":0},
                    {"idle_release_seconds":3601,"index_pause_ms":0},
                    {"idle_release_seconds":0,"index_pause_ms":2001},
                    {"idle_release_seconds":0,"index_pause_ms":False},
                    {"idle_release_seconds":0},
                    {"idle_release_seconds":0,"index_pause_ms":0,"identity":"bad"}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                ctrl.set_resource(bad)
        self.assertFalse(self.settings.exists())

    def test_missing_corrupt_and_unsupported_settings_never_import_code(self):
        self.custom("broken.json", adapter="evil.module")
        (self.folder / "malformed.json").write_text("{")
        ctrl = self.controller()
        options = {p["id"]:p for p in ctrl.snapshot()["profiles"]}
        self.assertFalse(options["local:broken.json"]["valid"])
        self.assertFalse(options["local:malformed.json"]["valid"])
        for bad in ("local:../evil.json", "local:a\\evil.json", "arbitrary.py",
                    "local:missing.json", "local:/abs.json", 5):
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                ctrl.choose(bad)
        self.assertFalse(self.settings.exists())

    def test_model_readiness_is_reported_without_any_download(self):
        self.custom()
        model = self.repo / "models" / "custom-weights"
        model.mkdir(parents=True)
        (self.repo / ".venv-ai" / "Scripts").mkdir(parents=True)
        (self.repo / ".venv-ai" / "Scripts" / "python.exe").write_bytes(b"test runner")
        ctrl = self.controller()
        current = {p["id"]:p for p in ctrl.snapshot()["profiles"]}["local:custom.json"]
        self.assertIn("aredoko-revision.txt",current["warning"])
        (model / "aredoko-revision.txt").write_text("0"*40)
        current = {p["id"]:p for p in ctrl.snapshot()["profiles"]}["local:custom.json"]
        self.assertIn("リビジョン",current["warning"])
        (model / "aredoko-revision.txt").write_text(DEFAULT_PROFILE.revision)
        current = {p["id"]:p for p in ctrl.snapshot()["profiles"]}["local:custom.json"]
        self.assertTrue(current["ready"])
        self.assertIn("未検証",current["warning"])

    def test_corrupt_selected_profile_disables_ai_without_changing_preference(self):
        self.custom()
        self.controller().choose("local:custom.json")
        (self.folder / "custom.json").write_text("{invalid")
        ctrl = self.controller()
        self.assertNotEqual(ctrl.startup_error,"")
        self.assertEqual(ctrl.snapshot()["selected"],"local:custom.json")
        self.assertFalse(ctrl.snapshot()["profiles"][1]["valid"])

    def test_api_session_guard_and_restart_only_persistence(self):
        profile = self.custom()
        cat = ProductionCatalog(self.repo / "catalog.sqlite")
        self.addCleanup(cat.close)
        ctrl = self.controller()
        server = ThreadingHTTPServer(("127.0.0.1",0),
                     production_handler(cat,"test-token",ai=DisabledAI(),profiles=ctrl))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        url = base+"/api/library/ai/profiles"
        with self.assertRaises(urllib.error.HTTPError) as ex:
            urllib.request.urlopen(url)
        ex.exception.close()
        self.assertEqual(ex.exception.code,403)
        def get():
            with urllib.request.urlopen(urllib.request.Request(url,headers={"X-Aredoko-Token":"test-token"})) as response:
                return json.load(response)
        def post(body,token="test-token",origin=True):
            headers = {"X-Aredoko-Token":token,"Content-Type":"application/json"}
            if origin: headers["Origin"]=base
            req = urllib.request.Request(base+"/api/library/ai/profile",json.dumps(body).encode(),headers=headers)
            with urllib.request.urlopen(req) as response:
                return json.load(response)
        self.assertEqual(get()["selected"],"default")
        for body,token,origin in [
            ({"id":"local:custom.json"},"bad",True),
            ({"id":"local:custom.json"},"test-token",False),
            ({"id":"local:../evil.json"},"test-token",True),
            ({"id":"local:custom.json","path":"override"},"test-token",True)
        ]:
            with self.subTest(body=body),self.assertRaises(urllib.error.HTTPError) as caught:
                post(body,token,origin)
            caught.exception.close()
        self.assertFalse(self.settings.exists())
        response = post({"id":"local:custom.json"})
        self.assertEqual(response["selected"],"local:custom.json")
        self.assertEqual(response["active"],"default")
        self.assertTrue(response["restart_required"])
        self.assertEqual(get()["active"],"default")
        self.assertEqual(self.controller().active,"local:custom.json")
        with urllib.request.urlopen(base+"/api/items?q=some&kind=&view=all&page=0") as result:
            self.assertEqual(json.load(result)["total"],0)


if __name__=="__main__": unittest.main()
