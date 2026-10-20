"""Activate the exact installed MSIX; never launch its EXE without identity.

Standard library only. No installation, registration, certificate changes, or
fallback to a different package. A retained process HANDLE, not a PID lookup,
controls the new frontend's lifetime.
"""
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile

from release_runtime import _relative, digest
from storage_lease import plain_path, storage_parent

PACKAGE_NAME = 'Aredoko.Alpha'
PACKAGE_PUBLISHER = 'CN=AppPublisher'
PACKAGE_PATH = 'frontend/Aredoko.msix'
PAYLOAD = ('Aredoko.WinUI.exe', 'Aredoko.WinUI.dll', 'Aredoko.Core.dll',
           'Aredoko.WinUI.deps.json', 'Aredoko.WinUI.runtimeconfig.json')
FOOTPRINT = {'[Content_Types].xml', 'AppxBlockMap.xml', 'AppxSignature.p7x',
             'AppxMetadata/CodeIntegrity.cat'}
NS = {'m': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}


def inspect_msix(path):
    """Bounded archive inspection, without extracting any files."""
    path = plain_path(path)
    if path.stat().st_size > 1024 ** 3:
        raise ValueError('Frontend MSIX exceeds limit')
    with zipfile.ZipFile(path) as package:
        items = package.infolist()
        if not 1 <= len(items) <= 4096 or sum(i.file_size for i in items) > 2 * 1024 ** 3:
            raise ValueError('Frontend MSIX inventory exceeds limit')
        names = set()
        for item in items:
            name = _relative(item.orig_filename.rstrip('/') if item.is_dir() else item.orig_filename)
            if name.casefold() in names or item.flag_bits & 1 or item.orig_filename != item.filename:
                raise ValueError('Duplicate or encrypted MSIX entry')
            names.add(name.casefold())
        info = package.getinfo('AppxManifest.xml')
        if info.file_size > 2 * 1024 ** 2:
            raise ValueError('Frontend manifest exceeds limit')
        xml = package.read(info)
        if b'<!DOCTYPE' in xml.upper():
            raise ValueError('Unsupported frontend manifest')
        tree = ET.fromstring(xml)
        identity = tree.find('m:Identity', NS)
        applications = tree.findall('m:Applications/m:Application', NS)
        if identity is None or len(applications) != 1:
            raise ValueError('Expected one packaged frontend application')
        app = applications[0]
        if (identity.get('Name') != PACKAGE_NAME or identity.get('Publisher') != PACKAGE_PUBLISHER
                or identity.get('ProcessorArchitecture') != 'x64'
                or not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', identity.get('Version', ''))
                or app.get('Id') != 'App' or app.get('Executable') != 'Aredoko.WinUI.exe'
                or app.get('EntryPoint') != 'Windows.FullTrustApplication'
                or tree.findall('m:Dependencies/m:PackageDependency', NS)):
            raise ValueError('Expected the self-contained Aredoko x64 MSIX')
        entries = []
        for item in items:
            if not item.is_dir() and item.filename not in FOOTPRINT:
                with package.open(item) as stream:
                    sha = hashlib.sha256()
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        sha.update(block)
                entries.append({'path': item.filename, 'bytes': item.file_size, 'sha256': sha.hexdigest()})
        if not set(PAYLOAD) <= {e['path'] for e in entries}:
            raise ValueError('Frontend MSIX is missing application files')
    return {'name': identity.get('Name'), 'publisher': identity.get('Publisher'),
            'version': identity.get('Version'), 'architecture': 'x64', 'application_id': 'App',
            'executable': 'Aredoko.WinUI.exe', 'entries': entries}


def copy_msix_payload(path, destination, expected):
    """Copy only inspected ordinary files into a new staging bin, never extractall."""
    plain_path(path)
    plain_path(destination, directory=True)
    with zipfile.ZipFile(path) as package:
        for entry in expected['entries']:
            target = destination / entry['path']
            storage_parent(target)
            with package.open(entry['path']) as source, target.open('xb') as output:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    output.write(block)
            plain_path(target)
            if target.stat().st_size != entry['bytes'] or digest(target) != entry['sha256']:
                raise ValueError('Frontend changed while staging: ' + entry['path'])


