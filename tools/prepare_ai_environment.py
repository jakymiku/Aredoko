"""Explicit offline development preparation; never marks AI ready or edits settings.

Run with the native-verified base CPython. Resolve/download/review the official
wheel lock first; this tool installs no unpinned or network-resolved package.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / ('backend/app' if (ROOT / 'backend/app').is_dir() else 'app')))
from ai_runtime import object_pairs
from ai_wheel_runtime import build_environment
from build_ai_wheel_lock import build, TORCH_HASHES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--lock-sha256', required=True)
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (sys.platform != 'win32' or sys.version_info[:3] != (3, 13, 17)
            or struct.calcsize('P') != 8 or sys.prefix != sys.base_prefix):
        raise RuntimeError('Run with the native-verified standalone CPython 3.13.17 x64')
    if args.lock.stat().st_size > 1024 * 1024:raise ValueError('Wheel lock exceeds limit')
    raw = args.lock.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.lock_sha256:
        raise ValueError('Explicit wheel lock changed')
    lock = json.loads(raw, object_pairs_hook=object_pairs)
    # Reuse the source-owned supported roots/origin/tag checks at this external
    # input boundary; no downloaded report or catalog is executable authority.
    report = {'version': '1', 'environment': {'sys_platform': 'win32', 'platform_machine': 'AMD64', 'python_full_version': '3.13.17'},
              'install': [{'metadata': {'name': entry['name'], 'version': entry['version']},
                           'is_direct': entry['name'] in TORCH_HASHES,
                           'download_info': {'url': entry['url'], 'archive_info': {'hashes': {'sha256': entry['sha256']}}}}
                          for entry in lock['entries']]}
    canonical, _ = build(report)
    if canonical != lock:raise ValueError('Unexpected wheel lock fields')
    last = [None, -1]
    def progress(value):
        bucket = value.get('bytes_done', 0) // (256 * 1024**2)
        if value['stage'] != last[0] or 'package' in value or bucket != last[1]:
            print(json.dumps(value), flush=True);last[:] = [value['stage'], bucket]
    result = build_environment(Path(sys.executable), args.wheels, args.output, lock, progress=progress)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':main()
