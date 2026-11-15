"""Safe Windows Sandbox runner helpers scoped to the launched trial instance."""
import json
import pathlib
import subprocess
import time

SANDBOX_PROCESS_NAMES = (
    'WindowsSandbox',
    'WindowsSandboxClient',
    'WindowsSandboxRemoteSession',
    'WindowsSandboxServer',
    'vmmemWindowsSandbox',
)


class ExistingSandboxError(RuntimeError):
    """Raised when an unrelated Windows Sandbox session is already active."""


def list_sandbox_processes():
    """Return active Windows Sandbox processes via CIM as (pid, name, parent_pid, cmdline)."""
    names = ','.join(f"'{n}.exe'" for n in SANDBOX_PROCESS_NAMES)
    script = (
        f"$items = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.Name -in @({names}, 'vmmemWindowsSandbox') }} | "
        f"Select-Object ProcessId,Name,ParentProcessId,CommandLine); "
        f"ConvertTo-Json -InputObject $items -Compress"
    )
    proc = subprocess.run(
        ['powershell', '-NoProfile', '-Command', script],
        capture_output=True,
        text=True,
    )
    raw = (proc.stdout or '').strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        parsed = [parsed]
    return [
        {
            'pid': int(row['ProcessId']),
            'name': str(row.get('Name') or ''),
            'parent_pid': int(row['ParentProcessId']) if row.get('ParentProcessId') is not None else None,
            'cmdline': str(row.get('CommandLine') or ''),
        }
        for row in parsed
    ]


def select_owned_sandbox_pids(processes, root_pid, wsb_path, pre_existing_pids=()):
    """Select only PIDs owned by this trial's root PID or exact .wsb path."""
    protected = set(pre_existing_pids)
    normalized_wsb = str(pathlib.Path(wsb_path).resolve()).casefold()
    by_pid = {int(p['pid']): p for p in processes}

    def references_other_wsb(cmdline):
        lower = (cmdline or '').casefold()
        return '.wsb' in lower and normalized_wsb not in lower

    owned = set()
    if root_pid is not None and root_pid in by_pid and root_pid not in protected:
        if not references_other_wsb(by_pid[root_pid].get('cmdline', '')):
            owned.add(root_pid)

    for p in processes:
        pid = int(p['pid'])
        if pid in protected:
            continue
        cmd = (p.get('cmdline') or '').casefold()
        if normalized_wsb in cmd:
            owned.add(pid)

    # Transitively collect direct/indirect children of any owned process.
    changed = True
    while changed:
        changed = False
        for p in processes:
            pid = int(p['pid'])
            parent = p.get('parent_pid')
            if pid in owned or pid in protected or references_other_wsb(p.get('cmdline', '')):
                continue
            if parent in owned:
                owned.add(pid)
                changed = True

    return sorted(owned)


def terminate_pids(pids):
    """Force-stop only the specified PIDs."""
    if not pids:
        return
    id_list = ','.join(str(int(pid)) for pid in pids)
    subprocess.run(
        [
            'powershell',
            '-NoProfile',
            '-Command',
            f"Stop-Process -Id {id_list} -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        text=True,
    )


def run_wsb_trial(
    wsb_path,
    evidence_dir,
    *,
    timeout_seconds=240,
    wait_exit_seconds=30,
    vm_shutdown_seconds=25,
    list_processes=list_sandbox_processes,
    popen=subprocess.Popen,
    stop_pids=terminate_pids,
):
    """Launch a single isolated .wsb trial and clean up only processes owned by it."""
    wsb = pathlib.Path(wsb_path).resolve()
    evidence = pathlib.Path(evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    result_file = evidence / 'result.json'
    failure_file = evidence / 'failure.json'
    for stale in (result_file, failure_file):
        if stale.exists():
            stale.unlink()

    existing = list_processes()
    if existing:
        raise ExistingSandboxError(
            'Another Windows Sandbox instance is already running; refusing to launch or terminate existing processes.'
        )

    proc = popen(
        [r'C:\Windows\System32\WindowsSandbox.exe', str(wsb)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (wsb.parent / 'host-launch.json').write_text(
        json.dumps({'pid': proc.pid, 'wsb': str(wsb)}, indent=2),
        encoding='utf-8',
    )

    deadline = time.monotonic() + timeout_seconds
    found = None
    report = {}
    try:
        while time.monotonic() < deadline:
            if result_file.exists():
                found = result_file
                break
            if failure_file.exists():
                found = failure_file
                break
            time.sleep(1.0)

        time.sleep(3.0)
        report = {'timed_out': found is None}
        if found is not None:
            report['evidence_file'] = found.name
            report['payload'] = json.loads(found.read_text(encoding='utf-8-sig'))
    finally:
        try:
            proc.wait(timeout=wait_exit_seconds)
        except subprocess.TimeoutExpired:
            pass
        owned = select_owned_sandbox_pids(list_processes(), proc.pid, wsb, pre_existing_pids=())
        if owned:
            stop_pids(owned)
        elif proc.poll() is None:
            proc.terminate()
        end = time.monotonic() + vm_shutdown_seconds
        while time.monotonic() < end:
            if not any(
                p.get('name', '').casefold().startswith('vmmemwindowssandbox')
                for p in list_processes()
            ):
                break
            time.sleep(1.0)

    return found == result_file and report.get('payload', {}).get('pass') is True, report
