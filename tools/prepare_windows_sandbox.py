"""Prepare a manual Windows Sandbox session for a sealed basic release.

Only writes a new ignored configuration/evidence directory; never launches it.
Schema: https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file
"""
import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from release_runtime import MANAGED_PYTHON, digest, ordinary_tree, verify_release
from storage_lease import plain_path, storage_parent

REPO = Path(__file__).resolve().parents[1]


def prepare(release, validation_kit, output, *, managed_python_download=False):
    release = plain_path(release, directory=True)
    validation_kit = plain_path(validation_kit, directory=True)
    output = Path(os.path.abspath(output))
    allowed = REPO / 'data/ai-ui'
    if output == allowed or not output.is_relative_to(allowed):
        raise ValueError('Choose a new output directory under data/ai-ui')
    for source in (release, validation_kit):
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('Output must not overlap the release or validation kit')
    if release.is_relative_to(validation_kit) or validation_kit.is_relative_to(release):
        raise ValueError('Release and validation kit must be independent directories')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Choose a new output directory; existing files are never removed')

    manifest = verify_release(release)
    if (manifest.get('frontend_activation') != 'portable'
            or manifest.get('ai_runtime_bundled') is not False
            or manifest.get('models_bundled') is not False):
        raise ValueError('A sealed portable basic release is required')
    if managed_python_download and (manifest.get('managed_python') != MANAGED_PYTHON
                                    or manifest.get('python_bundled') is not False):
        raise ValueError('The download trial requires a managed Python release without bundled Python')
    # Reject linked descendants before exposing a whole kit directory to a guest.
    for _ in ordinary_tree(validation_kit):
        pass
    candidate = json.loads(plain_path(validation_kit / 'candidate.json').read_text(encoding='utf-8'))
    if not isinstance(candidate, dict) or candidate.get('manifest_sha256') != digest(release / 'manifest.json'):
        raise ValueError('Validation kit manifest does not match the selected release')
    if candidate.get('zip_sha256') is not None:
        archive = plain_path(release.parent / 'Aredoko-windows-x64.zip')
        if candidate['zip_sha256'] != digest(archive):
            raise ValueError('Validation kit application ZIP does not match the selected release')

    evidence = output / 'evidence'
    configuration = ET.Element('Configuration')
    for option in ('vGPU', 'ClipboardRedirection', 'AudioInput', 'VideoInput', 'PrinterRedirection'):
        ET.SubElement(configuration, option).text = 'Disable'
    ET.SubElement(configuration, 'Networking').text = 'Enable' if managed_python_download else 'Disable'
    mappings = ET.SubElement(configuration, 'MappedFolders')
    for host, guest, readonly in (
            (release, r'C:\Aredoko', True),
            (validation_kit, r'C:\AredokoValidation', True),
            (evidence, r'C:\AredokoEvidence', False)):
        mapping = ET.SubElement(mappings, 'MappedFolder')
        ET.SubElement(mapping, 'HostFolder').text = str(host)
        ET.SubElement(mapping, 'SandboxFolder').text = guest
        ET.SubElement(mapping, 'ReadOnly').text = str(readonly).lower()
    ET.SubElement(ET.SubElement(configuration, 'LogonCommand'), 'Command').text = r'explorer.exe C:\Aredoko'
    ET.indent(configuration)

    storage_parent(output)
    output.mkdir()
    plain_path(output, directory=True)
    evidence.mkdir()
    target = output / 'Aredoko.wsb'
    ET.ElementTree(configuration).write(target, encoding='utf-8', xml_declaration=True)
    if managed_python_download:
        trial = (
            '起動前に、ゲストのPython・.NET SDKの有無と %LOCALAPPDATA%\\Aredoko が未作成であることを記録してください。'
            'ゲストに基本環境のファイルを先に持ち込まず、通常EXEから公式のCPythonとPillowの取得・構築を確認します。'
            '読み取り専用で展開済みの候補を使い、生成素材チェックリストの手順2〜3で生成素材3件の一覧表示まで確認します。'
            'AI環境やモデルの取得は省略します。'
            '結果と %LOCALAPPDATA%\\Aredoko\\logs の起動ログを証拠に残してください。\n'
            'この構成ではゲストのネットワークを有効にします。\n'
        )
    else:
        trial = 'AIや追加runtimeは取得せず、結果は実際に確認した項目だけ記録します。\nネットワークは無効です。\n'
    (output / 'README.txt').write_text(
        'Aredoko Windows Sandbox 手動確認\n\n'
        'Sandbox有効化が3010（再起動待ち）で終わった場合、Windowsを再起動してからAredoko.wsbを開いてください。'
        'このツールは再起動やSandbox起動を行いません。\n'
        'ゲストではC:\\Aredokoが開きます。'
        '通常のAredoko.exeとC:\\AredokoValidation\\はじめに.txtの生成素材チェックリストを使います。\n'
        + trial +
        'アプリと検証セットは読み取り専用です。result-template.jsonをC:\\AredokoEvidenceへコピーして編集してください。'
        '配置変更の確認はゲスト内の別フォルダへアプリ一式をコピーして行います。\n'
        'ゲストのデータはSandbox終了時に消えます。閉じる前に結果と必要なログをC:\\AredokoEvidenceへ保存してください。'
        'このフォルダだけがホストのevidenceフォルダへ書き戻されます。\n'
        'クリップボード、vGPU、音声入力、映像入力、プリンター共有は無効です。\n'
        'この設定の準備はclean Windowsでの動作合格を意味しません。\n\n'
        '設定形式: https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file\n',
        encoding='utf-8-sig')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--validation-kit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--managed-python-download', action='store_true',
                        help='Enable guest networking for the managed Python first-run trial')
    args = parser.parse_args()
    configuration = prepare(args.release, args.validation_kit, args.output,
                            managed_python_download=args.managed_python_download)
    print(json.dumps({'configuration': str(configuration), 'clean_windows_verified': False}))


if __name__ == '__main__':
    main()
