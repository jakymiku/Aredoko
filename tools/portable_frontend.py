"""Explicit unpackaged frontend receipt and owned initial-screen handshake."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import struct
import threading

from release_runtime import _relative, digest, ordinary_tree, runtime_environment
from storage_lease import plain_path
from startup_ipc import _object

RECEIPT = 'portable-build.json'
READY_FORMAT = 'aredoko-frontend-ready-v1'
PAYLOAD = {'Aredoko.WinUI.exe', 'Aredoko.WinUI.dll', 'Aredoko.Core.dll',
           'Aredoko.WinUI.deps.json', 'Aredoko.WinUI.runtimeconfig.json', 'System.Console.dll'}


def inspect_bootstrap(path):
    path = plain_path(path)
    with path.open('rb') as stream:header = stream.read(4096)
    if len(header) < 64 or header[:2] != b'MZ':raise ValueError('Expected a built x64 Windows bootstrap')
    offset = struct.unpack_from('<I', header, 60)[0]
    if offset > len(header) - 264:raise ValueError('Invalid bootstrap PE header')
    if (header[offset:offset+4] != b'PE\0\0' or struct.unpack_from('<H', header, offset+4)[0] != 0x8664
            or struct.unpack_from('<H', header, offset+24)[0] != 0x20b
            or struct.unpack_from('<H', header, offset+24+68)[0] != 2
            or struct.unpack_from('<I', header, offset+24+224)[0] == 0):
        raise ValueError('Expected the x64 Windows GUI CLR bootstrap, not a script or another build')
    return path


def inspect_portable(root):
    root = plain_path(root, directory=True)
    marker = plain_path(root / RECEIPT)
    if marker.stat().st_size > 2 * 1024**2:raise ValueError('Portable receipt exceeds limit')
    value = json.loads(marker.read_text(encoding='utf-8-sig'), object_pairs_hook=_object)
    if (not isinstance(value, dict) or value.get('format') != 'aredoko-portable-build-v1'
            or value.get('channel') != 'Portable' or value.get('configuration') != 'Portable'
            or value.get('windows_package_type') != 'None' or value.get('self_contained') is not True):
        raise ValueError('Expected an explicit Portable publish receipt')
    entries = value.get('entries')
    if not isinstance(entries, list) or not 5 <= len(entries) <= 4096:raise ValueError('Invalid portable inventory')
    expected = set();total = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'path', 'bytes', 'sha256'}:raise ValueError('Invalid portable entry')
        name = _relative(entry['path'])
        if name.casefold() in expected or name.casefold() in {RECEIPT, 'appxmanifest.xml'}:raise ValueError('Unexpected portable entry')
        expected.add(name.casefold())
        if type(entry['bytes']) is not int or entry['bytes'] < 0:raise ValueError('Invalid portable size')
        total += entry['bytes']
        if total > 2 * 1024**3:raise ValueError('Portable frontend exceeds limit')
        path = plain_path(root / name)
        if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:raise ValueError('Portable frontend changed')
    actual = {p.relative_to(root).as_posix().casefold() for p in ordinary_tree(root) if p.suffix.lower() != '.pdb'}
    if actual != expected | {RECEIPT} or not {p.casefold() for p in PAYLOAD} <= expected:raise ValueError('Portable inventory mismatch')
    config = plain_path(root / 'Aredoko.WinUI.runtimeconfig.json')
    if config.stat().st_size > 65536:raise ValueError('Runtime config exceeds limit')
    options = json.loads(config.read_text(encoding='utf-8-sig'), object_pairs_hook=_object).get('runtimeOptions', {})
    included = options.get('includedFrameworks') if isinstance(options, dict) else None
    if not isinstance(options, dict) or 'framework' in options or 'frameworks' in options or not isinstance(included, list) or not included:
        raise ValueError('Portable frontend requires self-contained .NET')
    # A GUI publish may contain a DLL that its trimmed .deps graph cannot load.
    # Fail before launching rather than timing out after a successful first frame.
    deps_path = plain_path(root / 'Aredoko.WinUI.deps.json')
    if deps_path.stat().st_size > 2 * 1024**2:raise ValueError('Portable dependencies exceed limit')
    deps = json.loads(deps_path.read_text(encoding='utf-8-sig'), object_pairs_hook=_object)
    target = deps.get('runtimeTarget', {}).get('name') if isinstance(deps, dict) else None
    libraries = deps.get('targets', {}).get(target, {}) if isinstance(target, str) else {}
    if (not isinstance(libraries, dict) or not any(
            isinstance(library, dict) and isinstance(library.get('runtime'), dict)
            and 'System.Console.dll' in library['runtime'] for library in libraries.values())):
        raise ValueError('Portable startup Console dependency is missing from the runtime graph')
    return value


class ReadyProcess:
    """Retains the Popen handle; stdout is a dedicated readiness/log channel."""
    def __init__(self, process, nonce, instance, log):
        self.process = process
        self.ready = threading.Event()
        self.ready_error = None
        self.stdin = None
        self._nonce, self._instance, self._log = nonce, instance, log
        self._reader = threading.Thread(target=self._read, daemon=True, name='portable-ready')
        self._reader.start()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(4097)
                if not line:break
                if len(line) > 4096 or not line.endswith(b'\n'):raise ValueError('Frontend frame exceeds limit')
                try:value = json.loads(line, object_pairs_hook=_object)
                except (ValueError, UnicodeError):
                    if READY_FORMAT.encode() in line:raise ValueError('Malformed initial-screen acknowledgement')
                    value = None
                if isinstance(value, dict) and value.get('format') == READY_FORMAT:
                    if (set(value) != {'format', 'nonce', 'instance_id', 'status'} or self.ready.is_set()
                            or value['nonce'] != self._nonce or value['instance_id'] != self._instance
                            or value['status'] != 'ready'):
                        raise ValueError('Invalid initial-screen acknowledgement')
                    self.ready.set()
                else:
                    self._log.write(line);self._log.flush()
            if not self.ready.is_set():raise ValueError('Frontend closed before ready')
        except Exception:
            self.ready_error = 'frontend_ready_failed'

    @property
    def returncode(self):return self.process.returncode
    def poll(self):return self.process.poll()
    def wait(self, timeout):return self.process.wait(timeout=timeout)
    def terminate(self):return self.process.terminate()
    def kill(self):return self.process.kill()
    def close(self):
        self._reader.join(timeout=2)
        self.process.stdout.close()


class PortableFrontend:
    def __init__(self, root, manifest, instance):
        if manifest.get('frontend_activation') != 'portable':raise ValueError('Explicit portable channel required')
        self.root, self.instance = root, instance
        inspect_portable(root / 'bin')
        self.executable = plain_path(root / 'bin/Aredoko.WinUI.exe')

    def start(self, arguments, log):
        inspect_portable(self.root / 'bin')
        nonce = secrets.token_hex(16)
        env = runtime_environment(self.root / 'runtime/media')
        env['AREDOKO_STARTUP_NONCE'] = nonce
        env['AREDOKO_STARTUP_INSTANCE'] = self.instance
        child = subprocess.Popen([str(self.executable), *arguments], cwd=self.root / 'bin', env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log, close_fds=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), bufsize=0)
        try:return ReadyProcess(child, nonce, self.instance, log)
        except BaseException:
            if child.poll() is None:child.terminate();child.wait(timeout=5)
            child.stdout.close();raise
