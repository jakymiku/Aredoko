"""Inherited-pipe protocol, actual guards and generated-only child processes."""
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import launch_release as launch
import release_runtime as runtime
import startup_ipc as ipc
import test_release_parallel as fixtures
import test_release_staging as staging
from startup_progress import StartupCancelled

SESSION = 'a' * 32


def command(name='hello', session=SESSION):
    return (json.dumps({'format': ipc.FORMAT, 'command': name, 'session_id': session}) + '\n').encode()


class StartupPipeTests(unittest.TestCase):
    setUp = fixtures.ParallelReleaseTests.setUp

    def streams(self, frames=None):
        read_fd, write_fd = os.pipe()
        incoming = os.fdopen(read_fd, 'rb', buffering=0)
        parent = os.fdopen(write_fd, 'wb', buffering=0)
        self.addCleanup(incoming.close)
        self.addCleanup(parent.close)
        initial = command() if frames is None else frames
        if len(initial) > ipc.MAX_FRAME:
            # Windows os.pipe() has a 4KiB buffer: the deliberately oversized
            # invalid frame must be fed while the protocol reader is running.
            sent = []
            producer = threading.Thread(target=lambda: sent.append(parent.write(initial)), daemon=True)
            producer.start()
            def joined():
                producer.join(2)
                self.assertFalse(producer.is_alive())
                self.assertEqual(sent, [len(initial)])
            self.addCleanup(joined)
        else:
            parent.write(initial)
        return incoming, parent, io.BytesIO()

    def prepared(self):
        # These bytes validate layout only. They are never executed as Windows binaries.
        names = ['runtime/python/' + name for name in ('python.exe', 'pythonw.exe', 'python311.dll',
                 'python311.zip', 'LICENSE.txt', 'Lib/site-packages/PIL/__init__.py')]
        names += ['runtime/media/' + name for name in ('ffmpeg.exe', 'ffprobe.exe', 'LICENSE.txt')]
        for name in names:
            path = self.root / name;path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'generated layout only')
        self.manifest.update(python_bundled=True, media_tools_bundled=True)
        self.manifest['entries'] += [{'path': name, 'bytes': (self.root / name).stat().st_size,
            'sha256': hashlib.sha256((self.root / name).read_bytes()).hexdigest()} for name in names]
        self.manifest.update(files_count=len(self.manifest['entries']),
            total_bytes=sum(row['bytes'] for row in self.manifest['entries']))
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        (self.root / 'sha256sums.txt').write_text(''.join(f"{row['sha256']}  {row['path']}\n" for row in self.manifest['entries']))

    def events(self, output):
        frames = output.getvalue().splitlines(keepends=True)
        self.assertTrue(all(len(frame) <= ipc.MAX_FRAME and frame.endswith(b'\n') for frame in frames))
        return [json.loads(frame) for frame in frames]

    def test_real_guard_counts_and_payload_unchanged_over_pipe(self):
        self.prepared()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        guarded = runtime.plain_path;hashed = runtime.digest
        paths = Counter();hashes = Counter();lock = threading.Lock()
        def guard(path, **kwargs):
            with lock:paths[(str(path), kwargs.get('directory', False))] += 1
            return guarded(path, **kwargs)
        def digest(path, **kwargs):
            with lock:hashes[path] += 1
            return hashed(path, **kwargs)
        incoming, parent, output = self.streams()
        with patch.object(runtime, 'plain_path', guard), patch.object(runtime, 'digest', digest):
            launch.preflight(self.root, imports=False)
            expected = paths.copy();paths.clear();hashes.clear()
            self.assertEqual(ipc.serve_preflight(self.root, incoming, output, imports=False), 0)
        self.assertEqual(paths, expected)
        self.assertEqual(hashes, Counter({self.root / row['path']: 1 for row in self.manifest['entries']}))
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})
        events = self.events(output)
        self.assertEqual(events[0]['kind'], 'hello')
        self.assertEqual(events[-1]['status'], 'preflight_complete')
        stages = [e['progress'] for e in events if e['kind'] == 'progress']
        self.assertEqual([e['stage'] for e in stages if e['state'] == 'complete'],
                         ['manifest', 'file_hashes', 'inventory', 'runtime_layout'])
        completed = [e for e in stages if e['stage'] == 'file_hashes' and e['state'] == 'complete'][0]
        self.assertEqual(completed['completed_files'], len(self.manifest['entries']))
        self.assertEqual(completed['completed_bytes'], self.manifest['total_bytes'])
        self.assertTrue(all(e['session_id'] == SESSION for e in events))
        for private in (str(self.root), 'Aredoko.WinUI.exe', 'ready', 'percent', 'ETA'):
            self.assertNotIn(private, output.getvalue().decode())

    def test_invalid_handshakes_never_start_verification(self):
        invalid = [b'{}\n', b'[]\n', b'not json\n', command('cancel'), command(session='wrong'),
                   command().replace(b'"command": "hello"', b'"command":"hello","command":"hello"'),
                   command().replace(b'"hello"', b'"hello", "extra":"private"'),
                   command().replace(b'"hello"', b'true'), b'x' * ipc.MAX_FRAME + b'\n', b'\xff\n']
        for frame in invalid:
            with self.subTest(frame=frame[:60]):
                incoming, parent, output = self.streams(frame)
                with patch.object(launch, 'preflight') as verify:
                    self.assertEqual(ipc.serve_preflight(self.root, incoming, output, hello_timeout=0.2), 2)
                verify.assert_not_called();self.assertEqual(output.getvalue(), b'')

    def test_owner_eof_and_truncated_frame_before_hello_do_no_work(self):
        for frame in (b'', command()[:-1]):
            incoming, parent, output = self.streams(frame);parent.close()
            with patch.object(launch, 'preflight') as verify:
                self.assertEqual(ipc.serve_preflight(self.root, incoming, output), 2)
            verify.assert_not_called()

    def test_hello_deadline_does_not_start_verification(self):
        incoming, parent, output = self.streams(b'')
        with patch.object(launch, 'preflight') as verify:
            self.assertEqual(ipc.serve_preflight(self.root, incoming, output, hello_timeout=0.02), 2)
        verify.assert_not_called()

    def test_cancel_or_eof_during_probe_reaps_only_owned_process(self):
        for close_owner in (False, True):
            with self.subTest(close_owner=close_owner):
                incoming, parent, output = self.streams()
                other = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(30)'])
                children = [];original = subprocess.Popen;started = threading.Event();result = []
                def spawn(*args, **kwargs):
                    child = original(*args, **kwargs);children.append(child);started.set();return child
                def verify(root, *, progress, **kwargs):
                    with progress.phase('python_imports'):
                        launch._runtime_check([sys.executable, '-B', '-c', 'import time;time.sleep(30)'],
                            root=root, timeout=10, progress=progress, capture=True)
                def run():result.append(ipc.serve_preflight(self.root, incoming, output))
                worker = threading.Thread(target=run)
                try:
                    with patch.object(launch, 'preflight', verify), patch.object(launch.subprocess, 'Popen', spawn):
                        worker.start();self.assertTrue(started.wait(3))
                        if close_owner:parent.close()
                        else:parent.write(command('cancel'))
                        worker.join(5)
                    self.assertFalse(worker.is_alive());self.assertEqual(result, [2])
                    self.assertEqual(self.events(output)[-1]['status'], 'cancelled')
                    self.assertIsNotNone(children[0].poll());self.assertIsNone(other.poll())
                    self.assertTrue(children[0].stdout.closed);self.assertTrue(children[0].stderr.closed)
                finally:
                    parent.close();worker.join(5)
                    for child in children + [other]:
                        if child.poll() is None:child.kill()
                        child.wait(5)

    def test_duplicate_hello_wrong_session_and_unknown_command_cancel_work(self):
        for frame in (command(), command('cancel', 'b' * 32), command('run')):
            incoming, parent, output = self.streams()
            pipe = ipc.StartupPipe(incoming, output);pipe.start()
            parent.write(frame)
            deadline = time.monotonic() + 2
            while pipe.reason is None and time.monotonic() < deadline:time.sleep(0.005)
            with self.assertRaises(StartupCancelled):pipe.control.check_cancelled()
            self.assertEqual(pipe.finish('preflight_complete'), 2)
            self.assertEqual(self.events(output)[-1]['reason'], 'protocol_error')

    def test_slow_output_is_bounded_and_never_blocks_progress_producer(self):
        gate = threading.Event();entered = threading.Event()
        class SlowOutput(io.BytesIO):
            def write(self, data):entered.set();gate.wait(3);return super().write(data)
        incoming, parent, _ = self.streams();output = SlowOutput()
        pipe = ipc.StartupPipe(incoming, output)
        try:
            pipe.start();self.assertTrue(entered.wait(2))
            with self.assertRaises(StartupCancelled):
                for _ in range(ipc.MAX_PENDING + 1):
                    with pipe.control.phase('manifest'):pass
            self.assertEqual(pipe.reason, 'output_backpressure')
            self.assertLessEqual(pipe._pending.qsize(), ipc.MAX_PENDING)
            self.assertEqual(pipe.finish('preflight_complete', timeout=0.01), 2)
        finally:gate.set()

    def test_partial_writes_are_completed_before_terminal_receipt(self):
        class PartialOutput(io.BytesIO):
            def write(self, data):return super().write(data[:3])
        incoming, parent, _ = self.streams();output = PartialOutput()
        with patch.object(launch, 'preflight', return_value={}):
            self.assertEqual(ipc.serve_preflight(self.root, incoming, output), 0)
        self.assertEqual([e['kind'] for e in self.events(output)], ['hello', 'result'])

    def test_writer_waits_for_terminal_enqueue_after_result_is_sealed(self):
        incoming, parent, output = self.streams();pipe = ipc.StartupPipe(incoming, output)
        pipe.start();original = pipe._send
        def delayed_send(value, receipt=None):
            # Cross at least one empty-queue poll after finish seals input.
            if value['kind'] == 'result':time.sleep(0.15)
            return original(value, receipt)
        with patch.object(pipe, '_send', delayed_send):
            self.assertEqual(pipe.finish('preflight_complete'), 0)
        self.assertEqual(self.events(output)[-1]['status'], 'preflight_complete')

    def test_closed_or_stalled_output_never_returns_success(self):
        for invalid_write in (None, 0):
            class BadOutput:
                def write(self, data):return invalid_write
                def flush(self):pass
            incoming, parent, _ = self.streams()
            with patch.object(launch, 'preflight', return_value={}):
                self.assertEqual(ipc.serve_preflight(self.root, incoming, BadOutput(), drain_timeout=0.02), 2)

    def test_failed_verification_hides_private_exception_details(self):
        incoming, parent, output = self.streams()
        with patch.object(launch, 'preflight', side_effect=ValueError('private path and token')):
            self.assertEqual(ipc.serve_preflight(self.root, incoming, output), 2)
        self.assertEqual(self.events(output)[-1]['reason'], 'verification_failed')
        self.assertNotIn(b'private', output.getvalue());self.assertNotIn(b'token', output.getvalue())

    def test_corrupt_payload_cannot_report_preflight_complete(self):
        (self.root / 'bin/Aredoko.WinUI.exe').write_bytes(b'changed')
        incoming, parent, output = self.streams()
        self.assertEqual(ipc.serve_preflight(self.root, incoming, output, imports=False), 2)
        self.assertEqual(self.events(output)[-1]['status'], 'failed')
        self.assertNotIn(b'preflight_complete', output.getvalue())

    def test_progress_schema_rejects_paths_invalid_counts_and_forged_states(self):
        incoming, parent, output = self.streams();pipe = ipc.StartupPipe(incoming, output)
        pipe.start()
        try:
            with pipe.control.phase('manifest'):snapshot = pipe.control.snapshot
            for changes in ({'path': 'private'}, {'stage': 'app_ready'}, {'state': 'ready'},
                            {'completed_files': True}, {'completed_bytes': -1}, {'total_files': -1},
                            {'completed_bytes': 2**63}, {'sequence': False}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):pipe.publish({**snapshot, **changes})
        finally:pipe.finish('failed')

    def test_real_worker_process_streams_without_gui_or_payload_writes(self):
        self.prepared()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        # Existing host Python, layout-only generated payload. No Windows ABI claim.
        script = ('import os,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                  'from startup_ipc import serve_preflight;'
                  'raise SystemExit(serve_preflight(Path(sys.argv[2]),'
                  'os.fdopen(os.dup(0),"rb",buffering=0),os.fdopen(os.dup(1),"wb",buffering=0),imports=False))')
        child = subprocess.Popen([sys.executable, '-B', '-c', script, str(ROOT / 'tools'), str(self.root)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            child.stdin.write(command());child.stdin.flush()
            events = []
            # A watchdog bounds a regression that would otherwise block readline.
            watchdog = threading.Timer(8, child.kill);watchdog.start()
            try:
                while True:
                    line = child.stdout.readline();self.assertTrue(line, 'Worker ended before terminal result')
                    event = json.loads(line);events.append(event)
                    if event['kind'] == 'result':break
                self.assertEqual(child.wait(3), 0)
            finally:watchdog.cancel()
            self.assertEqual(events[-1]['status'], 'preflight_complete')
            self.assertEqual(child.stderr.read(), b'')
        finally:
            if child.poll() is None:child.kill();child.wait(3)
            for stream in (child.stdin, child.stdout, child.stderr):stream.close()
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()})

    def test_real_worker_exits_when_owner_never_reads_output(self):
        # A raw inherited output pipe can block inside write. It must never
        # keep the worker alive at interpreter shutdown after queue overflow.
        script = '''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import launch_release
from startup_ipc import serve_preflight
def generated_check(root, *, progress, **kwargs):
    for _ in range(10000):
        with progress.phase('manifest'):pass
launch_release.preflight=generated_check
raise SystemExit(serve_preflight(Path(sys.argv[2]),os.fdopen(os.dup(0),'rb',buffering=0),os.fdopen(os.dup(1),'wb',buffering=0),drain_timeout=0.05))
'''
        child = subprocess.Popen([sys.executable, '-B', '-c', script, str(ROOT / 'tools'), str(self.root)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            child.stdin.write(command());child.stdin.flush()
            self.assertEqual(child.wait(5), 2)
            self.assertEqual(child.stderr.read(), b'')
        finally:
            if child.poll() is None:child.kill();child.wait(3)
            for stream in (child.stdin, child.stdout, child.stderr):stream.close()

    def test_internal_cli_rejects_nonpipe_and_settings_without_creating_files(self):
        script = str(ROOT / 'tools/launch_release.py')
        with (self.root / 'generated-output').open('wb') as output:
            result = subprocess.run([sys.executable, '-B', script, '--startup-preflight'],
                input=command(), stdout=output, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 2);self.assertEqual(result.stderr, b'')
        self.assertEqual((self.root / 'generated-output').read_bytes(), b'')
        missing = self.root / 'must-not-be-created.json'
        result = subprocess.run([sys.executable, '-B', script, '--startup-preflight', '--settings', str(missing)],
            input=command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 2);self.assertEqual(result.stdout, b'')
        self.assertFalse(missing.exists())


class PackagedStartupPipeTests(unittest.TestCase):
    setUp = staging.ReleaseStagingTests.setUp

    def test_packaged_cli_is_framed_nonlaunching_and_unchanged(self):
        staging.release.package(self.output, skip_build=True)
        child = subprocess.Popen([sys.executable, '-B', str(self.output / 'tools/launch_release.py'), '--startup-preflight'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.base)
        try:
            child.stdin.write(command());child.stdin.flush()
            watchdog = threading.Timer(8, child.kill);watchdog.start()
            try:
                events = []
                while True:
                    line = child.stdout.readline();self.assertTrue(line)
                    event = json.loads(line);events.append(event)
                    if event['kind'] == 'result':break
                self.assertEqual(child.wait(3), 2)
            finally:watchdog.cancel()
            # Fixture deliberately has no bundled runtime. Its failure is truthful.
            self.assertEqual(events[-1]['status'], 'failed')
            self.assertEqual(child.stderr.read(), b'')
            self.assertNotIn('ready', json.dumps(events))
        finally:
            if child.poll() is None:child.kill();child.wait(3)
            for stream in (child.stdin, child.stdout, child.stderr):stream.close()
        runtime.verify_release(self.output)


if __name__ == '__main__':unittest.main()
