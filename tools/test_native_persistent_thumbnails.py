"""P3 persistent thumbnail cache across native Aredoko.exe restart acceptance.

Generated media and isolated catalog only. Validates that derived thumbnails
persist in <catalog>.sqlite.thumbs.sqlite and serve hits upon app restart.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import time
import traceback
import zipfile
from urllib.request import ProxyHandler, Request, build_opener

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'app'), str(REPO / 'tools')]

from production import ProductionCatalog
from storage_lease import storage_lease
from create_preview_fixture import png
from native_ui_tools import nodes


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description="P3 persistent thumbnail cache across restart test.")
    parser.add_argument('--release', type=Path, required=True, help='Path to release directory containing Aredoko.exe')
    parser.add_argument('--attempt', type=int, default=1, choices=(1, 2, 3), help='Attempt number (1-3)')
    args = parser.parse_args()

    release = args.release.resolve()
    expected_app = (release / 'bin/Aredoko.WinUI.exe').resolve()
    target = REPO / 'data/ai-ui/p3-persistent-thumbs-20261024' / f'run{args.attempt:02}'

    if (os.name != 'nt' or not (release.is_relative_to(REPO / 'dist') or release.is_relative_to(REPO / 'data/ai-ui'))
            or not (release / 'Aredoko.exe').is_file() or not expected_app.is_file() or target.exists()):
        raise SystemExit('New dedicated release candidate and non-existing output directory required')

    target.mkdir(parents=True)
    local_root = target / 'local'
    data_dir = local_root / 'Aredoko'
    data_dir.mkdir(parents=True)
    catalog_path = data_dir / 'catalog.sqlite'
    thumbs_db_path = data_dir / 'catalog.sqlite.thumbs.sqlite'

    media_dir = target / 'media'
    media_dir.mkdir()

    print('Generating synthetic media fixtures (24 PNGs + 2 CBZ archives)...', flush=True)
    # 24 synthetic PNG images with distinct dimensions and palettes
    for i in range(24):
        w = 140 + (i % 6) * 20
        h = 160 + (i % 4) * 20
        color = (30 + (i * 17) % 200, 40 + (i * 23) % 190, 60 + (i * 29) % 180)
        (media_dir / f'image_{i:02d}.png').write_bytes(png(width=w, height=h, color=color))

    # 2 synthetic CBZ archives, each containing 4 pages
    for b in range(2):
        cbz_path = media_dir / f'book_{b:02d}.cbz'
        with zipfile.ZipFile(cbz_path, 'w') as zf:
            for p in range(4):
                pw = 150 + p * 10
                ph = 200 + p * 10
                pcolor = (50 + b * 50 + p * 20, 80 + b * 30 + p * 15, 120 + b * 20 + p * 10)
                zf.writestr(f'{p+1:03d}.png', png(width=pw, height=ph, color=pcolor))

    def get_source_hashes():
        return {
            p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(media_dir.iterdir())
        }

    initial_source_hashes = get_source_hashes()
    if len(initial_source_hashes) != 26:
        raise SystemExit(f'Expected 26 media files, got {len(initial_source_hashes)}')

    print('Scanning synthetic fixtures into isolated catalog.sqlite...', flush=True)
    cat = ProductionCatalog(catalog_path)
    root_id = cat.add_root(str(media_dir))
    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(25)
    scan_search = cat.search()
    scan_total = scan_search.get('total', 0)
    items = scan_search.get('items', [])
    cat.close()

    if scan_total != 26 or len(items) == 0:
        raise SystemExit(f'Expected 26 indexed items in catalog, found {scan_total}')

    first_id = items[0]['id']

    # Initial launch settings
    initial_launch_settings = {
        'database': str(catalog_path),
        'ui_theme': 'dark',
    }
    (data_dir / 'launch-settings.json').write_text(json.dumps(initial_launch_settings, indent=2), encoding='utf-8')

    report = {
        'pass': False,
        'attempt': args.attempt,
        'release': str(release),
        'checks': [],
        'screenshots': [],
        'visual_review': 'pending',
        'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'owned_bootstrap_pids': [],
        'owned_app_pids': [],
        'exits': [],
        'phase0_memory': None,
        'phase1_memory': None,
    }

    env = {
        **os.environ,
        'LOCALAPPDATA': str(local_root),
        'APPDATA': str(local_root),
        'AREDOKO_DB': str(catalog_path),
        'WINAPP_UI_WORKFLOW_ID': 'aredoko-p3-persistent-thumbs-20261024',
    }

    user = ctypes.WinDLL('user32', use_last_error=True)
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    def check(name, value):
        report['checks'].append({'name': name, 'pass': bool(value)})
        print(f'[{ "PASS" if value else "FAIL" }] {name}', flush=True)
        if not value:
            raise AssertionError(name)

    def cli(*parts):
        result = subprocess.run(
            ['winapp', 'ui', *map(str, parts)],
            cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
        )
        with (target / 'commands.log').open('a', encoding='utf-8') as log:
            log.write(json.dumps({'args': list(map(str, parts)), 'code': result.returncode, 'out': result.stdout, 'err': result.stderr}, ensure_ascii=False) + '\n')
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    seen_pids = set()
    seen_instances = set()
    hwnd = None
    pid = None
    proc_handle = None
    bootstrap = None
    opener = build_opener(ProxyHandler({}))

    def session_info():
        try:
            with opener.open('http://127.0.0.1:8769/api/session', timeout=1.5) as response:
                return json.load(response)
        except Exception:
            return None

    def candidate_app_pids(include_seen=False):
        pids = set()
        def callback(w, _):
            owner = wintypes.DWORD()
            user.GetWindowThreadProcessId(w, ctypes.byref(owner))
            if owner.value and (include_seen or owner.value not in seen_pids):
                pids.add(owner.value)
            return True
        user.EnumWindows(WNDENUMPROC(callback), 0)
        matches = []
        for cand_pid in sorted(pids):
            h = kernel.OpenProcess(0x101000, False, cand_pid)
            if not h:
                continue
            try:
                size = wintypes.DWORD(4096)
                buf = ctypes.create_unicode_buffer(4096)
                code = wintypes.DWORD()
                if (kernel.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                        and os.path.normcase(str(Path(buf.value).resolve())) == os.path.normcase(str(expected_app))
                        and kernel.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259):
                    matches.append((cand_pid, h))
                    h = None
            finally:
                if h:
                    kernel.CloseHandle(h)
        return matches

    def attach_phase(phase):
        nonlocal hwnd, pid, proc_handle
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if bootstrap is not None and bootstrap.poll() is not None:
                raise RuntimeError(f'Owned launcher exited early during phase {phase} with code {bootstrap.returncode}')
            matches = candidate_app_pids()
            for cand_pid, h in matches:
                try:
                    windows = json.loads(cli('list-windows', '-a', cand_pid, '--json'))
                    main_wins = [w for w in windows if w.get('title') and w['title'] != 'PopupHost']
                    info = session_info()
                    if len(main_wins) == 1 and isinstance(info, dict) and info.get('instance_id') not in seen_instances:
                        pid = cand_pid
                        proc_handle = h
                        hwnd = str(main_wins[0]['hwnd'])
                        seen_pids.add(cand_pid)
                        seen_instances.add(info['instance_id'])
                        report['owned_app_pids'].append(cand_pid)
                        report['checks'].append(f'phase {phase} ready (pid={cand_pid})')
                        for other_pid, other_h in matches:
                            if other_pid != cand_pid:
                                kernel.CloseHandle(other_h)
                        return
                except Exception:
                    pass
                kernel.CloseHandle(h)
            time.sleep(0.2)
        raise AssertionError(f'Timed out waiting for phase {phase} owned window')

    def wait_app_exit(phase):
        nonlocal proc_handle, hwnd, pid
        if not proc_handle:
            return
        wait_res = kernel.WaitForSingleObject(proc_handle, 20000)
        code = wintypes.DWORD()
        ok = kernel.GetExitCodeProcess(proc_handle, ctypes.byref(code))
        kernel.CloseHandle(proc_handle)
        proc_handle = None
        hwnd = None
        pid = None
        if wait_res != 0 or not ok or code.value != 0:
            raise AssertionError(f'Phase {phase} WinUI did not exit cleanly (wait={wait_res}, exit={code.value})')
        report['exits'].append({'phase': phase, 'frontend_exit': int(code.value)})
        report['checks'].append(f'phase {phase} WinUI exited 0')

    def ui(*parts):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(int(hwnd), ctypes.byref(owner))
        if owner.value != pid:
            raise RuntimeError('Owned window changed')
        return cli(*parts, '-w', hwnd)

    def tree():
        return {n['automationId']: n for n in nodes(json.loads(ui('inspect', '--depth', '22', '--json'))) if n.get('automationId')}

    def shot(name):
        path = target / (name + '.png')
        ui('screenshot', '--focus', '--output', path)
        report['screenshots'].append(str(path))
        payload = path.read_bytes()
        if payload[:8] != b'\x89PNG\r\n\x1a\n' or len(payload) < 24 or min(struct.unpack('>II', payload[16:24])) < 100:
            raise RuntimeError('Screenshot is empty or corrupted')
        (target / (name + '.json')).write_text(ui('inspect', '--depth', '22', '--json'), encoding='utf-8')

    def get_process_memory(target_pid):
        mem = {'WorkingSet64': 0, 'PrivateMemorySize64': 0}
        try:
            res = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 f'(Get-Process -Id {target_pid} | Select-Object WorkingSet64, PrivateMemorySize64) | ConvertTo-Json'],
                capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0 and res.stdout.strip():
                parsed = json.loads(res.stdout)
                mem['WorkingSet64'] = int(parsed.get('WorkingSet64', 0))
                mem['PrivateMemorySize64'] = int(parsed.get('PrivateMemorySize64', 0))
                return mem
        except Exception:
            pass

        try:
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD),
                    ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t),
                    ('PrivateUsage', ctypes.c_size_t),
                ]
            h = kernel.OpenProcess(0x1000 | 0x0400, False, target_pid)
            if h:
                try:
                    counters = PROCESS_MEMORY_COUNTERS_EX()
                    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
                    if psapi.GetProcessMemoryInfo(h, ctypes.byref(counters), counters.cb):
                        mem['WorkingSet64'] = int(counters.WorkingSetSize)
                        mem['PrivateMemorySize64'] = int(counters.PrivateUsage)
                finally:
                    kernel.CloseHandle(h)
        except Exception:
            pass
        return mem

    def close_main_window(target_hwnd):
        input_script = REPO / 'tools/winui_Input.ps1'
        closed_via_script = False
        if input_script.is_file():
            try:
                res = subprocess.run(
                    ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(input_script), 'close'],
                    cwd=REPO, capture_output=True, text=True, timeout=10
                )
                if res.returncode == 0:
                    closed_via_script = True
            except Exception:
                pass
        if not closed_via_script:
            user.PostMessageW(int(target_hwnd), 0x10, 0, 0)

    def wait_for_thumbnails_ready(label):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            nodes_by_id = tree()
            if f'Preview{first_id}' in nodes_by_id:
                loading = [
                    aid for aid, n in nodes_by_id.items()
                    if aid.startswith('PreviewStatus') and n.get('name') == '読込中'
                ]
                if not loading:
                    report['checks'].append({'name': f'{label} thumbnails ready', 'pass': True})
                    return
            time.sleep(0.25)
        raise AssertionError(f'Timed out waiting for {label} thumbnails to finish loading')

    try:
        # =========================================================================
        # PHASE 0: Initial launch, thumbnail generation, and clean exit
        # =========================================================================
        print('\n--- Starting Phase 0 ---', flush=True)
        bootstrap = subprocess.Popen([str(release / 'Aredoko.exe')], cwd=release, env=env)
        report['owned_bootstrap_pids'].append(bootstrap.pid)
        attach_phase(0)

        ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '20000')
        ui('wait-for', f'Item{first_id}', '-t', '15000')
        wait_for_thumbnails_ready('phase 0 list')

        # Switch to Grid view if currently in list view
        visible_nodes = tree()
        if 'BtnLayout' in visible_nodes and visible_nodes['BtnLayout'].get('name') == 'グリッド表示':
            print('Switching from List view to Grid view in Phase 0...', flush=True)
            ui('invoke', 'BtnLayout')
            time.sleep(0.4)

        # Wait for Grid view thumbnails to be realized and loaded
        ui('wait-for', f'Preview{first_id}', '-t', '15000')
        wait_for_thumbnails_ready('phase 0 grid')

        shot('01-phase0-grid-thumbs')
        phase0_memory = get_process_memory(pid)
        report['phase0_memory'] = phase0_memory
        print(f'Phase 0 WinUI memory: {phase0_memory}', flush=True)

        print('Closing Phase 0 window cleanly...', flush=True)
        close_main_window(hwnd)
        wait_app_exit(0)

        boot0_code = bootstrap.wait(timeout=25)
        bootstrap = None
        report['exits'].append({'phase': 0, 'bootstrap_exit': boot0_code})
        check('phase 0 bootstrap exited 0', boot0_code == 0)

        # =========================================================================
        # BETWEEN PHASE 0 AND PHASE 1: Disk state verification
        # =========================================================================
        print('\n--- Verifying Phase 0 disk cache state ---', flush=True)
        check('catalog.sqlite.thumbs.sqlite exists', thumbs_db_path.is_file())
        for suffix in ('-wal', '-shm', '-journal'):
            companion = Path(str(thumbs_db_path) + suffix)
            check(f'no leftover {suffix} after phase 0', not companion.exists())
        with storage_lease(thumbs_db_path):
            check('thumbs_db storage_lease released after phase 0', True)

        with sqlite3.connect(thumbs_db_path) as db:
            quick = db.execute('PRAGMA quick_check').fetchall()
            check('PRAGMA quick_check == ok after phase 0', quick == [('ok',)])
            user_ver = db.execute('PRAGMA user_version').fetchone()[0]
            check('PRAGMA user_version == 1 after phase 0', user_ver == 1)
            phase0_rows = db.execute('SELECT COUNT(*) FROM thumbs').fetchone()[0]
            check('thumbs rows > 0 after phase 0', phase0_rows > 0)
            phase0_max_touched = db.execute('SELECT COALESCE(MAX(touched), 0) FROM thumbs').fetchone()[0]
            check('phase0_max_touched > 0', phase0_max_touched > 0)
            phase0_bytes = db.execute('SELECT COALESCE(SUM(length(png)), 0) FROM thumbs').fetchone()[0]
            check('phase0_bytes > 0', phase0_bytes > 0)

        report['phase0_rows'] = phase0_rows
        report['phase0_max_touched'] = phase0_max_touched
        report['phase0_bytes'] = phase0_bytes
        print(f'Phase 0 cache metrics: rows={phase0_rows}, max_touched={phase0_max_touched}, bytes={phase0_bytes}', flush=True)

        # =========================================================================
        # PHASE 1: Restart, persistent cache hits, and clean exit
        # =========================================================================
        print('\n--- Starting Phase 1 (Restart) ---', flush=True)
        bootstrap = subprocess.Popen([str(release / 'Aredoko.exe')], cwd=release, env=env)
        report['owned_bootstrap_pids'].append(bootstrap.pid)
        attach_phase(1)

        ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '20000')
        ui('wait-for', f'Item{first_id}', '-t', '15000')
        wait_for_thumbnails_ready('phase 1 list')

        visible_nodes = tree()
        if 'BtnLayout' in visible_nodes and visible_nodes['BtnLayout'].get('name') == 'グリッド表示':
            print('Switching from List view to Grid view in Phase 1...', flush=True)
            ui('invoke', 'BtnLayout')
            time.sleep(0.4)

        ui('wait-for', f'Preview{first_id}', '-t', '15000')
        wait_for_thumbnails_ready('phase 1 grid')

        shot('02-phase1-restarted-thumbs')
        phase1_memory = get_process_memory(pid)
        report['phase1_memory'] = phase1_memory
        print(f'Phase 1 WinUI memory: {phase1_memory}', flush=True)

        print('Closing Phase 1 window cleanly...', flush=True)
        close_main_window(hwnd)
        wait_app_exit(1)

        boot1_code = bootstrap.wait(timeout=25)
        bootstrap = None
        report['exits'].append({'phase': 1, 'bootstrap_exit': boot1_code})
        check('phase 1 bootstrap exited 0', boot1_code == 0)

        # =========================================================================
        # POST-PHASE 1: Verify persistent cache hits and source integrity
        # =========================================================================
        print('\n--- Verifying Post-Phase 1 persistent hits ---', flush=True)
        check('catalog.sqlite.thumbs.sqlite exists post-phase 1', thumbs_db_path.is_file())
        for suffix in ('-wal', '-shm', '-journal'):
            companion = Path(str(thumbs_db_path) + suffix)
            check(f'no leftover {suffix} post-phase 1', not companion.exists())
        with storage_lease(thumbs_db_path):
            check('thumbs_db storage_lease released post-phase 1', True)

        with sqlite3.connect(thumbs_db_path) as db:
            quick = db.execute('PRAGMA quick_check').fetchall()
            check('PRAGMA quick_check == ok post-phase 1', quick == [('ok',)])
            phase1_rows = db.execute('SELECT COUNT(*) FROM thumbs').fetchone()[0]
            phase1_max_touched = db.execute('SELECT COALESCE(MAX(touched), 0) FROM thumbs').fetchone()[0]
            phase1_bytes = db.execute('SELECT COALESCE(SUM(length(png)), 0) FROM thumbs').fetchone()[0]

        report['phase1_rows'] = phase1_rows
        report['phase1_max_touched'] = phase1_max_touched
        report['phase1_bytes'] = phase1_bytes
        print(f'Phase 1 cache metrics: rows={phase1_rows}, max_touched={phase1_max_touched}, bytes={phase1_bytes}', flush=True)

        check('phase1_rows == phase0_rows (all requests served from persistent cache)',
              phase1_rows == phase0_rows)
        check('phase1_bytes == phase0_bytes (cached PNG payloads unchanged)',
              phase1_bytes == phase0_bytes)
        check('phase1_max_touched > phase0_max_touched (persistent disk cache hit across restart)',
              phase1_max_touched > phase0_max_touched)

        remaining = candidate_app_pids(include_seen=True)
        for _, h in remaining:
            kernel.CloseHandle(h)
        check('no remaining Aredoko.WinUI.exe processes', len(remaining) == 0)

        final_source_hashes = get_source_hashes()
        check('synthetic sources 100% unchanged', final_source_hashes == initial_source_hashes)

        report['pass'] = True
        print('\n>>> P3 Persistent Thumbnails Native Acceptance PASSED <<<', flush=True)

    except Exception:
        report['error'] = traceback.format_exc()
        print(report['error'], flush=True)
        if hwnd and pid:
            try:
                shot('failure')
            except Exception:
                report['failure_capture_error'] = traceback.format_exc()
    finally:
        # Cleanup any lingering process handles
        if hwnd and user:
            try:
                user.PostMessageW(int(hwnd), 0x10, 0, 0)
            except Exception:
                pass
        if proc_handle:
            try:
                kernel.CloseHandle(proc_handle)
            except Exception:
                pass
        if bootstrap is not None and bootstrap.poll() is None:
            try:
                bootstrap.terminate()
                bootstrap.wait(timeout=10)
            except Exception:
                pass

        (target / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
