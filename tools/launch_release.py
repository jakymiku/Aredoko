"""Owned, console-free release launcher. Windows activation remains a native gate."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from release_runtime import verify_release, python_layout, media_layout, runtime_environment
from storage_lease import plain_path, storage_parent, storage_lease
from packaged_frontend import prepare_frontend

CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
PATH_OPTIONS = {'database': '--db', 'ai_python': '--ai-python', 'models_root': '--models-root',
                'ai_profile': '--ai-profile', 'ai_settings': '--ai-settings',
                'ai_profiles_dir': '--ai-profiles-dir', 'tagger_profile': '--tagger-profile'}


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
    if not isinstance(settings, dict) or set(settings) - (set(PATH_OPTIONS) | {'viewer_settings', 'ui_theme', 'ai_ranking'}):
        raise ValueError('Unknown launch setting')
    for key in set(PATH_OPTIONS) | {'viewer_settings'}:
        if key in settings and (not isinstance(settings[key], str) or not Path(settings[key]).is_absolute() or any(ord(c) < 32 for c in settings[key])):
            raise ValueError('Launch paths must be absolute: ' + key)
    if settings.get('ui_theme', 'system') not in ('system', 'light', 'dark') or settings.get('ai_ranking', 'mean-rrf') not in ('max', 'mean-rrf'):
        raise ValueError('Invalid launch preference')
    return settings


def preflight(root, *, imports=True):
    manifest = verify_release(root)
    if manifest.get('python_bundled') is not True or manifest.get('media_tools_bundled') is not True:
        raise ValueError('The staged release needs bundled Python and FFmpeg/ffprobe')
    python_layout(root / 'runtime/python', manifest.get('ai_runtime_bundled') is True)
    media_layout(root / 'runtime/media')
    if imports:
        if os.name != 'nt':raise RuntimeError('Windows runtime checks require Windows')
        args = [str(root / 'runtime/python/python.exe'), '-B', str(root / 'tools/probe_release_runtime.py')]
        if manifest.get('ai_runtime_bundled') is True:args.append('--ai')
        result = subprocess.run(args, cwd=root, env=runtime_environment(), capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=90, creationflags=CREATE_NO_WINDOW)
        if result.returncode or json.loads(result.stdout).get('pass') is not True:
            raise RuntimeError('Bundled Python imports failed; check the prepared runtime')
        for name in ('ffmpeg.exe', 'ffprobe.exe'):
            result = subprocess.run([str(root / 'runtime/media' / name), '-version'], cwd=root,
                                    env=runtime_environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=10, creationflags=CREATE_NO_WINDOW)
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


def run_session(backend_command, app_command, *, port, instance, logs, cwd, env, startup_timeout=20, app_factory=None):
    """Launch only owned children, and never attach to another service on a port."""
    # This advisory check provides a clear error; the per-launch session ID is
    # the race-safe proof that the listening server is ours.
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1', port))
        except OSError as error:raise RuntimeError('Aredoko port is already in use') from error
    backend = app = None
    with (logs / 'backend.log').open('xb') as output, (logs / 'backend-error.log').open('xb') as errors, (logs / 'app.log').open('xb') as app_log:
        try:
            backend = subprocess.Popen(backend_command, stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                       cwd=cwd, env=env, creationflags=CREATE_NO_WINDOW, close_fds=True)
            deadline = time.monotonic() + startup_timeout
            while True:
                if backend.poll() is not None:raise RuntimeError('Backend exited during startup; see backend-error.log')
                try:
                    session = _session(port)
                except (OSError, ValueError):
                    session = None
                if isinstance(session, dict):
                    if session.get('mode') != 'production' or session.get('instance_id') != instance:
                        raise RuntimeError('The listening backend does not belong to this launch')
                    break
                if time.monotonic() >= deadline:raise RuntimeError('Backend startup timed out')
                time.sleep(0.1)
            app = (app_factory(app_command, app_log) if app_factory is not None else
                   subprocess.Popen(app_command, stdin=subprocess.DEVNULL, stdout=app_log, stderr=app_log,
                                    cwd=cwd, env=env, close_fds=True))
            while app.poll() is None:
                if backend.poll() is not None:raise AppSessionError('Backend stopped unexpectedly; see backend-error.log')
                time.sleep(0.1)
            if app.returncode:raise AppSessionError(f'Windows app exited with code {app.returncode}; see app.log')
        finally:
            try:
                try:_stop_owned(app)
                finally:
                    if app is not None and hasattr(app, 'close'):app.close()
            finally:_stop_owned(backend, graceful=True)
    if backend.returncode:raise AppSessionError('Backend did not exit cleanly; see backend-error.log')


def launch(root, data, settings):
    # All writable state stays outside the versioned release. Reject accidental
    # source/payload placement before creating logs or opening a database.
    paths = [data, *(Path(settings[k]) for k in ('database', 'ai_settings', 'viewer_settings') if k in settings)]
    if any(p.resolve().is_relative_to(root.resolve()) for p in paths):
        raise ValueError('User data must be outside the release directory')
    storage_parent(data / 'launcher')
    with storage_lease(data / 'launcher'):
        instance = secrets.token_hex(16)
        logs = data / 'logs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + instance)
        storage_parent(logs / 'launcher.log');plain_path(logs, directory=True)
        values = {'database': str(data / 'catalog.sqlite'), 'ai_python': str(root / 'runtime/python/python.exe'),
                  'models_root': str(data / 'models'), 'ai_settings': str(data / 'settings.json'),
                  'ai_profiles_dir': str(data / 'ai-profiles'), **settings}
        backend = [str(root / 'runtime/python/python.exe'), '-B', '-u', str(root / 'backend/app/production_server.py'),
                   '--instance-id', instance, '--exit-on-stdin-close', '--ai-ranking', values.get('ai_ranking', 'mean-rrf')]
        for key, option in PATH_OPTIONS.items():
            if key in values:backend += [option, values[key]]
        app = ['--ui-theme', values.get('ui_theme', 'system'),
               '--viewer-settings', values.get('viewer_settings', str(data / 'viewer-settings.json'))]
        try:
            manifest = preflight(root)
            frontend = prepare_frontend(root, manifest)
            run_session(backend, app, port=8769, instance=instance, logs=logs, cwd=root,
                        env=runtime_environment(root / 'runtime/media'), app_factory=frontend.start)
        except Exception as error:
            (logs / 'launcher.log').write_text(type(error).__name__ + ': ' + str(error) + '\n', encoding='utf-8')
            failure_type = AppSessionError if isinstance(error, AppSessionError) else RuntimeError
            raise failure_type(str(error) + '\nLogs: ' + str(logs)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--verify-only', action='store_true', help='Hash inventory only, on any OS; no child processes or writes')
    checks.add_argument('--check', action='store_true', help='Windows import/tool checks; no database, GUI, or model loading')
    checks.add_argument('--check-activation', action='store_true', help='Read-only installed MSIX identity/payload check, plus runtime checks; no activation')
    parser.add_argument('--no-error-dialog', action='store_true', help='Automation only: keep error logs and nonzero exit without a modal dialog')
    parser.add_argument('--settings', type=Path, help='Explicit launch-settings.json (otherwise in LOCALAPPDATA/Aredoko)')
    for key in set(PATH_OPTIONS) | {'viewer_settings', 'ui_theme', 'ai_ranking'}:
        parser.add_argument('--' + key.replace('_', '-'))
    args = parser.parse_args()
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
            settings.update({key: getattr(args, key) for key in set(PATH_OPTIONS) | {'viewer_settings', 'ui_theme', 'ai_ranking'} if getattr(args, key) is not None})
            launch(ROOT, data, validate_settings(settings))
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
