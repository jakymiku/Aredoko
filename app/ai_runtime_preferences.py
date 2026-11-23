"""Explicit restart-only runtime/model locations; no discovery/download/hot swap."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import secrets
from ai_runtime import inspect_runtime, model_state, object_pairs, legacy_runtime_state
from storage_lease import plain_path, storage_parent, storage_lease
from model_locations import FIELD as LOCATIONS, ModelTarget, parse_locations, serialize_locations

MAX_SETTINGS = 16384
UNSET = object()
MODEL_ROOT_FIELDS = {'embedding':'embedding_models_root','tagger':'tagger_models_root','intent':'intent_models_root'}


def model_root(settings, role, default=None, *, target=None):
    if role not in MODEL_ROOT_FIELDS:raise ValueError('Unknown model role')
    if target is not None:
        if not isinstance(target,ModelTarget) or target.role!=role:raise ValueError('Model placement role mismatch')
        for identity,root in parse_locations(settings.get(LOCATIONS,[])):
            if identity==target:return root
    return settings.get(MODEL_ROOT_FIELDS[role],settings.get('models_root',default))


def read_preferences(path):
    path=plain_path(path,missing=True)
    if not path.exists():return {}
    if path.stat().st_size>MAX_SETTINGS:raise ValueError('Launch preferences exceed limit')
    value=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=object_pairs)
    if not isinstance(value,dict):raise ValueError('Invalid launch preferences')
    if 'verify_ai_runtime' in value and type(value['verify_ai_runtime']) is not bool:raise ValueError('Invalid runtime verification preference')
    for name in ('ai_python','ai_runtime_root','models_root',*MODEL_ROOT_FIELDS.values()):
        if name in value and (not isinstance(value[name],str) or len(value[name])>4096
                or not Path(value[name]).is_absolute() or any(ord(c)<32 for c in value[name])):
            raise ValueError('Invalid AI location')
    if ('ai_runtime_root' in value)!=('ai_runtime_manifest_sha256' in value):raise ValueError('Incomplete AI runtime selection')
    if 'ai_runtime_manifest_sha256' in value:
        checksum=value['ai_runtime_manifest_sha256']
        if not isinstance(checksum,str) or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum):
            raise ValueError('Invalid AI runtime digest')
    parse_locations(value.get(LOCATIONS,[]))
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
        common=data.get('models_root',str(self.path.parent/'models'))
        try:target=ModelTarget.for_profile('embedding',self.profile) if self.profile is not None else None
        except ValueError:target=None
        models=model_root(data,'embedding',common,target=target)
        model=model_state(self.profile,self.repo,models)
        runtime_changed=selected is not None and self.active_python is not None and os.path.normcase(str(selected))!=os.path.normcase(self.active_python)
        models_changed=self.active_models_root is not None and models is not None and os.path.normcase(str(models))!=os.path.normcase(self.active_models_root)
        verify=data.get('verify_ai_runtime',True);active_verify=self.started.get('verify_ai_runtime',True)
        selection_changed=verify!=active_verify or any(data.get(k)!=self.started.get(k) for k in ('ai_python','ai_runtime_root','ai_runtime_manifest_sha256','models_root',LOCATIONS,*MODEL_ROOT_FIELDS.values()))
        return {'runtime':runtime,'model':model,'runtime_root':data.get('ai_runtime_root'),'models_root':models,'shared_models_root':common,'model_roots':{role:model_root(data,role,common) for role in MODEL_ROOT_FIELDS},'model_locations':data.get(LOCATIONS,[]),'restart_required':selection_changed or runtime_changed or models_changed,
                'verify_ai_runtime':verify,'active_verify_ai_runtime':active_verify,
                'selection_service_available':True,'selection_api_supported':True,'downloads_supported':False,
                'inference_verified':False,'message':'設定の変更は次回起動時に反映します。実行環境とモデルは別々に確認します。'}

    def select(self,*,runtime_root=UNSET,runtime_expected=None,models_root=UNSET,model_role=None,model_target=None,verify_ai_runtime=UNSET,consent=False,cancelled=lambda:False,progress=None,publish=None):
        if consent is not True:raise ValueError('Explicit runtime folder consent required')
        if verify_ai_runtime is not UNSET and type(verify_ai_runtime) is not bool:raise ValueError('Invalid runtime verification preference')
        if model_role is not None and (not isinstance(model_role,str) or model_role not in MODEL_ROOT_FIELDS or models_root is UNSET):raise ValueError('Explicit model role and folder required')
        target=ModelTarget.from_dict(model_target) if model_target is not None else None
        if target is not None and (model_role is not None or models_root is UNSET):raise ValueError('Select one explicit model target')
        # This synchronous CPU service runs inside the owned setup job,
        # not a blocking GUI endpoint. Never execute/import the selected runtime.
        info=None
        if runtime_root is not UNSET and runtime_root is not None:
            if not isinstance(runtime_root,str) or not Path(runtime_root).is_absolute():raise ValueError('Select an absolute runtime folder')
            previous=read_preferences(self.path) if self.path.exists() else {}
            pinned=runtime_expected or (previous.get('ai_runtime_manifest_sha256') if previous.get('ai_runtime_root')==runtime_root else None)
            info=inspect_runtime(runtime_root,verify=True,expected=pinned,cancelled=cancelled,progress=progress)
        if models_root is not UNSET and models_root is not None:
            if not isinstance(models_root,str) or not Path(models_root).is_absolute():raise ValueError('Select an absolute models folder')
            models_root=str(plain_path(models_root,directory=True))
        storage_parent(self.path)
        with storage_lease(self.path):
            value=read_preferences(self.path)
            if verify_ai_runtime is not UNSET:value['verify_ai_runtime']=verify_ai_runtime
            if runtime_root is not UNSET:
                value.pop('ai_runtime_root',None);value.pop('ai_runtime_manifest_sha256',None);value.pop('ai_python',None)
                if info is not None:
                    value.pop('ai_python',None)
                    value.update(ai_runtime_root=info['root'],ai_runtime_manifest_sha256=info['manifest_sha256'])
            if models_root is not UNSET:
                placements=list(parse_locations(value.get(LOCATIONS,[])))
                if target is not None:
                    placements=[entry for entry in placements if entry[0]!=target]
                    if models_root is not None:placements.append((target,models_root))
                elif model_role is not None:
                    field=MODEL_ROOT_FIELDS[model_role]
                    if models_root is None:value.pop(field,None)
                    else:value[field]=models_root
                    placements=[entry for entry in placements if entry[0].role!=model_role]
                else:
                    # The legacy common picker/reset deliberately replaces all
                    # role/model overrides, without touching any model files.
                    for field in MODEL_ROOT_FIELDS.values():value.pop(field,None)
                    if models_root is None:value.pop('models_root',None)
                    else:value['models_root']=models_root
                    placements=[]
                if placements:value[LOCATIONS]=serialize_locations(placements)
                else:value.pop(LOCATIONS,None)
                parse_locations(value.get(LOCATIONS,[]))
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
