"""Bounded R02/R03 CUDA/native acceptance. Existing weights, generated media only.

Run gpu first in a NEW data/ai-ui directory, then gui against that same run.
No quality tuning, private media, downloads or overwrite of existing recovery data.
The native stage exercises the actual development launcher and restored settings.
"""
import argparse
import ctypes
from ctypes import wintypes
from http.server import ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler
from storage_backup import backup, restore
from create_preview_fixture import png
from test_index_gpu_scaling import MeasuredEncoder, owned_tree
from test_index_gpu_api import vector_digest


def media_hashes(root):
    return {str(p.relative_to(root)): [hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns]
            for p in root.rglob('*') if p.is_file()}


class Run:
    def __init__(self, target, stage, attempt=1):
        self.target = target
        self.stage = stage
        self.attempt = attempt
        self.native = target / f'native-{attempt:02}'
        self.report = {'pass': False, 'stage': stage, 'attempt': attempt, 'checks': [], 'screenshots': [],
                       'visual_review': 'pending' if stage == 'gui' else 'not_applicable',
                       'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
                       'generated_sources_only': True, 'actual_model': True,
                       'audit_scope': 'R02 request/full-pool shape; R03 same-host offline restore and native launcher'}

    def check(self, name, condition):
        self.report['checks'].append({'name': name, 'pass': bool(condition)})
        print(json.dumps({'check': name, 'pass': bool(condition)}), flush=True)
        if not condition:
            raise RuntimeError(name)

    def api(self, route, body=None, expected=200):
        request = urllib.request.Request(self.origin + route,
            None if body is None else json.dumps(body, ensure_ascii=False).encode(),
            headers={**getattr(self, 'headers', {}), 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload, code = json.load(response), response.status
        except urllib.error.HTTPError as error:
            with error:
                payload, code = json.load(error), error.code
        if code != expected:
            raise RuntimeError(f'{route}: HTTP {code}, expected {expected}: {payload}')
        return payload

    def wait(self, predicate, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.1)
        raise TimeoutError('Bounded acceptance wait')

    def gpu(self):
        media = self.target / 'generated sources'
        media.mkdir()
        folders = [media / 'root-a', media / 'root-b']
        for number, folder in enumerate(folders):
            folder.mkdir()
            for index, color in enumerate(((40, 70 + number * 60, 190), (180, 65 + number * 60, 40))):
                (folder / f'asset-{number}-{index}.png').write_bytes(png(color=color))
        with zipfile.ZipFile(folders[0] / 'book.cbz', 'w') as book:
            for index, color in enumerate(((75, 110, 185), (200, 180, 50), (50, 160, 90))):
                book.writestr(f'page-{index}.png', png(color=color))
        original = media_hashes(media)
        (self.target / 'source-hashes.json').write_text(json.dumps(original), encoding='utf-8')
        source = self.target / 'original library'
        source.mkdir()
        profiles = source / 'profiles'
        profiles.mkdir()
        (profiles / 'recovery.json').write_text(json.dumps({**DEFAULT_PROFILE.to_dict(), 'label': 'Recovery CUDA fixture'}), encoding='utf-8')
        settings = source / 'ai-settings.json'
        viewer = source / 'viewer-settings.json'
        viewer.write_text('{"version":1,"wheel_up_advances":true}', encoding='utf-8')
        catalog = ProductionCatalog(source / 'catalog.sqlite')
        ai = server = http_thread = query_thread = encoder = None
        gate = threading.Event()
        try:
            roots = []
            for folder in folders:
                root = catalog.add_root(str(folder))
                roots.append(root)
                catalog.start_scan(root)
                catalog._worker.join(15)
            rows = catalog.search()['items']
            book = next(row for row in rows if row['kind'] == 'book')
            image = next(row for row in rows if row['title'] == 'asset-0-0.png')
            catalog.update([image['id']], {'tags': ['recovery-proof'], 'shelf': '復旧確認', 'reviewed': True})
            catalog.record_view(image['id'])
            settings.write_text(json.dumps({'version': 1, 'profile': 'local:recovery.json',
                'scope': {'root_ids': roots, 'kind': '', 'shelf': None},
                'resource': {'idle_release_seconds': 0, 'index_pause_ms': 0}}), encoding='utf-8')
            preferences = AIProfileSettings(REPO, settings, profile_directory=profiles)
            encoder = MeasuredEncoder()
            ai = AISearch(catalog, encoder)
            self.check('five generated items, isolated restored profile', len(rows) == 5 and not preferences.startup_error)
            token = secrets.token_urlsafe(32)
            server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(catalog, token, ai=ai, profiles=preferences))
            http_thread = threading.Thread(target=server.serve_forever, daemon=True)
            http_thread.start()
            self.origin = f'http://127.0.0.1:{server.server_port}'
            self.headers = {'Origin': self.origin, 'X-Aredoko-Token': token}
            self.api('/api/library/ai/index', {})
            ai.worker.join(180)
            self.check('five real CUDA text/cover indexes', ai.status()['state'] == 'complete' and ai.status()['indexed'] == 5 and encoder.device == 'cuda')
            snapshot = ai.pages.index.refresh(book['id'])
            snapshot = ai.pages.index.list(book['id'])
            revision = snapshot['source_revision']
            self.api('/api/library/ai/pages', {'item_id': book['id'], 'page_ids': [p['page_id'] for p in snapshot['pages']], 'revision': revision, 'scope': {}})
            ai.worker.join(180)
            self.check('three real CUDA internal pages', ai.status()['state'] == 'complete' and ai.pages.coverage(book['id'], revision, {})['indexed_pages'] == 3)
            manifest = ai.previews.manifest(book['id'])
            catalog.save_reader_progress(book['id'], {'revision': manifest['revision'], 'page': 1, 'mode': 'single'}, ai.previews)
            results = {}
            for mode in ('all', 'cover', 'text'):
                request_id = self.api('/api/library/ai/searches/prepare', {})['request_id']
                result = self.api('/api/library/ai/search', {'request_id': request_id, 'query': '青い画像', 'source': mode})
                self.check(mode + ' complete pool and owned echo', result['request_id'] == request_id and result['search_complete'] and result['search_candidate_total'] == 5 and result['indexed_total'] == 5 and result['total'] == 5)
                results[mode] = [(r['id'], r['semantic_score']) for r in result['items']]
                self.check(mode + ' completed request cannot cancel another', not self.api('/api/library/ai/searches/cancel', {'request_id': request_id})['cancel_requested'])
            scoped = self.api('/api/library/ai/search', {'query': '青い画像', 'source': 'cover', 'scope': {'root_ids': [roots[1]]}})
            self.check('real CUDA root scope stays isolated', scoped['search_candidate_total'] == 2 and {r['root_id'] for r in scoped['items']} == {roots[1]})
            similar = self.api('/api/library/ai/similar', {'item_id': image['id']})
            self.check('saved image-origin similarity full pool', similar['search_complete'] and similar['total'] == 4 and image['id'] not in [r['id'] for r in similar['items']])
            cancelled_id = self.api('/api/library/ai/searches/prepare', {})['request_id']
            self.check('cancel before query accepted', self.api('/api/library/ai/searches/cancel', {'request_id': cancelled_id})['cancel_requested'])
            result = self.api('/api/library/ai/search', {'request_id': cancelled_id, 'query': '青い画像'}, expected=409)
            self.check('cancelled reservation not resurrected', result.get('error_code') == 'search_request_unavailable')
            # Only test scheduling is gated; the encoder still executes a real CUDA
            # query after cancellation. Production must discard its eventual result.
            entered = threading.Event()
            encode = encoder.encode
            def blocked(operation, value):
                if operation == 'query':
                    entered.set()
                    if not gate.wait(15):
                        raise TimeoutError('Owned CUDA query gate')
                return encode(operation, value)
            encoder.encode = blocked
            request_id = self.api('/api/library/ai/searches/prepare', {})['request_id']
            received = {}
            def query():
                try:
                    received['result'] = self.api('/api/library/ai/search', {'request_id': request_id, 'query': '青い画像'}, expected=409)
                except Exception as error:
                    received['error'] = str(error)
            query_thread = threading.Thread(target=query)
            query_thread.start()
            self.check('owned real-query inference guard entered', entered.wait(5))
            begin = time.perf_counter()
            self.check('running request cancellation accepted', self.api('/api/library/ai/searches/cancel', {'request_id': request_id})['cancel_requested'])
            self.report['cancel_receipt_seconds'] = time.perf_counter() - begin
            gate.set()
            query_thread.join(90)
            encoder.encode = encode
            self.check('real CUDA completion discarded after cancel', not query_thread.is_alive() and received.get('result', {}).get('error_code') == 'search_cancelled' and 'items' not in received.get('result', {}))
            digest = vector_digest(ai)
            before_calls = dict(encoder.calls)
            self.check('search lock usable after cancellation', self.api('/api/library/ai/search', {'query': '青い画像', 'source': 'all'})['total'] == 5)
            self.report.update(peak_cuda_allocated_mib=encoder.peak_cuda_allocated_mib, inference_calls=dict(encoder.calls))
            server.shutdown(); server.server_close(); server = None
            http_thread.join(5); http_thread = None
            ai.close(); ai = None
            self.check('all owned CUDA process handles exited', len(encoder.observed_exits) >= 2 and all(r['stopped'] for r in encoder.observed_exits))
            self.report['owned_exits'] = encoder.observed_exits
            catalog.close(); catalog = None
            bundle = self.target / 'backup bundle'
            restored = self.target / 'restored library'
            self.report['backup'] = backup(source / 'catalog.sqlite', bundle, settings=settings, viewer_settings=viewer, profiles=profiles)
            self.report['restore'] = restore(bundle, restored)
            self.check('restore requires revalidation and never auto resumes', self.report['restore']['requires_source_revalidation'] and not self.report['restore']['automatic_resume'])
            catalog = ProductionCatalog(restored / 'catalog.sqlite')
            encoder = MeasuredEncoder()
            ai = AISearch(catalog, encoder)
            restored_settings = AIProfileSettings(REPO, restored / 'settings/ai-settings.json', profile_directory=restored / 'profiles')
            self.check('profile, metadata and reader position restored', restored_settings.active == 'local:recovery.json' and not restored_settings.startup_error and catalog.get(image['id'])['tags'] == ['recovery-proof'] and catalog.reader_progress(book['id'])['progress']['page'] == 1)
            self.check('saved CUDA vectors survive restore without startup inference', vector_digest(ai) == digest and not encoder.resident and ai.coverage()['fresh_total'] == 5)
            self.check('three page vectors revalidate on original generated sources', ai.pages.coverage(book['id'], revision, {})['indexed_pages'] == 3)
            for mode in ('all', 'cover', 'text'):
                restored_result = ai.search('青い画像', source=mode)
                self.check(mode + ' restored real-CUDA query ranks and scores exact', [(r['id'], r['semantic_score']) for r in restored_result['items']] == results[mode])
            self.check('restore search never encodes documents or images', encoder.calls['document'] == 0 and encoder.calls['image'] == 0 and encoder.calls['query'] == 3)
            self.report.update(book_id=book['id'], image_id=image['id'], root_ids=roots,
                               pre_backup_document_image_calls={k: before_calls[k] for k in ('document', 'image')})
            self.report['pass'] = True
        finally:
            gate.set()
            if query_thread: query_thread.join(90)
            if server: server.shutdown(); server.server_close()
            if http_thread: http_thread.join(5)
            if ai: ai.close()
            if catalog: catalog.close()
            if encoder:
                self.report['final_owned_exits'] = encoder.observed_exits
                self.check('final real worker process instances stopped', bool(encoder.observed_exits) and all(r['stopped'] for r in encoder.observed_exits))
            self.check('all generated original bytes and timestamps unchanged', media_hashes(media) == original)

    def cli(self, *arguments):
        result = subprocess.run(['winapp', *map(str, arguments)], cwd=REPO, env=self.env,
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
        if result.returncode:
            raise RuntimeError(f'winapp {arguments}: {result.stdout}{result.stderr}')
        return result.stdout

    def ui(self, *arguments, hwnd=None):
        return self.cli('ui', *arguments, '-w', hwnd or self.hwnd)

    def capture(self, name, hwnd=None):
        path = self.native / (name + '.png')
        self.ui('screenshot', '--output', path, hwnd=hwnd)
        self.check('delivered ' + name, path.is_file() and path.stat().st_size > 0)
        self.report['screenshots'].append(str(path))
        (path.with_suffix('.tree.json')).write_text(self.ui('inspect', '--json', '--depth', '12', hwnd=hwnd), encoding='utf-8')

    def ready(self):
        self.ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '30000')
        time.sleep(.4)

    def owned_window(self, hwnd):
        owner = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(owner))
        if owner.value != self.app_pid:
            raise RuntimeError('Window is not owned by this acceptance run')

    def keys(self, identifier, sequence):
        self.owned_window(self.hwnd)
        self.user32.SetForegroundWindow(int(self.hwnd))
        time.sleep(.1)
        if self.user32.GetForegroundWindow() != int(self.hwnd):
            raise RuntimeError('Windows denied owned test-window activation; no global input sent')
        self.ui('focus', identifier)
        self.ui('send-keys', sequence, '--target', identifier, '--via', 'send-input')

    def launch(self, theme):
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', 8769)) == 0:
                raise RuntimeError('Port 8769 occupied; never attach to unknown library')
        restored = self.target / 'restored library'
        # Process-scoped execution only; never change the user's persisted policy.
        args = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(REPO / 'tools/start-winui.ps1'),
                '-Database', str(restored / 'catalog.sqlite'), '-AISettings', str(restored / 'settings/ai-settings.json'),
                '-AIProfilesDirectory', str(restored / 'profiles'), '-ViewerSettings', str(restored / 'settings/viewer-settings.json'), '-UITheme', theme]
        log = self.native / (theme + '-launcher.log')
        self.log = log.open('w', encoding='utf-8')
        self.launcher = subprocess.Popen(args, cwd=REPO, env=self.env, stdout=self.log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        def find_owned_app():
            if self.launcher.poll() is not None:
                raise RuntimeError('Actual launcher failed: ' + log.read_text(encoding='utf-8', errors='replace'))
            for pid in owned_tree(self.launcher.pid) - {self.launcher.pid}:
                handle = self.kernel.OpenProcess(0x1000, False, pid)
                if not handle: continue
                try:
                    name = ctypes.create_unicode_buffer(32768)
                    length = wintypes.DWORD(len(name))
                    if self.kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(length)) and Path(name.value).name == 'Aredoko.WinUI.exe':
                        self.app_pid = pid
                        return True
                finally: self.kernel.CloseHandle(handle)
            return False
        self.wait(find_owned_app, 100)
        def window_ready():
            windows = json.loads(self.cli('ui', 'list-windows', '-a', self.app_pid, '--json'))
            main = [w for w in windows if w.get('hwnd') and 'Aredoko' in w.get('title', '') and w.get('title') != 'PopupHost']
            if len(main) == 1:
                self.hwnd = str(main[0]['hwnd'])
                return True
            return False
        self.wait(window_ready, 20)
        self.ready()
        self.origin = 'http://127.0.0.1:8769'
        self.headers = {}
        session = self.api('/api/session')
        self.headers = {'Origin': self.origin, 'X-Aredoko-Token': session['token']}
        self.check(theme + ' actual launcher is cold; restored profile loaded', not self.api('/api/library/ai/status')['resident'] and self.api('/api/library/ai/profiles')['active'] == 'local:recovery.json')

    def close(self):
        if self.app_pid and self.hwnd:
            self.owned_window(self.hwnd)
            self.api('/api/library/ai/release', {})
            self.check('native release clears worker residency', not self.api('/api/library/ai/status')['resident'])
            handle = self.kernel.OpenProcess(0x100000, False, self.app_pid)
            try:
                if not self.user32.PostMessageW(int(self.hwnd), 0x0010, 0, 0):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.check('owned app exits normally', self.kernel.WaitForSingleObject(handle, 10000) == 0)
            finally: self.kernel.CloseHandle(handle)
            self.app_pid = self.hwnd = None
        if self.launcher:
            self.check('actual launcher exits after stopping its backend', self.launcher.wait(timeout=15) == 0)
            self.launcher = None
        if self.log: self.log.close(); self.log = None

    def gui(self):
        gpu = json.loads((self.target / 'gpu-result.json').read_text(encoding='utf-8'))
        if not gpu['pass']: raise RuntimeError('GPU/recovery prerequisite did not pass')
        self.native.mkdir(exist_ok=False)
        self.env = {**os.environ, 'WINAPP_UI_WORKFLOW_ID': 'aredoko-recovery-' + uuid.uuid4().hex, 'PYTHONIOENCODING': 'utf-8'}
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.app_pid = self.hwnd = self.launcher = self.log = None
        # Refuse existing native instances instead of attaching or killing them.
        existing = subprocess.run(['powershell', '-NoProfile', '-Command', 'if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'], capture_output=True)
        self.check('no other native Aredoko instance', existing.returncode == 0)
        media = self.target / 'generated sources'
        originals = json.loads((self.target / 'source-hashes.json').read_text(encoding='utf-8'))
        restored = self.target / 'restored library'
        settings_before = {str(p): p.read_bytes() for p in (restored / 'settings').glob('*.json')}
        try:
            for theme in ('Light', 'Dark'):
                self.launch(theme)
                row = next(r for r in self.api('/api/items')['items'] if r['id'] == gpu['image_id'])
                self.check(theme + ' restored manual metadata and previous favorite', row['tags'] == ['recovery-proof'] and (theme != 'Dark' or row['favorite']))
                self.ui('set-value', 'TxtQuery', 'asset-0-0.png'); self.ui('invoke', 'BtnSearch'); self.ready()
                self.ui('wait-for', 'TxtCount', '--value', '1 件', '-t', '5000')
                self.ui('invoke', 'Item' + str(gpu['image_id']), '--action', 'select')
                self.ui('wait-for', 'TxtTags', '--value', 'recovery-proof', '-t', '5000')
                if theme == 'Light':
                    self.ui('invoke', 'ChkFavorite', '--action', 'toggle-on'); self.ui('invoke', 'BtnSave')
                    self.ui('wait-for', 'TxtEditStatus', '--value', '保存しました', '-t', '5000')
                self.owned_window(self.hwnd)
                self.check(theme + ' owned resize', bool(self.user32.SetWindowPos(int(self.hwnd), None, 0, 0, 1200 if theme == 'Light' else 700, 820 if theme == 'Light' else 620, 0x2 | 0x4 | 0x10)))
                time.sleep(.6)
                # Crossing Inline -> Overlay can dismiss the pane. Re-open it
                # through the observed application action before asserting it.
                # Added after native attempt 3; not rerun in that bounded cycle.
                self.ui('invoke', 'BtnDetails')
                self.ui('wait-for', 'TxtTags', '--value', 'recovery-proof', '-t', '5000')
                self.capture(theme + '-restored-detail')
                self.ui('invoke', 'BtnCloseDetails'); self.ready()
                self.ui('invoke', 'BtnSettings')
                self.ui('wait-for', 'SettingsWheel', '--value', '上に回す（下で戻る）', '-t', '5000')
                self.capture(theme + '-restored-viewer-settings')
                self.ui('invoke', 'CloseButton'); self.ready()
                self.keys('CmbSearchMode', 'home down esc')
                self.ui('wait-for', 'CmbSearchMode', '--value', '両方で探す（AI）', '-t', '3000')
                self.ui('set-value', 'TxtQuery', '青い画像'); self.ui('invoke', 'BtnSearch'); self.ready()
                self.ui('wait-for', 'TxtCount', '--value', '5 件', '-t', '30000')
                self.check(theme + ' native Core request handshake and real CUDA search', self.api('/api/library/ai/status')['device'] == 'cuda')
                self.capture(theme + '-restored-combined-search')
                if theme == 'Light':
                    refused = subprocess.run([sys.executable, 'tools/backup_library.py', 'backup', '--catalog', str(restored / 'catalog.sqlite'), '--output', str(self.target / 'must-not-exist-live-backup')], cwd=REPO, capture_output=True, text=True, timeout=15)
                    self.check('actual production owner lease refuses live backup', refused.returncode == 2 and 'StorageBusyError' in refused.stderr and not (self.target / 'must-not-exist-live-backup').exists())
                self.close()
            self.report['pass'] = True
        except Exception:
            if self.hwnd:
                try: self.capture('failure')
                except Exception: pass
            raise
        finally:
            failing = sys.exc_info()[0] is not None
            try:
                try: self.close()
                except Exception as error:
                    self.report['cleanup_error'] = str(error)
                    if not failing: raise
            finally:
                self.cli('ui', 'yield')
                self.check('native flow preserves original media bytes and timestamps', media_hashes(media) == originals)
                self.check('native startup never rewrites restored AI/viewer settings', all(p.read_bytes() == data for name, data in settings_before.items() for p in [Path(name)]))


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=('gpu', 'gui'), required=True)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    target = args.output.resolve()
    if os.name != 'nt' or not target.is_relative_to((REPO / 'data/ai-ui').resolve()):
        parser.error('Windows and generated evidence under data/ai-ui required')
    if args.stage == 'gpu': target.mkdir(parents=True, exist_ok=False)
    if not target.is_dir(): parser.error('Existing GPU run directory required for native stage')
    name = 'gpu-result.json' if args.stage == 'gpu' else f'gui-result-{args.attempt:02}.json'
    if (target / name).exists() or args.stage == 'gui' and (target / f'native-{args.attempt:02}').exists():
        parser.error('Fresh result/attempt path required; never overwrite earlier evidence')
    run = Run(target, args.stage, args.attempt)
    started = time.perf_counter()
    try:
        getattr(run, args.stage)()
    except Exception as error:
        run.report.update({'pass': False, 'error': str(error), 'traceback': traceback.format_exc()})
        print(traceback.format_exc(), flush=True)
    finally:
        run.report['elapsed_seconds'] = time.perf_counter() - started
        (target / name).write_text(json.dumps(run.report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'stage': args.stage, 'pass': run.report['pass'], 'checks': len(run.report['checks']), 'error': run.report.get('error')}), flush=True)
    return 0 if run.report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
