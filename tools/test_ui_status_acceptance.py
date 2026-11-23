"""R10/R11 AI state clarity, cancellation, and UI consistency acceptance harness.

Run cpu stage without GPU/GUI activation.
GPU/GUI stages are deferred per user instruction and prepared for batch execution in R14.
Generated media only; no private scans, no network downloads, no quality tuning.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(REPO / 'app'))
sys.path.insert(0, str(REPO / 'tools'))


def check(name, condition, report):
    report.setdefault('checks', []).append({'name': name, 'pass': bool(condition)})
    print(json.dumps({'check': name, 'pass': bool(condition)}), flush=True)
    if not condition:
        raise AssertionError(f"Check failed: {name}")


def run_cpu_stage(target_dir):
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'cpu', 'pass': False, 'checks': [], 'timestamp': time.time()}
    print("Running R10/R11 CPU state clarity and UI acceptance stage...")

    # 1. Run Core unit tests
    cmd_core = ['dotnet', 'run', '--project', 'tests/Aredoko.Core.Tests', '-c', 'Release']
    p_core = subprocess.run(cmd_core, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Core.Tests pass in Release (including StatusClarityTests)", p_core.returncode == 0, report)
    (target_dir / 'core-tests.log').write_text(p_core.stdout or '', encoding='utf-8')

    # 2. Run Python unit tests
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = '-1'
    env['PYTHONPATH'] = f"{REPO / 'tests'};{REPO / 'app'};{REPO / 'tools'}"
    cmd_py = [sys.executable, '-m', 'unittest', 'tests/test_ai_status_clarity.py']
    p_py = subprocess.run(cmd_py, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Python test_ai_status_clarity passes", p_py.returncode == 0, report)
    (target_dir / 'python-status.log').write_text((p_py.stderr or '') + '\n' + (p_py.stdout or ''), encoding='utf-8')

    # 3. Build WinUI Release
    cmd_build = ['dotnet', 'build', 'src/Aredoko.WinUI/Aredoko.WinUI.csproj', '-c', 'Release', '-p:Platform=x64', '--no-restore']
    p_build = subprocess.run(cmd_build, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("WinUI x64 Release builds with 0 errors", p_build.returncode == 0, report)
    (target_dir / 'winui-build.log').write_text(p_build.stdout or '', encoding='utf-8')

    # 4. Programmatic status code & guidance checks
    from ai_search import AISearch
    from production import ProductionCatalog
    from production_server import DisabledAI

    cat_path = target_dir / 'status_acceptance_catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    media_dir = target_dir / 'status_media'
    media_dir.mkdir(parents=True, exist_ok=True)
    root_id = cat.add_root(str(media_dir))

    f1 = media_dir / 'sample1.wav'
    f1.write_bytes(b'RIFF_sample_audio_content')
    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)

    class StubEncoder:
        available = True
        device = 'cpu'
        def encode(self, op, text): return [1.0] + [0.0] * 767
        def close(self): pass

    ai = AISearch(cat, StubEncoder())
    st = ai.status()
    check("AISearch status returns status_code == ready", st.get('status_code') == 'ready', report)

    with ai.guard:
        ai.store.save_state({'state': 'running', 'processed': 0, 'total': 1, 'indexed': 0, 'skipped': 0, 'error': ''})
    check("AISearch status returns status_code == running when active", ai.status().get('status_code') == 'running', report)
    with ai.guard:
        ai.store.save_state({'state': 'complete', 'processed': 0, 'total': 0, 'indexed': 0, 'skipped': 0, 'error': ''})

    cov = ai.coverage()
    check("AISearch coverage returns coverage_status == unindexed before indexing", cov.get('coverage_status') == 'unindexed', report)

    search_res = ai.search('sample')
    check("AISearch search returns search_status == unindexed when not indexed", search_res.get('search_status') == 'unindexed', report)
    check("AISearch search candidate total is 1", search_res.get('search_candidate_total') == 1, report)
    check("AISearch indexed total is 0", search_res.get('indexed_total') == 0, report)

    ai.close()
    cat.close()

    # 5. DisabledAI behavior check
    disabled = DisabledAI("AI未導入", status_code="model_missing")
    dst = disabled.status()
    check("DisabledAI status available is False", dst['available'] is False, report)
    check("DisabledAI status status_code is model_missing", dst['status_code'] == 'model_missing', report)

    disabled_corrupt = DisabledAI("プロファイル破損", status_code="corrupt_profile")
    check("DisabledAI status status_code is corrupt_profile", disabled_corrupt.status()['status_code'] == 'corrupt_profile', report)

    # 6. Verify documentation checklist exists
    checklist = REPO / 'docs' / 'ui-consistency-checklist.md'
    check("UI consistency checklist exists", checklist.exists(), report)
    check_content = checklist.read_text(encoding='utf-8')
    check("Checklist covers status clarity matrix", "Status Clarity Matrix" in check_content, report)
    check("Checklist covers keyboard navigation", "Keyboard & Narrator" in check_content, report)
    check("Checklist covers diagnostics safety", "Redacted Diagnostics" in check_content, report)

    report['pass'] = True
    (target_dir / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"R10/R11 CPU acceptance STAGE PASS: {len(report['checks'])} checks verified.")
    return report


def run_gui_stage(target_dir):
    """Native WinUI UIA automation for R10/R11 status clarity, cancellation & diagnostics."""
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gui', 'pass': False, 'checks': [], 'screenshots': [], 'timestamp': time.time()}
    print("Running R10/R11 GUI state clarity and diagnostics acceptance stage...")
    import uuid
    from create_preview_fixture import png
    from production import ProductionCatalog

    gui_dir = target_dir / 'gui'
    gui_dir.mkdir(parents=True, exist_ok=True)

    winapp_check = subprocess.run(['winapp', '--version'], capture_output=True, text=True)
    check("winapp CLI tool available", winapp_check.returncode == 0, report)

    media_dir = gui_dir / 'media'
    media_dir.mkdir(exist_ok=True)
    (media_dir / 'sample_doc_01.png').write_bytes(png(color=(90, 140, 210)))
    (media_dir / 'sample_doc_02.png').write_bytes(png(color=(210, 90, 140)))

    cat_path = gui_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    root_id = cat.add_root(str(media_dir))
    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)
    cat.close()

    env = {**os.environ, 'WINAPP_UI_WORKFLOW_ID': 'aredoko-status-' + uuid.uuid4().hex, 'PYTHONIOENCODING': 'utf-8'}
    cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(REPO / 'tools/start-winui.ps1'),
           '-Database', str(cat_path), '-UITheme', 'Light']
    log_path = gui_dir / 'launcher.log'
    log_file = log_path.open('w', encoding='utf-8')
    proc = subprocess.Popen(cmd, cwd=REPO, env=env, stdout=log_file, stderr=subprocess.STDOUT)
    hwnd = None
    app_pid = None
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"Launcher process exited prematurely: {log_path.read_text(encoding='utf-8', errors='replace')}")
            hwnd_out = subprocess.run(['winapp', 'ui', 'list-windows', '--json'], capture_output=True, text=True)
            try:
                windows = json.loads(hwnd_out.stdout or '[]')
            except Exception:
                windows = []
            main = [w for w in windows if 'Aredoko' in w.get('title', '') and w.get('title') != 'PopupHost']
            if main and main[0].get('hwnd'):
                hwnd = str(main[0]['hwnd'])
                app_pid = main[0].get('processId') or main[0].get('pid')
                break
            time.sleep(2)
        if not hwnd:
            raise RuntimeError(f"Aredoko window not found within timeout. Launcher log:\n{log_path.read_text(encoding='utf-8', errors='replace')}")

        def ui(*args, window=None):
            w = str(window) if window else hwnd
            res = subprocess.run(['winapp', 'ui', *args, '-w', w], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
            raw_out = (res.stdout or '').strip()
            safe_out = raw_out.encode('ascii', errors='backslashreplace').decode('ascii')
            print(f"UI {args} (window={w}) -> rc={res.returncode}: {safe_out}", flush=True)
            if res.returncode != 0:
                raise RuntimeError(f"winapp error: {res.stderr or res.stdout}")
            return res.stdout

        ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '30000')
        check("ItemList ready", True, report)

        # 1. Search Box
        ui('set-value', 'TxtQuery', 'sample')
        ui('invoke', 'BtnSearch')
        time.sleep(1)
        check("Search query executed without crash", True, report)

        # 2. Settings dialog and Diagnostics
        ui('invoke', 'BtnSettings')
        ui('wait-for', 'BtnDiagnostics', '-t', '10000')
        check("BtnDiagnostics available in settings", True, report)

        ui('invoke', 'BtnDiagnostics')
        time.sleep(1)
        ui('wait-for', 'TxtDiagnostics', '-t', '10000')
        check("Diagnostics dialog opened", True, report)

        diag_text = ui('get-value', 'TxtDiagnostics')
        check("Diagnostics text does not expose the Windows user profile path",
              str(Path.home()).casefold() not in diag_text.casefold(), report)

        ui('wait-for', 'BtnCopyDiagnostics', '-t', '5000')
        ui('invoke', 'BtnCopyDiagnostics')
        check("BtnCopyDiagnostics invoked", True, report)

        diag_shot = gui_dir / 'diagnostics-dialog.png'
        ui('screenshot', '--output', str(diag_shot))
        report['screenshots'].append(str(diag_shot))

        # Close diagnostics dialog
        ui('wait-for', 'CloseButton', '-t', '5000')
        ui('invoke', 'CloseButton')
        time.sleep(1)

        # 3. Settings dialog and Backup Guide
        ui('invoke', 'BtnSettings')
        ui('wait-for', 'BtnBackupGuide', '-t', '10000')
        check("BtnBackupGuide available in settings", True, report)

        ui('invoke', 'BtnBackupGuide')
        time.sleep(1)
        ui('wait-for', 'BackupGuideDialog', '-t', '10000')
        check("Backup guide dialog opened", True, report)

        backup_shot = gui_dir / 'backup-guide-dialog.png'
        ui('screenshot', '--output', str(backup_shot))
        report['screenshots'].append(str(backup_shot))

        # Close backup guide dialog
        ui('wait-for', 'CloseButton', '-t', '5000')
        ui('invoke', 'CloseButton')
        time.sleep(1)

        report['pass'] = True
    finally:
        if hwnd:
            try:
                subprocess.run(['winapp', 'ui', 'close', '-w', hwnd], capture_output=True, timeout=5)
            except Exception:
                pass
        if app_pid:
            subprocess.run(['taskkill', '/PID', str(app_pid), '/T', '/F'], capture_output=True)
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
        try:
            proc.wait(5)
        except Exception:
            pass
        try:
            log_file.close()
        except Exception:
            pass

    (target_dir / 'gui-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print("UI status GUI stage completed successfully.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['cpu', 'gpu', 'gui', 'all'], default='cpu')
    parser.add_argument('--output-dir', type=Path, default=REPO / 'data' / 'acceptance' / 'r10-r11-latest')
    args = parser.parse_args()

    out_dir = Path(args.output_dir).resolve()
    if args.stage in ('cpu', 'gpu', 'all'):
        run_cpu_stage(out_dir)
    if args.stage in ('gui', 'all'):
        run_gui_stage(out_dir)


if __name__ == '__main__':
    main()
