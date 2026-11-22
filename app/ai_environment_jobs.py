"""Opt-in official dependency/model acquisition, construction and activation."""
from contextlib import nullcontext
from copy import deepcopy
import ctypes,io,json,logging,os,secrets,shutil,threading
from pathlib import Path

from ai_acquisition import Catalog,acquire
from ai_profiles import DEFAULT_PROFILE
from ai_runtime import inspect_runtime
from ai_runtime_preferences import read_preferences,model_root
from ai_wheel_runtime import build_environment
from managed_ai_runtime import RECIPES,RECIPE_SHA256,recipe,recipe_spec,seal,verify_base
from model_locations import ModelTarget
from runtime_cache import cache_lease
from runtime_paths import bind_runtime
from storage_lease import plain_path,storage_parent

TARGET_LABELS={
    'cuda':'CUDA 版（NVIDIA GPU 向け・高速）',
    'cpu':'軽量 CPU 版（CPU / Radeon 等・省容量）',
}

ACTIVE={'waiting','checking_runtime','checking_base','downloading_runtime','building','checking_model','downloading_model','probing','saving','cancelling'}
FAILURE_MESSAGES={
    'checking_base':'基本Pythonの検証に失敗しました。Aredokoを再起動し、基本環境の準備状態を確認してください。',
    'downloading_runtime':'AIパッケージを取得できませんでした。通信と空き容量を確認して再試行してください。途中までの取得は保持しています。',
    'building':'AI環境を構築できませんでした。空き容量と取得ファイルの整合性を確認してください。',
    'checking_model':'モデルを確認できませんでした。モデルの保存先と整合性を確認してください。',
    'downloading_model':'モデルを取得できませんでした。通信と空き容量を確認して再試行してください。途中までの取得は保持しています。',
    'probing':'モデルの動作確認に失敗しました。他のAI処理が終わってから再試行するか、診断情報を確認してください。',
    'checking_runtime':'実行環境の整合性を確認できませんでした。診断情報を確認してください。',
    'saving':'動作確認後の設定を保存できませんでした。他の設定処理が完了してから再試行してください。'}
class EnvironmentBusy(RuntimeError):pass


def detect_nvidia_gpu():
    override=os.environ.get('AREDOKO_AI_SETUP_TARGET','').strip().lower()
    if override in ('cuda','cpu'):
        return {'target':override,'nvidia_detected':override=='cuda','gpu_name':None,'source':'env_override'}
    if os.environ.get('AREDOKO_AI_DEVICE','').strip().lower()=='cpu' or os.environ.get('CUDA_VISIBLE_DEVICES','').strip()=='-1':
        return {'target':'cpu','nvidia_detected':False,'gpu_name':None,'source':'env_cpu'}
    if os.name!='nt':
        return {'target':'cpu','nvidia_detected':False,'gpu_name':None,'source':'non_windows'}
    try:
        lib=ctypes.WinDLL('nvcuda.dll',winmode=0x00000800)
        lib.cuInit.argtypes=[ctypes.c_uint];lib.cuInit.restype=ctypes.c_int
        lib.cuDeviceGetCount.argtypes=[ctypes.POINTER(ctypes.c_int)];lib.cuDeviceGetCount.restype=ctypes.c_int
        lib.cuDeviceGetName.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int];lib.cuDeviceGetName.restype=ctypes.c_int
        if lib.cuInit(0)!=0:
            return {'target':'cpu','nvidia_detected':False,'gpu_name':None,'source':'cuda_init_failed'}
        count=ctypes.c_int(0)
        if lib.cuDeviceGetCount(ctypes.byref(count))!=0 or count.value<=0:
            return {'target':'cpu','nvidia_detected':False,'gpu_name':None,'source':'no_cuda_device'}
        gpu_name=None
        buf=ctypes.create_string_buffer(256)
        if lib.cuDeviceGetName(buf,len(buf),0)==0:
            decoded=buf.value.decode('utf-8','replace').strip()
            gpu_name=decoded or None
        return {'target':'cuda','nvidia_detected':True,'gpu_name':gpu_name,'source':'nvcuda'}
    except (OSError,AttributeError):
        return {'target':'cpu','nvidia_detected':False,'gpu_name':None,'source':'no_nvcuda'}


