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
import time
_pack_lock=threading.Lock()
_state_lock=threading.Lock()
_verify_state={}
_verify_jobs={}
_SLOW_VERIFY_SECONDS=300.0
_verify_enabled=True


def configure_runtime_verification(enabled=True):
    """Restart-only preference. Acquisition and explicit repair always verify."""
    if type(enabled) is not bool:raise ValueError('Invalid runtime verification preference')
    global _verify_enabled
    _verify_enabled=enabled


def _root_key(root):
    return os.path.normcase(os.path.abspath(root))


def _idle_status(state='idle'):
    return {
        'state': state,
        'files_done': 0,
        'files_total': 0,
        'bytes_done': 0,
        'bytes_total': 0,
        'elapsed_seconds': 0.0,
        'slow': False,
        'error': '',
    }


def bind_runtime(root,expected):
    _pack_bindings[_root_key(root)]=expected


def bound_runtime_digest(python):
    if python is None:
        return None
    return _pack_bindings.get(_root_key(runtime_root(python)))


def runtime_root(python):
    python=Path(python)
    direct=python.parent
    if (direct/'aredoko-ai-runtime.json').exists() or _root_key(direct) in _pack_bindings:
        return direct
    outer=direct.parent
    if direct.name.casefold()=='scripts' and ((outer/'aredoko-ai-runtime.json').exists() or _root_key(outer) in _pack_bindings):
        return outer
    return direct


def runtime_verification_status(python):
    if python is None:
        return _idle_status('idle')
    python=Path(python)
    root_key=_root_key(runtime_root(python))
    marker=runtime_root(python)/'aredoko-ai-runtime.json'
    expected=_pack_bindings.get(root_key)
    with _state_lock:
        entry=_verify_state.get(root_key)
        if entry is None:
            if expected is None and not (marker.exists() or marker.is_symlink()):
                return _idle_status('idle')
            return _idle_status('idle')
        state=entry['state']
        started_at=entry.get('started_at')
        if state=='verifying' and started_at is not None:
            elapsed=round(max(0.0,time.monotonic()-started_at),2)
        else:
            elapsed=round(float(entry.get('elapsed_seconds',0.0)),2)
        return {
            'state': state,
            'files_done': int(entry.get('files_done',0)),
            'files_total': int(entry.get('files_total',0)),
            'bytes_done': int(entry.get('bytes_done',0)),
            'bytes_total': int(entry.get('bytes_total',0)),
            'elapsed_seconds': elapsed,
            'slow': bool(state=='verifying' and elapsed>=_SLOW_VERIFY_SECONDS),
            'error': str(entry.get('error','')),
        }


def verify_runtime_pack(python, *, cancelled=lambda: False):
    python=Path(python)
    root_key=_root_key(runtime_root(python))
    marker=runtime_root(python)/'aredoko-ai-runtime.json'
    expected=_pack_bindings.get(root_key)
    if expected is None and not (marker.exists() or marker.is_symlink()):
        return None
    from ai_runtime import inspect_runtime
    # A queued verification must also be cancellable while another pack owns
    # the hash lock. Never leave a background reader alive after restore proof.
    while not _pack_lock.acquire(timeout=0.05):
        if cancelled():raise RuntimeError('Runtime validation cancelled')
    try:
        if cancelled():raise RuntimeError('Runtime validation cancelled')
        try:
            info=inspect_runtime(runtime_root(python),expected=expected,cancelled=cancelled)
        except Exception as error:
            with _state_lock:
                prev=_verify_state.get(root_key) or {}
                _verify_state[root_key]={
                    'state':'failed',
                    'files_done':int(prev.get('files_done',0)),
                    'files_total':int(prev.get('files_total',0)),
                    'bytes_done':int(prev.get('bytes_done',0)),
                    'bytes_total':int(prev.get('bytes_total',0)),
                    'elapsed_seconds':float(prev.get('elapsed_seconds',0.0)),
                    'started_at':None,
                    'error':str(error),
                }
            raise
        key=(info['root'],info['manifest_sha256'])
        if not _verify_enabled:
            with _state_lock:_verify_state[root_key]=_idle_status('skipped')
            return info
        if key in _verified_packs:
            with _state_lock:
                prev=_verify_state.get(root_key)
                if prev is None or prev.get('state')!='verified':
                    _verify_state[root_key]={
                        'state':'verified',
                        'files_done':int(info.get('files',0)),
                        'files_total':int(info.get('files',0)),
                        'bytes_done':int(info.get('bytes',0)),
                        'bytes_total':int(info.get('bytes',0)),
                        'elapsed_seconds':float(prev.get('elapsed_seconds',0.0)) if prev else 0.0,
                        'started_at':None,
                        'error':'',
                    }
            return info
        started_at=time.monotonic()
        with _state_lock:
            _verify_state[root_key]={
                'state':'verifying',
                'files_done':0,
                'files_total':int(info.get('files',0)),
                'bytes_done':0,
                'bytes_total':int(info.get('bytes',0)),
                'elapsed_seconds':0.0,
                'started_at':started_at,
                'error':'',
            }
        def _on_progress(counts):
            now=time.monotonic()
            with _state_lock:
                cur=_verify_state.get(root_key)
                if cur is not None and cur.get('state')=='verifying':
                    cur['files_done']=int(counts.get('files_done',cur['files_done']))
                    cur['files_total']=int(counts.get('files_total',cur['files_total']))
                    cur['bytes_done']=int(counts.get('bytes_done',cur['bytes_done']))
                    cur['bytes_total']=int(counts.get('bytes_total',cur['bytes_total']))
                    cur['elapsed_seconds']=max(0.0,now-started_at)
        try:
            full_info=inspect_runtime(runtime_root(python),verify=True,expected=expected,cancelled=cancelled,progress=_on_progress)
            if cancelled():raise RuntimeError('Runtime validation cancelled')
            elapsed=max(0.0,time.monotonic()-started_at)
            with _state_lock:
                _verified_packs.add(key)
                _verify_state[root_key]={
                    'state':'verified',
                    'files_done':int(full_info.get('files',0)),
                    'files_total':int(full_info.get('files',0)),
                    'bytes_done':int(full_info.get('bytes',0)),
                    'bytes_total':int(full_info.get('bytes',0)),
                    'elapsed_seconds':elapsed,
                    'started_at':None,
                    'error':'',
                }
            return full_info
        except Exception as error:
            elapsed=max(0.0,time.monotonic()-started_at)
            with _state_lock:
                cur=_verify_state.get(root_key) or {}
                _verify_state[root_key]={
                    'state':'cancelled' if cancelled() else 'failed',
                    'files_done':int(cur.get('files_done',0)),
                    'files_total':int(cur.get('files_total',info.get('files',0))),
                    'bytes_done':int(cur.get('bytes_done',0)),
                    'bytes_total':int(cur.get('bytes_total',info.get('bytes',0))),
                    'elapsed_seconds':elapsed,
                    'started_at':None,
                    'error':str(error),
                }
            raise
    finally:
        _pack_lock.release()


