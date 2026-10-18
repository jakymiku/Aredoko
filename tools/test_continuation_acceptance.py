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


def run_gui_stage(target_dir):
    # Deferred stage: to be invoked when user explicitly authorizes GPU/GUI test batch.
    print("GUI stage is prepared and deferred per user instruction. Run when permitted.")
    return {'stage': 'gui', 'deferred': True, 'pass': None}


def main():
    parser = argparse.ArgumentParser(description="R04 continuation acceptance harness")
    parser.add_argument('--stage', choices=['cpu', 'gpu', 'gui', 'all'], default='cpu')
    parser.add_argument('--output', type=str, default=str(REPO / 'data' / 'continuation-acceptance'))
    args = parser.parse_args()

    out_dir = Path(args.output)
    if args.stage in ('cpu', 'all'):
        run_cpu_stage(out_dir)
    if args.stage in ('gui', 'all'):
        run_gui_stage(out_dir)


if __name__ == '__main__':
    main()
