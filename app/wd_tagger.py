"""Replaceable, explicitly local WD adapter with owned worker cleanup."""
import base64
import email.parser
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from ai_process import AIUnavailable,worker_failure
from ai_search import AIBusy
from ai_runtime_preferences import read_preferences,model_root
from model_locations import ModelTarget
from tag_suggestions import TaggerInfo, TagProposal, SuggestionConflict
from tagger_profile import load_profile, RUNTIME_VERSION, WDProfile
from tagger_worker import labels, bundled_ort_dll
from runtime_paths import worker_python,worker_command,runtime_root,bound_runtime_digest
from ai_runtime import MARKER,inspect_runtime
from storage_lease import plain_path

UNAVAILABLE='タグ分類モデルまたは専用ランタイムが未導入です。検索・手動タグは引き続き利用できます。'


class DisabledTagger:
    def status(self):return {'available':False,'reason':UNAVAILABLE}
    def close(self):pass


class WDTagger:
    def __init__(self,repo,profile,ai=None,*,ai_python=None,models_root=None,preferences_path=None):
        self.repo=Path(repo)
        self.python=worker_python(self.repo,ai_python)
        self.models_root=models_root
        self.preferences_path=Path(preferences_path) if preferences_path is not None else None
        self.profile=profile
        self.ai=ai
        self._lock=threading.Lock()
        self._closed=threading.Event()
        self._runtime_cache=None
        p=profile.data()
        self.info=TaggerInfo(p['adapter'],'1/'+profile.key,p['model_id'],p['revision'],
                            'exif-first-frame-white-square-bicubic-bgr-nhwc-255-v1')

    def _effective_models_root(self):
        try:
            self.profile.verify(self.repo,models_root=self.models_root)
            return self.models_root
        except (ValueError,OSError):
            pass
        if self.preferences_path is not None:
            try:
                selected=read_preferences(self.preferences_path)
                candidate=model_root(selected,'tagger',self.models_root,target=ModelTarget.for_profile('tagger',self.profile))
                if candidate is not None:
                    self.profile.verify(self.repo,models_root=candidate)
                    return Path(candidate)
            except (ValueError,OSError,KeyError):
                pass
            try:
                downloads=plain_path(self.preferences_path.parent/'ai-downloads',directory=True)
                for entry in sorted(downloads.iterdir(),reverse=True):
                    if not entry.name.startswith('wd-') or entry.is_symlink() or not entry.is_dir():continue
                    try:
                        self.profile.verify(self.repo,models_root=entry)
                        return entry
                    except (ValueError,OSError):
                        continue
            except (ValueError,OSError):
                pass
        return self.models_root

    def status(self):
        try:
            effective_root=self._effective_models_root()
            directory=self.profile.verify(self.repo,models_root=effective_root)
            marker=directory/'aredoko-runtime.json'
            root=runtime_root(self.python)
            runtime_marker=root/MARKER
            if runtime_marker.exists() or runtime_marker.is_symlink():
                # Downloaded model packs do not contain machine-runtime claims.
                # The selected sealed runtime declares its own installed version;
                # worker_command still verifies the full pack before execution.
                expected=bound_runtime_digest(self.python)
                if expected is not None:
                    st=plain_path(runtime_marker).stat()
                    cache_key=(str(root),expected,st.st_mtime_ns,st.st_size)
                    if self._runtime_cache is not None and self._runtime_cache[0]==cache_key:
                        info=self._runtime_cache[1]
                    else:
                        info=inspect_runtime(root,expected=expected)
                        self._runtime_cache=(cache_key,info)
                else:
                    info=inspect_runtime(root)
                if 'onnxruntime' in info['abi']['modules']:
                    metadata=plain_path(root/f'Lib/site-packages/onnxruntime-{RUNTIME_VERSION}.dist-info/METADATA')
                    if metadata.stat().st_size>1024**2:raise ValueError('Runtime metadata exceeds limit')
                    with metadata.open('rb') as stream:raw=stream.read(1024**2+1)
                    if len(raw)>1024**2:raise ValueError('Runtime metadata exceeds limit')
                    declared=email.parser.BytesParser().parsebytes(raw,headersonly=True)
                    runtime_ready=(declared.get_all('Name')==['onnxruntime']
                                   and declared.get_all('Version')==[RUNTIME_VERSION])
                else:
                    runtime_ready=('PIL' in info['abi']['modules'] and bundled_ort_dll(self.repo) is not None)
            elif marker.exists() or marker.is_symlink():
                runtime_ready=(not marker.is_symlink() and json.loads(marker.read_text(encoding='utf-8'))=={'onnxruntime':RUNTIME_VERSION})
            else:
                prefix=self.python.parent.parent if self.python.parent.name.casefold()=='scripts' else self.python.parent
                has_pil=(root/'Lib/site-packages/PIL/__init__.py').is_file() or (prefix/'Lib/site-packages/PIL/__init__.py').is_file()
                runtime_ready=(has_pil and bundled_ort_dll(self.repo) is not None)
            ready=not self._closed.is_set() and self.python.is_file() and runtime_ready
        except (ValueError,OSError):ready=False
        return {'available':ready,'reason':'' if ready else UNAVAILABLE,
                'profile':self.profile.data()['id'],'device':'cpu'}

    def _scores(self,data,cancelled):
        if type(data) is not bytes or not 1<=len(data)<=8*1024**2:
            raise AIUnavailable('タグ分類の画像サイズが上限を超えています。')
        env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
             'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':str(self.profile.data()['cpu_threads'])}
        try:command=worker_command(self.python,Path(__file__).with_name('tagger_worker.py'),['--profile-json',self.profile.document,'--parent-pid',str(os.getpid())],cancelled=lambda:cancelled() or self._closed.is_set())
        except (ValueError,OSError,RuntimeError) as error:
            if cancelled() or self._closed.is_set():raise SuggestionConflict('タグ候補の生成を取り消しました。候補は保存していません。') from error
            raise AIUnavailable('AI runtime validation failed') from error
        effective_root=self._effective_models_root()
        if effective_root is not None:command+=['--models-root',str(Path(effective_root).absolute())]
        process=subprocess.Popen(command,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        responses=queue.Queue(maxsize=1)
        def read():
            try:
                line=process.stdout.readline(2_000_001)
                if not line or len(line)>2_000_000:raise ValueError('Invalid response size')
                responses.put(json.loads(line))
            except (OSError,ValueError):responses.put({'error':'Invalid response'})
        def write():
            try:
                process.stdin.write(json.dumps({'image':base64.b64encode(data).decode('ascii')}).encode()+b'\n')
                process.stdin.flush()
                process.stdin.close()
            except (OSError,ValueError):pass
        reader=threading.Thread(target=read,daemon=True)
        writer=threading.Thread(target=write,daemon=True)
        reader.start();writer.start()
        deadline=time.monotonic()+self.profile.data()['timeout_seconds']
        try:
            while True:
                if cancelled() or self._closed.is_set():
                    raise SuggestionConflict('タグ候補の生成を取り消しました。候補は保存していません。')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise AIUnavailable('タグ分類が制限時間を超えました。候補は保存していません。')
                try:result=responses.get(timeout=min(.05,remaining))
                except queue.Empty:continue
                if type(result) is dict and 'error' in result:raise worker_failure(result)
                if type(result) is not dict or set(result)!={'key','scores'} or result['key']!=self.profile.key:
                    raise AIUnavailable('タグ分類の応答を確認できません。候補は保存していません。')
                scores=result['scores']
                if (type(scores) is not list or len(scores)!=self.profile.data()['label_count']
                        or any(type(s) not in (int,float) or not math.isfinite(s) or not 0<=s<=1 for s in scores)):
                    raise AIUnavailable('タグ分類の応答を確認できません。候補は保存していません。')
                return scores
        finally:
            # Popen owns this exact process instance; never kill by name/PID scan.
            if process.poll() is None:process.kill()
            process.wait(timeout=10)
            writer.join(timeout=2);reader.join(timeout=2)
            if not process.stdin.closed:process.stdin.close()
            process.stdout.close()

    def suggest(self,source,cancelled):
        if not self._lock.acquire(blocking=False):raise AIBusy('タグ候補を生成中です。完了後にやり直してください。')
        shared=getattr(self.ai,'inference',None)
        acquired=False
        try:
            if not self.status()['available']:raise AIUnavailable(UNAVAILABLE)
            if shared is not None:
                acquired=shared.acquire(blocking=False)
                if not acquired:raise AIBusy('AI検索または索引を処理中です。完了後にタグ候補を生成してください。')
                with self.ai.guard:
                    if self.ai._closed:raise AIUnavailable(UNAVAILABLE)
                    if self.ai.worker and self.ai.worker.is_alive():
                        raise AIBusy('AI索引を作成中です。完了後にタグ候補を生成してください。')
            if cancelled() or self._closed.is_set():
                raise SuggestionConflict('タグ候補の生成を取り消しました。候補は保存していません。')
            scores=self._scores(source['data'],cancelled)
            config=self.profile.data()
            rows=labels(self.profile.directory(self.repo,models_root=self._effective_models_root())/'selected_tags.csv',config['label_count'])
            candidates=[]
            for index,((name,category),score) in enumerate(zip(rows,scores)):
                threshold=config['general_threshold'] if category==0 else config['character_threshold']
                # Rating rows are not searchable content tags. General/character
                # rows include all publisher labels; there is no NSFW word filter.
                if category not in (0,4) or score<=threshold or len(name)>60 or any(ord(c)<32 for c in name):continue
                candidates.append((index,name,category,score))
            candidates.sort(key=lambda row:(-row[3],row[0]))
            return [TagProposal(name,f'画像分類の推定候補・{"キャラクター" if category==4 else "一般タグ"}。'
                f'分類出力 {score:.4f}（正解確率ではありません）。画像/表紙のみ、本文・人物関係は未確認。')
                for _,name,category,score in candidates[:config['max_candidates']]]
        finally:
            if acquired:
                self.ai._last_activity=time.monotonic()
                shared.release()
            self._lock.release()

    def close(self):
        self._closed.set()
        with self._lock:pass


def create_tagger(ai=None,profile_path=None,repo=None,*,ai_python=None,models_root=None,profile_definition=None,preferences_path=None):
    repo=Path(repo) if repo else Path(__file__).resolve().parents[1]
    try:
        definition=load_profile(repo,profile_path) if profile_definition is None else profile_definition
        if not isinstance(definition,WDProfile):raise ValueError('Invalid tagger definition')
        return WDTagger(repo,definition,ai,ai_python=ai_python,models_root=models_root,preferences_path=preferences_path)
    except (ValueError,OSError):return DisabledTagger()
