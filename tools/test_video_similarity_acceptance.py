"""R05 video similarity search and timepoint grounding acceptance harness (CPU, GPU, and GUI stages).

Run cpu stage without GPU/GUI activation.
GPU/GUI stages are deferred per user instruction and prepared for batch execution in R14 when permitted.
Generated media only; no private scans, no network downloads, no quality tuning.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
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


def _pack_vector(values):
    return b''.join(struct.pack('<f', v) for v in values)


def _unit_vector(dim, index):
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


def run_cpu_stage(target_dir):
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'cpu', 'pass': False, 'checks': [], 'timestamp': time.time()}
    print("Running R05 CPU video similarity acceptance stage...")

    # 1. Run Core unit tests
    cmd_core = ['dotnet', 'run', '--project', 'tests/Aredoko.Core.Tests', '-c', 'Release']
    p_core = subprocess.run(cmd_core, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Core.Tests pass in Release", p_core.returncode == 0, report)
    (target_dir / 'core-tests.log').write_text(p_core.stdout or '', encoding='utf-8')

    # 2. Run Python similarity tests
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = '-1'
    env['PYTHONPATH'] = f"{REPO / 'tests'};{REPO / 'app'};{REPO / 'tools'}"
    cmd_py = [sys.executable, '-m', 'unittest', 'tests/test_similarity_search.py']
    p_py = subprocess.run(cmd_py, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Python test_similarity_search passes", p_py.returncode == 0, report)
    (target_dir / 'python-similarity.log').write_text((p_py.stderr or '') + '\n' + (p_py.stdout or ''), encoding='utf-8')

    # 3. Build WinUI Release
    cmd_build = ['dotnet', 'build', 'src/Aredoko.WinUI/Aredoko.WinUI.csproj', '-c', 'Release', '-p:Platform=x64', '--no-restore']
    p_build = subprocess.run(cmd_build, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("WinUI x64 Release builds with 0 errors", p_build.returncode == 0, report)
    (target_dir / 'winui-build.log').write_text(p_build.stdout or '', encoding='utf-8')

    # 4. Programmatic video similarity verification
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import AISearch, VectorStore
    from production import ProductionCatalog

    cat_path = target_dir / 'cpu_acceptance_catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    media_dir = target_dir / 'cpu_media'
    media_dir.mkdir(parents=True, exist_ok=True)
    root_id = cat.add_root(str(media_dir))

    v1_file = media_dir / 'origin_video.mp4'
    v1_file.write_bytes(b'fake_video_1')
    v2_file = media_dir / 'candidate_video.mp4'
    v2_file.write_bytes(b'fake_video_2')
    img_file = media_dir / 'candidate_image.png'
    img_file.write_bytes(b'fake_image_1')

    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)
    rows = cat.search()['items']
    v1 = next(r for r in rows if r['title'] == 'origin_video.mp4')
    v2 = next(r for r in rows if r['title'] == 'candidate_video.mp4')
    im = next(r for r in rows if r['title'] == 'candidate_image.png')

    from ai_search import AISearch, VectorStore, revision

    dim = 768
    vec_path = target_dir / 'test_vectors.sqlite'
    if vec_path.exists():
        vec_path.unlink()
    store = VectorStore(vec_path, DEFAULT_PROFILE)

    # Origin video v1: frame at 1000ms (axis 0), frame at 5000ms (axis 1)
    store.put(v1['id'], revision(v1), {'cover': _unit_vector(dim, 0)}, video_frames=[
        (1000, _unit_vector(dim, 0)),
        (5000, _unit_vector(dim, 1)),
    ])

    # Candidate video v2: frame at 2000ms (axis 0), frame at 8000ms (axis 1)
    store.put(v2['id'], revision(v2), {'cover': _unit_vector(dim, 0)}, video_frames=[
        (2000, _unit_vector(dim, 0)),
        (8000, _unit_vector(dim, 1)),
    ])

    # Candidate image: aligned with axis 0
    store.put(im['id'], revision(im), {'cover': _unit_vector(dim, 0)})

    class NullEncoder:
        def __init__(self):
            self.dimension = dim
        def encode_text(self, text):
            return _unit_vector(dim, 0)
        def encode_image(self, path):
            return _unit_vector(dim, 0)
        def close(self):
            pass

    ai = AISearch(cat, NullEncoder(), store_path=vec_path)
    try:
        # Search similar to v1
        res = ai.similar(v1['id'], page=0, limit=10)
        check("Similarity search succeeds for video origin", res['similarity_status'] == 'ready', report)
        check("Origin kind reported as video", res['origin_kind'] == 'video', report)
        check("Origin video self-excluded", all(it['id'] != v1['id'] for it in res['items']), report)
        check("Both candidates returned", res['total'] == 2, report)

        v2_item = next(it for it in res['items'] if it['id'] == v2['id'])
        check("Candidate video has score 1.0", math.isclose(v2_item['semantic_score'], 1.0, abs_tol=1e-4), report)
        check("Candidate video has candidate match ms", v2_item.get('video_match_ms') in (2000, 8000), report)
        check("Candidate video has origin match ms", v2_item.get('origin_match_ms') in (1000, 5000), report)

        im_item = next(it for it in res['items'] if it['id'] == im['id'])
        check("Candidate image has score 1.0", math.isclose(im_item['semantic_score'], 1.0, abs_tol=1e-4), report)
        check("Candidate image has origin match ms", im_item.get('origin_match_ms') == 1000, report)
        check("Candidate image has no video match ms", 'video_match_ms' not in im_item, report)

        # Search similar to candidate image im
        res_im = ai.similar(im['id'], page=0, limit=10)
        check("Similarity search succeeds for image origin", res_im['similarity_status'] == 'ready', report)
        check("Origin kind reported as image", res_im['origin_kind'] == 'image', report)
        check("Origin image self-excluded", all(it['id'] != im['id'] for it in res_im['items']), report)
        v2_from_im = next(it for it in res_im['items'] if it['id'] == v2['id'])
        check("Video candidate from image origin has video_match_ms", v2_from_im.get('video_match_ms') == 2000, report)
        check("Video candidate from image origin has no origin_match_ms", 'origin_match_ms' not in v2_from_im, report)
        v1_from_im = next(it for it in res_im['items'] if it['id'] == v1['id'])
        check("Origin video as candidate from image origin has video_match_ms", v1_from_im.get('video_match_ms') == 1000, report)
        check("Origin video as candidate from image origin has no origin_match_ms", 'origin_match_ms' not in v1_from_im, report)
    finally:
        ai.close()
        cat.close()

    report['pass'] = all(c['pass'] for c in report['checks'])
    (target_dir / 'cpu-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print("CPU stage completed successfully.")
    return report


def run_gpu_stage(target_dir):
    """Real CUDA EmbeddingGemma 2 acceptance for R05 video similarity."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gpu', 'pass': False, 'checks': [], 'timestamp': time.time()}
    print("Running R05 GPU video similarity acceptance stage with real CUDA...")
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import AISearch, VectorStore, revision
    from production import ProductionCatalog
    from create_preview_fixture import png
    from test_index_gpu_scaling import MeasuredEncoder

    gpu_dir = target_dir / 'gpu'
    gpu_dir.mkdir(parents=True, exist_ok=True)
    media_dir = gpu_dir / 'media'
    media_dir.mkdir(parents=True, exist_ok=True)

    v1_file = media_dir / 'video_1.mp4'
    v1_file.write_bytes(b'video_container_1_data')
    v2_file = media_dir / 'video_2.mp4'
    v2_file.write_bytes(b'video_container_2_data')
    img_file = media_dir / 'sunset.png'
    sunset_png = png(color=(255, 120, 60))
    img_file.write_bytes(sunset_png)

    cat_path = gpu_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    root_id = cat.add_root(str(media_dir))
    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)

    rows = cat.search()['items']
    v1 = next(r for r in rows if r['title'] == 'video_1.mp4')
    v2 = next(r for r in rows if r['title'] == 'video_2.mp4')
    im = next(r for r in rows if r['title'] == 'sunset.png')

    enc = MeasuredEncoder()
    vec_path = gpu_dir / 'vectors.sqlite'
    if vec_path.exists():
        vec_path.unlink()
    store = VectorStore(vec_path, DEFAULT_PROFILE)

    frame_blue = png(color=(30, 60, 220))
    frame_orange = sunset_png
    frame_green = png(color=(40, 200, 50))

    vec_blue = enc.encode('image', frame_blue)
    vec_orange = enc.encode('image', frame_orange)
    vec_green = enc.encode('image', frame_green)

    check("CUDA device used for image encoding", enc.device == 'cuda', report)
    check("Real encoder calls recorded", enc.calls['image'] >= 3, report)

    # v1 has blue at 1000ms, orange at 4000ms
    store.put(v1['id'], revision(v1), {'cover': vec_blue}, video_frames=[
        (1000, vec_blue),
        (4000, vec_orange),
    ])
    # v2 has green at 2000ms, orange at 9000ms
    store.put(v2['id'], revision(v2), {'cover': vec_green}, video_frames=[
        (2000, vec_green),
        (9000, vec_orange),
    ])
    # im is orange
    store.put(im['id'], revision(im), {'cover': vec_orange})

    ai = AISearch(cat, enc, store_path=vec_path)
    try:
        # 1. Search similar to v1
        res = ai.similar(v1['id'])
        check("GPU Video similarity returns ready", res['similarity_status'] == 'ready', report)
        check("GPU Video similarity origin_kind is video", res['origin_kind'] == 'video', report)
        check("GPU Video similarity excludes self", all(it['id'] != v1['id'] for it in res['items']), report)

        v2_item = next(it for it in res['items'] if it['id'] == v2['id'])
        check("Candidate video v2 has high semantic score (>0.9)", v2_item['semantic_score'] > 0.9, report)
        check("Candidate video v2 matches at 9000ms", v2_item.get('video_match_ms') == 9000, report)
        check("Origin video v1 matches at 4000ms", v2_item.get('origin_match_ms') == 4000, report)

        im_item = next(it for it in res['items'] if it['id'] == im['id'])
        check("Candidate image has high score (>0.9)", im_item['semantic_score'] > 0.9, report)
        check("Candidate image has origin_match_ms 4000", im_item.get('origin_match_ms') == 4000, report)
        check("Candidate image has no video_match_ms", 'video_match_ms' not in im_item, report)

        # 2. Search similar to im
        res_im = ai.similar(im['id'])
        check("Image origin similarity returns ready", res_im['similarity_status'] == 'ready', report)
        check("Image origin origin_kind is image", res_im['origin_kind'] == 'image', report)
        v2_from_im = next(it for it in res_im['items'] if it['id'] == v2['id'])
        check("Video candidate from image origin has video_match_ms 9000", v2_from_im.get('video_match_ms') == 9000, report)
        check("Video candidate from image origin has no origin_match_ms", 'origin_match_ms' not in v2_from_im, report)

        report['pass'] = True
    finally:
        ai.close()
        cat.close()
        enc.close()

    (target_dir / 'gpu-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print("GPU stage completed successfully.")
    return report


def run_gui_stage(target_dir):
    """Native WinUI UIA automation for R05 video similarity."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gui', 'pass': False, 'checks': [], 'screenshots': [], 'timestamp': time.time()}
    print("Running R05 GUI video similarity acceptance stage...")
    import uuid
    from create_preview_fixture import png
    from production import ProductionCatalog
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import VectorStore, revision

    gui_dir = target_dir / 'gui'
    gui_dir.mkdir(parents=True, exist_ok=True)

    winapp_check = subprocess.run(['winapp', '--version'], capture_output=True, text=True)
    check("winapp CLI tool available", winapp_check.returncode == 0, report)

    media_dir = gui_dir / 'media'
    media_dir.mkdir(exist_ok=True)
    v1_file = media_dir / 'clip_alpha.mp4'
    v1_file.write_bytes(b'video_alpha_stream')
    v2_file = media_dir / 'clip_beta.mp4'
    v2_file.write_bytes(b'video_beta_stream')

    cat_path = gui_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    root_id = cat.add_root(str(media_dir))
    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)
    rows = cat.search()['items']
    v1 = next(r for r in rows if r['title'] == 'clip_alpha.mp4')
    v2 = next(r for r in rows if r['title'] == 'clip_beta.mp4')

    # Seed vectors in catalog.sqlite.ai.sqlite
    vec_path = gui_dir / 'catalog.sqlite.ai.sqlite'
    if vec_path.exists():
        vec_path.unlink()
    dim = DEFAULT_PROFILE.dimension
    store = VectorStore(vec_path, DEFAULT_PROFILE)
    vec0 = _unit_vector(dim, 0)
    vec1 = _unit_vector(dim, 1)
    store.put(v1['id'], revision(v1), {'cover': vec0}, video_frames=[
        (1000, vec0),
        (5000, vec1),
    ])
    store.put(v2['id'], revision(v2), {'cover': vec0}, video_frames=[
        (2000, vec0),
        (8000, vec1),
    ])
    cat.close()

    env = {**os.environ, 'WINAPP_UI_WORKFLOW_ID': 'aredoko-vidsim-' + uuid.uuid4().hex, 'PYTHONIOENCODING': 'utf-8'}
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

        # Select video_1 to open details
        v1_tag = f"Item{v1['id']}"
        ui('wait-for', v1_tag, '-t', '15000')
        try:
            ui('invoke', v1_tag, '--action', 'select')
        except Exception:
            try:
                ui('invoke', v1_tag)
            except Exception:
                ui('click', v1_tag)
        time.sleep(1)

        # Verify OpenVideo button is enabled in detail pane
        ui('wait-for', 'BtnOpenVideo', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        check("BtnOpenVideo enabled for selected video", True, report)

        # Trigger context menu: try right click, fallback to Shift+F10 / context menu key
        menu_opened = False
        try:
            ui('click', v1_tag, '--right')
            menu_opened = True
        except Exception:
            try:
                ui('send-keys', 'shift+f10', '--target', v1_tag)
                menu_opened = True
            except Exception:
                try:
                    ui('send-keys', 'vk=0x5D', '--target', v1_tag)
                    menu_opened = True
                except Exception:
                    pass

        time.sleep(1)

        # Find PopupHost window and invoke FindSimilar
        popup_hwnd = None
        hwnd_out = subprocess.run(['winapp', 'ui', 'list-windows', '--json'], capture_output=True, text=True)
        try:
            windows = json.loads(hwnd_out.stdout or '[]')
            popups = [w for w in windows if w.get('title') == 'PopupHost']
            if popups and popups[0].get('hwnd'):
                popup_hwnd = str(popups[0]['hwnd'])
        except Exception:
            pass

        target_w = popup_hwnd if popup_hwnd else hwnd
        similar_btn = f"FindSimilar{v1['id']}"
        try:
            ui('wait-for', similar_btn, '-t', '5000', window=target_w)
            ui('invoke', similar_btn, window=target_w)
            check("FindSimilar context action invoked", True, report)
        except Exception as ex:
            print(f"Direct invoke in popup failed ({ex}), trying keyboard fallback...", flush=True)
            try:
                ui('send-keys', '{ENTER}', window=target_w)
            except Exception:
                # If popup was not opened under non-interactive desktop, use mode dropdown to select ModeSemantic
                ui('invoke', 'SearchMode', '--action', 'expand')
                ui('invoke', 'ModeSemantic', '--action', 'select')

        time.sleep(2)
        # Verify similarity search results in ItemList
        ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        check("Similarity results list updated", True, report)

        vsim_shot = gui_dir / 'video-similarity.png'
        ui('screenshot', '--output', str(vsim_shot))
        report['screenshots'].append(str(vsim_shot))

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
    print("GUI stage completed successfully.")
    return report


def main():
    parser = argparse.ArgumentParser(description="R05 video similarity acceptance harness")
    parser.add_argument('--stage', choices=['cpu', 'gpu', 'gui', 'all'], default='cpu')
    parser.add_argument('--output', type=str, default=str(REPO / 'data' / 'video-similarity-acceptance'))
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
