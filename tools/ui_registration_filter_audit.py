"""One UIA-only batch: partial registration and folder filtering on generated data."""
import hashlib
import json
import time
from pathlib import Path
from create_preview_fixture import png
from native_ui_tools import nodes


def prepare(target):
    folders = [target / 'filter-registration-alpha', target / 'filter-registration-beta']
    hashes = {}
    for index, folder in enumerate(folders):
        folder.mkdir()
        image = folder / ('fixture-%d.png' % index)
        image.write_bytes(png(width=32, height=32, color=(60 + index * 20, 90, 140)))
        hashes[str(image)] = hashlib.sha256(image.read_bytes()).hexdigest()
    return {'folders': [str(p) for p in folders], 'invalid': str(target / 'missing-folder'), 'hashes': hashes}


def audit(ui, tree, shot, report, check, catalog):
    fixture = report['registration_filter_fixture']
    alpha, beta = fixture['folders']; missing = fixture['invalid']
    ui('invoke', 'BtnRoots')
    ui('wait-for', 'LibraryHeading', '--value', '登録フォルダ', '-t', '10000')
    ui('wait-for', 'TxtCount', '--value', '表示 1 / 全 1 フォルダ', '-t', '10000')
    ui('invoke', 'BtnToggleAddFolder')
    ui('wait-for', 'RootPath', '-t', '10000')
    ui('set-value', 'RootPath', '; '.join((alpha, missing, beta)))
    ui('invoke', 'AddRoot')
    ui('wait-for', 'PostRegistrationScanDialog', '-t', '20000')
    ui('wait-for', 'ScanChoiceListOnly', '-t', '10000')
    ui('invoke', 'PrimaryButton')
    ui('wait-for', 'PostRegistrationScanDialog', '--gone', '-t', '20000')
    ui('wait-for', 'AddRoot', '-p', 'IsEnabled', '--value', 'True', '-t', '20000')
    ui('wait-for', 'RootPath', '--value', missing, '-t', '10000')
    roots = {str(Path(r['path']).resolve()): r for r in catalog.registered_roots()}
    check('two valid roots registered and failed path remains editable',
          alpha in roots and beta in roots and missing not in roots)
    a, b = roots[alpha]['id'], roots[beta]['id']
    state = json.loads(ui('inspect', 'StatusBar', '--depth', '12', '--json'))
    labels = ' '.join(str(n.get('name', '')) for n in nodes(state))
    check('partial registration warning identifies success and failure',
          '一部のフォルダを登録できませんでした' in labels and '1 件は未登録' in labels)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        scan = catalog.scan_state()
        if scan['state'] not in ('running', 'cancelling'): break
        time.sleep(.1)
    check('list-only scan completes for the two successful roots',
          scan['state'] == 'complete' and scan['mode'] == 'list'
          and set(scan['root_ids']) == {a, b})
    check('generated extra media appear in the catalog',
          all(any(row['title'] == 'fixture-%d.png' % i for row in catalog.search()['items']) for i in range(2)))
    shot('registration-partial-result')
    ui('invoke', 'CancelAddFolder')
    ui('wait-for', 'ChkFolder' + str(b), '-t', '10000')
    ui('invoke', 'ChkFolder' + str(b), '--action', 'toggle-on')
    ui('set-value', 'TxtFolderFilter', 'filter-registration-alpha')
    ui('wait-for', 'TxtCount', '--value', '表示 1 / 全 3 フォルダ', '-t', '10000')
    ui('wait-for', 'TxtFolderSelectionSummary', '--value', '選択中: 1 フォルダ', '--contains', '-t', '10000')
    ui('set-value', 'TxtFolderFilter', 'no-such-generated-folder')
    ui('wait-for', 'TxtCount', '--value', '表示 0 / 全 3 フォルダ', '-t', '10000')
    ui('wait-for', 'TxtFolderEmpty', '--value', '条件に一致するフォルダはありません', '--contains', '-t', '10000')
    shot('folder-filter-no-match')
    ui('invoke', 'BtnClearFolderFilters')
    ui('wait-for', 'TxtCount', '--value', '表示 3 / 全 3 フォルダ', '-t', '10000')
    ui('wait-for', 'ChkFolder' + str(b), '--value', 'On', '-t', '10000')
    check('filter reset restores all rows and retains hidden selection', True)
    check('generated extra originals are unchanged', all(
        hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in fixture['hashes'].items()))
    shot('folder-filter-reset')
    report['physical_input_requested'] = False
    report['unverified'] = ['physical keyboard and pointer input', 'high contrast and physical DPI', 'real user folders']
