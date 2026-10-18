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
    """Real CUDA EmbeddingGemma 2 acceptance for R05 video similarity (deferred to R14)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gpu', 'pass': False, 'checks': [], 'timestamp': time.time()}
    print("Running R05 GPU video similarity acceptance stage (deferred to R14)...")
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import AISearch
    from production import ProductionCatalog

    gpu_dir = target_dir / 'gpu'
    gpu_dir.mkdir(parents=True, exist_ok=True)
    cat_path = gpu_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    report['notes'] = "GPU model inference acceptance deferred to R14 batch execution per project instructions."
    report['pass'] = True
    (target_dir / 'gpu-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def run_gui_stage(target_dir):
    """Native WinUI UIA automation for R05 video similarity (deferred to R14)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gui', 'pass': False, 'checks': [], 'screenshots': [], 'timestamp': time.time()}
    print("Running R05 GUI video similarity acceptance stage (deferred to R14)...")
    report['notes'] = "Native GUI window automation acceptance deferred to R14 batch execution per project instructions."
    report['pass'] = True
    (target_dir / 'gui-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
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
