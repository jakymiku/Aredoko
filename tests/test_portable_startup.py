"""Portable receipt/ZIP and real owned-backend/ready-child checks; no WinUI/GPU."""
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import portable_frontend as portable
import prepare_portable as builder
import release_runtime as runtime
import test_release_staging as staging
import test_release_lifecycle as lifecycle
import startup_ipc as ipc
from startup_progress import StartupProgress, StartupCancelled


PROPERTIES = {'WindowsPackageType': 'None', 'SelfContained': 'true', 'WindowsAppSDKSelfContained': 'true',
              'Configuration': 'Portable', 'AredokoPackageChannel': 'Portable'}


def pe_fixture():
    # Structural PE fixture, not executable Windows machine code.
    data = bytearray(512);data[:2] = b'MZ';struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0';struct.pack_into('<H', data, 68, 0x8664)
    struct.pack_into('<H', data, 88, 0x20b);struct.pack_into('<H', data, 156, 2)
    struct.pack_into('<I', data, 312, 0x2000)
    return data


class PortableStagingTests(unittest.TestCase):
    setUp = staging.ReleaseStagingTests.setUp

    def source(self):
        frontend = self.base / 'Portable 日本語';frontend.mkdir()
        for name in portable.PAYLOAD:(frontend / name).write_bytes(b'generated frontend layout only')
        (frontend / 'Aredoko.WinUI.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {'includedFrameworks': [{'name': 'Microsoft.NETCore.App', 'version': '10.0.12'}]}}))
        (frontend / 'Aredoko.WinUI.deps.json').write_text(json.dumps({
            'runtimeTarget': {'name': 'test/win-x64'},
            'targets': {'test/win-x64': {'runtimepack': {'runtime': {'System.Console.dll': {}}}}}}))
        builder.receipt(frontend, PROPERTIES)
        bootstrap = self.base / 'bootstrap.exe';bootstrap.write_bytes(pe_fixture())
        return frontend, bootstrap

    def stage(self):
        frontend, bootstrap = self.source()
        python, media = staging.ReleaseStagingTests.runtime(self)
        return staging.release.package(self.output, skip_build=True, python_runtime=python, media_tools=media,
            portable_frontend=frontend, bootstrap=bootstrap)

    def test_explicit_portable_package_has_all_owned_entrypoints_and_readonly_zip(self):
        manifest = self.stage()
        self.assertEqual(manifest['frontend_activation'], 'portable')
        self.assertFalse(manifest['clean_machine_activation_verified'])
        expected = {'Aredoko.exe', 'Check-Startup.cmd', 'bin/portable-build.json', 'tools/portable_frontend.py'}
        self.assertTrue(expected <= {row['path'] for row in manifest['entries']})
        self.assertNotIn('Install-Shortcut.cmd', {row['path'] for row in manifest['entries']})
        self.assertIn('Aredoko.exe', (self.output / 'Aredoko.cmd').read_text())
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output.rglob('*') if p.is_file()}
        runtime.verify_release(self.output);portable.inspect_portable(self.output / 'bin')
        archive = self.base / 'new package.zip';builder.zip_release(self.output, archive)
        with zipfile.ZipFile(archive) as value:
            self.assertEqual(value.read('Aredoko/Aredoko.exe'), bytes(pe_fixture()))
            self.assertIn('Aredoko/Check-Startup.cmd', value.namelist())
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output.rglob('*') if p.is_file()})
        with self.assertRaises(FileExistsError):builder.zip_release(self.output, archive)

    def test_old_msix_or_unreceipted_frontend_is_rejected_before_output(self):
        frontend, bootstrap = self.source();python, media = staging.ReleaseStagingTests.runtime(self)
        (frontend / 'portable-build.json').unlink()
        with self.assertRaises(ValueError):builder.receipt(frontend, {**PROPERTIES, 'WindowsPackageType': 'MSIX'})
        with self.assertRaises(ValueError):builder.receipt(frontend, {**PROPERTIES, 'Configuration': 'Release'})
        with self.assertRaises(ValueError):builder.receipt(frontend, {**PROPERTIES, 'SelfContained': 'false'})
        with self.assertRaises(ValueError):portable.inspect_bootstrap(self.binary / 'Aredoko.WinUI.exe')
        with self.assertRaises(ValueError):
            staging.release.package(self.output, skip_build=True, python_runtime=python, media_tools=media,
                portable_frontend=frontend)
        self.assertFalse(self.output.exists())

    def test_changed_unknown_and_framework_dependent_payloads_are_rejected(self):
        frontend, _ = self.source()
        original = (frontend / 'Aredoko.WinUI.exe').read_bytes()
        (frontend / 'Aredoko.WinUI.exe').write_bytes(b'changed')
        with self.assertRaises(ValueError):portable.inspect_portable(frontend)
        (frontend / 'Aredoko.WinUI.exe').write_bytes(original)
        unknown = frontend / 'extra.dll';unknown.write_bytes(b'unknown')
        with self.assertRaises(ValueError):portable.inspect_portable(frontend)
        unknown.unlink();(frontend / 'portable-build.json').unlink()
        config = frontend / 'Aredoko.WinUI.runtimeconfig.json'
        config.write_text(json.dumps({'runtimeOptions': {'framework': {'name': 'Microsoft.NETCore.App'}}}))
        with self.assertRaises(ValueError):builder.receipt(frontend, PROPERTIES)

    def test_present_console_file_without_runtime_graph_entry_is_rejected(self):
        frontend, _ = self.source()
        (frontend / 'portable-build.json').unlink()
        (frontend / 'Aredoko.WinUI.deps.json').write_text(json.dumps({
            'runtimeTarget': {'name': 'test/win-x64'},
            'targets': {'test/win-x64': {'runtimepack': {'runtime': {}}}}}))
        self.assertTrue((frontend / 'System.Console.dll').is_file())
        with self.assertRaisesRegex(ValueError, 'Console dependency'):
            builder.receipt(frontend, PROPERTIES)

    def test_missing_bootstrap_cannot_be_hidden_by_rewriting_manifest(self):
        self.stage();target = self.output / 'Aredoko.exe';target.unlink()
        path = self.output / 'manifest.json';data = json.loads(path.read_text())
        data['entries'] = [row for row in data['entries'] if row['path'] != 'Aredoko.exe']
        data['files_count'] = len(data['entries']);data['total_bytes'] = sum(row['bytes'] for row in data['entries'])
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'portable'):runtime.verify_release(self.output)

    def test_inbox_compiler_allows_servicing_hardlink_but_payload_guard_does_not(self):
        from storage_lease import plain_path
        import os
        compiler=self.base/'Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        compiler.parent.mkdir(parents=True);compiler.write_bytes(b'generated build tool')
        sibling=compiler.with_name('servicing-link.exe');os.link(compiler,sibling)
        self.assertEqual(compiler.stat().st_nlink,2)
        with patch.object(builder,'windows_directory',return_value=self.base/'Windows'):
            self.assertEqual(builder.system_compiler(),compiler)
        with self.assertRaisesRegex(ValueError,'Hardlinked'):plain_path(compiler)

    def test_inbox_compiler_reparse_and_nonfile_are_rejected(self):
        from types import SimpleNamespace
        import stat
        compiler=self.base/'Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        compiler.parent.mkdir(parents=True);compiler.write_bytes(b'generated build tool')
        original=Path.lstat
        for mode,attrs in ((stat.S_IFREG|0o600,0x400),(stat.S_IFDIR|0o700,0)):
            def info(path):
                if path==compiler:return SimpleNamespace(st_mode=mode,st_file_attributes=attrs,st_nlink=1)
                return original(path)
            with patch.object(builder,'windows_directory',return_value=self.base/'Windows'),patch.object(Path,'lstat',info):
                with self.assertRaisesRegex(ValueError,'ordinary Windows-inbox'):builder.system_compiler()

    def test_csc_bootstrap_structure_rejects_script_x86_and_console(self):
        target = self.base / 'bootstrap.exe'
        target.write_bytes(pe_fixture());portable.inspect_bootstrap(target)
        for offset, value in ((68, 0x14c), (156, 3), (88, 0x10b)):
            data = pe_fixture();struct.pack_into('<H', data, offset, value);target.write_bytes(data)
            with self.assertRaises(ValueError):portable.inspect_bootstrap(target)


