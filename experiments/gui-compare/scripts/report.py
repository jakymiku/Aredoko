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
from html import escape
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



def write_html_report(summary: list[dict], path: str) -> None:
    phases = ('Idle', 'Search', 'Scroll', 'Detail', 'Edit')
    labels = {'Idle': '待機', 'Search': '検索', 'Scroll': 'スクロール',
              'Detail': '詳細表示', 'Edit': 'タグ編集'}
    metrics = (
        ('median_private_mib', 'Private Bytes 中央値（MiB）', '確保した専用仮想メモリの合計。実RAM使用量ではない'),
        ('median_sum_working_set_mib', 'Working Set 合算中央値（MiB）', '共有物理ページの二重計上を含む'),
        ('avg_cpu_pct_one_core', '平均 CPU 使用率（1論理コア＝100%）', '累積CPU時間からの近似で、操作時間の差に影響される'),
    )
    ui = {(row['variant'], row['phase']): row for row in summary
          if row['component'] == 'ui-tree'}
    parts = ['<!doctype html><html lang="ja"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>Aredoko GUI比較結果</title>',
             '<style>body{font:16px/1.6 system-ui,sans-serif;background:#10151b;color:#e9eff6;'
             'max-width:1080px;padding:24px;margin:auto}h1{font-size:28px}h2{margin-top:38px}'
             '.panel{background:#19222d;border:1px solid #394656;border-radius:12px;'
             'padding:18px;margin:12px 0}.pair{display:grid;grid-template-columns:105px 1fr 110px;'
             'align-items:center;gap:10px;margin:8px 0}.bar{background:#354050;height:14px;'
             'border-radius:7px;overflow:hidden}.fill{display:block;height:100%;border-radius:7px}'
             '.tauri{background:#70a5f1}.winui{background:#c6a5ef}'
             '.muted{color:#b4c1cf}strong{font-weight:700}small{display:block}'
             '@media(max-width:560px){.pair{grid-template-columns:80px 1fr 80px}}'
             '</style><h1>Aredoko GUI比較結果</h1>',
             '<p class="muted">Tauri + React と WinUI 3 / Windows / 5万件の架空データ</p>']
    for key, title, caveat in metrics:
        parts.append('<h2>' + escape(title) + '</h2><p class="muted">'
                     + escape(caveat) + '</p>')
        for phase in phases:
            pairs = [(name, ui.get((name, phase))) for name in ('Tauri', 'WinUI')]
            scale = max((r.get(key) or 0 for _, r in pairs if r), default=0)
            parts.append('<div class="panel"><strong>' + escape(labels[phase]) + '</strong>')
            for variant, row in pairs:
                value = None if row is None else row.get(key)
                if value is None:
                    bar = ''
                    label = 'データなし'
                else:
                    bar = ('<span class="fill ' + variant.lower() + '" style="width:'
                           + f'{(value / scale * 100 if scale else 0):.1f}%' + '"></span>')
                    label = f'{value:.2f}'
                parts.append('<div class="pair"><span>' + escape(variant)
                             + '</span><div class="bar">' + bar + '</div><span>'
                             + escape(label) + '</span></div>')
            parts.append('</div>')
    parts.append('<div class="panel"><strong>比較上の注意</strong><small>'
                 'アプリ本体と子プロセスの計測値。共通Pythonバックエンドは除外。'
                 '本測定でもUI操作速度・描画方式・起動条件の影響は残る。'
                 'FPS、GPUメモリ、入力遅延、コールド起動時間は測定していない。'
                 '性能の順位を保証するものではない。</small></div></html>')
    Path(path).write_text('\n'.join(parts), encoding='utf-8')



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_files', nargs='+')
    parser.add_argument('--json', help='Optional JSON report path')
    parser.add_argument('--html', help='Optional offline Japanese HTML graph report')
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
    if args.html:
        write_html_report(summary, args.html)
    if args.json:
        Path(args.json).write_text(json.dumps({'samples': summary, 'caveats': [
            'Working Set sums can double count shared pages',
            'Process parenthood can miss detached WebView2 processes',
            'CPU estimate uses deltas of observed process CPU counters; not a profiler',
            'Only sample metrics are reported; no fabricated startup/GPU stats'
        ]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
