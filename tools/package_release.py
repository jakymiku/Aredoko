"""Distribution packaging script for Aredoko.

Produces a standalone release directory containing:
- Self-contained WinUI 3 application (no dotnet SDK or winapp required at runtime)
- Python backend application package (no remote downloads, offline by default)
- Standalone launcher scripts (start-aredoko.ps1, Aredoko.cmd)
- Third-party license notices and user guide
- Release manifest and SHA256 checksums
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]


def compute_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def package(output_dir, version='1.0.0', skip_build=False, dry_run=False):
    output_dir = Path(output_dir).resolve()
    print(f"=== Packaging Aredoko v{version} ===")
    print(f"Target directory: {output_dir}")

    # 1. Validate prerequisites
    req_files = [
        REPO / 'src' / 'Aredoko.WinUI' / 'Aredoko.WinUI.csproj',
        REPO / 'app' / 'production_server.py',
        REPO / 'app' / 'storage_schema_v1.json',
        REPO / 'THIRD_PARTY_NOTICES.md',
        REPO / 'docs' / 'user-guide.md',
        REPO / 'tools' / 'start-aredoko.ps1',
        REPO / 'tools' / 'backup_library.py',
    ]
    for rf in req_files:
        if not rf.exists():
            raise FileNotFoundError(f"Required source file not found: {rf}")

    winui_bin = REPO / 'src' / 'Aredoko.WinUI' / 'bin' / 'x64' / 'Release' / 'net10.0-windows10.0.26100.0' / 'win-x64'
    if not skip_build and not dry_run:
        print("\n--- Building WinUI x64 Release (self-contained) ---")
        cmd = ['dotnet', 'build', 'src/Aredoko.WinUI/Aredoko.WinUI.csproj', '-c', 'Release', '-p:Platform=x64', '-p:SelfContained=true', '--no-restore']
        res = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if res.returncode != 0:
            print(res.stdout)
            print(res.stderr)
            raise RuntimeError("WinUI build failed during packaging")
        print("WinUI build succeeded.")

    if dry_run:
        print("\n[Dry Run] Prerequisites verified. Skipping file copy.")
        return {'version': version, 'dry_run': True, 'pass': True}

    # 2. Prepare output directory
    if output_dir.exists():
        print(f"Cleaning existing output directory: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bin_dir = output_dir / 'bin'
    backend_app_dir = output_dir / 'backend' / 'app'
    backend_config_dir = output_dir / 'backend' / 'config'
    tools_dir = output_dir / 'tools'

    bin_dir.mkdir(parents=True, exist_ok=True)
    backend_app_dir.mkdir(parents=True, exist_ok=True)
    backend_config_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)

    # 3. Copy WinUI binaries
    print("\n--- Copying WinUI binaries ---")
    if not winui_bin.exists():
        raise FileNotFoundError(f"WinUI build output not found at: {winui_bin}")
    for item in winui_bin.iterdir():
        if item.suffix.lower() == '.pdb':
            continue  # Exclude debug symbols from clean release
        target = bin_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    print(f"Copied {len(list(bin_dir.iterdir()))} items to bin/")

    # 4. Copy backend files
    print("\n--- Copying Backend package ---")
    app_source = REPO / 'app'
    for item in app_source.glob('*'):
        if item.is_file() and (item.suffix in ('.py', '.json') or item.name == '__init__.py'):
            shutil.copy2(item, backend_app_dir / item.name)

    # Copy config profiles
    config_source = REPO / 'config'
    if config_source.exists():
        for sub in ('profiles', 'tagger-profiles'):
            s_dir = config_source / sub
            if s_dir.exists():
                t_dir = backend_config_dir / sub
                shutil.copytree(s_dir, t_dir)

    # 5. Copy tools & notices
    print("\n--- Copying Launchers & Notices ---")
    shutil.copy2(REPO / 'tools' / 'start-aredoko.ps1', output_dir / 'start-aredoko.ps1')
    shutil.copy2(REPO / 'tools' / 'backup_library.py', tools_dir / 'backup_library.py')
    shutil.copy2(REPO / 'THIRD_PARTY_NOTICES.md', output_dir / 'THIRD_PARTY_NOTICES.md')
    shutil.copy2(REPO / 'docs' / 'user-guide.md', output_dir / 'USER_GUIDE.md')

    # Create Aredoko.cmd helper
    cmd_content = '@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-aredoko.ps1" %*\r\n'
    (output_dir / 'Aredoko.cmd').write_text(cmd_content, encoding='utf-8')

    # 6. Checkpoint any template SQLite database
    for db_file in output_dir.rglob('*.sqlite'):
        try:
            with closing(sqlite3.connect(db_file)) as db:
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass

    # 7. Generate Manifest & SHA256 checksums
    print("\n--- Computing SHA256 Checksums & Generating Manifest ---")
    manifest_entries = []
    sha256_lines = []
    total_bytes = 0

    for path in sorted(output_dir.rglob('*')):
        if path.is_file():
            rel_path = path.relative_to(output_dir).as_posix()
            size = path.stat().st_size
            digest = compute_sha256(path)
            total_bytes += size
            manifest_entries.append({
                'path': rel_path,
                'bytes': size,
                'sha256': digest
            })
            sha256_lines.append(f"{digest}  {rel_path}\n")

    manifest = {
        'format': 'aredoko-release-manifest',
        'version': version,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'platform': 'windows-x64',
        'files_count': len(manifest_entries),
        'total_bytes': total_bytes,
        'entries': manifest_entries
    }

    manifest_file = output_dir / 'manifest.json'
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

    sha_file = output_dir / 'sha256sums.txt'
    sha_file.write_text(''.join(sha256_lines), encoding='utf-8')

    print(f"\nPackaging complete: {len(manifest_entries)} files ({total_bytes / (1024*1024):.2f} MiB)")
    print(f"Manifest: {manifest_file}")
    print(f"Checksums: {sha_file}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=REPO / 'dist' / 'aredoko-release-windows-x64')
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--skip-build', action='store_true', help='Skip dotnet build step')
    parser.add_argument('--check', action='store_true', help='Dry-run verification of packaging prerequisites')
    args = parser.parse_args()

    package(args.output_dir, version=args.version, skip_build=args.skip_build, dry_run=args.check)


if __name__ == '__main__':
    main()
