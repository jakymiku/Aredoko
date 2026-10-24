"""Owned, console-free release launcher. Windows activation remains a native gate."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import sys
import time
import urllib.request
from contextlib import nullcontext

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from release_runtime import verify_release, python_layout, media_layout, runtime_environment
from storage_lease import plain_path, storage_parent, storage_lease
from packaged_frontend import prepare_frontend
from startup_progress import StartupCancelled, StartupProgress
sys.path.insert(0, str(ROOT / ('backend/app' if (ROOT / 'backend/app').is_dir() else 'app')))
from restore_switch import (
    check_pending_restore,
    get_restore_pending_info,
    is_restore_pending,
    commit_restore_switch,
    rollback_restore_switch,
)

CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
RUNTIME_FIELDS = {'ai_runtime_root', 'ai_runtime_manifest_sha256'}

PATH_OPTIONS = {'database': '--db', 'ai_python': '--ai-python', 'models_root': '--models-root',
                'ai_profile': '--ai-profile', 'ai_settings': '--ai-settings',
                'ai_profiles_dir': '--ai-profiles-dir', 'tagger_profile': '--tagger-profile',
                'embedding_models_root':'--embedding-models-root','tagger_models_root':'--tagger-models-root',
                'intent_models_root':'--intent-models-root'}


class AppSessionError(RuntimeError):
    """The frontend was started, but its session ended unexpectedly."""


def report_failure(error, *, show_dialog=True):
    heading = ('Aredoko stopped unexpectedly.' if isinstance(error, AppSessionError)
               else 'Aredoko could not start.')
    message = heading + '\n' + str(error)
    if sys.stderr is not None:print(message, file=sys.stderr)
    if show_dialog and os.name == 'nt':
        _show_error_dialog(message)
    return 1


def _show_error_dialog(message):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, 'Aredoko Alpha', 0x10)


def load_settings(data, explicit=None):
    path = Path(explicit) if explicit is not None else data / 'launch-settings.json'
    settings = {}
    if path.exists():
        plain_path(path)
        if path.stat().st_size > 16384:raise ValueError('Launch settings exceed limit')
        settings = json.loads(path.read_text(encoding='utf-8-sig'))
    elif explicit is not None:
        raise FileNotFoundError('Explicit launch settings are missing')
    return validate_settings(settings)


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) - (set(PATH_OPTIONS) | {'viewer_settings', 'ui_theme', 'ai_ranking'} | RUNTIME_FIELDS):
        raise ValueError('Unknown launch setting')
    for key in set(PATH_OPTIONS) | {'viewer_settings', 'ai_runtime_root'}:
        if key in settings and (not isinstance(settings[key], str) or not Path(settings[key]).is_absolute() or any(ord(c) < 32 for c in settings[key])):
            raise ValueError('Launch paths must be absolute: ' + key)
    if ('ai_runtime_root' in settings) != ('ai_runtime_manifest_sha256' in settings):
        raise ValueError('AI runtime location and inventory digest must be supplied together')
    if 'ai_runtime_manifest_sha256' in settings:
        checksum=settings['ai_runtime_manifest_sha256']
        if not isinstance(checksum,str) or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum):
            raise ValueError('Invalid AI runtime inventory digest')
    if settings.get('ui_theme', 'system') not in ('system', 'light', 'dark') or settings.get('ai_ranking', 'mean-rrf') not in ('max', 'mean-rrf'):
        raise ValueError('Invalid launch preference')
    return settings


def _runtime_check(command, *, root, timeout, progress, capture=False):
    """Poll only this child; cancellation never searches processes by name/PID."""
    progress.check_cancelled()
    with subprocess.Popen(command, cwd=root, env=runtime_environment(), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
                          text=True, encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW,
                          close_fds=True) as child:
        deadline = time.monotonic() + timeout
        try:
            while True:
                progress.check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = child.communicate(timeout=min(0.1, remaining))
                    progress.check_cancelled()
                    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:pass
        finally:
            _stop_owned(child)


def preflight(root, *, imports=True, progress=None):
    control = progress if progress is not None else StartupProgress()
    manifest = verify_release(root, progress=progress)
    with control.phase('runtime_layout'):
        if manifest.get('python_bundled') is not True or manifest.get('media_tools_bundled') is not True:
            raise ValueError('The staged release needs bundled Python and FFmpeg/ffprobe')
        python_layout(root / 'runtime/python', manifest.get('ai_runtime_bundled') is True, progress=progress)
        media_layout(root / 'runtime/media', progress=progress)
    if imports:
        if os.name != 'nt':raise RuntimeError('Windows runtime checks require Windows')
        args = [str(root / 'runtime/python/python.exe'), '-B', str(root / 'tools/probe_release_runtime.py')]
        if manifest.get('ai_runtime_bundled') is True:args.append('--ai')
        with control.phase('python_imports'):
            result = _runtime_check(args, root=root, timeout=90, progress=control, capture=True)
            if result.returncode or json.loads(result.stdout).get('pass') is not True:
                raise RuntimeError('Bundled Python imports failed; check the prepared runtime')
        with control.phase('media_probe'):
            for name in ('ffmpeg.exe', 'ffprobe.exe'):
                result = _runtime_check([str(root / 'runtime/media' / name), '-version'],
                                        root=root, timeout=10, progress=control)
                if result.returncode:raise RuntimeError('Bundled video tool failed: ' + name)
    return manifest


def _session(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}/api/session', timeout=0.4) as response:
        value = response.read(65537)
    if len(value) > 65536:raise ValueError('Invalid backend session')
    return json.loads(value)


def _stop_owned(process, graceful=False, timeout=8):
    if process is None:return
    if graceful and process.stdin is not None:
        process.stdin.close()
    if process.poll() is None:
        if not graceful:process.terminate()
        try:process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=5)


def run_session(backend_command, app_command, *, port, instance, logs, cwd, env, startup_timeout=20, app_factory=None, progress=None, require_ready=False, on_ready=None, frontend_timeout=60, data=None, restore_handoff=None):
    """Launch only owned children, and never attach to another service on a port."""
    # This advisory check provides a clear error; the per-launch session ID is
    # the race-safe proof that the listening server is ours.
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1', port))
        except OSError as error:raise RuntimeError('Aredoko port is already in use') from error
    backend = app = None
    ready_reached = False
    effective_data = data if data is not None else (logs.parent.parent if logs is not None and getattr(logs, 'parent', None) and logs.parent.name == 'logs' else None)
    if progress is not None:progress.check_cancelled()
    with (logs / 'backend.log').open('xb') as output, (logs / 'backend-error.log').open('xb') as errors, (logs / 'app.log').open('xb') as app_log:
        try:
            with progress.phase('backend_start') if progress is not None else nullcontext():
                backend = subprocess.Popen(backend_command, stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                       cwd=cwd, env=env, creationflags=CREATE_NO_WINDOW, close_fds=True)
                deadline = time.monotonic() + startup_timeout
                while True:
                    if progress is not None:progress.check_cancelled()
                    if backend.poll() is not None:raise RuntimeError('Backend exited during startup; see backend-error.log')
                    try:session = _session(port)
                    except (OSError, ValueError):session = None
                    if isinstance(session, dict):
                        if session.get('mode') != 'production' or session.get('instance_id') != instance:
                            raise RuntimeError('The listening backend does not belong to this launch')
                        break
                    if time.monotonic() >= deadline:raise RuntimeError('Backend startup timed out')
                    time.sleep(0.1)
            with progress.phase('frontend_start') if progress is not None else nullcontext():
                if progress is not None:progress.check_cancelled()
                app = (app_factory(app_command, app_log) if app_factory is not None else
                       subprocess.Popen(app_command, stdin=subprocess.DEVNULL, stdout=app_log, stderr=app_log,
                                    cwd=cwd, env=env, close_fds=True))
                if require_ready:
                    deadline = time.monotonic() + frontend_timeout
                    while not app.ready.is_set():
                        if progress is not None:progress.check_cancelled()
                        if backend.poll() is not None or app.poll() is not None:raise RuntimeError('Application exited before ready')
                        if app.ready_error is not None:raise RuntimeError('Initial screen failed; see app.log')
                        if time.monotonic() >= deadline:raise RuntimeError('Initial screen timed out')
                        time.sleep(0.05)
                    if app.ready_error is not None or app.poll() is not None or backend.poll() is not None:
                        raise RuntimeError('Application was not alive at ready')
                    session = _session(port)
                    if session.get('mode') != 'production' or session.get('instance_id') != instance:
                        raise RuntimeError('Backend identity changed before ready')
            if effective_data is not None and is_restore_pending(effective_data) and not require_ready:
                raise RuntimeError('Restore requires a verified frontend ready handshake')
            ready_reached = True
            if effective_data is not None and is_restore_pending(effective_data):
                commit_restore_switch(effective_data)
            if on_ready is not None:on_ready()
            while app.poll() is None:
                if backend.poll() is not None:raise AppSessionError('Backend stopped unexpectedly; see backend-error.log')
                time.sleep(0.1)
            if app.returncode:raise AppSessionError(f'Windows app exited with code {app.returncode}; see app.log')
        except Exception as error:
            if not ready_reached and effective_data is not None and is_restore_pending(effective_data):
                try:
                    rollback_restore_switch(effective_data, error=str(error))
                except Exception:
                    pass
            raise
        finally:
            try:
                try:_stop_owned(app)
                finally:
                    if app is not None and hasattr(app, 'close'):app.close()
            finally:_stop_owned(backend, graceful=True)
    if backend.returncode:raise AppSessionError('Backend did not exit cleanly; see backend-error.log')
    if restore_handoff is not None:return restore_handoff.finish(effective_data,backend,app)


def launch(root, data, settings, *, progress=None, startup_pipe=None, force_full=False, preferences_path=None, startup_overrides=None):
    # All writable state stays outside the versioned release. Reject accidental
    # source/payload placement before creating logs or opening a database.
    def validate_writable_locations(current):
        validate_settings(current)
        paths = [data, *(Path(current[k]) for k in ('database', 'ai_settings', 'viewer_settings', 'ai_profiles_dir') if k in current)]
        if any(p.resolve().is_relative_to(root.resolve()) for p in paths):
            raise ValueError('User data must be outside the release directory')

    validate_writable_locations(settings)
    storage_parent(data / 'launcher')
    with storage_lease(data / 'launcher'):
        previous=get_restore_pending_info(data)
        rolled_back=check_pending_restore(data)
        if rolled_back or isinstance(previous,dict) and previous.get('status')=='committed':
            settings = load_settings(data, preferences_path)
            if not rolled_back and startup_overrides:settings.update(startup_overrides)
            validate_writable_locations(settings)
        for attempt in range(8):
            result=_launch_once(root,data,settings,progress=progress,startup_pipe=startup_pipe if attempt==0 else None,force_full=force_full,preferences_path=preferences_path,explicit_profile=attempt==0 and bool(startup_overrides and startup_overrides.get('ai_profile')))
            if not isinstance(result,dict) or result.get('restart') is not True:return result
            check_pending_restore(data)
            settings=load_settings(data,preferences_path)
            validate_writable_locations(settings)
        raise RuntimeError('Too many restore restarts in one launcher session')


def _launch_once(root,data,settings,*,progress=None,startup_pipe=None,force_full=False,preferences_path=None,explicit_profile=False):
    instance = secrets.token_hex(16)
    logs = data / 'logs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + instance)
    storage_parent(logs / 'launcher.log');plain_path(logs, directory=True)
    values = {'database': str(data / 'catalog.sqlite'), 'ai_python': str(root / 'runtime/python/python.exe'),
              'models_root': str(data / 'models'), 'ai_settings': str(data / 'settings.json'),
              'ai_profiles_dir': str(data / 'ai-profiles'), **settings}
    from ai_runtime_preferences import runtime_python
    values['ai_python']=str(runtime_python(settings, values['ai_python'], data/'unavailable-ai-runtime/python.exe'))
    backend = [str(root / 'runtime/python/python.exe'), '-B', '-u', str(root / 'backend/app/production_server.py'),
               '--instance-id', instance, '--exit-on-stdin-close', '--ai-ranking', values.get('ai_ranking', 'mean-rrf')]
    for key, option in PATH_OPTIONS.items():
        if key in values:backend += [option, values[key]]
    pending=get_restore_pending_info(data)
    if not explicit_profile and isinstance(pending,dict) and pending.get('transient_ai_profile')==values.get('ai_profile') and values.get('ai_profile') is not None:
        backend.append('--ai-profile-transient')
    backend += ['--runtime-preferences', str(preferences_path if preferences_path is not None else data/'launch-settings.json')]
    app = ['--ui-theme', values.get('ui_theme', 'system'),
           '--viewer-settings', values.get('viewer_settings', str(data / 'viewer-settings.json'))]
    try:
        from startup_validation import startup_preflight
        manifest = startup_preflight(root, data / 'release-validation',
            lambda: preflight(root, progress=progress), progress=progress, force_full=force_full)
        if progress is not None:progress.check_cancelled()
        portable = manifest.get('frontend_activation') == 'portable'
        if startup_pipe is not None and not portable:raise ValueError('The owned bootstrap requires an explicit portable release')
        if portable:
            from portable_frontend import PortableFrontend
            frontend = PortableFrontend(root, manifest, instance)
        else:frontend = prepare_frontend(root, manifest)
        if progress is not None:progress.check_cancelled()
        handoff=None
        if portable and preferences_path is None:
            from restore_handoff import RestoreHandoff
            handoff=RestoreHandoff(logs,instance,Path(values['database']))
            backend += ['--restore-session-dir',str(logs)]
        return run_session(backend, app, port=8769, instance=instance, logs=logs, cwd=root,
                    env=runtime_environment(root / 'runtime/media'), app_factory=frontend.start,
                    progress=progress if portable else None, require_ready=portable,
                    on_ready=startup_pipe.mark_ready if startup_pipe is not None else None, data=data, restore_handoff=handoff)
    except Exception as error:
        if is_restore_pending(data):
            try:
                rollback_restore_switch(data, error=str(error))
            except Exception:
                pass
        (logs / 'launcher.log').write_text(type(error).__name__ + ': ' + str(error) + '\n', encoding='utf-8')
        failure_type = (StartupCancelled if isinstance(error, StartupCancelled) else
                        AppSessionError if isinstance(error, AppSessionError) else RuntimeError)
        raise failure_type(str(error) + '\nLogs: ' + str(logs)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--verify-only', action='store_true', help='Hash inventory only, on any OS; no child processes or writes')
    checks.add_argument('--check', action='store_true', help='Windows import/tool checks; no database, GUI, or model loading')
    checks.add_argument('--check-activation', action='store_true', help='Read-only installed MSIX identity/payload check, plus runtime checks; no activation')
    checks.add_argument('--startup-preflight', action='store_true', help='Internal inherited-pipe preflight worker; no application launch')
    checks.add_argument('--startup-owned', action='store_true', help='Internal portable bootstrap worker')
    checks.add_argument('--startup-smoke', action='store_true', help='Internal portable startup check with fresh isolated data')
    parser.add_argument('--full-check', action='store_true', help='Force full preflight on this launch, refreshing normal-startup validation')
    parser.add_argument('--no-error-dialog', action='store_true', help='Automation only: keep error logs and nonzero exit without a modal dialog')
    parser.add_argument('--settings', type=Path, help='Explicit launch-settings.json (otherwise in LOCALAPPDATA/Aredoko)')
    for key in set(PATH_OPTIONS) | {'viewer_settings', 'ui_theme', 'ai_ranking'} | RUNTIME_FIELDS:
        parser.add_argument('--' + key.replace('_', '-'))
    args = parser.parse_args()
    if args.startup_preflight or args.startup_owned or args.startup_smoke:
        # This is a one-shot worker, not the user-facing product entrypoint.
        # Use independent raw descriptors: a blocked writer must not hold a
        # Python standard-stream buffer lock during process shutdown.
        if args.full_check or args.settings is not None or any(getattr(args, key) is not None for key in set(PATH_OPTIONS) | {'viewer_settings', 'ui_theme', 'ai_ranking'} | RUNTIME_FIELDS):
            return 2
        try:
            if not all(stat.S_ISFIFO(os.fstat(stream.fileno()).st_mode) for stream in (sys.stdin, sys.stdout)):
                return 2
            incoming = os.fdopen(os.dup(sys.stdin.fileno()), 'rb', buffering=0)
            outgoing = os.fdopen(os.dup(sys.stdout.fileno()), 'wb', buffering=0)
            from startup_ipc import serve_preflight, serve_owned
            if args.startup_preflight:return serve_preflight(ROOT, incoming, outgoing)
            return serve_owned(ROOT, incoming, outgoing, smoke=args.startup_smoke)
        except Exception:
            return 2
    try:
        if args.verify_only:
            manifest = verify_release(ROOT)
        elif args.check or args.check_activation:
            manifest = preflight(ROOT)
            if args.check_activation:prepare_frontend(ROOT, manifest)
        else:
            if os.name != 'nt':raise RuntimeError('Aredoko release launch requires Windows')
            base = os.environ.get('LOCALAPPDATA')
            if not base or not Path(base).is_absolute():raise ValueError('LOCALAPPDATA is unavailable')
            data = Path(base) / 'Aredoko'
            settings = load_settings(data, args.settings)
            overrides={key: getattr(args, key) for key in set(PATH_OPTIONS) | {'viewer_settings', 'ui_theme', 'ai_ranking'} | RUNTIME_FIELDS if getattr(args, key) is not None}
            settings.update(overrides)
            launch(ROOT, data, validate_settings(settings), force_full=args.full_check,
                   preferences_path=Path(args.settings).absolute() if args.settings is not None else None,startup_overrides=overrides)
            return 0
        print(json.dumps({'pass': True, 'version': manifest['version'], 'readiness': 'staging-only',
                          'clean_machine_activation_verified': False,
                          'frontend_activation': manifest.get('frontend_activation', 'unconfigured'),
                          'installed_frontend_checked': args.check_activation}))
        return 0
    except Exception as error:
        return report_failure(error, show_dialog=not (args.no_error_dialog or args.check or args.check_activation or args.verify_only))


if __name__ == '__main__':
    sys.exit(main())