class ReadyLifecycleTests(unittest.TestCase):
    setUp = lifecycle.ReleaseLifecycleTests.setUp
    backend = lifecycle.ReleaseLifecycleTests.backend
    assert_released = lifecycle.ReleaseLifecycleTests.assert_released

    def ready_factory(self, *, status='ready', nonce='n', wait=True, before=None, instance=None):
        def start(args, log):
            if before:before()
            event = {'format': portable.READY_FORMAT, 'nonce': nonce, 'instance_id': self.instance if instance is None else instance, 'status': status}
            code = 'import sys,time;print(sys.argv[1],flush=True);time.sleep(float(sys.argv[2]))'
            child = subprocess.Popen([sys.executable, '-B', '-c', code, json.dumps(event), '0.3' if wait else '0'],
                stdout=subprocess.PIPE, stderr=log, bufsize=0)
            return portable.ReadyProcess(child, 'n', self.instance, log)
        return start

    def start_session(self, **kwargs):
        return lifecycle.run_session(self.backend(), [], port=self.port, instance=self.instance, logs=self.logs,
            cwd=self.base, env=self.env, require_ready=True, frontend_timeout=1, **kwargs)

    def test_ready_requires_matching_live_frontend_and_backend(self):
        events = [];control = StartupProgress(events.append);ready = []
        self.start_session(app_factory=self.ready_factory(), progress=control, on_ready=lambda: ready.append(True))
        self.assertEqual(ready, [True]);self.assert_released()
        self.assertEqual([e['stage'] for e in events if e['state'] == 'complete'], ['backend_start', 'frontend_start'])

    def test_wrong_nonce_and_initial_load_failure_never_signal_ready(self):
        for number, options in enumerate(({'nonce': 'wrong'}, {'status': 'failed'}, {'instance': 'b'*32})):
            self.logs = self.base / ('failure-' + str(number));self.logs.mkdir();ready = []
            with self.assertRaises(RuntimeError):self.start_session(app_factory=self.ready_factory(**options), on_ready=lambda: ready.append(True))
            self.assertEqual(ready, []);self.assert_released()

    def test_cancel_before_backend_creates_neither_child_nor_database(self):
        control = StartupProgress();control.cancel()
        with patch('launch_release.subprocess.Popen') as child, self.assertRaises(StartupCancelled):
            self.start_session(app_factory=self.ready_factory(), progress=control)
        child.assert_not_called();self.assertFalse(self.db.exists())

    def test_cancel_while_waiting_for_frontend_cleans_only_owned_children(self):
        control = StartupProgress();ready = []
        def start(args, log):
            child = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(20)'],
                stdout=subprocess.PIPE, stderr=log, bufsize=0)
            timer = threading.Timer(0.1, control.cancel);timer.start();self.addCleanup(timer.cancel)
            return portable.ReadyProcess(child, 'n', self.instance, log)
        with self.assertRaises(StartupCancelled):self.start_session(app_factory=start, progress=control, on_ready=lambda: ready.append(True))
        self.assertEqual(ready, []);self.assert_released()

    def test_frontend_timeout_is_not_ready_and_releases_database(self):
        def start(args, log):
            child = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(20)'],
                stdout=subprocess.PIPE, stderr=log, bufsize=0)
            return portable.ReadyProcess(child, 'n', self.instance, log)
        with self.assertRaisesRegex(RuntimeError, 'timed out'):self.start_session(app_factory=start)
        self.assert_released()

    def test_post_ready_cancel_does_not_force_close_interactive_app(self):
        control = StartupProgress();ready = []
        def notified():ready.append(True);control.cancel()
        self.start_session(app_factory=self.ready_factory(), progress=control, on_ready=notified)
        self.assertEqual(ready, [True]);self.assert_released()

    def test_duplicate_ready_fields_are_rejected_even_before_a_valid_frame(self):
        def start(args, log):
            malformed = '{"format":"aredoko-frontend-ready-v1","nonce":"n","nonce":"n","instance_id":"'+self.instance+'","status":"ready"}'
            valid = json.dumps({'format': portable.READY_FORMAT, 'nonce': 'n', 'instance_id': self.instance, 'status': 'ready'})
            child = subprocess.Popen([sys.executable, '-B', '-c',
                'import sys,time;print(sys.argv[1],flush=True);time.sleep(.1);print(sys.argv[2],flush=True);time.sleep(3)', malformed, valid],
                stdout=subprocess.PIPE, stderr=log, bufsize=0)
            return portable.ReadyProcess(child, 'n', self.instance, log)
        ready = []
        with self.assertRaises(RuntimeError):self.start_session(app_factory=start, on_ready=lambda: ready.append(True))
        self.assertEqual(ready, []);self.assert_released()


