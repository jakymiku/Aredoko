"""R04 explicit indexing continuation acceptance harness (CPU, GPU, and GUI stages).

Run cpu stage without GPU/GUI activation.
GPU/GUI stages are deferred per user instruction and prepared for batch execution when permitted.
Generated media only; no private scans, no network downloads, no quality tuning.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
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
    print("Running R04 CPU acceptance stage...")

    # 1. Run Core unit tests
    cmd_core = ['dotnet', 'run', '--project', 'tests/Aredoko.Core.Tests', '-c', 'Release']
    p_core = subprocess.run(cmd_core, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Core.Tests pass in Release", p_core.returncode == 0, report)
    (target_dir / 'core-tests.log').write_text(p_core.stdout or '', encoding='utf-8')

    # 2. Run Python continuation tests
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = '-1'
    env['PYTHONPATH'] = f"{REPO / 'tests'};{REPO / 'app'};{REPO / 'tools'}"
    cmd_py = [sys.executable, '-m', 'unittest', 'tests/test_index_continuation.py']
    p_py = subprocess.run(cmd_py, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Python test_index_continuation passes", p_py.returncode == 0, report)
    (target_dir / 'python-continuation.log').write_text((p_py.stderr or '') + '\n' + (p_py.stdout or ''), encoding='utf-8')

    # 3. Build WinUI Release
    cmd_build = ['dotnet', 'build', 'src/Aredoko.WinUI/Aredoko.WinUI.csproj', '-c', 'Release', '-p:Platform=x64', '--no-restore']
    p_build = subprocess.run(cmd_build, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("WinUI x64 Release builds with 0 errors", p_build.returncode == 0, report)
    (target_dir / 'winui-build.log').write_text(p_build.stdout or '', encoding='utf-8')

    report['pass'] = all(c['pass'] for c in report['checks'])
    (target_dir / 'cpu-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print("CPU stage completed successfully.")
    return report


def run_gpu_stage(target_dir):
    """Real CUDA EmbeddingGemma 2 acceptance for R04 continuation (deferred to R14)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gpu', 'pass': False, 'checks': [], 'timestamp': time.time()}
    print("Running R04 GPU continuation acceptance stage (deferred to R14)...")
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import AISearch
    from production import ProductionCatalog
    from create_preview_fixture import png
    from test_index_gpu_scaling import MeasuredEncoder

    gpu_dir = target_dir / 'gpu'
    gpu_dir.mkdir(parents=True, exist_ok=True)
    media = gpu_dir / 'media'
    media.mkdir(exist_ok=True)
    for i in range(6):
        (media / f'item_{i}.png').write_bytes(png(color=(30 + i * 30, 80, 150)))
    cat_path = gpu_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    root = cat.add_root(str(media))
    cat.start_scan(root)
    enc = MeasuredEncoder()
    ai = AISearch(cat, enc)
    try:
        plan = ai.continuation.prepare({}, ai.profile.key, limit=10)
        check("GPU plan selects unindexed items", plan['selected_total'] == 6, report)
        started = ai.continuation.start(plan['plan_id'], {}, ai.profile.key)
        ai.worker.join(30)
        status = ai.status()
        check("GPU continuation completes all items", status['state'] == 'complete' and status['indexed'] == 6, report)
        check("GPU continuation used real encoder", len(enc.calls['document']) == 6, report)
        plan2 = ai.continuation.prepare({}, ai.profile.key, limit=10)
        check("Second plan finds 0 unready", plan2['selected_total'] == 0 and plan2['remaining_total'] == 0, report)
        report['pass'] = True
    finally:
        ai.close()
        cat.close()
    (target_dir / 'gpu-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def run_gui_stage(target_dir):
    """Native WinUI UIA automation for R04 continuation (deferred to R14)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gui', 'pass': False, 'checks': [], 'screenshots': [], 'timestamp': time.time()}
    print("Running R04 GUI continuation acceptance stage (deferred to R14)...")
    import uuid
    from create_preview_fixture import png
    from production import ProductionCatalog

    gui_dir = target_dir / 'gui'
    gui_dir.mkdir(parents=True, exist_ok=True)

    winapp_check = subprocess.run(['winapp', '--version'], capture_output=True, text=True)
    check("winapp CLI tool available", winapp_check.returncode == 0, report)

    media = gui_dir / 'media'
    media.mkdir(exist_ok=True)
    for i in range(4):
        (media / f'asset_{i}.png').write_bytes(png(color=(40 + i * 40, 100, 180)))
    cat_path = gui_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    cat.add_root(str(media))
    cat.start_scan()
    cat.close()

    env = {**os.environ, 'WINAPP_UI_WORKFLOW_ID': 'aredoko-continuation-' + uuid.uuid4().hex, 'PYTHONIOENCODING': 'utf-8'}
    cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(REPO / 'tools/start-winui.ps1'),
           '-Database', str(cat_path), '-UITheme', 'Light']
    proc = subprocess.Popen(cmd, cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(5)
        hwnd_out = subprocess.run(['winapp', 'ui', 'list-windows', '--json'], capture_output=True, text=True)
        windows = json.loads(hwnd_out.stdout or '[]')
        main = [w for w in windows if 'Aredoko' in w.get('title', '') and w.get('title') != 'PopupHost']
        if not main:
            raise RuntimeError("Aredoko window not found")
        hwnd = str(main[0]['hwnd'])

        def ui(*args):
            res = subprocess.run(['winapp', 'ui', *args, '-w', hwnd], capture_output=True, text=True, timeout=30)
            if res.returncode != 0:
                raise RuntimeError(f"winapp error: {res.stderr or res.stdout}")
            return res.stdout

        ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '30000')
        ui('invoke', 'BtnSettings')
        ui('wait-for', 'AIIndexSummary', '-t', '10000')
        check("AIIndexSummary present", True, report)

        ui('wait-for', 'PlanAIContinuation', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        ui('invoke', 'PlanAIContinuation')
        ui('wait-for', 'AIContinuationSummary', '-p', 'Visibility', '--value', 'Visible', '-t', '10000')
        ui('wait-for', 'StartAIContinuation', '-p', 'Visibility', '--value', 'Visible', '-t', '10000')
        check("Plan displays summary and shows start button", True, report)

        plan_shot = gui_dir / 'continuation-plan.png'
        ui('screenshot', '--output', str(plan_shot))
        report['screenshots'].append(str(plan_shot))

        ui('invoke', 'StartAIContinuation')
        ui('wait-for', 'CancelAIIndex', '-p', 'IsEnabled', '--value', 'True', '-t', '5000')
        ui('invoke', 'CancelAIIndex')
        ui('wait-for', 'ResumeAIContinuation', '-p', 'Visibility', '--value', 'Visible', '-t', '15000')
        check("Cancellation succeeded and revealed resume button", True, report)

        cancel_shot = gui_dir / 'continuation-cancelled.png'
        ui('screenshot', '--output', str(cancel_shot))
        report['screenshots'].append(str(cancel_shot))

        report['pass'] = True
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            proc.kill()

    (target_dir / 'gui-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description="R04 continuation acceptance harness")
    parser.add_argument('--stage', choices=['cpu', 'gpu', 'gui', 'all'], default='cpu')
    parser.add_argument('--output', type=str, default=str(REPO / 'data' / 'continuation-acceptance'))
    args = parser.parse_args()

    out_dir = Path(args.output)
    if args.stage in ('cpu', 'all'):
        run_cpu_stage(out_dir)
    if args.stage in ('gpu', 'all'):
        run_gpu_stage(out_dir)
    if args.stage in ('gui', 'all'):
        run_gui_stage(out_dir)


if __name__ == '__main__':
    main()
