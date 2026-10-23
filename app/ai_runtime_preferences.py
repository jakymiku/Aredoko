"""Explicit restart-only runtime/model locations; no discovery/download/hot swap."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import secrets
from ai_runtime import inspect_runtime, model_state, object_pairs, legacy_runtime_state
from storage_lease import plain_path, storage_parent, storage_lease

MAX_SETTINGS = 16384
UNSET = object()


def read_preferences(path):
    path=plain_path(path,missing=True)
    if not path.exists():return {}
    if path.stat().st_size>MAX_SETTINGS:raise ValueError('Launch preferences exceed limit')
    value=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=object_pairs)
    if not isinstance(value,dict):raise ValueError('Invalid launch preferences')
    for name in ('ai_python','ai_runtime_root','models_root'):
        if name in value and (not isinstance(value[name],str) or len(value[name])>4096
                or not Path(value[name]).is_absolute() or any(ord(c)<32 for c in value[name])):
            raise ValueError('Invalid AI location')
    if ('ai_runtime_root' in value)!=('ai_runtime_manifest_sha256' in value):raise ValueError('Incomplete AI runtime selection')
    if 'ai_runtime_manifest_sha256' in value:
        checksum=value['ai_runtime_manifest_sha256']
        if not isinstance(checksum,str) or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum):
            raise ValueError('Invalid AI runtime digest')
    return value


def runtime_python(settings, default, unavailable):
    # Preserve explicit legacy interpreter overrides and command-line semantics.
    if 'ai_python' in settings:return Path(settings['ai_python'])
    if 'ai_runtime_root' not in settings:return Path(default)
    try:
        info=inspect_runtime(settings['ai_runtime_root'],expected=settings['ai_runtime_manifest_sha256'])
        return Path(info['python'])
    except (OSError,ValueError,KeyError):
        # Broken AI setup must not prevent basic browsing or silently run a
        # different interpreter. The setup snapshot explains the saved failure.
        return Path(unavailable)


class AIRuntimePreferences:
    def __init__(self,path,repo,profile,*,active_python=None,active_models_root=None):
        self.path=Path(path);self.repo=Path(repo);self.profile=profile
        try:self.started=read_preferences(self.path)
        except (ValueError,OSError,UnicodeError):self.started={}
        self.active_python=str(active_python) if active_python is not None else None
        self.active_models_root=str(active_models_root) if active_models_root is not None else None

    def snapshot(self):
        try:data=read_preferences(self.path)
        except (OSError,ValueError,UnicodeError):
            return {'runtime':{'state':'preferences_invalid','ready':False},
                    'model':{'state':'preferences_invalid','ready':False},'restart_required':False}
        selected=None
        if 'ai_runtime_root' in data:
            try:
                info=inspect_runtime(data['ai_runtime_root'],expected=data['ai_runtime_manifest_sha256'])
                runtime={'state':'pack_files_present','ready':True,**info};selected=info['python']
            except (OSError,ValueError,KeyError):runtime={'state':'runtime_invalid','ready':False}
        else:
            selected=data.get('ai_python',self.active_python)
            runtime={'state':legacy_runtime_state(selected),'ready':False,
                     'verification':'not_checked','model_loaded':False,'driver_tested':False}
        models=data.get('models_root',str(self.path.parent/'models'))
        model=model_state(self.profile,self.repo,models)
        runtime_changed=selected is not None and self.active_python is not None and os.path.normcase(str(selected))!=os.path.normcase(self.active_python)
        models_changed=self.active_models_root is not None and models is not None and os.path.normcase(str(models))!=os.path.normcase(self.active_models_root)
        selection_changed=any(data.get(k)!=self.started.get(k) for k in ('ai_python','ai_runtime_root','ai_runtime_manifest_sha256','models_root'))
        return {'runtime':runtime,'model':model,'restart_required':selection_changed or runtime_changed or models_changed,
                'selection_service_available':True,'selection_api_supported':True,'downloads_supported':False,
                'inference_verified':False,'message':'設定の変更は次回起動時に反映します。実行環境とモデルは別々に確認します。'}

    def select(self,*,runtime_root=UNSET,models_root=UNSET,consent=False,cancelled=lambda:False,progress=None,publish=None):
        if consent is not True:raise ValueError('Explicit runtime folder consent required')
        # This synchronous CPU service runs inside the owned setup job,
        # not a blocking GUI endpoint. Never execute/import the selected runtime.
        info=None
        if runtime_root is not UNSET and runtime_root is not None:
            if not isinstance(runtime_root,str) or not Path(runtime_root).is_absolute():raise ValueError('Select an absolute runtime folder')
            info=inspect_runtime(runtime_root,verify=True,cancelled=cancelled,progress=progress)
        if models_root is not UNSET and models_root is not None:
            if not isinstance(models_root,str) or not Path(models_root).is_absolute():raise ValueError('Select an absolute models folder')
            models_root=str(plain_path(models_root,directory=True))
        storage_parent(self.path)
        with storage_lease(self.path):
            value=read_preferences(self.path)
            if runtime_root is not UNSET:
                value.pop('ai_runtime_root',None);value.pop('ai_runtime_manifest_sha256',None);value.pop('ai_python',None)
                if info is not None:
                    value.pop('ai_python',None)
                    value.update(ai_runtime_root=info['root'],ai_runtime_manifest_sha256=info['manifest_sha256'])
            if models_root is not UNSET:
                if models_root is None:value.pop('models_root',None)
                else:value['models_root']=models_root
            content=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
            if len(content)>MAX_SETTINGS:raise ValueError('Launch preferences exceed limit')
            temporary=self.path.with_name(self.path.name+'.'+secrets.token_hex(8)+'.tmp')
            try:
                if cancelled():raise RuntimeError('Runtime selection cancelled')
                with temporary.open('xb') as stream:
                    stream.write(content);stream.flush();os.fsync(stream.fileno())
                if cancelled():raise RuntimeError('Runtime selection cancelled')
                plain_path(temporary);plain_path(self.path,missing=True)
                # The owned setup job serializes cancellation against this
                # final commit. CLI callers retain the ordinary atomic replace.
                def replace():
                    plain_path(temporary);plain_path(self.path,missing=True)
                    os.replace(temporary,self.path)
                fence=getattr(self,'writer_fence',None)
                # Enter the pause boundary before the owned job's publish lock,
                # keeping its cancel/close responsive while backup is paused.
                with fence.write(cancelled=cancelled) if fence is not None else nullcontext():
                    if publish is None:replace()
                    else:publish(replace)
            finally:
                if temporary.exists():plain_path(temporary);temporary.unlink()
        return self.snapshot()
