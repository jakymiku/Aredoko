"""R06/R07 audio speech content indexing and time-grounded search acceptance harness.

Run cpu stage without GPU/GUI activation.
GPU/GUI stages are deferred per user instruction and prepared for batch execution in R14.
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
    print("Running R06/R07 CPU audio speech acceptance stage...")

    # 1. Run Core unit tests
    cmd_core = ['dotnet', 'run', '--project', 'tests/Aredoko.Core.Tests', '-c', 'Release']
    p_core = subprocess.run(cmd_core, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Core.Tests pass in Release", p_core.returncode == 0, report)
    (target_dir / 'core-tests.log').write_text(p_core.stdout or '', encoding='utf-8')

    # 2. Run Python audio semantics & acoustics tests
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = '-1'
    env['PYTHONPATH'] = f"{REPO / 'tests'};{REPO / 'app'};{REPO / 'tools'}"
    cmd_py1 = [sys.executable, '-m', 'unittest', 'tests/test_audio_semantics.py']
    p_py1 = subprocess.run(cmd_py1, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Python test_audio_semantics passes", p_py1.returncode == 0, report)

    cmd_py2 = [sys.executable, '-m', 'unittest', 'tests/test_audio_acoustics.py']
    p_py2 = subprocess.run(cmd_py2, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("Python test_audio_acoustics passes", p_py2.returncode == 0, report)
    (target_dir / 'python-audio.log').write_text((p_py1.stderr or '') + '\n' + (p_py2.stderr or '') + '\n' + (p_py2.stdout or ''), encoding='utf-8')

    # 3. Build WinUI Release
    cmd_build = ['dotnet', 'build', 'src/Aredoko.WinUI/Aredoko.WinUI.csproj', '-c', 'Release', '-p:Platform=x64', '--no-restore']
    p_build = subprocess.run(cmd_build, cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')
    check("WinUI x64 Release builds with 0 errors", p_build.returncode == 0, report)
    (target_dir / 'winui-build.log').write_text(p_build.stdout or '', encoding='utf-8')

    # 4. Programmatic audio speech verification
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import AISearch, VectorStore, revision
    from audio_semantics import AudioSpeechVectors, CONTRACT
    from production import ProductionCatalog

    cat_path = target_dir / 'audio_acceptance_catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    media_dir = target_dir / 'audio_media'
    media_dir.mkdir(parents=True, exist_ok=True)
    root_id = cat.add_root(str(media_dir))

    audio_file = media_dir / 'speech_audio.mp3'
    audio_file.write_bytes(b'ID3_audio_speech_content_test')
    silence_file = media_dir / 'silent_audio.wav'
    silence_file.write_bytes(b'RIFF_silence_audio_content_test')
    rain_file = media_dir / 'rain_sfx.wav'
    rain_file.write_bytes(b'RIFF_rain_sfx_audio_content_test')
    jazz_file = media_dir / 'jazz_piano.mp3'
    jazz_file.write_bytes(b'ID3_jazz_piano_audio_content_test')

    initial_mtime = audio_file.stat().st_mtime_ns
    rain_mtime = rain_file.stat().st_mtime_ns

    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)
    rows = cat.search()['items']
    a_row = next(r for r in rows if r['title'] == 'speech_audio.mp3')
    s_row = next(r for r in rows if r['title'] == 'silent_audio.wav')
    r_row = next(r for r in rows if r['title'] == 'rain_sfx.wav')
    j_row = next(r for r in rows if r['title'] == 'jazz_piano.mp3')

    dim = 768
    vec_path = target_dir / 'audio_vectors.sqlite'
    if vec_path.exists():
        vec_path.unlink()
    store = VectorStore(vec_path, DEFAULT_PROFILE)

    class MockEncoder:
        def __init__(self):
            self.profile = DEFAULT_PROFILE
            self.dimension = dim
            self.available = True
            self.resident = True
            self.calls = []

        def encode(self, op, text):
            self.calls.append((op, text))
            v = [0.0] * dim
            if '報告' in text:
                v[0] = 1.0
            else:
                v[1] = 1.0
            return v

        def release(self):
            return {'released': True, 'resident': False}

        def close(self):
            pass

    encoder = MockEncoder()
    ai = AISearch(cat, encoder, store_path=vec_path)

    # Index speech segments for a_row
    # Segment 1 at 3500ms matching '報告' (axis 0)
    rev_a = revision(a_row)
    ai.audio_speech.put_segments(a_row['id'], rev_a, [
        (3500, 8000, "進捗報告の内容です", _unit_vector(dim, 0)),
        (8000, 15000, "その他の発言です", _unit_vector(dim, 1)),
    ])

    check("Speech segments indexed and fresh", ai.audio_speech.fresh(a_row['id'], rev_a), report)
    check("Silent audio has no segments", not ai.audio_speech.fresh(s_row['id'], revision(s_row)), report)

    # Search for "報告"
    query_vec = _unit_vector(dim, 0)
    speech_scores = ai.audio_speech.rank([a_row, s_row], query_vec)
    check("Speech rank hits audio file", a_row['id'] in speech_scores, report)
    check("Speech rank ignores silent file", s_row['id'] not in speech_scores, report)

    score, evid = speech_scores[a_row['id']]
    check("Speech segment score is 1.0", abs(score - 1.0) < 1e-4, report)
    check("Speech segment start_ms grounded to 3500ms", evid['start_ms'] == 3500, report)
    check("Speech segment snippet captured", evid['snippet'] == "進捗報告の内容です", report)

    # Full search through AISearch.search
    search_res = ai.search("進捗報告", source='all')
    check("Search complete", search_res.get('search_complete') is True, report)
    hit = next((it for it in search_res['items'] if it['id'] == a_row['id']), None)
    check("Audio hit in search items", hit is not None, report)
    if hit:
        check("Audio hit has audio_match_ms 3500", hit.get('audio_match_ms') == 3500, report)
        check("Audio hit has snippet", hit.get('audio_match_snippet') == "進捗報告の内容です", report)

    # Verify zero-allocation packed vector reuse
    cached_segs = ai.audio_speech.get_segments(a_row['id'], rev_a, include_vectors=False)
    check("Cached segments retrieved as raw bytes", len(cached_segs) == 2 and isinstance(cached_segs[0]['vector'], bytes), report)
    ai.audio_speech.put_segments(a_row['id'], rev_a, cached_segs)
    check("Cached packed vectors reused successfully", ai.audio_speech.fresh(a_row['id'], rev_a), report)

    # Programmatic R08 acoustic features and similarity verification
    from audio_acoustics import ACOUSTIC_DIMENSION, CONTRACT as ACOUSTIC_CONTRACT
    ac_dim = ACOUSTIC_DIMENSION
    rev_r = revision(r_row)
    rev_j = revision(j_row)
    v_shared = _unit_vector(ac_dim, 25)
    v_diff = _unit_vector(ac_dim, 50)

    ai.audio_acoustics.put_features(r_row['id'], rev_r, [
        {'at_ms': 4000, 'vector': v_shared, 'descriptors': ['雨音', '激しい雨']},
        {'at_ms': 12000, 'vector': v_diff, 'descriptors': ['環境音']}
    ])
    ai.audio_acoustics.put_features(j_row['id'], rev_j, [
        {'at_ms': 18000, 'vector': v_shared, 'descriptors': ['ジャズピアノ', 'BGM']}
    ])

    check("Acoustic features indexed and fresh", ai.audio_acoustics.fresh(r_row['id'], rev_r), report)
    check("Silent audio has no acoustic features", not ai.audio_acoustics.fresh(s_row['id'], revision(s_row)), report)

    # Search with acoustic descriptor "雨音"
    acoustic_search = ai.search("雨音", source='all')
    check("Acoustic search complete", acoustic_search.get('search_complete') is True, report)
    rain_hit = next((it for it in acoustic_search['items'] if it['id'] == r_row['id']), None)
    check("Rain audio hit in search items", rain_hit is not None, report)
    if rain_hit:
        check("Rain hit has audio_match_ms 4000", rain_hit.get('audio_match_ms') == 4000, report)
        check("Rain hit has acoustic snippet", "雨音" in rain_hit.get('audio_match_snippet', ''), report)

    # Audio similarity search with rain as origin
    sim_res = ai.similar(r_row['id'])
    check("Audio similarity status is ready", sim_res.get('similarity_status') == 'ready', report)
    check("Audio similarity source is acoustic", sim_res.get('source') == 'acoustic', report)
    check("Audio similarity origin_kind is audio", sim_res.get('origin_kind') == 'audio', report)
    check("Audio similarity excludes self", r_row['id'] not in [it['id'] for it in sim_res['items']], report)
    jazz_sim_hit = next((it for it in sim_res['items'] if it['id'] == j_row['id']), None)
    check("Jazz hit in similarity items", jazz_sim_hit is not None, report)
    if jazz_sim_hit:
        check("Similarity hit has audio_match_ms 18000", jazz_sim_hit.get('audio_match_ms') == 18000, report)
        check("Similarity hit has origin_match_ms 4000", jazz_sim_hit.get('origin_match_ms') == 4000, report)

    # Unindexed origin returns unindexed fallback cleanly
    sim_unindexed = ai.similar(s_row['id'])
    check("Silent audio origin returns unindexed", sim_unindexed.get('similarity_status') == 'unindexed', report)

    # Space isolation check: 768D vector rejected in acoustic space
    isolated = False
    try:
        ai.audio_acoustics.score_candidates([r_row], [(1000, [0.0] * 768)])
    except ValueError:
        isolated = True
    check("Acoustic space isolation strictly enforced", isolated, report)

    # Previews audio manifest and range check
    from previews import PreviewReader
    prev = PreviewReader(cat)
    manifest = prev.audio_manifest(r_row['id'])
    check("Audio manifest generated with audio/wav mime", manifest.get('mime') == 'audio/wav', report)
    range_data, range_mime, range_total = prev.audio_range(r_row['id'], 0, 15, manifest['revision'])
    check("Audio range reads valid byte slice", len(range_data) == 16 and range_total > 16, report)

    # Verify original source media immutability
    check("Original source audio unmodified", audio_file.stat().st_mtime_ns == initial_mtime, report)
    check("Original rain audio unmodified", rain_file.stat().st_mtime_ns == rain_mtime, report)

    ai.close()
    cat.close()
    report['pass'] = all(c['pass'] for c in report['checks'])
    (target_dir / 'cpu-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"R06-R09 CPU acceptance STAGE PASS: {len(report['checks'])} checks verified.")


def main():
    parser = argparse.ArgumentParser(description="R06/R07 audio acceptance test harness")
    parser.add_argument('--stage', choices=['cpu', 'gpu', 'gui', 'all'], default='cpu',
                        help='Stage to run (gpu and gui are deferred per user instruction)')
    parser.add_argument('--out-dir', type=Path, default=REPO / 'data' / 'ai-acceptance' / 'audio-cpu',
                        help='Output directory for reports and logs')
    args = parser.parse_args()

    if args.stage in ('gpu', 'gui'):
        print(f"STAGE {args.stage.upper()} DEFERRED: Deferred per user instruction for batch verification in R14.")
        sys.exit(0)

    if args.stage in ('cpu', 'all'):
        run_cpu_stage(args.out_dir)


if __name__ == '__main__':
    main()
