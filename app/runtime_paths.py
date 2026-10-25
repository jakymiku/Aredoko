"""Explicit local runtime locations; never search PATH or download assets."""
import os
from pathlib import Path


def worker_python(repo, override=None):
    return Path(os.path.abspath(override)) if override is not None else Path(repo) / '.venv-ai/Scripts/python.exe'


def model_directory(repo, relative, models_root=None):
    base = Path(os.path.abspath(models_root if models_root is not None else Path(repo) / 'models'))
    target = base / relative
    # Inspect lexical ancestors before resolve() can hide links/junctions.
    for part in reversed((target, *target.parents)):
        if part.is_symlink() or (part.exists() and getattr(part.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Linked model directory is not allowed')
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError('Model directory escapes models')
    return target


# A selected pack is fully verified once per backend lifetime before execution.
# Its manifest/core are checked on every spawn. Packs are immutable after setup;
# this cache is not a guarantee against same-user mid-session bulk tampering.
_verified_packs=set()
_pack_bindings={}
import threading
_pack_lock=threading.Lock()


def bind_runtime(root,expected):
    _pack_bindings[os.path.normcase(os.path.abspath(root))]=expected


def worker_command(python,script,arguments):
    from storage_lease import plain_path
    python=Path(python);script=plain_path(script)
    marker=python.parent/'aredoko-ai-runtime.json'
    expected=_pack_bindings.get(os.path.normcase(os.path.abspath(python.parent)))
    if expected is not None or marker.exists() or marker.is_symlink():
        from ai_runtime import inspect_runtime
        with _pack_lock:
            info=inspect_runtime(python.parent,expected=expected)
            key=(info['root'],info['manifest_sha256'])
            if key not in _verified_packs:
                inspect_runtime(python.parent,verify=True,expected=expected)
                _verified_packs.add(key)
    # Legacy venvs retain their existing script invocation. Standalone Python's
    # _pth ignores the script directory, so explicitly add this app's worker
    # directory rather than accidentally importing an older app from the pack.
    isolated=any(python.parent.glob('python3*._pth'))
    if not isolated:return [str(python),'-X','utf8','-B','-u',str(script),*arguments]
    bootstrap="import os,runpy,sys; p=sys.argv[1]; sys.argv=sys.argv[1:]; sys.path.insert(0,os.path.dirname(p)); runpy.run_path(p,run_name='__main__')"
    return [str(python),'-X','utf8','-I','-B','-u','-c',bootstrap,str(script),*arguments]