def discover_package(expected):
    """Read the current user's OS registration; no developer tooling required."""
    if os.name != 'nt':
        raise RuntimeError('MSIX activation requires Windows')
    # The identity is fixed by inspect_msix; no user input becomes shell code.
    script = ("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
              "$p=@(Get-AppxPackage -Name '" + PACKAGE_NAME + "' | Select-Object Name,Publisher,"
              "@{n='Version';e={$_.Version.ToString()}},@{n='Architecture';e={$_.Architecture.ToString()}},"
              "PackageFamilyName,PackageFullName,InstallLocation,IsDevelopmentMode); "
              "ConvertTo-Json -InputObject $p -Compress")
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8-sig', errors='strict',
                            timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Cannot inspect the registered frontend package')
    if len(result.stdout) > 65536:
        raise ValueError('Registered package response exceeds limit')
    values = json.loads(result.stdout)
    if not isinstance(values, list) or len(values) != 1:
        raise RuntimeError('Install the matching Aredoko frontend MSIX before creating or using the shortcut')
    return validate_registration(values[0], expected)


def validate_registration(value, expected):
    if (not isinstance(value, dict) or value.get('Name') != expected['name']
            or value.get('Publisher') != expected['publisher'] or value.get('Version') != expected['version']
            or value.get('Architecture', '').lower() != 'x64' or value.get('IsDevelopmentMode') is not False):
        raise ValueError('The registered frontend is a different build or a development package')
    family = value.get('PackageFamilyName', '')
    full = value.get('PackageFullName', '')
    if (not re.fullmatch(re.escape(expected['name']) + r'_[a-z0-9]{13}', family)
            or full != f"{expected['name']}_{expected['version']}_x64__{family.rsplit('_', 1)[1]}"):
        raise ValueError('Unexpected registered package identity')
    location = value.get('InstallLocation')
    if not isinstance(location, str) or not Path(location).is_absolute():
        raise ValueError('Invalid package installation directory')
    return {'directory': Path(location), 'full_name': full, 'aumid': family + '!' + expected['application_id']}


def verify_installed(expected, registration):
    root = plain_path(registration['directory'], directory=True)
    for entry in expected['entries']:
        path = plain_path(root / entry['path'])
        if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise ValueError('Installed frontend differs from the release MSIX: ' + entry['path'])
    return root / expected['executable']


class GUID(ctypes.Structure):
    _fields_ = [('data', ctypes.c_ubyte * 16)]

    def __init__(self, text):
        super().__init__()
        self.data[:] = uuid.UUID(text).bytes_le


def _hresult(value, operation):
    if value < 0:
        raise OSError(f'{operation} failed (HRESULT 0x{value & 0xffffffff:08x})')


def activate_application(aumid, arguments):
    """Windows IApplicationActivationManager, AO_NOERRORUI; no shell/PID guessing."""
    ole = ctypes.OleDLL('ole32')
    ole.CoInitializeEx.argtypes = [W.LPVOID, W.DWORD]
    ole.CoInitializeEx.restype = W.LONG
    ole.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), W.LPVOID, W.DWORD,
                                   ctypes.POINTER(GUID), ctypes.POINTER(W.LPVOID)]
    ole.CoCreateInstance.restype = W.LONG
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    initialized = ole.CoInitializeEx(None, 2)
    _hresult(initialized, 'COM initialization')
    manager = W.LPVOID()
    try:
        _hresult(ole.CoCreateInstance(ctypes.byref(GUID('45ba127d-10a8-46ea-8ab7-56ea9078943c')),
                 None, 4, ctypes.byref(GUID('2e941141-7f97-4756-ba1d-9decde894a3d')),
                 ctypes.byref(manager)), 'Application activation manager creation')
        table = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(W.LPVOID))).contents
        activate = ctypes.WINFUNCTYPE(W.LONG, W.LPVOID, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                                      ctypes.POINTER(W.DWORD))(table[3])
        pid = W.DWORD()
        _hresult(activate(manager, aumid, subprocess.list2cmdline(arguments), 2, ctypes.byref(pid)),
                 'Packaged frontend activation')
        return pid.value
    finally:
        if manager:
            table = ctypes.cast(manager, ctypes.POINTER(ctypes.POINTER(W.LPVOID))).contents
            ctypes.WINFUNCTYPE(W.ULONG, W.LPVOID)(table[2])(manager)
        ole.CoUninitialize()


