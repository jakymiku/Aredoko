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
from collections import defaultdict
from pathlib import Path

EXPECTED = {'Tauri', 'WinUI'}


def summarize(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
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
    samples = defaultdict(list)
    for (variant, phase, trial, timestamp, component), values in groups.items():
        samples[(variant, phase, trial, component)].append((sum(v[0] for v in values), sum(v[1] for v in values)))
    result = []
    for (variant, phase, trial, component), values in sorted(samples.items()):
        private = [a for a, _ in values]
        working = [b for _, b in values]
        result.append({
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
    print('NOTE: startup latency, input delay, dropped frames, and GPU VRAM are NOT measured by this script.')
    for item in summary:
        print('{variant:5} {phase:8} #{trial} {component:7} samples={samples:2} private median={median_private_mib:8.2f} MiB peak={max_private_mib:8.2f} MiB summed-WS median={median_sum_working_set_mib:8.2f} MiB'.format(**item))
    if args.json:
        Path(args.json).write_text(json.dumps({'samples': summary, 'caveats': [
            'Working Set sums can double count shared pages',
            'Process parenthood can miss detached WebView2 processes',
            'Only sample metrics are reported; no fabricated startup/GPU stats'
        ]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
