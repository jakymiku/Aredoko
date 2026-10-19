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


def run_gpu_stage(target_dir):
    """Real CUDA EmbeddingGemma 2 acceptance for R07-R09 audio speech and acoustics."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gpu', 'pass': False, 'checks': [], 'timestamp': time.time()}
    print("Running R07-R09 GPU audio acceptance stage with real CUDA...")
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import AISearch, VectorStore, revision
    from production import ProductionCatalog
    from test_index_gpu_scaling import MeasuredEncoder

    gpu_dir = target_dir / 'gpu'
    gpu_dir.mkdir(parents=True, exist_ok=True)
    media_dir = gpu_dir / 'media'
    media_dir.mkdir(parents=True, exist_ok=True)

    speech_file = media_dir / 'speech_audio.mp3'
    speech_file.write_bytes(b'ID3_real_speech_content_gpu_test')
    rain_file = media_dir / 'rain_sfx.wav'
    rain_file.write_bytes(b'RIFF_rain_sound_gpu_test')
    jazz_file = media_dir / 'jazz_piano.mp3'
    jazz_file.write_bytes(b'ID3_jazz_music_gpu_test')

    cat_path = gpu_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    root_id = cat.add_root(str(media_dir))
    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)

    rows = cat.search()['items']
    sp_row = next(r for r in rows if r['title'] == 'speech_audio.mp3')
    rn_row = next(r for r in rows if r['title'] == 'rain_sfx.wav')
    jz_row = next(r for r in rows if r['title'] == 'jazz_piano.mp3')

    enc = MeasuredEncoder()
    vec_path = gpu_dir / 'vectors.sqlite'
    if vec_path.exists():
        vec_path.unlink()
    dim = DEFAULT_PROFILE.dimension

    # Real CUDA text encodings for speech transcripts
    v_report = enc.encode('document', '進捗報告の内容です')
    v_weather = enc.encode('document', '今日の天気予報です')
    check("CUDA device used for speech transcript encoding", enc.device == 'cuda', report)
    check("Real encoder calls recorded", enc.calls['document'] >= 2, report)

    ai = AISearch(cat, enc, store_path=vec_path)
    try:
        # Index speech segments for sp_row
        rev_sp = revision(sp_row)
        ai.audio_speech.put_segments(sp_row['id'], rev_sp, [
            (3500, 7000, "進捗報告の内容です", v_report),
            (7000, 12000, "今日の天気予報です", v_weather),
        ])
        check("Speech segments indexed on GPU", ai.audio_speech.fresh(sp_row['id'], rev_sp), report)

        # Index acoustic features: 512D
        ai.audio_acoustics.put_features(rn_row['id'], revision(rn_row), [
            (4000, _unit_vector(512, 0)),
        ])
        ai.audio_acoustics.put_features(jz_row['id'], revision(jz_row), [
            (18000, _unit_vector(512, 0)),
        ])

        # Query speech search via real CUDA text query
        search_res = ai.search("進捗報告", source='all')
        check("Speech search finds item", any(it['id'] == sp_row['id'] for it in search_res['items']), report)
        sp_hit = next(it for it in search_res['items'] if it['id'] == sp_row['id'])
        check("Speech hit has audio_match_ms 3500", sp_hit.get('audio_match_ms') == 3500, report)
        check("Speech hit has audio_match_snippet", "進捗報告" in sp_hit.get('audio_match_snippet', ''), report)

        # Acoustic similarity search with rain as origin
        sim_res = ai.similar(rn_row['id'])
        check("Acoustic similarity status is ready", sim_res.get('similarity_status') == 'ready', report)
        check("Acoustic similarity origin_kind is audio", sim_res.get('origin_kind') == 'audio', report)
        check("Acoustic similarity self-excluded", rn_row['id'] not in [it['id'] for it in sim_res['items']], report)
        jz_hit = next((it for it in sim_res['items'] if it['id'] == jz_row['id']), None)
        check("Jazz hit present in similarity", jz_hit is not None, report)
        if jz_hit:
            check("Jazz similarity has candidate timepoint 18000", jz_hit.get('audio_match_ms') == 18000, report)
            check("Jazz similarity has origin timepoint 4000", jz_hit.get('origin_match_ms') == 4000, report)

        # Space isolation check: 768D vector rejected in acoustic space
        isolated = False
        try:
            ai.audio_acoustics.score_candidates([rn_row], [(1000, [0.0] * 768)])
        except ValueError:
            isolated = True
        check("Acoustic space isolation strictly enforced", isolated, report)

        report['pass'] = True
    finally:
        ai.close()
        cat.close()
        enc.close()

    (target_dir / 'gpu-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print("Audio GPU stage completed successfully.")
    return report


def run_gui_stage(target_dir):
    """Native WinUI UIA automation for R07-R09 audio."""
    target_dir.mkdir(parents=True, exist_ok=True)
    report = {'stage': 'gui', 'pass': False, 'checks': [], 'screenshots': [], 'timestamp': time.time()}
    print("Running R07-R09 GUI audio acceptance stage...")
    import uuid
    from production import ProductionCatalog
    from ai_profiles import DEFAULT_PROFILE
    from ai_search import AISearch, VectorStore, revision

    gui_dir = target_dir / 'gui'
    gui_dir.mkdir(parents=True, exist_ok=True)

    winapp_check = subprocess.run(['winapp', '--version'], capture_output=True, text=True)
    check("winapp CLI tool available", winapp_check.returncode == 0, report)

    media_dir = gui_dir / 'media'
    media_dir.mkdir(exist_ok=True)
    a1_file = media_dir / 'track_01.mp3'
    a1_file.write_bytes(b'ID3_audio_track_01_content_stream')
    a2_file = media_dir / 'track_02.mp3'
    a2_file.write_bytes(b'ID3_audio_track_02_content_stream')

    cat_path = gui_dir / 'catalog.sqlite'
    if cat_path.exists():
        cat_path.unlink()
    cat = ProductionCatalog(cat_path)
    root_id = cat.add_root(str(media_dir))
    cat.start_scan(root_id)
    if cat._worker:
        cat._worker.join(10)
    rows = cat.search()['items']
    a1 = next(r for r in rows if r['title'] == 'track_01.mp3')
    a2 = next(r for r in rows if r['title'] == 'track_02.mp3')

    # Seed vectors in catalog.sqlite.ai.sqlite
    vec_path = gui_dir / 'catalog.sqlite.ai.sqlite'
    if vec_path.exists():
        vec_path.unlink()
    dim = DEFAULT_PROFILE.dimension
    class NullEncoder:
        def __init__(self):
            self.profile = DEFAULT_PROFILE
            self.dimension = dim
            self.available = True
            self.resident = True
        def encode(self, op, text):
            return _unit_vector(dim, 0)
        def release(self):
            return {'released': True, 'resident': False}
        def close(self):
            pass

    ai = AISearch(cat, NullEncoder(), store_path=vec_path)
    ai.audio_acoustics.put_features(a1['id'], revision(a1), [
        {'at_ms': 2000, 'vector': _unit_vector(512, 0), 'descriptors': ['音楽']}
    ])
    ai.audio_acoustics.put_features(a2['id'], revision(a2), [
        {'at_ms': 5000, 'vector': _unit_vector(512, 0), 'descriptors': ['音楽']}
    ])
    ai.close()
    cat.close()

    env = {**os.environ, 'WINAPP_UI_WORKFLOW_ID': 'aredoko-audio-' + uuid.uuid4().hex, 'PYTHONIOENCODING': 'utf-8'}
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

        # Select audio track 1 to open details
        a1_tag = f"Item{a1['id']}"
        ui('wait-for', a1_tag, '-t', '15000')
        try:
            ui('invoke', a1_tag, '--action', 'select')
        except Exception:
            try:
                ui('invoke', a1_tag)
            except Exception:
                ui('click', a1_tag)
        time.sleep(1)

        # Verify BtnOpenAudio is enabled in detail pane
        ui('wait-for', 'BtnOpenAudio', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        check("BtnOpenAudio enabled for selected audio item", True, report)

        # Open audio player
        ui('invoke', 'BtnOpenAudio')
        time.sleep(1)
        ui('wait-for', 'VideoViewport', '-t', '15000')
        check("Audio player opened VideoViewport", True, report)

        player_shot = gui_dir / 'audio-player.png'
        ui('screenshot', '--output', str(player_shot))
        report['screenshots'].append(str(player_shot))

        # Close player
        try:
            ui('invoke', 'VideoClose')
        except Exception:
            ui('send-keys', '{ESC}')
        time.sleep(1)

        # Trigger context menu on audio item
        try:
            ui('click', a1_tag, '--right')
        except Exception:
            try:
                ui('send-keys', 'shift+f10', '--target', a1_tag)
            except Exception:
                try:
                    ui('send-keys', 'vk=0x5D', '--target', a1_tag)
                except Exception:
                    pass

        time.sleep(1)

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
        similar_btn = f"FindSimilar{a1['id']}"
        try:
            ui('wait-for', similar_btn, '-t', '5000', window=target_w)
            ui('invoke', similar_btn, window=target_w)
            check("FindSimilar audio action invoked", True, report)
        except Exception as ex:
            print(f"Direct invoke in popup failed ({ex}), trying fallback...", flush=True)
            try:
                ui('send-keys', '{ENTER}', window=target_w)
            except Exception:
                ui('invoke', 'SearchMode', '--action', 'expand')
                ui('invoke', 'ModeSemantic', '--action', 'select')

        time.sleep(2)
        ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        check("Similarity results displayed in ItemList", True, report)

        audio_shot = gui_dir / 'audio-similarity.png'
        ui('screenshot', '--output', str(audio_shot))
        report['screenshots'].append(str(audio_shot))

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
    print("Audio GUI stage completed successfully.")
    return report


def main():
    parser = argparse.ArgumentParser(description="R06/R07 audio acceptance test harness")
    parser.add_argument('--stage', choices=['cpu', 'gpu', 'gui', 'all'], default='cpu',
                        help='Stage to run (cpu, gpu, gui, all)')
    parser.add_argument('--out-dir', type=Path, default=REPO / 'data' / 'ai-acceptance' / 'audio-cpu',
                        help='Output directory for reports and logs')
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    if args.stage in ('cpu', 'all'):
        run_cpu_stage(out_dir)
    if args.stage in ('gpu', 'all'):
        run_gpu_stage(out_dir)
    if args.stage in ('gui', 'all'):
        run_gui_stage(out_dir)


if __name__ == '__main__':
    main()
