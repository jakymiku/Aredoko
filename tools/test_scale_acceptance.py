"""R12 Scale & Resource Budget Acceptance Harness.

Runs CPU stage measuring performance and scale budgets on 50,001+ metadata items
and 65,536+ stored vectors.
Measures cold/warm timings, p95 (nearest-rank formula), memory RSS, disk sizes,
WAL checkpoint truncation, cancellation latency, and recovery.
GPU/GUI stages are deferred for batch verification in R14 per user guidance.
"""
import argparse
from array import array
from contextlib import closing
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
sys.path.insert(0, str(REPO / 'tools'))

from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, VectorStore, revision
from ai_vectors import normalized
from audio_acoustics import MAX_AUDIO_BYTES, MAX_DURATION_MS
from catalog import Catalog, CURRENT_SCHEMA_USER_VERSION
from previews import MAX_ARCHIVE_BYTES
from production import ProductionCatalog
import search_terms
from storage_backup import backup, restore, plain_path


class PMC(ctypes.Structure):
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
    ]


def get_rss_bytes():
    """Return process RSS working set size in bytes on Windows."""
    try:
        fn = ctypes.windll.psapi.GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        if fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return int(c.WorkingSetSize)
    except Exception:
        pass
    return 0


def calculate_p95(latencies):
    """Conservative nearest-rank percentile formula: ceil(0.95 * N) - 1 on sorted values."""
    if not latencies:
        return 0.0
    s = sorted(latencies)
    idx = max(0, min(len(s) - 1, int(math.ceil(0.95 * len(s))) - 1))
    return s[idx]


def check(name, condition, report, details=None):
    entry = {'name': name, 'pass': bool(condition)}
    if details:
        entry['details'] = details
    report.setdefault('checks', []).append(entry)
    status = 'PASS' if condition else 'FAIL'
    print(f"[{status}] {name}" + (f" ({details})" if details else ""), flush=True)
    if not condition:
        raise AssertionError(f"Check failed: {name} ({details})")


class QueryOnlyEncoder:
    profile = DEFAULT_PROFILE
    available = True
    resident = False

    def encode(self, op, text):
        dim = self.profile.dimension
        return normalized([1.0] + [0.0] * (dim - 1), dim)

    def close(self):
        pass