class RuntimeVerificationJob:
    """One backend-owned reader; close must succeed before restore can switch."""
    def __init__(self,python):
        self.python=python
        self.cancelled=threading.Event()
        self.thread=threading.Thread(target=self._run,daemon=True,name='ai-runtime-verify')

    def _run(self):
        key=_root_key(runtime_root(self.python))
        try:
            verify_runtime_pack(self.python,cancelled=self.cancelled.is_set)
        except Exception:
            with _state_lock:
                entry=_verify_state.get(key)
                if entry is not None and entry['state']=='verifying':
                    entry.update(state='cancelled' if self.cancelled.is_set() else 'failed',started_at=None)
        finally:
            with _state_lock:
                if _verify_jobs.get(key) is self:_verify_jobs.pop(key)

    def close(self,timeout=10):
        self.cancelled.set()
        self.thread.join(timeout)
        return not self.thread.is_alive()


def start_runtime_verification(python):
    if python is None:
        return False
    python=Path(python)
    root_key=_root_key(runtime_root(python))
    if not _verify_enabled:
        with _state_lock:_verify_state[root_key]=_idle_status('skipped')
        return None
    marker=runtime_root(python)/'aredoko-ai-runtime.json'
    expected=_pack_bindings.get(root_key)
    if expected is None and not (marker.exists() or marker.is_symlink()):
        return False
    with _state_lock:
        if root_key in _verify_jobs:return None
        cur=_verify_state.get(root_key)
        if cur is not None and cur.get('state') in ('verifying','verified'):
            if cur.get('state')=='verifying' or any(_root_key(r)==root_key for r,_ in _verified_packs):
                return None
        job=RuntimeVerificationJob(python)
        _verify_jobs[root_key]=job
        # Publish before thread start, including time spent waiting for the lock.
        _verify_state[root_key]={**_idle_status('verifying'),'started_at':time.monotonic()}
        try:job.thread.start()
        except Exception:
            _verify_jobs.pop(root_key,None)
            _verify_state.pop(root_key,None)
            raise
    return job


def worker_command(python,script,arguments,*,cancelled=lambda:False):
    from storage_lease import plain_path
    if cancelled():raise RuntimeError('Runtime validation cancelled')
    python=Path(python);script=plain_path(script)
    verify_runtime_pack(python,cancelled=cancelled)
    if cancelled():raise RuntimeError('Runtime validation cancelled')
    # Legacy venvs retain their existing script invocation. Standalone Python's
    # _pth ignores the script directory, so explicitly add this app's worker
    # directory rather than accidentally importing an older app from the pack.
    isolated=any(python.parent.glob('python3*._pth'))
    if not isolated:return [str(python),'-X','utf8','-B','-u',str(script),*arguments]
    bootstrap="import os,runpy,sys; p=sys.argv[1]; sys.argv=sys.argv[1:]; sys.path.insert(0,os.path.dirname(p)); runpy.run_path(p,run_name='__main__')"
    return [str(python),'-X','utf8','-I','-B','-u','-c',bootstrap,str(script),*arguments]