def wheel_catalog(target='cuda'):
    spec=recipe_spec(target)
    lock=recipe(target)
    path=Path(__file__).resolve().parents[1]/spec['sizes']
    sizes=json.loads(plain_path(path).read_text(encoding='utf8'))
    if sizes.get('format')!='aredoko-wheel-sizes-v1' or sizes.get('recipe_sha256')!=spec['sha256']:
        raise ValueError('Wheel size definition changed')
    if set(sizes['sizes'])!={entry['filename'] for entry in lock['entries']}:raise ValueError('Incomplete wheel size definition')
    document={'format':'aredoko-acquisition-v1','id':spec['id'],'revision':spec['sha256'],'kind':'runtime',
              'license':'Individual upstream licenses included in each wheel','license_url':'https://github.com/pytorch/pytorch/blob/v2.9.1/LICENSE',
              'allowed_hosts':['files.pythonhosted.org','download.pytorch.org','download-r2.pytorch.org'],
              'entries':[{'path':entry['filename'],'bytes':sizes['sizes'][entry['filename']],'url':entry['url'],'sha256':entry['sha256'],'role':'runtime'} for entry in lock['entries']]}
    return Catalog.parse(json.dumps(document).encode())


def probe_model(python,model,profile,*,cancelled=lambda:False,reserve=nullcontext):
    from PIL import Image
    from ai_process import EncoderProcess
    if cancelled():raise InterruptedError('Setup cancelled')
    with reserve():
        encoder=EncoderProcess(python,model,profile,gpu_budget_mib=4096,budget_if_cuda=True)
        try:
            buffer=io.BytesIO();Image.new('RGB',(32,32),'blue').save(buffer,format='PNG')
            query=encoder.encode('query','青い正方形')
            if cancelled():raise InterruptedError('Setup cancelled')
            image=encoder.encode('image',buffer.getvalue())
            if query is None or image is None:raise ValueError('Generated inference probe was skipped')
            if cancelled():raise InterruptedError('Setup cancelled')
            return {'pass':True,'profile':profile.key,'device':encoder.device,'dimension':profile.dimension,
                    'peak_memory_mib':encoder.telemetry.get('peak_memory_mib',0)}
        finally:encoder.close()


