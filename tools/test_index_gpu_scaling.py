"""Manual offline EG2 scaling on newly generated sources; never private media.

Uses the production scanner/index/search, existing project Python/weights only.
No GUI, download, arbitrary profile, or source path arguments. Results are
single-run measurements, not representative retrieval quality or 1TB claims.
"""
import argparse
from collections import Counter
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import threading
import time
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from ai_process import EncoderProcess
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, MAX_ITEMS
from production import ProductionCatalog
from create_preview_fixture import png


def source_digest(media):
    digest = hashlib.sha256()
    for path in sorted(media.iterdir()):
        stat = path.stat()
        digest.update(path.name.encode('utf-8'))
        digest.update(path.read_bytes())
        digest.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode())
    return digest.hexdigest()


def memory_bytes(pid):
    """Read one owned process; GPU allocations come from worker telemetry."""
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    *[(name, ctypes.c_size_t) for name in (
                        'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                        'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage',
                        'PrivateUsage')]]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    process = kernel.OpenProcess(0x1000 | 0x10, False, pid)
    if not process:
        return None
    try:
        data = Counters(); data.cb = ctypes.sizeof(data)
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(data), data.cb):
            return None
        return {'working_set': data.WorkingSetSize, 'private': data.PrivateUsage,
                'lifetime_peak_working_set': data.PeakWorkingSetSize}
    finally:
        kernel.CloseHandle(process)



def owned_tree(root):
    """Read descendants of a live owned Popen root (venv launcher on Windows)."""
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    parents = {}; entry = Entry(); entry.dwSize = ctypes.sizeof(entry)
    try:
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    selected = {root}
    while True:
        larger = selected | {pid for pid, parent in parents.items() if parent in selected}
        if larger == selected: return selected
        selected = larger


