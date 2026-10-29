"""Stage an Aredoko build in a NEW directory, with a verifiable payload manifest.

This is not an MSIX installer or a clean-machine deployment acceptance. Python,
AI dependencies/weights and Windows activation/runtime provisioning are separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from storage_lease import plain_path, storage_parent
from release_runtime import python_layout, media_layout, configure_embedded_python
from packaged_frontend import inspect_msix, copy_msix_payload, PACKAGE_PATH

PAYLOAD = ('Aredoko.WinUI.exe', 'Aredoko.WinUI.dll', 'Aredoko.Core.dll',
           'Aredoko.WinUI.deps.json', 'Aredoko.WinUI.runtimeconfig.json')


def compute_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def copy_payload(source, destination):
    """Do not follow junctions/symlinks into unrelated files during staging."""
    plain_path(source, directory=source.is_dir())
    if source.is_dir():
        destination.mkdir()
        for child in source.iterdir():
            if child.suffix.lower() != '.pdb':
                copy_payload(child, destination / child.name)
    else:
        shutil.copy2(source, destination)


def validate_output(output):
    # Validate lexical ancestors without resolve() hiding junctions. --check
    # does not create even the parent directories.
    current = output
    while not current.exists() and not current.is_symlink():
        if current.parent == current:
            raise ValueError('Output storage is unavailable')
        current = current.parent
    plain_path(current, directory=True)
    if output.exists() or output.is_symlink():
        raise FileExistsError('Choose a new output directory; existing files are never removed')


def package(output_dir, version='1.0.0', skip_build=False, dry_run=False, *, python_runtime=None, media_tools=None, include_ai_runtime=False, frontend_msix=None, portable_frontend=None, bootstrap=None):
    output_dir = Path(os.path.abspath(output_dir))
    validate_output(output_dir)
    if not isinstance(version, str) or not 1 <= len(version) <= 64 or any(ord(c) < 32 for c in version):
        raise ValueError('Invalid version label')
    required = [REPO / name for name in (
        'app/production_server.py', 'app/storage_schema_v1.json', 'THIRD_PARTY_NOTICES.md',
        'docs/user-guide.md', 'tools/start-aredoko.ps1', 'tools/native-arguments.ps1',
        'tools/backup_library.py', 'tools/release_runtime.py', 'tools/launch_release.py',
        'tools/probe_release_runtime.py', 'tools/startup_validation.py', 'tools/startup_progress.py', 'tools/startup_ipc.py', 'tools/portable_frontend.py', 'tools/packaged_frontend.py', 'tools/install-release-shortcut.ps1')]
    for path in required:
        plain_path(path)
    binary = REPO / 'src/Aredoko.WinUI/bin/x64/Release/net10.0-windows10.0.26100.0/win-x64'
    if include_ai_runtime and python_runtime is None:
        raise ValueError('--include-ai-runtime requires --python-runtime')
    python_runtime = Path(os.path.abspath(python_runtime)) if python_runtime is not None else None
    media_tools = Path(os.path.abspath(media_tools)) if media_tools is not None else None
    frontend_msix = Path(os.path.abspath(frontend_msix)) if frontend_msix is not None else None
    frontend = inspect_msix(frontend_msix) if frontend_msix is not None else None
    portable_frontend = Path(os.path.abspath(portable_frontend)) if portable_frontend is not None else None
    bootstrap = Path(os.path.abspath(bootstrap)) if bootstrap is not None else None
    if (portable_frontend is None) != (bootstrap is None):raise ValueError('Portable publish and bootstrap must be supplied together')
    if portable_frontend is not None:
        if frontend_msix is not None or python_runtime is None or media_tools is None:
            raise ValueError('Portable requires Python/media and cannot use an MSIX')
        from portable_frontend import inspect_portable, inspect_bootstrap
        inspect_portable(portable_frontend)
        inspect_bootstrap(bootstrap)
        binary = portable_frontend
    activation = 'portable' if portable_frontend is not None else 'msix' if frontend is not None else 'unconfigured'
    sources = [binary, REPO / 'app', REPO / 'config', REPO / 'docs', REPO / 'tools']
    sources += [p for p in (python_runtime, media_tools, frontend_msix, portable_frontend, bootstrap) if p is not None]
    for source in sources:
        if output_dir.is_relative_to(source) or source.is_relative_to(output_dir):
            raise ValueError('Output and payload source directories must not overlap')
    stem = python_layout(python_runtime, include_ai_runtime) if python_runtime is not None else None
    if media_tools is not None:media_layout(media_tools)
    if frontend is None and portable_frontend is None and not skip_build and not dry_run:
        built = subprocess.run(['dotnet', 'build', 'src/Aredoko.WinUI/Aredoko.WinUI.csproj',
            '-c', 'Release', '-p:Platform=x64', '-p:SelfContained=true', '--no-restore'],
            cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if built.returncode:
            raise RuntimeError('WinUI staging build failed\n' + built.stdout + built.stderr)
    if frontend is None:
        for name in PAYLOAD:
            plain_path(binary / name)
    if dry_run:
        return {'version': version, 'dry_run': True, 'pass': True,
                'readiness': 'staging-only', 'frontend_activation': activation, 'python_bundled': python_runtime is not None,
                'ai_runtime_bundled': include_ai_runtime, 'media_tools_bundled': media_tools is not None,
                'runtime_imports_verified': False, 'clean_machine_activation_verified': False}

    # Exclusive creation is the reservation. Failure leaves an incomplete new
    # staging directory, never a recursive deletion of an existing directory.
    validate_output(output_dir)
    storage_parent(output_dir)
    output_dir.mkdir()
    plain_path(output_dir, directory=True)
    bin_dir = output_dir / 'bin'; bin_dir.mkdir()
    backend = output_dir / 'backend'; backend.mkdir()
    app_dir = backend / 'app'; app_dir.mkdir()
    config_dir = backend / 'config'; config_dir.mkdir()
    tools_dir = output_dir / 'tools'; tools_dir.mkdir()
    if frontend is not None:
        copy_msix_payload(frontend_msix, bin_dir, frontend)
    else:
        for item in binary.iterdir():
            if item.suffix.lower() != '.pdb' and item.name.lower() not in ('appx', 'publish'):
                copy_payload(item, bin_dir / item.name)
    for item in (REPO / 'app').iterdir():
        if item.is_file() and item.suffix in ('.py', '.json'):
            copy_payload(item, app_dir / item.name)
    for sub in ('ai-profiles', 'profiles', 'tagger-profiles', 'acquisition'):
        source = REPO / 'config' / sub
        if source.exists():
            copy_payload(source, config_dir / sub)
    for name in ('start-aredoko.ps1', 'native-arguments.ps1'):
        copy_payload(REPO / 'tools' / name, output_dir / name)
    for name in ('backup_library.py', 'release_runtime.py', 'launch_release.py', 'probe_release_runtime.py', 'startup_validation.py', 'startup_progress.py', 'startup_ipc.py', 'portable_frontend.py', 'packaged_frontend.py'):
        copy_payload(REPO / 'tools' / name, tools_dir / name)
    if portable_frontend is None:
        copy_payload(REPO / 'tools/install-release-shortcut.ps1', output_dir / 'install-release-shortcut.ps1')
    if frontend_msix is not None:
        (output_dir / 'frontend').mkdir()
        copy_payload(frontend_msix, output_dir / PACKAGE_PATH)
    if python_runtime is not None or media_tools is not None:
        runtime_dir = output_dir / 'runtime'; runtime_dir.mkdir()
        if python_runtime is not None:
            copy_payload(python_runtime, runtime_dir / 'python')
            configure_embedded_python(runtime_dir / 'python', stem)
        if media_tools is not None:
            copy_payload(media_tools, runtime_dir / 'media')
    copy_payload(REPO / 'THIRD_PARTY_NOTICES.md', output_dir / 'THIRD_PARTY_NOTICES.md')
    docs_dir = output_dir / 'docs'; docs_dir.mkdir()
    for source in (REPO / 'docs').glob('*.md'):
        copy_payload(source, docs_dir / source.name)
    if portable_frontend is None:
        (output_dir / 'USER_GUIDE.md').write_text('# Aredoko\n\n[利用ガイド](docs/user-guide.md)\n', encoding='utf-8')
        (output_dir / 'Aredoko.cmd').write_text(
            '@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-aredoko.ps1" %*\r\n', encoding='utf-8')
        (output_dir / 'Install-Shortcut.cmd').write_text(
            '@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-release-shortcut.ps1"\r\nif errorlevel 1 pause\r\n', encoding='utf-8')
    else:
        (output_dir / 'USER_GUIDE.md').write_text(
            '# Aredoko を使い始める\n\n'
            'ZIPをすべて解凍し、Aredoko.exeを開いてください。バックエンドは一緒に起動します。\n\n'
            '初めての方は [はじめに.txt](はじめに.txt)、詳しい使い方は [利用ガイド](docs/user-guide.md) をご覧ください。\n\n'
            '通常はCheck-Startup.cmdを使う必要はありません。起動できないときの診断用で、専用の空のライブラリを使います。\n', encoding='utf-8')
        (output_dir / 'はじめに.txt').write_text(
            'Aredoko を使い始める\n'
            '===================\n\n'
            '1. ZIPをすべて解凍する\n'
            '   ZIPの中から直接起動せず、解凍したフォルダを開いてください。\n\n'
            '2. Aredoko.exeを開く\n'
            '   起動中は進捗が表示されます。Pythonやバックエンドを別に起動する必要はありません。\n\n'
            '3. フォルダを追加して、アイテム一覧を読み込む\n'
            '   フォルダの登録後、一覧だけの読み込みか、AI索引の作成も行うかを選べます。\n'
            '   後から行う場合は「登録フォルダ」の設定から読み込めます。\n\n'
            '4. 検索・閲覧・整理を試す\n'
            '   まず「ファイル名・タグ」で検索できます。ダブルクリックで対応するビューアが開きます。\n'
            '   右クリックや「詳細」からタグ・棚・お気に入りを編集できます。\n\n'
            'AI検索を使うには\n'
            '   モデルとAI実行環境が別途必要です。「設定」のAI検索の準備から、取得や既存配置の案内を確認してください。\n'
            '   AIを準備しなくても、ファイル名・タグ検索や整理・閲覧は利用できます。\n\n'
            '更新するときは\n'
            '   Aredokoを終了し、新しいZIPを別のフォルダへ解凍してAredoko.exeを開きます。\n'
            '   登録情報・タグ・棚・設定は、既定ではユーザーデータ領域に保存され、配布フォルダとは分かれています。\n'
            '   大切な登録情報は、更新前に設定のバックアップから保存できます。\n\n'
            '起動できないときだけ\n'
            '   Check-Startup.cmdで、専用の空のライブラリによる起動確認ができます。普段の作品が出ないのはこのためです。\n'
            '   通常利用ではAredoko.exeへ戻ってください。エラーが出た場合は、表示された内容とログの場所を控えてください。\n\n'
            '詳しい使い方：docs\\user-guide.md\n', encoding='utf-8-sig')
        (output_dir / 'Aredoko.cmd').write_text('@echo off\r\nstart "" "%~dp0Aredoko.exe" %*\r\n', encoding='ascii')
    if portable_frontend is not None:
        copy_payload(bootstrap, output_dir / 'Aredoko.exe')
        (output_dir / 'Check-Startup.cmd').write_text('@echo off\r\nstart "" "%~dp0Aredoko.exe" --startup-check\r\n', encoding='ascii')
    entries = []
    for path in sorted(output_dir.rglob('*')):
        if path.is_file():
            plain_path(path)
            entries.append({'path': path.relative_to(output_dir).as_posix(),
                            'bytes': path.stat().st_size, 'sha256': compute_sha256(path)})
    manifest = {'format': 'aredoko-release-manifest', 'version': version,
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'platform': 'windows-x64', 'files_count': len(entries),
                'total_bytes': sum(e['bytes'] for e in entries), 'entries': entries,
                'readiness': 'staging-only', 'frontend_activation': activation, 'python_bundled': python_runtime is not None, 'ai_runtime_bundled': include_ai_runtime,
                'media_tools_bundled': media_tools is not None, 'runtime_imports_verified': False,
                'models_bundled': False,
                'clean_machine_activation_verified': False}
    (output_dir / 'sha256sums.txt').write_text(''.join(
        f"{e['sha256']}  {e['path']}\n" for e in entries), encoding='utf-8')
    # Publish the completion marker last. No template databases or models are
    # collected, checkpointed or mutated by this packaging tool.
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'output': str(output_dir), 'files': len(entries), 'readiness': 'staging-only'}))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=REPO / 'dist/aredoko-release-windows-x64')
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--check', action='store_true', help='Validate a new destination and existing build without writing or launching')
    parser.add_argument('--python-runtime', type=Path, help='Explicit prepared standalone Windows Python directory; never downloaded')
    parser.add_argument('--media-tools', type=Path, help='Explicit FFmpeg/ffprobe directory with LICENSE.txt; never downloaded')
    parser.add_argument('--include-ai-runtime', action='store_true', help='Require AI dependencies in the supplied Python runtime (no model copying)')
    parser.add_argument('--frontend-msix', type=Path, help='Explicit self-contained frontend MSIX; its published payload supplies bin. No install/signing')
    parser.add_argument('--portable-frontend', type=Path, help='Explicit Portable publish directory with build receipt')
    parser.add_argument('--bootstrap', type=Path, help='Built root Aredoko.exe for the portable channel')
    args = parser.parse_args()
    package(args.output_dir, args.version, args.skip_build, args.check,
            python_runtime=args.python_runtime, media_tools=args.media_tools, include_ai_runtime=args.include_ai_runtime, frontend_msix=args.frontend_msix,
            portable_frontend=args.portable_frontend, bootstrap=args.bootstrap)


if __name__ == '__main__':
    main()
