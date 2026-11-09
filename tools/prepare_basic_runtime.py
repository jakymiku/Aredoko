"""Build a NEW basic venv from the explicitly invoked, verified CPython.

No network, pip resolution, models, GUI or system installation. The caller must
verify the base interpreter with the native official-package verifier first.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ('backend/app' if (ROOT / 'backend/app').is_dir() else 'app')))
from storage_lease import plain_path, storage_parent

# https://pypi.org/pypi/Pillow/12.3.0/json, cp313 Windows x64 wheel.
PILLOW_SHA256 = '1cca606cd25738df4ed873d5ad46bbdb3d83b5cbca291f6b4ff13a4df6b0bbe8'


def verify_environment(archive, output):
    """Verify installed wheel bytes and venv launch binding before executing it."""
    output = plain_path(output, directory=True)
    configuration = {}
    for line in plain_path(output / 'pyvenv.cfg').read_text(encoding='utf-8').splitlines():
        name, value = line.split(' = ', 1)
        if name in configuration:
            raise ValueError('Duplicate venv configuration')
        configuration[name] = value
    if (set(configuration) != {'home', 'include-system-site-packages', 'version', 'executable', 'command'}
            or configuration['include-system-site-packages'] != 'false'
            or configuration['version'] != '3.13.17'
            or Path(configuration['home']) != Path(sys.base_prefix)
            or Path(configuration['executable']) != Path(sys.executable)):
        raise ValueError('Unexpected venv base or system site access')
    base = Path(sys.base_prefix) / 'Lib/venv/scripts/nt'
    scripts = plain_path(output / 'Scripts', directory=True)
    allowed_scripts = {'activate', 'activate.bat', 'activate.fish', 'Activate.ps1', 'deactivate.bat', 'python.exe', 'pythonw.exe'}
    if {p.name for p in scripts.iterdir()} != allowed_scripts:
        raise ValueError('Unlisted venv script or executable')
    for path in scripts.iterdir():
        plain_path(path)
    if {p.name for p in (output / 'Lib').iterdir()} != {'site-packages'}:
        raise ValueError('Unlisted venv library')
    for installed, original in (('python.exe', 'venvlauncher.exe'), ('pythonw.exe', 'venvwlauncher.exe')):
        if plain_path(output / 'Scripts' / installed).read_bytes() != plain_path(base / original).read_bytes():
            raise ValueError('Venv launcher changed')
    site = plain_path(output / 'Lib/site-packages', directory=True)
    expected = set()
    for entry in archive.infolist():
        target = site.joinpath(*entry.filename.split('/'))
        expected.add(target)
        with archive.open(entry) as source, plain_path(target).open('rb') as installed:
            if hashlib.file_digest(source, 'sha256').digest() != hashlib.file_digest(installed, 'sha256').digest():
                raise ValueError('Installed Pillow file changed: ' + entry.filename)
    actual = set()
    for folder, directories, files in os.walk(site, followlinks=False):
        plain_path(folder, directory=True)
        for name in directories:
            plain_path(Path(folder) / name, directory=True)
        for name in files:
            actual.add(plain_path(Path(folder) / name))
    if actual != expected:
        raise ValueError('Unlisted or missing basic site-packages files')


def prepare(wheel, output, *, verify=False):
    check_cancelled()
    if sys.version_info[:3] != (3, 13, 17) or sys.platform != 'win32':
        raise RuntimeError('Invoke with the verified CPython 3.13.17 Windows interpreter')
    wheel = plain_path(Path(os.path.abspath(wheel)))
    output = Path(os.path.abspath(output))
    storage_parent(output)
    plain_path(output, directory=True, missing=True)
    if output.exists() and not verify:
        raise FileExistsError('Existing runtime is never overwritten')
    # Keep artifact open and verify the bytes used for extraction.
    with wheel.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != PILLOW_SHA256:
            raise ValueError('Official Pillow wheel SHA256 mismatch')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            # This fixed wheel has no installer scripts or .data relocation.
            names = set()
            for entry in archive.infolist():
                parts = entry.filename.split('/')
                if (any(p in ('', '.', '..') for p in parts) or any(':' in p or '\\' in p for p in parts)
                        or entry.is_dir() or any(p.endswith('.data') for p in parts)
                        or entry.filename.casefold() in names):
                    raise ValueError('Unexpected fixed-wheel layout')
                names.add(entry.filename.casefold())
            if not verify:
                subprocess.run([sys.executable, '-I', '-B', '-m', 'venv', '--without-pip', str(output)], check=True)
                check_cancelled()
                site = plain_path(output / 'Lib/site-packages', directory=True)
                for entry in archive.infolist():
                    check_cancelled()
                    destination = site.joinpath(*entry.filename.split('/'))
                    storage_parent(destination)
                    plain_path(destination, missing=True)
                    with archive.open(entry) as source, destination.open('xb') as target:
                        while block := source.read(1024 * 1024):
                            target.write(block)
            verify_environment(archive, output)
    check_cancelled()
    python = plain_path(output / 'Scripts/python.exe')
    probe = subprocess.run([str(python), '-I', '-B', str(Path(__file__).with_name('probe_release_runtime.py'))],
                           check=True, capture_output=True, text=True)
    print(probe.stdout.strip())
    return python


def check_cancelled():
    marker = os.environ.get('AREDOKO_SETUP_CANCEL')
    if marker and Path(marker).exists():
        raise InterruptedError('Basic environment setup cancelled; backend not started')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    prepare(args.wheel, args.output, verify=args.verify)


if __name__ == '__main__':
    main()