class MeasuredEncoder(EncoderProcess):
    def __init__(self):
        super().__init__(REPO / '.venv-ai/Scripts/python.exe', DEFAULT_PROFILE.model_path(REPO))
        self.input_lengths = []; self.image_sizes = Counter()
        self.calls = Counter(); self.wall_seconds = Counter(); self.on_document = None
        self.children = []; self.peak_cuda_allocated_mib = 0
        self.handles = {}; self.observed_exits = []
        self.observation_lock = threading.Lock()

    def encode(self, operation, value):
        started = time.perf_counter()
        vector = super().encode(operation, value)
        if self.device != 'cuda': raise RuntimeError('Actual CUDA required for this measurement')
        self.wall_seconds[operation] += time.perf_counter() - started
        self.calls[operation] += 1
        if operation == 'document': self.input_lengths.append(len(value))
        if operation == 'image':
            if value[:8] != b'\x89PNG\r\n\x1a\n': raise RuntimeError('Generated PNG expected')
            self.image_sizes[(int.from_bytes(value[16:20], 'big'),
                              int.from_bytes(value[20:24], 'big'))] += 1
        if self.process not in self.children:
            self.children.append(self.process)
            self.observe()
        self.peak_cuda_allocated_mib = max(self.peak_cuda_allocated_mib,
                                         self.telemetry.get('peak_memory_mib', 0))
        if operation == 'document' and self.on_document:
            self.on_document(self.calls['document'])
        return vector


    def observe(self):
        with self.observation_lock:
            return self._observe()

    def _observe(self):
        if not self.process or self.process.poll() is not None: return []
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        pids = owned_tree(self.process.pid)
        for pid in pids:
            if pid not in self.handles:
                handle = kernel.OpenProcess(0x100000, False, pid)
                if handle: self.handles[pid] = handle
        return pids

    def close(self):
        # Hold process-instance handles, so later PID reuse cannot masquerade
        # as a still-running or stopped owned worker. Never kill by name/tree.
        super().close()
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        exits = []
        for pid, handle in self.handles.items():
            try: exits.append({'pid': pid, 'stopped': kernel.WaitForSingleObject(handle, 10000) == 0})
            finally: kernel.CloseHandle(handle)
        self.handles.clear(); self.observed_exits.extend(exits)
        if any(not row['stopped'] for row in exits): raise RuntimeError('Owned worker descendant did not exit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New folder below data/index-scaling')
    parser.add_argument('--stages', type=int, nargs='+', default=[64, 256, 1024, 2304])
    parser.add_argument('--cover-width', type=int, default=96)
    parser.add_argument('--cover-height', type=int, default=128)
    parser.add_argument('--metadata-tags', type=int, default=0,
                        help='Generated Japanese tags, each 60 chars; 0..30 (catalog limit)')
    args = parser.parse_args()
    target = args.output.resolve()
    if os.name != 'nt': parser.error('Windows measurement only')
    if not target.is_relative_to((REPO / 'data/index-scaling').resolve()):
        parser.error('Output must be inside data/index-scaling')
    if target.exists(): parser.error('Use a fresh output folder')
    if args.stages != sorted(set(args.stages)) or not all(32 <= n <= MAX_ITEMS for n in args.stages):
        parser.error('Stages must be strictly increasing, within 32..10000')
    if not (32 <= args.cover_width <= 768 and 32 <= args.cover_height <= 768):
        parser.error('Cover dimensions must be within 32..768')
    if not 0 <= args.metadata_tags <= 30:
        parser.error('Metadata tags must be within 0..30')
    target.mkdir(parents=True); media = target / 'generated'; media.mkdir()
    report = {'pass': False, 'actual_model': True, 'native_gui_run': False,
              'profile': DEFAULT_PROFILE.to_dict(), 'profile_key': DEFAULT_PROFILE.key,
              'coverage_limit': MAX_ITEMS, 'stages': [], 'checks': [],
              'fixtures': {'cover_width': args.cover_width, 'cover_height': args.cover_height,
                           'metadata_tags': args.metadata_tags, 'tag_chars': 60,
                           'generated_sources_only': True},
              'memory_scope': 'During builds only: controller and owned worker process-tree CPU memory sampled every 0.2s. '
                              'CUDA value is torch max_memory_allocated per worker lifetime, '
                              'not reserved/context/whole GPU or GUI memory.'}
    catalog = None; ai = None; encoders = []
    original = source_digest(media)
    try:
        snapshot = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu',
                                   '--format=csv,noheader'], capture_output=True, text=True, timeout=10,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        report['gpu_baseline'] = snapshot.stdout.strip() if snapshot.returncode == 0 else 'unavailable'
    except (OSError, subprocess.TimeoutExpired):
        report['gpu_baseline'] = 'unavailable'
    def check(name, condition):
        report['checks'].append({'name': name, 'pass': bool(condition)})
        if not condition: raise RuntimeError(name)
    def save():
        (target / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    def new_ai():
        encoder = MeasuredEncoder(); encoders.append(encoder)
        check('existing offline runtime/model available', encoder.available)
        return AISearch(catalog, encoder), encoder
    def build(label, expected, cancelled=False):
        memory = {}; samples = 0; stop = threading.Event(); sample_errors = []
        def sample():
            nonlocal samples
            samples += 1
            controller = memory_bytes(os.getpid())
            if controller:
                maxima = memory.setdefault('controller', {})
                for name, value in controller.items(): maxima[name] = max(maxima.get(name, 0), value)
            worker = [memory_bytes(pid) for pid in encoder.observe()]
            worker = [value for value in worker if value]
            if worker:
                maxima = memory.setdefault('worker_tree', {})
                for name in ('working_set', 'private'):
                    maxima[name] = max(maxima.get(name, 0), sum(value[name] for value in worker))
                maxima['max_live_process_count'] = max(maxima.get('max_live_process_count', 0), len(worker))
        def monitor():
            while not stop.is_set():
                try: sample()
                except Exception as ex:
                    sample_errors.append(type(ex).__name__); return
                stop.wait(.2)
        before = encoder.calls.copy(); wall_before = encoder.wall_seconds.copy()
        thread = threading.Thread(target=monitor, daemon=True); thread.start()
        started = time.perf_counter()
        try:
            initial = ai.start(); start_seconds = time.perf_counter() - started
            ai.worker.join(3600)
            check(label + ' bounded build ended', not ai.worker.is_alive())
            state = ai.status(); sample()
            check(label + ' memory sampler healthy', not sample_errors)
            check(label + ' controller memory readable', bool(memory.get('controller')))
            if encoder.calls['document'] > before['document']:
                check(label + ' worker memory readable', bool(memory.get('worker_tree')))
            check(label + ' index state', state['state'] == ('cancelled' if cancelled else 'complete')
                  and state['indexed'] == expected and state['skipped'] == 0)
            entry = {'phase': label, 'seconds': time.perf_counter() - started,
                     'start_seconds': start_seconds, 'source_count': catalog.search()['total'],
                     'state': {k: state[k] for k in ('state', 'total', 'processed', 'indexed', 'skipped', 'device')},
                     'new_calls': dict(encoder.calls - before),
                     'encode_wall_seconds_including_lazy_load': dict(encoder.wall_seconds - wall_before),
                     'cuda_lifetime_peak_allocated_mib': encoder.peak_cuda_allocated_mib,
                     'cpu_memory_bytes': memory, 'memory_samples': samples}
            report['stages'].append(entry); save()
            print(json.dumps(entry, ensure_ascii=True), flush=True)
            return entry
        finally:
            stop.set(); thread.join(5)
    def query(label, count):
        results = []
        for phrase, source in [('傘が必要な暗い都会の景色', 'text'), ('青い画像', 'cover'),
                               ('傘が必要な暗い都会の景色', 'all')]:
            started = time.perf_counter(); found = ai.search(phrase, source=source)
            check(label + ' ' + source + ' available CUDA results', bool(found['items'])
                  and encoder.device == 'cuda' and found['coverage_limit'] == MAX_ITEMS)
            if source != 'cover': check(label + ' ' + source + ' indexed total', found['total'] == count)
            results.append({'source': source, 'seconds': time.perf_counter() - started,
                            'total': found['total'], 'top': [x['title'] for x in found['items'][:3]]})
        report.setdefault('queries', []).append({'phase': label, 'results': results})
        save()
    colors = [(88, 111, 190), (73, 133, 111), (176, 98, 86), (148, 97, 165)]
    images = [png(width=args.cover_width, height=args.cover_height, color=c) for c in colors]
    sentence = 'これは検索負荷確認専用の架空資料です。配色構図印刷用途素材保存整理制作記録。'
    tags = [(f'{n:02d}：' + sentence * 3)[:60] for n in range(args.metadata_tags)]
    generated = 0
    try:
        catalog = ProductionCatalog(target / 'catalog.sqlite')
        root = catalog.add_root(str(media))
        ai, encoder = new_ai()
        for index, count in enumerate(args.stages):
            # New fixtures only; prior generated bytes/size/mtime must remain unchanged.
            old_files = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in media.iterdir()}
            for i in range(generated, count):
                prefix = f'{i:05d}'
                if i == 0:
                    path = media / (prefix + '-雨の夜の街並み.wav'); path.write_bytes(b'Fictional audio metadata only')
                elif i % 32 == 1:
                    with zipfile.ZipFile(media / (prefix + '-generated-book.cbz'), 'w') as book:
                        book.writestr('page1.png', images[(i // 32) % 4])
                elif i % 16 == 2:
                    (media / (prefix + '-generated-image.png')).write_bytes(images[(i // 16) % 4])
                else:
                    (media / (prefix + '-晴れた昼の海辺.wav')).write_bytes(b'Fictional audio metadata only')
            check('prior source bytes/mtime unchanged ' + str(count),
                  all((media / name).read_bytes() == data and (media / name).stat().st_mtime_ns == mtime
                      for name, (data, mtime) in old_files.items()))
            del old_files
            original = source_digest(media); started = time.perf_counter()
            catalog.start_scan(root); catalog._worker.join(120)
            check('scan ' + str(count), not catalog._worker.is_alive()
                  and catalog.scan_state()['state'] == 'complete' and catalog.search()['total'] == count)
            report.setdefault('scans', []).append({'count': count, 'seconds': time.perf_counter() - started})
            # Exercise the public metadata validator, only for newly generated IDs.
            # Source files and older rows/vectors remain unchanged across stages.
            new_ids = [row['id'] for row in ai._iter_rows() if row['id'] > generated]
            if tags:
                for offset in range(0, len(new_ids), 120):
                    catalog.update(new_ids[offset:offset + 120], {'tags': tags})
            lengths = []
            for row in ai._iter_rows():
                check_tags = row['tags'] == tags if tags else not row['tags']
                if not check_tags: raise RuntimeError('Generated metadata mismatch')
                lengths.append(len(row['title'] + '\n' + row['relative_path'] + '\n' + '、'.join(row['tags'])))
            check('generated metadata validated ' + str(count), len(new_ids) == count - generated)
            report.setdefault('metadata_lengths', []).append({'count': count, 'min': min(lengths),
                                                             'max': max(lengths)})
            increment = count - generated
            if index == len(args.stages) - 1 and generated and increment > 96:
                before = encoder.calls['document']; encoder.on_document = lambda n: ai.cancel_build() if n == before + 96 else None
                part = build('cancel-' + str(count), generated + 96, cancelled=True)
                check('cancel adds only 96 new documents', part['new_calls'].get('document') == 96)
                ai.close(); ai, encoder = new_ai()
                entry = build('resume-' + str(count), count)
                check('restart encodes only missing documents', entry['new_calls'].get('document') == increment - 96)
            else:
                entry = build('index-' + str(count), count)
                check('incremental document count ' + str(count), entry['new_calls'].get('document') == increment)
            check('actual indexing used CUDA ' + str(count), encoder.device == 'cuda')
            with ai.store.connect() as db:
                counts = dict(db.execute('SELECT modality,COUNT(*) FROM ai_vectors GROUP BY modality'))
            check('complete text and cover vectors ' + str(count), counts.get('text') == count
                  and counts.get('cover') == sum(i % 32 == 1 or i % 16 == 2 for i in range(1, count)))
            entry['vector_counts'] = counts
            query(str(count), count)
            check('source bytes/size/mtime preserved after GPU ' + str(count), source_digest(media) == original)
            generated = count; save()
        ai.close(); ai, encoder = new_ai()
        cached = build('fresh-restart-cache', generated)
        check('cached restart no inference or loaded worker', not encoder.calls and encoder.process is None and not encoder.device)
        query('cached-restart', generated)
        check('cache query loads CUDA without document/image inference', encoder.calls == Counter(query=3))
        check('source digest unchanged after cache queries', source_digest(media) == original)
        report['source_digest'] = original
        totals = sum((e.calls for e in encoders), Counter())
        check('no duplicate document/cover inference across all restarts',
              totals['document'] == generated and totals['image'] ==
              sum(i % 32 == 1 or i % 16 == 2 for i in range(1, generated)))
        actual_sizes = sum((e.image_sizes for e in encoders), Counter())
        check('actual encoder receives requested cover dimensions',
              set(actual_sizes) == {(args.cover_width, args.cover_height)})
        report['actual_inputs'] = {'document_chars_min': min(n for e in encoders for n in e.input_lengths),
                                   'document_chars_max': max(n for e in encoders for n in e.input_lengths),
                                   'cover_sizes': [{'width': w, 'height': h, 'count': n}
                                                   for (w, h), n in actual_sizes.items()]}
        report['pass'] = True
    except Exception as ex:
        report['error'] = type(ex).__name__ + ': ' + str(ex)
    finally:
        try:
            if ai: ai.close()
            for owned in encoders:
                if owned.process and owned.process not in owned.children:
                    owned.children.append(owned.process)
                owned.close()
            check('all owned GPU workers stopped', all(child.poll() is not None for e in encoders for child in e.children))
        except Exception as ex:
            report['pass'] = False; report['cleanup_error'] = str(ex)
        if catalog: catalog.close()
        report['source_hashes_unchanged'] = source_digest(media) == original
        if not report['source_hashes_unchanged']: report['pass'] = False
        report['observed_process_exits'] = [row for e in encoders for row in e.observed_exits]
        report['worker_pids'] = [p.pid for e in encoders for p in e.children]
        report['inference_calls'] = dict(sum((e.calls for e in encoders), Counter()))
        report['max_cuda_allocated_mib'] = max((e.peak_cuda_allocated_mib for e in encoders), default=0)
        save()
        print(json.dumps({'pass': report['pass'], 'error': report.get('error'), 'checks': len(report['checks'])}), flush=True)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