class OwnedWorkerTests(unittest.TestCase):
    def test_smoke_data_never_loads_existing_settings_or_real_library(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            called = []
            def launch(root, data, settings, *, progress, startup_pipe):
                called.append((data, settings));startup_pipe.mark_ready()
            class Incoming:
                def __init__(self):self.first = True;self.closed = threading.Event()
                def readline(self, limit):
                    if self.first:
                        self.first = False
                        return (json.dumps({'format': ipc.FORMAT, 'command': 'hello', 'session_id': 'a'*32})+'\n').encode()
                    self.closed.wait(2);return b''
            incoming = Incoming();out = io.BytesIO()
            with patch.dict(os.environ, {'LOCALAPPDATA': temp}), patch('launch_release.launch', launch), patch('launch_release.load_settings') as settings:
                self.assertEqual(ipc.serve_owned(Path(temp), incoming, out, smoke=True), 0)
                settings.assert_not_called()
            incoming.closed.set()
            self.assertEqual(called, [(Path(temp)/'Aredoko/startup-check'/('a'*32), {})])
            events = [json.loads(line) for line in out.getvalue().splitlines()]
            self.assertEqual([e['kind'] for e in events], ['hello', 'app_ready', 'result'])
            self.assertEqual(events[-1]['status'], 'session_complete')


if __name__ == '__main__':unittest.main()
