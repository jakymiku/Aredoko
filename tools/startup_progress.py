"""Cooperative startup control, independent of any GUI/runtime dependency.

Events describe one actual stage, never total startup percent or app readiness.
The caller owns the sink; no file/pipe/UI is opened by this module.
"""
from contextlib import contextmanager
import threading
import time


class StartupCancelled(RuntimeError):
    pass


class StartupProgress:
    def __init__(self, sink=None, *, interval=0.1, clock=time.monotonic):
        self._sink = sink
        self._clock = clock
        self._interval = max(0.1, interval)
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._value = None
        self._sequence = 0
        self._last_emit = float('-inf')

    def cancel(self):
        self._cancel.set()

    def check_cancelled(self):
        if self._cancel.is_set():
            raise StartupCancelled('Startup cancelled')

    @property
    def snapshot(self):
        with self._lock:
            return dict(self._value) if self._value is not None else None

    def _publish(self, *, force=False):
        now = self._clock()
        if force or now - self._last_emit >= self._interval:
            self._last_emit = now
            if self._sink is not None:
                self._sink(self.snapshot)

    @contextmanager
    def phase(self, stage, *, files=None, bytes=None):
        self.check_cancelled()
        if stage not in {'manifest', 'file_hashes', 'inventory', 'runtime_layout', 'python_imports', 'media_probe', 'backend_start', 'frontend_start'}:
            raise ValueError('Unknown startup stage')
        for total in (files, bytes):
            if total is not None and (type(total) is not int or total < 0):
                raise ValueError('Invalid startup total')
        self._sequence += 1
        with self._lock:
            self._value = {'format': 'aredoko-startup-progress-v1', 'sequence': self._sequence,
                           'stage': stage, 'state': 'running', 'completed_files': 0,
                           'total_files': files, 'completed_bytes': 0, 'total_bytes': bytes}
        try:
            self._publish(force=True)
            yield self
            self.check_cancelled()
            for name in ('files', 'bytes'):
                if self._value['total_' + name] is not None and self._value['completed_' + name] != self._value['total_' + name]:
                    raise ValueError('Startup stage is incomplete')
        except Exception as error:
            with self._lock:
                self._value['state'] = 'cancelled' if isinstance(error, StartupCancelled) else 'failed'
            # Keep the original failure if a disconnected UI sink also fails.
            try:self._publish(force=True)
            except Exception:pass
            raise
        else:
            with self._lock:
                self._value['state'] = 'complete'
            self._publish(force=True)

    def advance(self, *, files=0, bytes=0):
        self.check_cancelled()
        if any(type(value) is not int or value < 0 for value in (files, bytes)):
            raise ValueError('Invalid startup increment')
        with self._lock:
            if self._value is None or self._value['state'] != 'running':
                raise ValueError('No active startup stage')
            for name, amount in (('files', files), ('bytes', bytes)):
                completed = self._value['completed_' + name] + amount
                total = self._value['total_' + name]
                if total is not None and completed > total:
                    raise ValueError('Startup progress exceeds total')
            self._value['completed_files'] += files
            self._value['completed_bytes'] += bytes
        self._publish()