class AIEnvironmentJobs:
    def __init__(self,preferences,*,profile,specifications=(),reserve=nullcontext,busy=lambda:False):
        self.preferences=preferences;self.data=preferences.path.parent;self.profile=profile;self.reserve=reserve;self.busy=busy
        self.spec=next(((catalog,validator) for catalog,validator in specifications if catalog.kind=='model' and catalog.key=='embeddinggemma-2'),None)
        self.detected_hardware=detect_nvidia_gpu()
        self.default_target=self.detected_hardware['target']
        if profile is not None and profile.to_dict()==DEFAULT_PROFILE.to_dict() and self.spec is not None:
            self.catalogs={'cuda':wheel_catalog('cuda'),'cpu':wheel_catalog('cpu')}
            self.catalog=self.catalogs[self.default_target]
        else:
            self.catalogs={}
            self.catalog=None
        self.lock=threading.RLock();self.cancelled=threading.Event();self.thread=None;self.closed=False;self.committed=False
        self.value={'state':'idle','stage':'idle','target':self.default_target,'saved':False,'bytes_per_second':None,'bytes_done':0,'bytes_total':None,'files_done':0,'files_total':None,'message':'','error_code':None,'result':None}

    def describe(self):
        hardware=detect_nvidia_gpu()
        default_target=hardware['target']
        model_bytes=sum(entry.size for entry in self.spec[0].entries) if self.spec else 0
        targets={}
        for key in ('cuda','cpu'):
            cat=self.catalogs.get(key)
            if cat is None:continue
            runtime_bytes=sum(entry.size for entry in cat.entries)
            targets[key]={
                'label':TARGET_LABELS[key],
                'download_bytes':runtime_bytes+model_bytes,
                'runtime_bytes':runtime_bytes,
                'model_bytes':model_bytes,
                'recommended_free_bytes':RECIPES[key]['recommended_free_bytes'],
            }
        selected_info=targets.get(default_target)
        active_catalog=self.catalogs.get(default_target)
        return {'supported':bool(targets),'model':'EmbeddingGemma 2',
                'target':default_target,'detected_target':default_target,
                'detected_gpu':hardware.get('gpu_name'),
                'nvidia_detected':bool(hardware.get('nvidia_detected')),
                'targets':targets,
                'download_bytes':selected_info['download_bytes'] if selected_info else None,
                'recommended_free_bytes':selected_info['recommended_free_bytes'] if selected_info else 15_000_000_000,
                'gpu_budget_mib':4096,
                'sources':['Python Software Foundation','PyTorch','PyPI','Google / Hugging Face'],
                'licenses':[{'name':active_catalog.license,'url':active_catalog.license_url},{'name':self.spec[0].license,'url':self.spec[0].license_url}] if active_catalog and self.spec else [],
                'message':'お使いの環境に合わせて公式の固定版を取得し、整合性と生成素材の実推論を確認してから設定を保存します。既存の環境・モデルは保持します。',
                'job':self.snapshot()}

    def snapshot(self):
        with self.lock:return deepcopy(self.value)

    def start(self,body):
        if not isinstance(body,dict) or 'consent' not in body or set(body)-{'consent','bytes_per_second','target'} or body['consent']is not True:raise ValueError('Explicit AI setup consent required')
        rate=body.get('bytes_per_second')
        if rate is not None and (type(rate)is not int or not 1<=rate<=2**40):raise ValueError('Invalid optional bandwidth limit')
        explicit_target='target' in body
        if explicit_target:
            target=body['target']
            if not isinstance(target,str) or target not in RECIPES:raise ValueError('Invalid AI runtime target')
        else:
            target=detect_nvidia_gpu()['target']
        with self.lock:
            if not self.catalogs:raise ValueError('Automatic setup supports the built-in EmbeddingGemma 2 profile')
            if self.closed or self.thread is not None and self.thread.is_alive() or self.busy():raise EnvironmentBusy('Another setup operation is active')
            self.cancelled=threading.Event();self.committed=False
            self.value.update(state='waiting',stage='waiting',target=target,saved=False,bytes_per_second=rate,bytes_done=0,bytes_total=None,files_done=0,files_total=None,message='AI環境の準備を開始しています。',error_code=None,result=None)
            self.thread=threading.Thread(target=self._run,args=(rate,target,explicit_target),daemon=True,name='aredoko-ai-environment')
            try:self.thread.start()
            except Exception as error:
                self.thread=None;self.value.update(state='failed',error_code='worker_start_failed',message='準備を開始できませんでした。')
                raise EnvironmentBusy('Setup worker did not start') from error
            return self.snapshot()

    def _check(self):
        if self.closed or self.cancelled.is_set():raise InterruptedError('AI setup cancelled')

    def _phase(self,state,message):
        self._check()
        with self.lock:
            self.value.update(state=state,stage=state,message=message,bytes_done=0,bytes_total=None,files_done=0,files_total=None)

    def _progress(self,value):
        with self.lock:
            if not self.cancelled.is_set():
                self.value.update({key:value[key] for key in ('bytes_done','bytes_total','files_done','files_total') if key in value})
                if 'bytes_received' in value:self.value['bytes_done']=value['bytes_received']
                self.value['stage']=value.get('stage',self.value['state'])

    def _publish(self,operation):
        with self.lock:
            self._check();self.value.update(state='saving',message='動作確認済みの設定を保存しています。')
            operation();self.committed=True;self.value['saved']=True

    def _run(self,rate,target='cuda',explicit_target=False):
        try:
            spec=recipe_spec(target)
            runtime_catalog=self.catalogs[target]
            with cache_lease(self.data):
                self._check();settings=read_preferences(self.preferences.path) if self.preferences.path.exists() else {}
                info=None;environment=None
                if settings.get('ai_runtime_root') and settings.get('ai_runtime_manifest_sha256'):
                    self._phase('checking_runtime','選択済みの実行環境を確認しています。')
                    # A failed existing environment remains untouched. A new
                    # version is built instead; it never learns changed bytes.
                    try:info=inspect_runtime(settings['ai_runtime_root'],expected=settings['ai_runtime_manifest_sha256'],verify=True,cancelled=self.cancelled.is_set,progress=self._progress)
                    except (ValueError,OSError):self._check()
                if info is not None and explicit_target and info.get('abi',{}).get('compute')!=spec['compute']:
                    info=None
                if info is not None:
                    environment=Path(info['root']);python=Path(info['python'])
                    bind_runtime(environment,info['manifest_sha256'])
                else:
                    self._phase('checking_base','アプリ専用の基本Pythonを確認しています。')
                    home=self.data/'runtimes/cpython-3.13.17/tools';package=self.data/'runtime-artifacts/python.3.13.17.nupkg'
                    verify_base(home,package,full=True,cancelled=self.cancelled.is_set)
                    if shutil.disk_usage(self.data).free<spec['min_free_bytes']:raise OSError('Insufficient free setup space')
                    lock=recipe(target);cache=self.data/'runtime-cache'/spec['cache_dir'];storage_parent(cache/'marker')
                    complete=all((cache/entry['filename']).is_file() for entry in lock['entries'])
                    if not complete:
                        self._phase('downloading_runtime','公式のAI実行パッケージを取得しています。')
                        downloaded=acquire(runtime_catalog,self.data/'runtime-cache/incoming',validate=lambda root,cancelled:None,
                                           publish=lambda operation:(self._check(),operation()),cancelled=self.cancelled.is_set,progress=self._progress,bytes_per_second=rate)
                        source=Path(downloaded['root'])
                        # The complete immutable collection moves as a whole.
                        # A previous interrupted flat cache is retained separately.
                        if any(cache.iterdir()):cache.rename(cache.with_name('retained-'+secrets.token_hex(8)))
                        else:cache.rmdir()
                        source.rename(cache)
                    self._phase('building','AI専用仮想環境を構築・検証しています。')
                    environment=self.data/'runtimes'/(spec['dir_prefix']+secrets.token_hex(12))
                    build_environment(home/'python.exe',cache,environment,lock,cancelled=self.cancelled.is_set,progress=self._progress)
                    python=environment/'Scripts/python.exe'
                catalog,validator=self.spec
                self._phase('checking_model','対応するモデルの整合性を確認しています。')
                target_model=ModelTarget.for_profile('embedding',self.profile)
                selected=model_root(settings,'embedding',self.data/'models',target=target_model)
                selected=Path(selected);model_collection=None
                if selected.exists():
                    try:validator(selected,self.cancelled.is_set);model_collection=selected
                    except (ValueError,OSError):self._check()
                if model_collection is None:
                    self._phase('downloading_model','公式の検索モデルを取得・検証しています。')
                    downloaded=acquire(catalog,self.data/'ai-downloads',validate=validator,
                        publish=lambda operation:(self._check(),operation()),cancelled=self.cancelled.is_set,progress=self._progress,bytes_per_second=rate)
                    model_collection=Path(downloaded['root'])
                self._phase('probing','生成素材でモデルの読み込みと推論を確認しています。')
                proof=probe_model(python,self.profile.model_path(Path(__file__).resolve().parents[1],models_root=model_collection),self.profile,
                                  cancelled=self.cancelled.is_set,reserve=self.reserve)
                if info is None:
                    self._phase('checking_runtime','動作確認済み環境の検証記録を保存しています。')
                    info=seal(environment,cache,home,package,proof,target=target,cancelled=self.cancelled.is_set,progress=self._progress)
                self._phase('saving','設定を保存しています。')
                result=self.preferences.select(runtime_root=str(environment),models_root=str(model_collection),model_target=target_model.to_dict(),consent=True,
                    cancelled=self.cancelled.is_set,progress=self._progress,publish=self._publish)
                with self.lock:self.value.update(state='complete',stage='complete',result={'selection':result,'probe':proof,'target':target},message='実推論の確認と設定保存が完了しました。Aredokoを再起動して反映してください。')
        except Exception as error:
            with self.lock:
                if self.committed:self.value.update(state='complete',error_code='post_save_failed',message='設定は保存済みです。状態を再確認してください。')
                else:
                    cancelled=self.cancelled.is_set() or self.closed;phase=self.value['state']
                    self.value.update(state='cancelled' if cancelled else 'failed',error_code=getattr(error,'code',type(error).__name__),
                        message='準備を中止しました。既存設定は保持しています。' if cancelled else FAILURE_MESSAGES.get(phase,'AI環境を準備できませんでした。診断情報を確認してください。')+' 既存設定は保持しています。')
            if not self.cancelled.is_set() and not self.closed:logging.exception('AI environment setup failed')

    def cancel(self):
        with self.lock:
            accepted=self.value['state'] in ACTIVE and not self.committed
            if accepted:self.cancelled.set();self.value.update(state='cancelling',message='安全な区切りまで待って中止しています。モデル動作確認は応答まで時間がかかる場合があります。')
            return {**self.snapshot(),'cancel_accepted':accepted}

    def close(self,timeout=10):
        with self.lock:self.closed=True;self.cancelled.set();thread=self.thread
        if thread is not None:thread.join(timeout)
        return thread is None or not thread.is_alive()