def validate_process_identity(created, started, image, executable, package, full_name):
    if (created < started or os.path.normcase(image) != os.path.normcase(str(executable))
            or package != full_name):
        raise RuntimeError('Activated frontend ownership was not proven; the process was left untouched')


class WindowsProcess:
    """Owned handle retained after creation/path/package validation; never reopen by PID."""
    stdin = None

    def __init__(self, pid, executable, full_name, started):
        self.returncode = None
        self.pid = pid
        self.handle = None
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'OpenProcess': ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            'CloseHandle': ([W.HANDLE], W.BOOL),
            'WaitForSingleObject': ([W.HANDLE, W.DWORD], W.DWORD),
            'GetExitCodeProcess': ([W.HANDLE, ctypes.POINTER(W.DWORD)], W.BOOL),
            'TerminateProcess': ([W.HANDLE, W.UINT], W.BOOL),
            'GetProcessTimes': ([W.HANDLE, *([ctypes.POINTER(W.FILETIME)] * 4)], W.BOOL),
            'QueryFullProcessImageNameW': ([W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)], W.BOOL),
            'GetPackageFullName': ([W.HANDLE, ctypes.POINTER(W.UINT), W.LPWSTR], W.LONG),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        handle = self.kernel.OpenProcess(0x100000 | 0x1000 | 0x0001, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            times = [W.FILETIME() for _ in range(4)]
            self._check(self.kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)))
            created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            buffer = ctypes.create_unicode_buffer(32768)
            count = W.DWORD(len(buffer))
            self._check(self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(count)))
            size = W.UINT(32768)
            package = ctypes.create_unicode_buffer(size.value)
            result = self.kernel.GetPackageFullName(handle, ctypes.byref(size), package)
            if result:
                raise RuntimeError('Activated frontend ownership was not proven; the process was left untouched')
            validate_process_identity(created, started, buffer.value, executable, package.value, full_name)
            self.handle = handle
        except BaseException:
            self.kernel.CloseHandle(handle)
            raise

    @staticmethod
    def _check(value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())

    def poll(self):
        if self.returncode is None:
            result = self.kernel.WaitForSingleObject(self.handle, 0)
            if result == 0:
                code = W.DWORD()
                self._check(self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)))
                self.returncode = code.value
            elif result != 258:
                raise ctypes.WinError(ctypes.get_last_error())
        return self.returncode

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('packaged frontend', timeout)
            time.sleep(0.05)
        return self.returncode

    def terminate(self):
        if self.poll() is None:
            self._check(self.kernel.TerminateProcess(self.handle, 1))

    kill = terminate

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class PackagedFrontend:
    def __init__(self, expected, registration):
        self.expected = expected
        self.registration = registration
        self.executable = verify_installed(expected, registration)

    def start(self, arguments, log):
        # Revalidate immediately before activation, including all installed files.
        verify_installed(self.expected, self.registration)
        started = time.time_ns() // 100 + 116444736000000000
        pid = activate_application(self.registration['aumid'], arguments)
        process = WindowsProcess(pid, self.executable, self.registration['full_name'], started)
        try:
            log.write((json.dumps({'activation': 'msix', 'pid': pid,
                                  'package': self.registration['full_name']}) + '\n').encode('utf-8'))
            log.flush()
        except BaseException:
            try:
                process.terminate()
                process.wait(timeout=5)
            finally:
                process.close()
            raise
        return process


def prepare_frontend(root, manifest):
    if manifest.get('frontend_activation') != 'msix':
        raise ValueError('This staging folder has no packaged frontend; rebuild with --frontend-msix')
    expected = inspect_msix(root / PACKAGE_PATH)
    return PackagedFrontend(expected, discover_package(expected))
