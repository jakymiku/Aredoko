"""Local, restart-only AI profile preferences. Never downloads or executes models.

A GUI selection is a validated file *identifier*, not an arbitrary path or
Python import. The running encoder/SQLite vector-space identity stay unchanged.
"""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from ai_profiles import DEFAULT_PROFILE, load_profile
from ai_scope import validate_scope
from runtime_paths import worker_python

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.json\Z")
MAX_FILES = 64
RESOURCE_DEFAULT = {"idle_release_seconds": 0, "index_pause_ms": 0}

def validate_resource(value):
    if not isinstance(value, dict) or set(value) != set(RESOURCE_DEFAULT):
        raise ValueError("Invalid AI resource settings")
    idle = value["idle_release_seconds"]
    pause = value["index_pause_ms"]
    if type(idle) is not int or idle < 0 or idle > 3600:
        raise ValueError("Idle seconds must be 0..3600")
    if type(pause) is not int or pause < 0 or pause > 2000:
        raise ValueError("Index pause must be 0..2000 ms")
    return {"idle_release_seconds":idle,"index_pause_ms":pause}


def default_settings_path(repo):
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / "Aredoko" / "settings.json") if base else Path(repo) / "data" / "settings.json"

class AIProfileSettings:
    def __init__(self, repo, settings_path=None, command_line_profile=None, profile_directory=None, *, ai_python=None, models_root=None):
        self._write_lock = threading.RLock()
        self.repo = Path(repo).resolve()
        self.python = worker_python(self.repo, ai_python)
        self.models_root = models_root
        self.folder = Path(profile_directory) if profile_directory is not None else self.repo / "data" / "ai-profiles"
        self.path = Path(settings_path) if settings_path is not None else default_settings_path(self.repo)
        self.override = Path(command_line_profile).resolve() if command_line_profile is not None else None
        self.startup_error = ""
        self.started = "default"
        self.startup_path = None
        try:
            if self.override is not None:
                # An explicit -AIProfile must override a damaged saved preference.
                try:
                    self.started = self.selected()
                except (ValueError, OSError, json.JSONDecodeError):
                    self.started = "invalid"
                self.startup_path = self.override
            else:
                self.started = self.selected()
                self.startup_path = self.path_for(self.started)
            if self.startup_path is not None:
                load_profile(self.startup_path)
        except (ValueError, OSError, json.JSONDecodeError) as ex:
            self.startup_path = None
            self.startup_error = "モデル設定が無効です（" + type(ex).__name__ + "）。設定を確認してください。文字検索は利用できます。"
        self.active = "command-line" if self.override is not None else self.started

    def _read_settings(self):
        if not self.path.exists():
            return {"version":1,"profile":"default"}
        if self.path.is_symlink() or self.path.stat().st_size > 16384:
            raise ValueError("Invalid settings file")
        payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if (not isinstance(payload,dict)
                or not {"version","profile"} <= set(payload)
                or set(payload) - {"version","profile","resource","scope"}
                or type(payload["version"]) is not int or payload["version"] != 1
                or not isinstance(payload["profile"],str)):
            raise ValueError("Invalid AI settings")
        self.path_for(payload["profile"])
        if "resource" in payload:
            validate_resource(payload["resource"])
        return payload

    def selected(self):
        return self._read_settings()["profile"]

    def resource(self):
        data=self._read_settings()
        return validate_resource(data.get("resource",RESOURCE_DEFAULT))

    def scope(self):
        return validate_scope(self._read_settings().get("scope",{}))

    def set_scope(self,scope):
        # Root existence is checked by the authenticated catalog API.
        scope=validate_scope(scope)
        with self._write_lock:
            data=self._read_settings()
            data["scope"]=scope
            self._save_settings(data)
            return self.scope()

    def _save_settings(self,payload):
        fence=getattr(self,'writer_fence',None)
        with fence.write() if fence is not None else nullcontext():self._write_settings(payload)

    def _write_settings(self,payload):
        serialized=json.dumps(payload,ensure_ascii=False)
        if len(serialized.encode("utf-8"))>16384:raise ValueError("Settings exceed size limit")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.is_symlink():
            raise ValueError("Unsafe settings file")
        tmp_path=None
        try:
            fd,tmp_path=tempfile.mkstemp(prefix=".ai-settings-",suffix=".tmp",dir=self.path.parent)
            with os.fdopen(fd,"w",encoding="utf-8") as stream:
                stream.write(serialized)
            os.replace(tmp_path,self.path)
        finally:
            if tmp_path and Path(tmp_path).exists():
                Path(tmp_path).unlink()

    def set_resource(self,resource):
        with self._write_lock:
            return self._set_resource(resource)

    def _set_resource(self,resource):
        resource=validate_resource(resource)
        data=self._read_settings()
        data["resource"]=resource
        self._save_settings(data)
        return self.resource()

    def path_for(self, profile_id):
        if profile_id == "default":
            return None
        if not isinstance(profile_id, str) or not profile_id.startswith("local:"):
            raise ValueError("Unknown profile identifier")
        filename = profile_id.removeprefix("local:")
        if not NAME.fullmatch(filename):
            raise ValueError("Unsafe profile identifier")
        path = self.folder / filename
        if self.folder.is_symlink() or path.is_symlink() or path.resolve().parent != self.folder.resolve():
            raise ValueError("Profile must stay in local profile directory")
        return path

    def _candidate(self, profile_id):
        try:
            path = self.path_for(profile_id)
            profile = load_profile(path)
            model_path = profile.model_path(self.repo, models_root=self.models_root)
            marker = model_path / "aredoko-revision.txt"
            python = self.python
            if not python.is_file():
                warning = "AI用Python環境がありません。起動設定または配布ファイルを確認してください。"
            elif not model_path.is_dir():
                warning = "モデルフォルダがありません。自動ダウンロードは行いません。"
            elif not marker.is_file():
                warning = "重みのリビジョン確認ファイルがありません。aredoko-revision.txtを確認してください。"
            elif marker.read_text(encoding="utf-8").strip() != profile.revision:
                warning = "モデルのリビジョンが設定と一致しません。別の重みを上書きしないでください。"
            else:
                warning = ""
            return {"id": profile_id, "label": profile.label, "model_id": profile.model_id,
                    "modalities": list(profile.modalities), "adapter": profile.adapter,
                    "dimension": profile.dimension, "valid": True, "ready": not warning,
                    "warning": warning or "準備ファイルを確認済み。モデルの実ロード成功は未検証です。"}
        except (OSError, ValueError, json.JSONDecodeError) as ex:
            return {"id": profile_id, "label": profile_id, "model_id": "",
                    "modalities": [], "adapter": "", "dimension": 0,
                    "valid": False, "ready": False,
                    "warning": "設定を読み込めません（" + type(ex).__name__ + "）。JSON内容・場所を確認してください。"}

    def snapshot(self):
        candidates = [self._candidate("default")]
        if self.folder.is_dir() and not self.folder.is_symlink():
            # No recursive/symlink traversal; bounded file enumeration.
            for entry in sorted(self.folder.iterdir(), key=lambda p: p.name)[:MAX_FILES]:
                if NAME.fullmatch(entry.name) and (entry.is_file() or entry.is_symlink()):
                    candidates.append(self._candidate("local:" + entry.name))
        try:
            pending = self.selected()
            error = self.startup_error
        except (ValueError, OSError, json.JSONDecodeError) as ex:
            pending = "invalid"
            error = "保存済みのモデル設定が無効です（" + type(ex).__name__ + "）。"
        if pending not in {row["id"] for row in candidates} and pending not in ("default", "invalid"):
            candidates.append(self._candidate(pending))
        try: resource=self.resource()
        except (ValueError,OSError,json.JSONDecodeError): resource=dict(RESOURCE_DEFAULT)
        return {"profiles": candidates, "selected": pending, "active": self.active,
                "resource":resource,
                "command_line_override": self.override is not None,
                "restart_required": self.override is None and pending != self.started,
                "error": error,
                "message": "起動時の -AIProfile が優先です。GUI設定は -AIProfile を外した次回起動から適用します。" if self.override else
                           "モデルの変更は次回起動時に適用されます。現在の検索・索引処理は切り替わりません。"}

    def choose(self, profile_id):
        with self._write_lock:
            return self._choose(profile_id)

    def _choose(self, profile_id):
        candidate = self._candidate(profile_id)
        if not candidate["valid"]:
            raise ValueError("Invalid or missing profile. Fix the JSON before selecting.")
        # A damaged profile-only preference may still be repaired in the GUI.
        try:
            resource=self.resource()
        except (ValueError,OSError,json.JSONDecodeError):
            resource=dict(RESOURCE_DEFAULT)
        try:
            payload=self._read_settings()
        except (ValueError,OSError,json.JSONDecodeError):
            # Repairing damaged settings must not silently widen an old scope.
            payload={"version":1,"profile":profile_id,"scope":validate_scope({"root_ids":[]})}
        payload["profile"]=profile_id
        if resource != RESOURCE_DEFAULT:
            payload["resource"]=resource
        self._save_settings(payload)
        return self.snapshot()
