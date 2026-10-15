"""Isolated native Windows validation for the Registered-Folder Hub & multi-root search.

Uses only generated sandbox media in data/ai-ui. Requires an existing Release
build and winapp CLI. No downloads, models, private folders, or CI dispatch.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
sys.path.insert(0, str(REPO / 'tools'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, revision
from ai_settings import AIProfileSettings
from create_preview_fixture import png
from production import ProductionCatalog, ScanBusyError
from production_server import production_handler


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


class NoModelEncoder:
    available = True
    resident = False
    device = 'cpu-contract'

    def __init__(self):
        from dataclasses import replace
        self.profile = replace(DEFAULT_PROFILE, dimension=3, modalities=('text', 'cover'))
        self.calls = 0

    def encode(self, operation, value):
        self.calls += 1
        return [1.0, 0.0, 0.0]

    def close(self):
        pass


class RecordedHubAI(AISearch):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_requests = []
        self.similar_requests = []

    def search(self, query, kind='', view='all', page=0, limit=60, source='all', scope=None, **kwargs):
        self.search_requests.append({'query': query, 'kind': kind, 'view': view, 'source': source, 'scope': scope})
        return super().search(query, kind=kind, view=view, page=page, limit=limit, source=source, scope=scope, **kwargs)

    def similar(self, item_id, kind='', view='all', page=0, limit=60, scope=None, **kwargs):
        self.similar_requests.append({'item_id': item_id, 'kind': kind, 'view': view, 'scope': scope})
        return super().similar(item_id, kind=kind, view=view, page=page, limit=limit, scope=scope, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Native Windows required')
    target = args.output.resolve()
    if not target.is_relative_to((REPO / 'data/ai-ui').resolve()) or target.exists():
        parser.error('Output must be a new folder inside data/ai-ui')
    existing = subprocess.run(
        ['powershell', '-NoProfile', '-Command', 'if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'],
        capture_output=True, timeout=15)
    if existing.returncode:
        parser.error('Close the existing Aredoko app before running this isolated test')

    target.mkdir(parents=True, exist_ok=False)
    server = ThreadingHTTPServer(('127.0.0.1', 8769), BaseHTTPRequestHandler)
    catalog = ai = thread = process = hwnd = app_pid = None
    report = {
        'runtime_pass': False,
        'visual_review': 'pending: inspect every screenshot',
        'actual_model': False,
        'checks': [],
        'screenshots': [],
        'ai_search_requests': [],
        'ai_similar_requests': [],
    }
    env = {**os.environ, 'WINAPP_UI_WORKFLOW_ID': 'aredoko-folder-hub-' + uuid.uuid4().hex}
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def check(name, value):
        if not value:
            raise RuntimeError(name)
        report['checks'].append(name)
        print(json.dumps({'check': name}, ensure_ascii=True), flush=True)

    def cli(*parts):
        result = subprocess.run(['winapp', *map(str, parts)], cwd=REPO, env=env, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError('winapp ' + str(parts) + ': ' + result.stdout + result.stderr)
        return result.stdout

    def ui(*parts, window=None):
        return cli('ui', *parts, '-w', window or hwnd)

    def wait(identifier, value):
        ui('wait-for', identifier, '--value', value, '-t', '12000')

    def ready():
        ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '12000')
        time.sleep(.2)

    def owned(handle=None, foreground=False):
        handle = handle or hwnd
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(int(handle), ctypes.byref(owner))
        if owner.value != app_pid or kernel32.WaitForSingleObject(process, 0) == 0:
            raise RuntimeError('Owned window/process changed')
        if foreground:
            if user32.GetForegroundWindow() != int(hwnd):
                user32.SetForegroundWindow(int(hwnd))
                time.sleep(.1)
            if user32.GetForegroundWindow() != int(hwnd):
                raise RuntimeError('Windows denied owned-window activation')

    def shot(name):
        owned()
        path = target / (name + '.png')
        ui('screenshot', '--output', path)
        check('screenshot ' + name, path.is_file() and path.stat().st_size > 0)
        report['screenshots'].append(path.name)

    def choose(combo_id, item_name):
        ui('invoke', combo_id)
        time.sleep(.25)
        windows = json.loads(cli('ui', 'list-windows', '-a', app_pid, '--json'))
        ordered = [w for w in windows if w.get('title') == 'PopupHost'] + [w for w in windows if str(w.get('hwnd')) == hwnd]
        for w in ordered:
            handle = str(w['hwnd'])
            owned(handle)
            tree = json.loads(ui('inspect', '--json', '--depth', '14', window=handle))
            for n in nodes(tree):
                if n.get('type') == 'ListItem' and (n.get('automationId') == item_name or n.get('name') == item_name):
                    target_sel = n.get('automationId') or n.get('selector') or item_name
                    ui('invoke', target_sel, window=handle)
                    time.sleep(.15)
                    return
        raise RuntimeError(f'Combo option {item_name} not found in {combo_id}')

    def context_similar(identifier, source_id):
        if identifier.startswith('Item'):
            ui('scroll-into-view', identifier)
        owned(foreground=True)
        ui('click', identifier, '--right')
        for _ in range(20):
            windows = json.loads(cli('ui', 'list-windows', '-a', app_pid, '--json'))
            ordered = [w for w in windows if w.get('title') == 'PopupHost'] + [w for w in windows if str(w.get('hwnd')) == hwnd]
            for w in ordered:
                handle = str(w['hwnd'])
                owned(handle)
                tree = json.loads(ui('inspect', '--json', '--depth', '14', window=handle))
                if any(n.get('automationId') == 'FindSimilar' + str(source_id) for n in nodes(tree)):
                    ui('invoke', 'FindSimilar' + str(source_id), window=handle)
                    return
            time.sleep(.1)
        raise RuntimeError('No similarity context menu for ' + str(source_id))

    def close():
        nonlocal process, hwnd, app_pid
        if process:
            try:
                if kernel32.WaitForSingleObject(process, 0) != 0:
                    owned()
                    user32.PostMessageW(int(hwnd), 0x0010, 0, 0)
                    if kernel32.WaitForSingleObject(process, 7000) != 0:
                        report['cleanup_terminated_owned_process'] = True
                        kernel32.TerminateProcess(process, 1)
                    else:
                        report['graceful_closes'] = report.get('graceful_closes', 0) + 1
            finally:
                kernel32.CloseHandle(process)
                process = hwnd = app_pid = None

    try:
        media = target / 'media'
        # Create 3 roots with same leaf name 'works' under branch-a, branch-b, branch-c
        folders = {k: media / f'branch-{k}' / 'works' for k in ('a', 'b', 'c')}
        for idx, (k, folder) in enumerate(folders.items(), start=1):
            folder.mkdir(parents=True)
            for n in range(1, 3):
                (folder / f'{k}-item-{n}.png').write_bytes(png(60, 80, (200 if k != 'c' else 30, 40, 200 if k == 'c' else 40)))
        def source_digest():
            return {p.relative_to(media).as_posix(): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in media.rglob('*') if p.is_file()}
        source_before = source_digest()

        catalog = ProductionCatalog(target / 'catalog.sqlite')
        ra = catalog.add_root(str(folders['a']), default_shelf='AI画像', excludes=['*.tmp-a'])
        rb = catalog.add_root(str(folders['b']), default_shelf='', excludes=['*.tmp-b'])
        rc = catalog.add_root(str(folders['c']), default_shelf='背景', excludes=['*.tmp-c'])
        for r in (ra, rb, rc):
            catalog.start_scan(r)
            catalog._worker.join(10)
            check(f'scan root {r}', catalog.scan_state()['state'] == 'complete')

        # Set a custom manual shelf on the first item of root A so we can verify individual shelf preservation
        a_items = catalog.search(root_id=ra)['items']
        catalog.update([a_items[0]['id']], {'shelf': '手動確定棚', 'tags': ['霊夢']})
        b_items = catalog.search(root_id=rb)['items']
        catalog.update([b_items[0]['id']], {'tags': ['霊夢']})
        c_items = catalog.search(root_id=rc)['items']
        catalog.update([c_items[0]['id']], {'tags': ['霊夢']})

        encoder = NoModelEncoder()
        ai = RecordedHubAI(catalog, encoder)
        for row in catalog.search(limit=60)['items']:
            row_full = catalog.get(row['id'])
            ai.store.put(row['id'], revision(row_full), {'text': [1.0, 0.0, 0.0], 'cover': [1.0, 0.0, 0.0]})

        # Saved AI scope covers all roots initially
        settings_path = target / 'settings.json'
        settings_path.write_text(json.dumps({'version': 1, 'profile': 'default', 'scope': {'root_ids': [ra, rb, rc], 'kind': '', 'shelf': None}}), encoding='utf-8')
        settings_before = settings_path.read_bytes()
        profiles = AIProfileSettings(REPO, settings_path)

        faultState = {'fail_shelf_root': None}
        orig_set_root_shelf = catalog.set_root_shelf
        def hooked_set_root_shelf(root_id, shelf, fill_unset=False):
            if faultState['fail_shelf_root'] == root_id:
                faultState['fail_shelf_root'] = None
                raise ScanBusyError('Scan in progress; retry after it completes')
            return orig_set_root_shelf(root_id, shelf, fill_unset)
        catalog.set_root_shelf = hooked_set_root_shelf

        base_handler = production_handler(catalog, secrets.token_urlsafe(32), ai=ai, profiles=profiles)
        server.RequestHandlerClass = base_handler
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        for theme in ('Light', 'Dark'):
            launch = json.loads(cli(
                'run', 'src/Aredoko.WinUI', '-c', 'Release', '--arch', 'x64',
                '-p', 'Platform=x64', '-p', 'SelfContained=true', '--no-build',
                '--output-appx-directory', target / ('layout-' + theme.lower()),
                '--detach', '--json', '--args', '--ui-theme ' + theme.lower()))
            app_pid = int(launch['ProcessId'])
            process = kernel32.OpenProcess(0x00100001, False, app_pid)
            for _ in range(50):
                windows = json.loads(cli('ui', 'list-windows', '-a', app_pid, '--json'))
                matches = [w for w in windows if w.get('hwnd') and 'Aredoko' in w.get('title', '') and w.get('title') != 'PopupHost']
                if len(matches) == 1:
                    break
                time.sleep(.1)
            hwnd = str(matches[0]['hwnd'])
            user32.SetWindowPos(int(hwnd), None, 0, 0, 1200, 820, 0x0014)
            ready()
            wait('TxtCount', '6 件')

            # 1. Verify left nav has only single NavFolders entry, not per-root NavRoot1/2/3
            tree = json.loads(ui('inspect', '--json', '--depth', '12'))
            all_ids = {n.get('automationId') for n in nodes(tree) if n.get('automationId')}
            check(theme + ' compact left nav has NavFolders without per-root items',
                  'NavFolders' in all_ids and not any(str(x).startswith('NavRoot') for x in all_ids))

            # 2. Open Registered-Folder Hub via NavFolders
            ui('invoke', 'NavFolders', '--action', 'select')
            wait('TxtCount', '3 フォルダ')
            ui('wait-for', 'BtnSearchSelectedFolders', '-p', 'IsEnabled', '--value', 'False', '-t', '5000')
            check(theme + ' 0 selected folders disables SearchSelectedFolders', True)
            shot(theme + '-folder-hub-list')

            # 3. Filter folders by distinguishable short path and toggle Grid/List while keeping selection
            ui('invoke', f'ChkFolder{ra}')
            wait('TxtFolderSelectionSummary', '選択中: 1 フォルダ（branch-a/works）')
            ui('set-value', 'TxtFolderFilter', 'branch-b')
            wait('TxtCount', '1 フォルダ')
            ui('invoke', f'ChkFolder{rb}')
            wait('TxtFolderSelectionSummary', '選択中: 2 フォルダ（branch-a/works、branch-b/works）')
            ui('set-value', 'TxtFolderFilter', '')
            wait('TxtCount', '3 フォルダ')
            ui('invoke', 'BtnFolderLayout')
            shot(theme + '-folder-hub-grid')
            ui('invoke', 'BtnFolderLayout')
            check(theme + ' filter and layout toggle preserve multi-folder selection', True)

            # 4. Single-folder browse ("中を見る") and return to hub
            ui('invoke', f'OpenFolder{ra}')
            ready()
            wait('TxtCount', '2 件')
            ui('invoke', 'ExpandSearchOptions')
            wait('TxtActiveSearchScope', '検索対象: branch-a/works（1 フォルダ）')
            ui('invoke', 'BtnChangeSearchFolders')
            wait('TxtCount', '3 フォルダ')
            wait('TxtFolderSelectionSummary', '選択中: 2 フォルダ（branch-a/works、branch-b/works）')
            check(theme + ' single-folder browse and hub return preserve selection', True)

            # 5. Multi-root search (A + B out of A, B, C) across Literal, AI, and Similarity search
            ui('invoke', 'BtnSearchSelectedFolders')
            ready()
            wait('TxtCount', '4 件')
            check(theme + ' literal multi-root search returns union A+B excluding C', True)

            # Switch to AI Visual search on '霊夢' with A+B selected
            ui('set-value', 'TxtQuery', '霊夢')
            time.sleep(.35)
            choose('CmbSearchMode', 'ModeVisual')
            ui('invoke', 'BtnSearch')
            ready()
            wait('TxtCount', '4 件')
            check(theme + ' AI search uses selected multi-root union A+B',
                  ai.search_requests[-1]['scope']['root_ids'] == [ra, rb])

            # Similarity search from item in root A while A+B is active, then return
            origin_id = a_items[0]['id']
            context_similar(f'Item{origin_id}', origin_id)
            ready()
            wait('TxtCount', '3 件')  # 4 items in A+B minus origin_id itself = 3
            check(theme + ' similarity search honors multi-root union A+B and self-exclusion',
                  ai.similar_requests[-1]['scope']['root_ids'] == [ra, rb])
            shot(theme + '-multiroot-similarity')
            owned(foreground=True)
            ui('invoke', 'BtnSimilarityBack')
            ready()
            wait('TxtCount', '4 件')
            choose('CmbSearchMode', 'ModeLiteral')
            ui('set-value', 'TxtQuery', '')
            time.sleep(.35)
            ui('invoke', 'BtnSearch')
            ready()
            wait('TxtCount', '4 件')
            check(theme + ' similarity return restores multi-root selection A+B', True)

            if theme == 'Light':
                # 6. Batch initial-shelf editing: mixed values, KeepExisting no-op, partial failure & retry
                ui('invoke', 'BtnRoots')
                wait('TxtCount', '3 フォルダ')
                ui('invoke', 'BtnEditSelectedFolders')
                wait('TxtCurrentShelfSummary', '現在の初期棚: 複数の設定値')
                wait('TxtFolderEditStatus', '設定保存済み')
                shot('Light-batch-settings-mixed')

                # Saving without changing KeepExisting does not overwrite A or B
                ui('invoke', 'SaveRootShelf')
                wait('TxtFolderEditStatus', '変更された初期棚項目はありません（現在の設定を維持しました）。')
                roots_now = {r['id']: r['default_shelf'] for r in catalog.index.roots()}
                check('KeepExisting batch save preserves distinct shelves',
                      roots_now[ra] == 'AI画像' and roots_now[rb] == '')

                # Dirty discard check when switching from batch (A+B) to single (C)
                choose('RootInitialShelf', '新しい棚を作成')
                ui('set-value', 'RootNewShelf', '共通素材棚')
                wait('TxtFolderEditStatus', '未保存の設定変更')
                ui('invoke', f'ConfigFolder{rc}')
                ui('wait-for', 'PrimaryButton', '-t', '5000')
                ui('invoke', 'CloseButton')
                wait('RootNewShelf', '共通素材棚')
                check('Cancelling folder settings discard keeps unsaved batch draft', True)

                # Save batch shelf with FillUnset and simulated busy failure on root B, then retry
                ui('invoke', 'FillUnsetShelf')
                faultState['fail_shelf_root'] = rb
                ui('invoke', 'SaveRootShelf')
                ui('wait-for', 'SaveRootShelf', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
                check('Partial batch failure saves root A and keeps root B for retry',
                      {r['id']: r['default_shelf'] for r in catalog.index.roots()}[ra] == '共通素材棚'
                      and {r['id']: r['default_shelf'] for r in catalog.index.roots()}[rb] == '')
                # Retry saves remaining root B without re-failing
                ui('invoke', 'SaveRootShelf')
                ui('wait-for', 'SaveRootShelf', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
                wait('TxtFolderEditStatus', '設定保存済み')
                wait('ScanStatus', '初期棚を保存しました。既存の棚未設定ファイル2件に適用。')
                check('Retry applies to remaining root B and preserves manual item shelf on A',
                      {r['id']: r['default_shelf'] for r in catalog.index.roots()}[rb] == '共通素材棚'
                      and catalog.get(a_items[0]['id'])['shelf'] == '手動確定棚'
                      and catalog.get(a_items[1]['id'])['shelf'] == 'AI画像'
                      and catalog.get(b_items[1]['id'])['shelf'] == '共通素材棚')

                # 7. Unregister root B and restore from inactive filter, keeping manual tags/shelves
                ui('invoke', f'ConfigFolder{rb}')
                ui('scroll-into-view', 'UnregisterConsent')
                ui('invoke', 'UnregisterConsent')
                ui('scroll-into-view', 'UnregisterRoot')
                ui('invoke', 'UnregisterRoot')
                wait('TxtCount', '2 フォルダ')
                choose('CmbFolderState', 'FolderStateInactive')
                wait('TxtCount', '1 フォルダ')
                shot('Light-folder-inactive')
                ui('invoke', f'RestoreFolder{rb}')
                wait('RootPath', str(folders['b']))
                ui('invoke', 'RootConsent')
                ui('invoke', 'AddRoot')
                choose('CmbFolderState', 'FolderStateActive')
                wait('TxtCount', '3 フォルダ')
                check('Restored root B keeps manual tags and shelf',
                      catalog.get(b_items[0]['id'])['tags'] == ['霊夢']
                      and catalog.get(b_items[0]['id'])['shelf'] == '共通素材棚')

            # Narrow 700x620 screenshot in Folder Hub
            if not theme == 'Light':
                ui('invoke', 'BtnRoots')
                wait('TxtCount', '3 フォルダ')
            user32.SetWindowPos(int(hwnd), None, 0, 0, 700, 620, 0x0014)
            time.sleep(.3)
            shot(theme + '-folder-hub-narrow')
            close()

        check('source bytes/mtime unchanged', source_before == source_digest())
        check('saved settings unchanged', settings_before == settings_path.read_bytes())
        check('no model resident', not encoder.resident)
        report['ai_search_requests'] = ai.search_requests
        report['ai_similar_requests'] = ai.similar_requests
        report['runtime_pass'] = True
    except Exception as ex:
        report['error'] = str(ex)
        if hwnd:
            try:
                shot('failure')
            except Exception:
                pass
        raise
    finally:
        try:
            close()
        finally:
            if thread:
                server.shutdown()
                thread.join(5)
            server.server_close()
            if ai:
                ai.close()
            if catalog:
                catalog.close()
            if target.exists():
                (target / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            try:
                cli('ui', 'yield')
            except Exception:
                pass
    print(json.dumps({'runtime_pass': report['runtime_pass'], 'checks': len(report['checks']), 'screenshots': len(report['screenshots'])}))


if __name__ == '__main__':
    main()
