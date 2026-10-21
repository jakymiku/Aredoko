"""Windows developer preparation using existing caches/runtime only; never opens GUI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from release_runtime import verify_release, ordinary_tree, digest, python_layout, media_layout
from package_release import package, validate_output
from storage_lease import plain_path, storage_parent
from portable_frontend import inspect_portable, RECEIPT


def windows_directory():
    # Use the OS location, not a user-overridable SystemRoot value.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetSystemWindowsDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel.GetSystemWindowsDirectoryW.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    count = kernel.GetSystemWindowsDirectoryW(buffer, len(buffer))
    if not 0 < count < len(buffer):raise OSError('Cannot locate the Windows system directory')
    return Path(buffer.value)


def system_compiler():
    compiler = windows_directory() / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    plain_path(compiler.parent, directory=True)
    info = compiler.lstat()
    # Windows component servicing legitimately hardlinks inbox executables to
    # WinSxS. This narrow build-tool check does not change payload/source guards.
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_nlink < 1):
        raise ValueError('Expected an ordinary Windows-inbox compiler')
    return compiler


def receipt(frontend, properties):
    required = {'WindowsPackageType': 'None', 'SelfContained': 'true', 'WindowsAppSDKSelfContained': 'true',
                'Configuration': 'Portable', 'AredokoPackageChannel': 'Portable'}
    if any(str(properties.get(k, '')).lower() != v.lower() for k, v in required.items()):
        raise ValueError('The evaluated project is not a self-contained Portable channel')
    marker = frontend / RECEIPT
    if marker.exists():raise FileExistsError('A publish receipt already exists')
    entries = [{'path': p.relative_to(frontend).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p)}
               for p in sorted(ordinary_tree(frontend)) if p.suffix.lower() != '.pdb']
    value = {'format': 'aredoko-portable-build-v1', 'channel': 'Portable', 'configuration': 'Portable',
             'windows_package_type': 'None', 'self_contained': True, 'entries': entries}
    with marker.open('x', encoding='utf-8') as stream:json.dump(value, stream, ensure_ascii=False, indent=2)
    inspect_portable(frontend)
    return value


def zip_release(release, destination):
    manifest = verify_release(release)
    if destination.exists() or destination.is_symlink():raise FileExistsError('Choose a new ZIP destination')
    validate_output(destination)
    try:
        with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
            for path in sorted(ordinary_tree(release)):
                archive.write(path, 'Aredoko/' + path.relative_to(release).as_posix())
        expected = {row['path']: row['sha256'] for row in manifest['entries']}
        expected.update({name: digest(plain_path(release / name)) for name in ('manifest.json', 'sha256sums.txt')})
        with zipfile.ZipFile(destination) as archive:
            if set(archive.namelist()) != {'Aredoko/' + name for name in expected}:raise ValueError('ZIP inventory mismatch')
            for name, checksum in expected.items():
                sha = hashlib.sha256()
                with archive.open('Aredoko/' + name) as stream:
                    for block in iter(lambda: stream.read(1024*1024), b''):sha.update(block)
                if sha.hexdigest() != checksum:raise ValueError('ZIP content changed')
        verify_release(release)
    except Exception:
        # Keep any incomplete new archive as evidence, never overwrite/reuse it.
        raise


def prepare(runtime_release, output, *, dotnet='dotnet', make_zip=True):
    if os.name != 'nt':raise RuntimeError('Portable build preparation requires Windows; no downloads are attempted')
    runtime_release = plain_path(runtime_release, directory=True)
    manifest = verify_release(runtime_release)
    if manifest.get('python_bundled') is not True or manifest.get('media_tools_bundled') is not True:
        raise ValueError('Select an existing release with bundled Python and media runtime')
    python = runtime_release / 'runtime/python';media = runtime_release / 'runtime/media'
    python_layout(python, manifest.get('ai_runtime_bundled') is True);media_layout(media)
    csc = system_compiler()
    output = Path(os.path.abspath(output));validate_output(output)
    if output.is_relative_to(runtime_release) or runtime_release.is_relative_to(output):raise ValueError('Output must be separate from existing runtime assets')
    storage_parent(output);output.mkdir();plain_path(output, directory=True)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1', DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='true', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
    frontend = output / 'frontend';bootstrap = output / 'Aredoko.exe'
    project = str(ROOT / 'src/Aredoko.WinUI/Aredoko.WinUI.csproj')
    common = ['-p:Configuration=Portable', '-p:Platform=x64', '-p:AredokoPackageChannel=Portable']
    def run(command, label, timeout=600):
        with (output / (label + '.log')).open('xb') as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode:raise RuntimeError(label + ' failed; see ' + str(output / (label + '.log')))
    print('既存キャッシュで本体をビルドしています。', flush=True)
    query = subprocess.run([dotnet, 'msbuild', project, *common,
        '-getProperty:WindowsPackageType,SelfContained,WindowsAppSDKSelfContained,Configuration,AredokoPackageChannel'],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8-sig', timeout=60)
    (output / 'project-properties.log').write_text(query.stdout + '\n' + query.stderr, encoding='utf-8')
    if query.returncode:raise RuntimeError('Cannot evaluate cached Portable project properties')
    properties = json.loads(query.stdout)['Properties']
    run([dotnet, 'run', '--project', str(ROOT / 'tests/Aredoko.Core.Tests/Aredoko.Core.Tests.csproj'),
         '-c', 'Release', '--no-restore'], 'core-tests')
    run([dotnet, 'publish', project, '-c', 'Portable', '-p:Platform=x64', '-p:AredokoPackageChannel=Portable',
         '--no-restore', '-o', str(frontend)], 'frontend-build')
    receipt(frontend, properties)
    print('起動画面をビルドしています。', flush=True)
    if system_compiler() != csc:raise ValueError('Windows compiler location changed')
    run([str(csc), '/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/utf8output', '/codepage:65001',
         '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll', '/reference:System.Web.Extensions.dll',
         '/win32icon:' + str(ROOT / 'src/Aredoko.WinUI/Assets/AppIcon.ico'),
         '/win32manifest:' + str(ROOT / 'src/Aredoko.Bootstrap/app.manifest'),
         '/out:' + str(bootstrap), str(ROOT / 'src/Aredoko.Bootstrap/Bootstrap.cs')], 'bootstrap-build')
    run([str(bootstrap), '--self-test'], 'bootstrap-cpu', timeout=30)
    release = output / 'Aredoko'
    print('実行環境を新しいフォルダへコピーしています。', flush=True)
    package(release, version='alpha-portable-0', skip_build=True, python_runtime=python, media_tools=media,
            include_ai_runtime=manifest.get('ai_runtime_bundled') is True, portable_frontend=frontend, bootstrap=bootstrap)
    verify_release(release)
    # Probe real Windows imports/media, without opening GUI or a user database.
    run([str(release / 'runtime/python/python.exe'), '-I', '-B', str(release / 'tools/launch_release.py'), '--check'], 'runtime-check', timeout=240)
    if make_zip:
        print('ZIPを作成・照合しています。', flush=True)
        zip_release(release, output / 'Aredoko-windows-x64.zip')
    summary = {'format': 'aredoko-portable-preparation-v1', 'release': str(release),
               'bootstrap_cpu_pass': True, 'runtime_check_pass': True, 'native_gui_verified': False,
               'clean_windows_verified': False, 'zip_created': make_zip}
    with (output / 'preparation.json').open('x', encoding='utf-8') as stream:json.dump(summary, stream, indent=2)
    print('準備完了。起動チェック: ' + str(release / 'Check-Startup.cmd'), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-release', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / ('portable-' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)))
    parser.add_argument('--no-zip', action='store_true', help='Prepare an unpacked startup check first, skipping large archive creation')
    args = parser.parse_args()
    try:prepare(args.runtime_release, args.output, make_zip=not args.no_zip)
    except Exception as error:
        print('準備を完了できません: ' + str(error), file=sys.stderr);return 2
    return 0


if __name__ == '__main__':raise SystemExit(main())
