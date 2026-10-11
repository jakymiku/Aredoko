"""Summarize measured Windows GUI process samples; never invent missing samples.

CSV input is created by measure.ps1. Private Bytes are generally additive,
Working Set is displayed as a *summed* estimate with shared pages overcounted.
Missing trials and different workloads are not directly compared.
"""
from __future__ import annotations
import argparse
import csv
import json
import statistics
import os
import math
from datetime import datetime
from collections import defaultdict
from pathlib import Path

EXPECTED = {'Tauri', 'WinUI'}


def summarize(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    cpu_series = defaultdict(list)
    for row in rows:
        required = ('timestamp', 'variant', 'phase', 'trial', 'component', 'pid', 'private_bytes', 'working_set_bytes')
        if not all(k in row for k in required):
            raise ValueError('Missing required measurement columns')
        if row['variant'] not in EXPECTED or not row['phase']:
            raise ValueError('Unknown variant or missing phase')
        private = int(row['private_bytes'])
        working = int(row['working_set_bytes'])
        if private < 0 or working < 0:
            raise ValueError('Negative memory measurement')
        groups[(row['variant'], row['phase'], int(row['trial']), row['timestamp'], row['component'])].append((private, working))
        cpu = row.get('cpu_seconds')
        if cpu is not None and cpu != '':
            value = float(cpu)
            if not math.isfinite(value) or value < 0:
                raise ValueError('Invalid CPU counter')
            stamp = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            cpu_series[(row['variant'], row['phase'], int(row['trial']), row['component'], int(row['pid']))].append((stamp, value))
    samples = defaultdict(list)
    for (variant, phase, trial, timestamp, component), values in groups.items():
        samples[(variant, phase, trial, component)].append((sum(v[0] for v in values), sum(v[1] for v in values)))
    cpu_by_group = defaultdict(list)
    for (variant, phase, trial, component, pid), samples_by_pid in cpu_series.items():
        samples_by_pid.sort()
        first, last = samples_by_pid[0], samples_by_pid[-1]
        cpu_delta = sum(max(0., current[1] - previous[1])
                        for previous, current in zip(samples_by_pid, samples_by_pid[1:]))
        cpu_by_group[(variant, phase, trial, component)].append((first[0], last[0], cpu_delta))
    result = []
    for (variant, phase, trial, component), values in sorted(samples.items()):
        private = [a for a, _ in values]
        working = [b for _, b in values]
        cpu_samples = cpu_by_group.get((variant, phase, trial, component), [])
        cpu_percent = None
        if cpu_samples:
            interval = (max(t[1] for t in cpu_samples) - min(t[0] for t in cpu_samples)).total_seconds()
            if interval > 0:
                # Approximate CPU utilization for all sampled child processes,
                # where 100% means one full logical CPU core.
                cpu_percent = round(100 * sum(t[2] for t in cpu_samples) / interval, 2)
        result.append({
            'avg_cpu_pct_one_core': cpu_percent,
            'avg_cpu_pct_machine': (round(cpu_percent / max(1, os.cpu_count() or 1), 2)
                                    if cpu_percent is not None else None),
            'variant': variant, 'phase': phase, 'trial': trial, 'component': component,
            'samples': len(values), 'median_private_mib': round(statistics.median(private)/1048576, 2),
            'max_private_mib': round(max(private)/1048576, 2),
            'median_sum_working_set_mib': round(statistics.median(working)/1048576, 2),
            'max_sum_working_set_mib': round(max(working)/1048576, 2)
        })
    return result


def load(paths: list[str]) -> list[dict]:
    records = []
    for p in paths:
        with Path(p).open('r', encoding='utf-8-sig', newline='') as fp:
            records.extend(csv.DictReader(fp))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_files', nargs='+')
    parser.add_argument('--json', help='Optional JSON report path')
    args = parser.parse_args()
    summary = summarize(load(args.csv_files))
    print('NOTE: summed Working Set double-counts shared pages; results are not unique physical memory.')
    print('NOTE: app + Python are distinct components. Include child WebView2 processes if parented under the app.')
    print('NOTE: CPU is estimated from sampled cumulative process CPU time; short phases are noisy.')
    print('NOTE: startup latency, input delay, dropped frames, and GPU VRAM are NOT measured by this script.')
    for item in summary:
        print('{variant:5} {phase:8} #{trial} {component:7} samples={samples:2} private median={median_private_mib:8.2f} MiB peak={max_private_mib:8.2f} MiB summed-WS median={median_sum_working_set_mib:8.2f} MiB'.format(**item))
        if item['avg_cpu_pct_one_core'] is not None:
            print('    CPU estimate (100% = one logical core): {avg_cpu_pct_one_core:.2f}%, normalized machine share ~{avg_cpu_pct_machine:.2f}%'.format(**item))
    if args.json:
        Path(args.json).write_text(json.dumps({'samples': summary, 'caveats': [
            'Working Set sums can double count shared pages',
            'Process parenthood can miss detached WebView2 processes',
            'CPU estimate uses deltas of observed process CPU counters; not a profiler',
            'Only sample metrics are reported; no fabricated startup/GPU stats'
        ]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