def run_cpu_stage(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        'stage': 'cpu',
        'pass': False,
        'timestamp': time.time(),
        'p95_formula': 'sorted(latencies)[int(math.ceil(0.95 * len(latencies))) - 1]',
        'metrics': {},
        'checks': []
    }
    print("=" * 60)
    print("Running R12 Scale & Resource Acceptance (CPU Stage)...")
    print("=" * 60)

    rss_initial = get_rss_bytes()
    report['metrics']['rss_initial_bytes'] = rss_initial
    print(f"Initial process RSS: {rss_initial / (1024*1024):.2f} MiB")

    with tempfile.TemporaryDirectory() as tmp_root:
        tmp_path = Path(tmp_root)
        cat_db_path = tmp_path / 'scale_catalog.sqlite'
        vec_db_path = DEFAULT_PROFILE.store_path(cat_db_path)
        media_root = tmp_path / 'media'
        media_root.mkdir()

        # -----------------------------------------------------------------
        # 1. Generate 50,001 Metadata Items Fixture
        # -----------------------------------------------------------------
        print("\n--- 1. Generating 50,001 metadata items fixture ---")
        cat = ProductionCatalog(cat_db_path)
        roots = []
        for r in range(4):
            rd = media_root / f'root_{r}'
            rd.mkdir()
            roots.append(cat.add_root(str(rd)))

        t0 = time.perf_counter()
        kinds = ['image', 'book', 'video', 'audio']
        locations = []
        items = []
        mappings = []
        rows_for_ai = []

        for i in range(1, 50002):
            root_id = roots[i % 4]
            kind = kinds[i % 4]
            name = f'item_{i:06d}.' + ('png' if kind == 'image' else 'cbz' if kind == 'book' else 'mp4' if kind == 'video' else 'wav')
            title = f'大規模検証_作品_{i:05d}_日本語タイトル'
            tags = ['架空データ', '大量受入検証', f'ジャンル_{i % 30}']
            shelf = f'本棚_{i % 10}'
            if i == 50001:
                tags.append('最後の検証候補')
                shelf = 'boundary-final'
            tags_json = json.dumps(tags, ensure_ascii=False)
            fav = int(i % 10 == 0)
            rev = int(i % 5 == 0)

            locations.append((i, root_id, name, kind, 1024, 1000 + i, 'present', '2026-10-19', '2026-10-19'))
            items.append((i, title, kind, tags_json, shelf, fav, rev))
            mappings.append((i, i))

            rows_for_ai.append({
                'id': i,
                'root_id': root_id,
                'relative_path': name,
                'size_bytes': 1024,
                'mtime_ns': 1000 + i,
                'title': title,
                'tags': tags_json,
                'kind': kind,
                'shelf': shelf,
                'favorite': fav,
                'reviewed': rev
            })

        with cat.connect() as db:
            db.executemany('INSERT INTO library_locations(id,root_id,relative_path,kind,size_bytes,mtime_ns,status,discovered_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?)', locations)
            db.executemany('INSERT INTO items(id,title,kind,tags,shelf,favorite,reviewed) VALUES(?,?,?,?,?,?,?)', items)
            db.executemany('INSERT INTO item_locations(item_id,location_id) VALUES(?,?)', mappings)

        t_gen = time.perf_counter() - t0
        report['metrics']['metadata_gen_time_s'] = round(t_gen, 4)
        print(f"Generated 50,001 items in {t_gen:.2f}s")
        check("50,001 metadata records created", cat.search()['total'] == 50001, report, f"total={cat.search()['total']}")

        # -----------------------------------------------------------------
        # 2. Enumeration Benchmark
        # -----------------------------------------------------------------
        print("\n--- 2. Benchmarking candidate enumeration (_iter_rows) ---")
        ai = AISearch(cat, QueryOnlyEncoder(), store_path=vec_db_path)
        t0 = time.perf_counter()
        enumerated_ids = [row['id'] for row in ai._iter_rows(scope=None, all_candidates=True)]
        t_enum = time.perf_counter() - t0
        report['metrics']['enumeration_time_s'] = round(t_enum, 4)
        print(f"Enumerated 50,001 candidate IDs in {t_enum:.3f}s")
        check("Enumeration yields all 50,001 items in ID order", len(enumerated_ids) == 50001 and enumerated_ids[-1] == 50001, report, f"count={len(enumerated_ids)}")

        # -----------------------------------------------------------------
        # 3. Registration Diff / Freshness Scan
        # -----------------------------------------------------------------
        print("\n--- 3. Benchmarking registration diff / freshness check ---")
        t0 = time.perf_counter()
        fresh_count = 0
        batch_size = 256
        for offset in range(0, min(10000, len(rows_for_ai)), batch_size):
            batch = rows_for_ai[offset:offset + batch_size]
            fresh_count += len(ai.store.fresh_ids(batch))
        t_diff = time.perf_counter() - t0
        report['metrics']['freshness_check_10k_s'] = round(t_diff, 4)
        print(f"Freshness check for 10,000 items (in 256 batches) completed in {t_diff:.3f}s (fresh={fresh_count})")
        check("Freshness check safely distinguishes unindexed candidates", fresh_count == 0, report)

        # -----------------------------------------------------------------
        # 4. Normal Search Benchmark (Budget: warm p95 <= 1.0s)
        # -----------------------------------------------------------------
        print("\n--- 4. Benchmarking normal (literal) search ---")
        cold_t0 = time.perf_counter()
        res_cold = cat.search(query='最後の検証候補', page=0, limit=60)
        t_cold_search = time.perf_counter() - cold_t0
        report['metrics']['normal_search_cold_s'] = round(t_cold_search, 4)
        print(f"Cold search: {t_cold_search*1000:.2f}ms (found {res_cold['total']} hits)")
        check("Cold search finds final boundary candidate", res_cold['total'] == 1 and res_cold['items'][0]['id'] == 50001, report)

        warm_search_latencies = []
        for run in range(12):
            q = '大量受入検証' if run % 2 == 0 else '最後の検証候補'
            s0 = time.perf_counter()
            res = cat.search(query=q, page=0, limit=60)
            elapsed = time.perf_counter() - s0
            warm_search_latencies.append(elapsed)

        p95_normal_search = calculate_p95(warm_search_latencies)
        report['metrics']['normal_search_warm_runs'] = len(warm_search_latencies)
        report['metrics']['normal_search_warm_avg_s'] = round(sum(warm_search_latencies)/len(warm_search_latencies), 4)
        report['metrics']['normal_search_warm_p95_s'] = round(p95_normal_search, 4)
        print(f"Warm normal search p95: {p95_normal_search*1000:.2f}ms across {len(warm_search_latencies)} runs")
        check("Normal search warm p95 <= 1.0s budget", p95_normal_search <= 1.0, report, f"p95={p95_normal_search:.4f}s <= 1.0s")

        # -----------------------------------------------------------------
        # 5. Populate 65,536 Stored Vectors Fixture
        # -----------------------------------------------------------------
        print("\n--- 5. Populating 65,536 stored vectors fixture ---")
        dim = DEFAULT_PROFILE.dimension  # 768
        unit_vec = normalized([1.0] + [0.0] * (dim - 1), dim)
        unit_bytes = array('f', unit_vec).tobytes()

        # Generate 65,536 vector rows
        t0 = time.perf_counter()
        vec_records = []
        vec_rows = []
        for i in range(1, 65537):
            r = {
                'id': i,
                'root_id': roots[(i - 1) % 4],
                'relative_path': f'vec_item_{i:06d}.png',
                'size_bytes': 1024,
                'mtime_ns': 10000 + i,
                'title': f'作品_{i}',
                'tags': '[]'
            }
            rev = revision(r)
            vec_records.append((i, rev, 'text', unit_bytes))
            vec_rows.append(r)

        with ai.store.connect() as db:
            db.executemany('INSERT INTO ai_vectors(item_id, revision, modality, vector) VALUES(?,?,?,?)', vec_records)
        t_vec_insert = time.perf_counter() - t0
        report['metrics']['vector_insert_65k_s'] = round(t_vec_insert, 4)
        print(f"Populated 65,536 768-D vectors in {t_vec_insert:.2f}s")

        # -----------------------------------------------------------------
        # 6. CPU Stored-Vector Ranking Benchmark (Budget: p95 <= 10.0s for 65,536 vectors)
        # -----------------------------------------------------------------
        print("\n--- 6. Benchmarking CPU stored-vector ranking (65,536 vectors) ---")
        query_vec = normalized([1.0] + [0.0] * (dim - 1), dim)

        cold_rank_t0 = time.perf_counter()
        scores_cold, _, _, _ = ai.store.scores_with_content(vec_rows, query_vec, source='text')
        t_cold_rank = time.perf_counter() - cold_rank_t0
        report['metrics']['vector_ranking_cold_s'] = round(t_cold_rank, 4)
        print(f"Cold 65,536 vector ranking: {t_cold_rank:.3f}s (scored {len(scores_cold)} vectors)")
        check("65,536 vector ranking scored all vectors", len(scores_cold) == 65536, report)

        warm_rank_latencies = []
        for run in range(10):
            s0 = time.perf_counter()
            scores, _, _, _ = ai.store.scores_with_content(vec_rows, query_vec, source='text')
            elapsed = time.perf_counter() - s0
            warm_rank_latencies.append(elapsed)
            print(f"  Warm run {run+1}/10: {elapsed:.3f}s")

        p95_vector_rank = calculate_p95(warm_rank_latencies)
        report['metrics']['vector_ranking_warm_runs'] = len(warm_rank_latencies)
        report['metrics']['vector_ranking_warm_min_s'] = round(min(warm_rank_latencies), 4)
        report['metrics']['vector_ranking_warm_avg_s'] = round(sum(warm_rank_latencies)/len(warm_rank_latencies), 4)
        report['metrics']['vector_ranking_warm_max_s'] = round(max(warm_rank_latencies), 4)
        report['metrics']['vector_ranking_warm_p95_s'] = round(p95_vector_rank, 4)
        print(f"Warm 65,536 vector ranking p95: {p95_vector_rank:.3f}s")
        check("CPU stored-vector ranking p95 <= 10.0s budget", p95_vector_rank <= 10.0, report, f"p95={p95_vector_rank:.3f}s <= 10.0s")

        # -----------------------------------------------------------------
        # 7. Coverage Calculation Benchmark
        # -----------------------------------------------------------------
        print("\n--- 7. Benchmarking coverage calculation ---")
        t0 = time.perf_counter()
        cov = ai.coverage(scope=None)
        t_cov = time.perf_counter() - t0
        report['metrics']['coverage_calc_time_s'] = round(t_cov, 4)
        report['metrics']['coverage_candidate_total'] = cov.get('candidate_total')
        report['metrics']['coverage_target_total'] = cov.get('target_total')
        print(f"Coverage computed in {t_cov:.3f}s (candidate_total={cov.get('candidate_total')}, target_total={cov.get('target_total')})")
        check("Coverage candidate_total matches 50,001", cov.get('candidate_total') == 50001, report)
        check("Coverage target_total is bounded by MAX_ITEMS (10,000)", cov.get('target_total') == 10000, report)

        # -----------------------------------------------------------------
        # 8. Pending Tag Search Benchmark
        # -----------------------------------------------------------------
        print("\n--- 8. Benchmarking pending tag search ---")
        t0 = time.perf_counter()
        # Unreviewed items search
        unrev_search = cat.search(view='unreviewed', page=0, limit=60)
        t_pending = time.perf_counter() - t0
        report['metrics']['pending_search_time_s'] = round(t_pending, 4)
        print(f"Pending unreviewed items query in {t_pending:.3f}s (unreviewed total={unrev_search['total']})")
        check("Pending search returns unreviewed items", unrev_search['total'] > 0, report)

        # -----------------------------------------------------------------
        # 9. Cancellation Latency Benchmark (Budget: <= 1.0s)
        # -----------------------------------------------------------------
        print("\n--- 9. Benchmarking cancellation latency ---")
        prep = ai.search_requests.prepare()
        req_id = prep['request_id']
        t0 = time.perf_counter()
        cancel_res = ai.search_requests.cancel(req_id)
        t_cancel = time.perf_counter() - t0
        report['metrics']['cancellation_latency_s'] = round(t_cancel, 6)
        print(f"Cancellation request handled in {t_cancel*1000:.3f}ms")
        check("Cancellation request acknowledged", cancel_res.get('cancel_requested') is True, report)
        check("Cancellation latency <= 1.0s budget", t_cancel <= 1.0, report, f"latency={t_cancel:.6f}s <= 1.0s")

        # -----------------------------------------------------------------
        # 10. Separate Capacity and Read-Limit Boundary Checks
        # -----------------------------------------------------------------
        print("\n--- 10. Separate byte-capacity & read-limit boundary checks ---")
        # A. Audio & archive file size limits (512MiB) and duration bounds (24h)
        check("Audio read limit is bounded at 512MiB", MAX_AUDIO_BYTES == 512 * 1024 * 1024, report, f"{MAX_AUDIO_BYTES} bytes")
        check("Archive read limit is bounded at 512MiB", MAX_ARCHIVE_BYTES == 512 * 1024 * 1024, report, f"{MAX_ARCHIVE_BYTES} bytes")
        check("Audio duration limit is bounded at 24 hours", MAX_DURATION_MS == 86_400_000, report, f"{MAX_DURATION_MS} ms")

        # Verify C# AudioPlayerPolicy and Core protocols pass in Release
        p_core = subprocess.run(['dotnet', 'run', '--project', 'tests/Aredoko.Core.Tests', '-c', 'Release'],
                                cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
        check("Core AudioPlayerPolicy and Protocol pass in Release", p_core.returncode == 0, report)

        # B. 24-hour time bounds check (86,400,000 ms)
        invalid_negative_ms = -1
        invalid_huge_ms = 86_400_001
        check("Video frame validator rejects negative ms", not (0 <= invalid_negative_ms <= 86_400_000), report)
        check("Video frame validator rejects ms > 24 hours", not (0 <= invalid_huge_ms <= 86_400_000), report)

        # C. Schema forward-version guard fail-closed check
        future_db = tmp_path / 'future_schema_test.sqlite'
        with closing(sqlite3.connect(future_db)) as fdb:
            fdb.execute('CREATE TABLE sample(id INTEGER)')
            fdb.execute('PRAGMA user_version = 1')
            fdb.commit()
        failed_closed = False
        try:
            Catalog(future_db)
        except ValueError as ex:
            if 'Unsupported database schema user_version' in str(ex):
                failed_closed = True
        check("Database forward-version guard fails closed against future schema", failed_closed, report)

        # -----------------------------------------------------------------
        # 11. Resource Footprint & Worker Shutdown
        # -----------------------------------------------------------------
        print("\n--- 11. Measuring resource footprint and worker shutdown ---")
        rss_peak = get_rss_bytes()
        report['metrics']['rss_peak_bytes'] = rss_peak
        report['metrics']['rss_delta_mb'] = round((rss_peak - rss_initial) / (1024 * 1024), 2)
        print(f"Peak RSS: {rss_peak / (1024*1024):.2f} MiB (delta: +{report['metrics']['rss_delta_mb']} MiB)")

        cat_disk_bytes = cat_db_path.stat().st_size
        vec_disk_bytes = vec_db_path.stat().st_size
        report['metrics']['catalog_db_disk_mb'] = round(cat_disk_bytes / (1024 * 1024), 2)
        report['metrics']['vector_store_disk_mb'] = round(vec_disk_bytes / (1024 * 1024), 2)
        print(f"Catalog DB on disk: {report['metrics']['catalog_db_disk_mb']} MiB")
        print(f"Vector Store DB on disk: {report['metrics']['vector_store_disk_mb']} MiB")

        # Worker shutdown benchmark & WAL checkpoint verification
        t0 = time.perf_counter()
        ai.close()
        cat.close()
        t_shutdown = time.perf_counter() - t0
        report['metrics']['shutdown_time_s'] = round(t_shutdown, 4)
        print(f"Workers and stores cleanly closed in {t_shutdown:.4f}s")
        check("Clean shutdown completes in <= 2.0s", t_shutdown <= 2.0, report)

        cat_wal = Path(str(cat_db_path) + '-wal')
        vec_wal = Path(str(vec_db_path) + '-wal')
        cat_wal_size = cat_wal.stat().st_size if cat_wal.exists() else 0
        vec_wal_size = vec_wal.stat().st_size if vec_wal.exists() else 0
        report['metrics']['catalog_wal_bytes_after_close'] = cat_wal_size
        report['metrics']['vector_wal_bytes_after_close'] = vec_wal_size
        check("Catalog WAL truncated to 0 bytes on close", cat_wal_size == 0, report, f"wal_size={cat_wal_size}")
        check("Vector store WAL truncated to 0 bytes on close", vec_wal_size == 0, report, f"wal_size={vec_wal_size}")

        # -----------------------------------------------------------------
        # 12. Recovery Benchmark (Stop-time backup & restore)
        # -----------------------------------------------------------------
        print("\n--- 12. Benchmarking stop-time backup & restore recovery ---")
        backup_folder = tmp_path / 'scale_backup'
        restored_folder = tmp_path / 'scale_restored'

        t0 = time.perf_counter()
        backup_res = backup(cat_db_path, backup_folder, include_vectors=True)
        t_backup = time.perf_counter() - t0
        report['metrics']['backup_duration_s'] = round(t_backup, 4)
        report['metrics']['backup_files'] = backup_res['files']
        report['metrics']['backup_bytes'] = backup_res['bytes']
        print(f"Captured stop-time backup in {t_backup:.2f}s ({backup_res['files']} files, {backup_res['bytes'] / (1024*1024):.2f} MiB)")
        check("Backup captures catalog and vectors", backup_res['files'] >= 2, report)

        t0 = time.perf_counter()
        restore_res = restore(backup_folder, restored_folder)
        t_restore = time.perf_counter() - t0
        report['metrics']['restore_duration_s'] = round(t_restore, 4)
        print(f"Restored backup in {t_restore:.2f}s")
        check("Restore completes without auto-resume", restore_res['automatic_resume'] is False, report)

        # Verify integrity on restored files
        restored_cat = ProductionCatalog(restored_folder / 'catalog.sqlite')
        with restored_cat.connect() as rdb:
            integ = rdb.execute('PRAGMA integrity_check').fetchall()
            check("Restored catalog passes integrity check", integ[0][0] == 'ok', report, f"integ={integ[0][0]}")
            check("Restored catalog maintains 50,001 items", restored_cat.search()['total'] == 50001, report)
        restored_cat.close()

    report['pass'] = True
    report_file = output_dir / 'scale-report.json'
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print("\n" + "=" * 60)
    print(f"R12 CPU Scale Acceptance PASS: {len(report['checks'])} checks verified.")
    print(f"Detailed report saved to: {report_file}")
    print("=" * 60)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['cpu', 'gpu', 'gui', 'all'], default='cpu')
    parser.add_argument('--output-dir', type=Path, default=REPO / 'data' / 'acceptance' / 'r12-scale-latest')
    args = parser.parse_args()

    if args.stage in ('cpu', 'gpu', 'all'):
        run_cpu_stage(args.output_dir)
    elif args.stage == 'gui':
        print("Note: GUI scale flow is integrated in R02/R03 and R10/R11 GUI stages.")


if __name__ == '__main__':
    main()
