"""Inherited-pipe startup worker, with explicit portable session ownership.

The preflight-only entry never launches an app. The owned entry keeps the same
worker through guarded launch, initial-screen readiness and normal shutdown.
"""
import json
import queue
import re
import threading

from startup_progress import StartupCancelled, StartupProgress

FORMAT = 'aredoko-startup-pipe-v1'
MAX_FRAME = 4096
MAX_PENDING = 32
STAGES = {'manifest', 'file_hashes', 'inventory', 'runtime_layout', 'python_imports', 'media_probe', 'backend_start', 'frontend_start'}
PROGRESS_KEYS = {'format', 'sequence', 'stage', 'state', 'completed_files',
                 'total_files', 'completed_bytes', 'total_bytes'}


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:raise ValueError('Duplicate field')
        value[key] = item
    return value


class StartupPipe:
    """Bounded, fail-closed transport; callbacks never perform pipe I/O.

    Streams are caller-owned binary streams. Reader/writer are daemon threads:
    an unresponsive owner cannot hold worker shutdown open on blocking I/O.
    One object belongs to one startup/session; never reuse it for another launch.
    """
    def __init__(self, incoming, outgoing):
        self.control = StartupProgress(self.publish)
        self._incoming, self._outgoing = incoming, outgoing
        self._pending = queue.Queue(MAX_PENDING)
        self._hello = threading.Event()
        self._stop_writer = threading.Event()
        self._lock = threading.Lock()
        self._session = None
        self._reason = None
        self._done = False
        self._interactive = False

    @property
    def reason(self):
        with self._lock:return self._reason

    def _abort(self, reason):
        with self._lock:
            if self._done or self._interactive:return
            if self._reason is None:self._reason = reason
            self.control.cancel()
        self._hello.set()

    def _send(self, value, receipt=None):
        message = {'format': FORMAT, 'session_id': self._session, **value}
        frame = (json.dumps(message, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')
        if len(frame) > MAX_FRAME:raise ValueError('Startup frame exceeds limit')
        try:self._pending.put_nowait((frame, receipt))
        except queue.Full:
            self._abort('output_backpressure')
            raise StartupCancelled('Startup transport is unavailable') from None

    def _read(self):
        try:
            while True:
                frame = self._incoming.readline(MAX_FRAME + 1)
                if not frame:
                    self._abort('owner_eof');return
                if len(frame) > MAX_FRAME or not frame.endswith(b'\n'):raise ValueError('Invalid frame')
                message = json.loads(frame.decode('utf-8'), object_pairs_hook=_object)
                if (not isinstance(message, dict) or set(message) != {'format', 'command', 'session_id'}
                        or message['format'] != FORMAT or not isinstance(message['session_id'], str)
                        or re.fullmatch('[0-9a-f]{32}', message['session_id']) is None):
                    raise ValueError('Invalid control message')
                with self._lock:
                    if self._done:return
                    first = self._session is None
                    if first:
                        if message['command'] != 'hello':raise ValueError('Handshake required')
                        self._session = message['session_id']
                    elif message['session_id'] != self._session or message['command'] != 'cancel':
                        raise ValueError('Invalid control command')
                if first:
                    self._send({'kind': 'hello'})
                    self._hello.set()
                else:
                    self._abort('cancel_requested');return
        except Exception:
            self._abort('protocol_error')

    def _write(self):
        try:
            while True:
                try:frame, receipt = self._pending.get(timeout=0.1)
                except queue.Empty:
                    if self._stop_writer.is_set():return
                    continue
                view = memoryview(frame)
                while view:
                    count = self._outgoing.write(view)
                    if type(count) is not int or not 0 < count <= len(view):raise OSError('Pipe write failed')
                    view = view[count:]
                self._outgoing.flush()
                if receipt is not None:
                    receipt.set();return
        except Exception:
            self._abort('output_closed')

    def start(self, timeout=5):
        threading.Thread(target=self._write, name='startup-pipe-writer', daemon=True).start()
        threading.Thread(target=self._read, name='startup-pipe-reader', daemon=True).start()
        if not self._hello.wait(timeout):self._abort('hello_timeout')
        self.control.check_cancelled()

    def publish(self, snapshot):
        # Reconstruct the public schema rather than forwarding arbitrary fields.
        if (not isinstance(snapshot, dict) or set(snapshot) != PROGRESS_KEYS
                or snapshot['format'] != 'aredoko-startup-progress-v1'
                or snapshot['stage'] not in STAGES
                or snapshot['state'] not in {'running', 'complete', 'failed', 'cancelled'}):
            raise ValueError('Invalid progress snapshot')
        if type(snapshot['sequence']) is not int or snapshot['sequence'] < 1:
            raise ValueError('Invalid progress sequence')
        for unit in ('files', 'bytes'):
            completed, total = snapshot['completed_' + unit], snapshot['total_' + unit]
            if (type(completed) is not int or completed < 0 or completed > 2**63 - 1
                    or (total is not None and (type(total) is not int or not completed <= total <= 2**63 - 1))):
                raise ValueError('Invalid progress count')
        with self._lock:
            if self._done or self._interactive:return
        self._send({'kind': 'progress', 'progress': dict(snapshot)})

    def finish(self, status, *, timeout=2):
        if status not in {'preflight_complete', 'session_complete', 'failed', 'cancelled'}:
            raise ValueError('Invalid preflight result')
        with self._lock:
            reason = self._reason
            self._done = True
        if self._session is None:
            self._stop_writer.set();return 2
        if reason is not None:
            status = 'cancelled' if reason in {'cancel_requested', 'owner_eof'} else 'failed'
        elif status == 'failed':reason = 'session_failed' if self._interactive else 'verification_failed'
        receipt = threading.Event()
        try:
            self._send({'kind': 'result', 'status': status, 'reason': reason}, receipt)
            # Verification success is not success if its result cannot reach the UI.
            if not receipt.wait(timeout):return 2
            return 0 if status in {'preflight_complete', 'session_complete'} else 2
        except StartupCancelled:return 2
        finally:self._stop_writer.set()

    def mark_ready(self):
        # After the live frontend has acknowledged initial data and its first
        # rendering callback, owner loss must not discard interactive drafts.
        with self._lock:
            self.control.check_cancelled()
            self._interactive = True
        try:self._send({'kind': 'app_ready'})
        except StartupCancelled:pass


def serve_owned(root, incoming, outgoing, *, smoke=False):
    """Same verified worker owns the backend and frontend until normal exit."""
    import os
    from pathlib import Path
    from launch_release import launch, load_settings
    pipe = StartupPipe(incoming, outgoing)
    status = 'failed'
    try:
        pipe.start()
        base = os.environ.get('LOCALAPPDATA', '')
        if not base or not Path(base).is_absolute():raise ValueError('User data is unavailable')
        data = Path(base) / 'Aredoko'
        if smoke:
            data = data / 'startup-check' / pipe._session
            settings = {}  # Never inherit real DB, model or viewer paths.
        else:settings = load_settings(data)
        launch(root, data, settings, progress=pipe.control, startup_pipe=pipe)
        status = 'session_complete'
    except StartupCancelled:status = 'cancelled'
    except Exception as error:
        from launch_release import report_failure
        report_failure(error, show_dialog=False)  # Owned stderr log, never protocol stdout.
        status = 'failed'
    return pipe.finish(status)


def serve_preflight(root, incoming, outgoing, *, imports=True, hello_timeout=5, drain_timeout=2):
    """Run existing guards once. Return only preflight status, never app readiness."""
    from launch_release import preflight
    pipe = StartupPipe(incoming, outgoing)
    status = 'failed'
    try:
        pipe.start(hello_timeout)
        preflight(root, imports=imports, progress=pipe.control)
        pipe.control.check_cancelled()
        status = 'preflight_complete'
    except StartupCancelled:
        status = 'cancelled'
    except Exception:
        # Never transmit exception text, paths, tokens or source contents.
        status = 'failed'
    return pipe.finish(status, timeout=drain_timeout)
