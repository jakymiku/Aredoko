"""Artifact-bound construction and verification of an AI venv.

The original verified wheels remain the provenance evidence. An inventory made
from installed files is never a replacement for checking those artifacts.
"""
import hashlib
import json
from pathlib import Path
import os
import subprocess
import zipfile

from ai_runtime import relative, digest, files
from storage_lease import plain_path, storage_parent, storage_lease


def installed_path(name):
    """Map this fixed recipe's wheel payload without generating CLI wrappers."""
    relative(name)
    parts = name.split('/')
    if parts[0].endswith('.data'):
        if len(parts) < 3 or parts[1] not in ('purelib', 'platlib', 'scripts', 'data'):
            raise ValueError('Unsupported data relocation in fixed AI recipe')
        # Product workers invoke Python directly. Preserve upstream script bytes
        # as non-entrypoint artifacts rather than generating unverified EXEs.
        if parts[1] in ('purelib', 'platlib'):
            name = '/'.join(parts[2:])
        elif parts[1] == 'data':
            return '/'.join(parts[2:])
    return 'Lib/site-packages/' + name


def verify_wheels(root, artifacts, lock, *, cancelled=lambda: False, progress=None, inventory=None):
    """Compare every imported package byte directly with its official wheel."""
    root = plain_path(root, directory=True)
    artifacts = plain_path(artifacts, directory=True)
    expected = set()
    done = completed = total_files = total_bytes = 0
    for entry in lock['entries']:
        wheel = plain_path(artifacts / relative(entry['filename']))
        if digest(wheel, cancelled) != entry['sha256']:
            raise ValueError('Official AI wheel checksum mismatch: ' + entry['name'])
        with zipfile.ZipFile(wheel) as archive:
            for item in archive.infolist():
                if not item.is_dir():total_files += 1;total_bytes += item.file_size
    def report():
        if progress is not None:
            progress({'stage': 'checking_wheel_payload', 'bytes_done': done, 'bytes_total': total_bytes,
                      'files_done': completed, 'files_total': total_files})
    report()
    for entry in lock['entries']:
        if cancelled():raise InterruptedError('AI runtime verification cancelled')
        wheel = plain_path(artifacts / relative(entry['filename']))
        # Keep the same handle while comparing payloads, then recheck the
        # artifact after reading. Python open() is not an exclusive write lock.
        with wheel.open('rb') as stream:
            with zipfile.ZipFile(stream) as archive:
                for item in archive.infolist():
                    if item.is_dir():continue
                    if cancelled():raise InterruptedError('AI runtime verification cancelled')
                    name = installed_path(item.filename)
                    if name.casefold() in expected:
                        raise ValueError('Conflicting official AI wheel payloads')
                    expected.add(name.casefold())
                    target = plain_path(root / name)
                    if target.stat().st_size != item.file_size:
                        raise ValueError('Installed AI payload size changed: ' + name)
                    with archive.open(item) as source, target.open('rb') as installed:
                        # Bounded blocks retain cancellation while hashing large
                        # torch DLLs; no DLL/module/model is executed here.
                        left, right = hashlib.sha256(), hashlib.sha256()
                        while True:
                            if cancelled():raise InterruptedError('AI runtime verification cancelled')
                            original = source.read(1024 * 1024)
                            actual = installed.read(len(original) or 1)
                            if not original:
                                if actual:raise ValueError('Installed AI payload grew')
                                break
                            left.update(original);right.update(actual)
                            done += len(original)
                            report()
                        if left.digest() != right.digest():
                            raise ValueError('Installed AI payload changed: ' + name)
                        if inventory is not None:
                            inventory.append({'path': name, 'bytes': item.file_size, 'sha256': left.hexdigest()})
                    completed += 1;report()
        if digest(wheel, cancelled) != entry['sha256']:
            raise ValueError('AI wheel changed during content verification')
    site = root / 'Lib/site-packages'
    actual = {path.relative_to(root).as_posix().casefold() for path in files(site, cancelled, include_cache=True)}
    expected_site = {name for name in expected if name.startswith('lib/site-packages/')}
    if actual != expected_site:
        raise ValueError('Unlisted or missing managed AI site-packages files')
    other = expected - expected_site
    for top in {name.split('/')[0] for name in other}:
        # Use the actual original-case path; Windows is case-insensitive but
        # generated boundary tests also run on case-sensitive filesystems.
        folder = next(path for path in root.iterdir() if path.name.casefold() == top)
        found = {path.relative_to(root).as_posix().casefold() for path in files(folder, cancelled, include_cache=True)}
        if found != {name for name in other if name.startswith(top + '/')}:
            raise ValueError('Unlisted managed AI data files')
    return done


def build_environment(base_python, artifacts, output, lock, *, cancelled=lambda: False, progress=None):
    """Trusted caller supplies a reviewed lock and a native-verified base.

    This builds an unregistered environment. Model load/inference and settings
    publication are separate gates; no AI-ready marker is written here.
    """
    base_python = plain_path(base_python)
    artifacts = plain_path(artifacts, directory=True)
    output = Path(os.path.abspath(output))
    if (output.is_relative_to(base_python.parent) or base_python.is_relative_to(output)
            or output.is_relative_to(artifacts) or artifacts.is_relative_to(output)):
        raise ValueError('AI environment must be separate from base Python and wheel artifacts')
    plain_path(output, directory=True, missing=True)
    if output.exists():raise FileExistsError('Existing AI environments are never overwritten')
    storage_parent(output)
    with storage_lease(output.with_name(output.name + '-build')):
        for entry in lock['entries']:
            if cancelled():raise InterruptedError('AI setup cancelled')
            wheel = plain_path(artifacts / relative(entry['filename']))
            if digest(wheel, cancelled) != entry['sha256']:
                raise ValueError('Official AI wheel checksum mismatch: ' + entry['name'])
        if cancelled():raise InterruptedError('AI setup cancelled')
        env = {key: value for key, value in os.environ.items() if key.upper() not in {'PYTHONHOME', 'PYTHONPATH'}}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONUTF8='1')
        subprocess.run([str(base_python), '-I', '-X', 'utf8', '-B', '-m', 'venv', '--without-pip', str(output)],
                       check=True, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        seen = set()
        for entry in lock['entries']:
            if progress is not None:progress({'stage': 'installing_wheel', 'package': entry['name']})
            wheel = plain_path(artifacts / entry['filename'])
            with zipfile.ZipFile(wheel) as archive:
                for item in archive.infolist():
                    if item.is_dir():continue
                    if cancelled():raise InterruptedError('AI setup cancelled; unregistered environment retained')
                    name = installed_path(item.filename)
                    if name.casefold() in seen:raise ValueError('Conflicting AI wheel paths')
                    seen.add(name.casefold())
                    destination = output / name
                    storage_parent(destination);plain_path(destination, missing=True)
                    with archive.open(item) as source, destination.open('xb') as target:
                        while block := source.read(1024 * 1024):
                            if cancelled():raise InterruptedError('AI setup cancelled; unregistered environment retained')
                            target.write(block)
        verified_bytes = verify_wheels(output, artifacts, lock, cancelled=cancelled, progress=progress)
        receipt = {'format': 'aredoko-ai-environment-draft-v1', 'ai_ready': False,
                   'lock_sha256': hashlib.sha256(json.dumps(lock, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                   'wheel_payload_bytes_verified': verified_bytes, 'model_inference_verified': False}
        with (output / 'aredoko-ai-environment-draft.json').open('x', encoding='utf-8') as stream:
            json.dump(receipt, stream, indent=2)
        return {'root': str(output), 'python': str(output / 'Scripts/python.exe'), **receipt}
