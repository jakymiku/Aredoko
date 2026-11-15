"""Safe Windows Sandbox runner helpers scoped to the launched trial instance."""
import json
import pathlib
import secrets
import subprocess
import time
import xml.etree.ElementTree as ET

SANDBOX_PROCESS_NAMES = (
    'WindowsSandbox',
    'WindowsSandboxClient',
    'WindowsSandboxRemoteSession',
    'WindowsSandboxServer',
    'vmmemWindowsSandbox',
)


class ExistingSandboxError(RuntimeError):
    """Raised when an unrelated Windows Sandbox session is already active."""


class SandboxProbeError(RuntimeError):
    """Raised when active Windows Sandbox processes cannot be reliably inspected."""


def list_sandbox_processes():
    """Return active Windows Sandbox processes via CIM as (pid, name, parent_pid, cmdline)."""
    names = ','.join(f"'{n}.exe'" for n in SANDBOX_PROCESS_NAMES)
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "try { "
        "$items = @(Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.Name -in @({names}, 'vmmemWindowsSandbox') }} | "
        "Select-Object ProcessId,Name,ParentProcessId,CommandLine); "
        "if ($items.Count -eq 0) { '[]' } else { ConvertTo-Json -InputObject $items -Compress } "
        "} catch { "
        "[Console]::Error.WriteLine($_.Exception.Message); "
        "exit 1 "
        "}"
    )
    proc = subprocess.run(
        ['powershell', '-NoProfile', '-Command', script],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    raw = (proc.stdout or '').strip()
    if proc.returncode != 0 or not raw:
        detail = (proc.stderr or proc.stdout or f'exit code {proc.returncode}').strip()
        raise SandboxProbeError(f'Failed to inspect running Windows Sandbox processes: {detail}')
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SandboxProbeError(f'Invalid Windows Sandbox process list JSON: {raw[:200]}') from exc
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise SandboxProbeError(f'Unexpected Windows Sandbox process list type: {type(parsed).__name__}')
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


def _prepare_run_wsb(wsb, run_dir):
    """Write a per-run .wsb redirecting C:\\AredokoEvidence to run_dir when present."""
    try:
        tree = ET.parse(wsb)
    except ET.ParseError:
        return wsb
    root = tree.getroot()
    updated = False
    for folder in root.findall('.//MappedFolder'):
        sandbox_folder = (folder.findtext('SandboxFolder') or '').strip().casefold()
        host_el = folder.find('HostFolder')
        if sandbox_folder == r'c:\aredokoevidence' and host_el is not None:
            host_el.text = str(run_dir)
            updated = True
    if not updated:
        return wsb
    launch_wsb = run_dir / wsb.name
    tree.write(launch_wsb, encoding='utf-8', xml_declaration=True)
    return launch_wsb


def run_wsb_trial(
    wsb_path,
    evidence_dir,
    *,
    timeout_seconds=240,
    wait_exit_seconds=30,
    vm_shutdown_seconds=25,
    settle_seconds=3.0,
    list_processes=list_sandbox_processes,
    popen=subprocess.Popen,
    stop_pids=terminate_pids,
):
    """Launch a single isolated .wsb trial with per-run evidence and owned-PID cleanup."""
    wsb = pathlib.Path(wsb_path).resolve()
    evidence_root = pathlib.Path(evidence_dir)

    # Probe active Sandbox processes BEFORE creating or touching any files.
    existing = list_processes()
    if existing:
        raise ExistingSandboxError(
            'Another Windows Sandbox instance is already running; refusing to launch or terminate existing processes.'
        )

    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    run_dir = evidence_root / 'runs' / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    launch_wsb = _prepare_run_wsb(wsb, run_dir)
    result_file = run_dir / 'result.json'
    failure_file = run_dir / 'failure.json'

    proc = popen(
        [r'C:\Windows\System32\WindowsSandbox.exe', str(launch_wsb)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (run_dir / 'host-launch.json').write_text(
        json.dumps({'pid': proc.pid, 'wsb': str(launch_wsb), 'template_wsb': str(wsb)}, indent=2),
        encoding='utf-8',
    )

    deadline = time.monotonic() + timeout_seconds
    found = None
    report = {'evidence_dir': str(run_dir)}
    try:
        while time.monotonic() < deadline:
            if result_file.exists():
                found = result_file
                break
            if failure_file.exists():
                found = failure_file
                break
            time.sleep(1.0)

        if settle_seconds > 0:
            time.sleep(settle_seconds)
        report['timed_out'] = found is None
        if found is not None:
            report['evidence_file'] = found.name
            report['payload'] = json.loads(found.read_text(encoding='utf-8-sig'))
    finally:
        try:
            proc.wait(timeout=wait_exit_seconds)
        except subprocess.TimeoutExpired:
            pass
        try:
            current = list_processes()
        except SandboxProbeError as exc:
            report['cleanup_probe_error'] = str(exc)
            if proc.poll() is None:
                proc.terminate()
        else:
            owned = select_owned_sandbox_pids(current, proc.pid, launch_wsb, pre_existing_pids=())
            if owned:
                stop_pids(owned)
            elif proc.poll() is None:
                proc.terminate()
            end = time.monotonic() + vm_shutdown_seconds
            while time.monotonic() < end:
                try:
                    remaining = list_processes()
                except SandboxProbeError as exc:
                    report['cleanup_probe_error'] = str(exc)
                    break
                if not any(
                    p.get('name', '').casefold().startswith('vmmemwindowssandbox')
                    for p in remaining
                ):
                    break
                time.sleep(1.0)

    return found == result_file and report.get('payload', {}).get('pass') is True, report


def run_wsb_cli(wsb_path, evidence_dir, *, enrich_report=None):
    """Run a .wsb trial via run_wsb_trial and exit 2 on probe/conflict refusal."""
    import sys

    try:
        passed, report = run_wsb_trial(wsb_path, evidence_dir)
    except ExistingSandboxError as exc:
        print(json.dumps({'blocked': 'existing_sandbox_running', 'error': str(exc)}, ensure_ascii=False, indent=2), flush=True)
        sys.exit(2)
    except SandboxProbeError as exc:
        print(json.dumps({'blocked': 'sandbox_probe_failed', 'error': str(exc)}, ensure_ascii=False, indent=2), flush=True)
        sys.exit(2)

    if enrich_report is not None and report.get('evidence_dir'):
        enrich_report(pathlib.Path(report['evidence_dir']), report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    sys.exit(0 if passed else 1)
