"""Lazy production-facing audio feature. Status does not create a DB/worker."""
import logging
import threading

from ai_process import AIUnavailable,EncoderProcess
from ai_profiles import audio_profile_for
from ai_search import AIBusy
from audio_direct_jobs import AudioDirectJobs
from audio_direct_similarity import validate_similarity_request
from audio_input import MediaDecodeCancelled
from result_sessions import IndexStamp


class AudioDirectFeature:
    def __init__(self,catalog,image_ai,*,encoder_factory=None,stage_parent=None):
        self.catalog,self.image_ai=catalog,image_ai
        self.stage_parent=stage_parent;self.owner=None;self.monitor=None;self.closed=False;self.cleanup_done=False;self.initialization_failed=False
        self.init_lock=threading.Lock();self.close_event=threading.Event();self.idle_seconds=getattr(image_ai,'_idle_seconds',0);self.encoder=None;self.inference=None
        group=getattr(image_ai,'inference_group',None)
        if (group is not None and image_ai.profile.adapter=='embeddinggemma2'
                and (encoder_factory is not None or isinstance(image_ai.encoder,EncoderProcess))):
            profile=audio_profile_for(image_ai.profile)
            self.encoder=(encoder_factory(profile) if encoder_factory is not None else
                          EncoderProcess(image_ai.encoder.python,image_ai.encoder.model,profile,
                              gpu_budget_mib=image_ai.encoder.gpu_budget_mib,
                              budget_if_cuda=getattr(image_ai.encoder,'budget_if_cuda',False)))
            try:self.inference=group.for_encoder(self.encoder)
            except BaseException:
                self.encoder.close()
                raise

    def status(self):
        available=self.encoder is not None and bool(getattr(self.encoder,'available',True)) and not self.closed
        if self.owner is not None:return {'supported':True,'available':available,'initialized':True,**self.owner.status()}
        return {'supported':self.encoder is not None,'available':available,'state':'failed' if self.initialization_failed else 'idle','resident':False,
                'initialized':False,'candidate_total':0,'target':0,'processed':0,'indexed':0,
                'reused':0,'unavailable':0,'remaining_candidates':0,'job_id':None,'error_code':'audio_initialization_failed' if self.initialization_failed else None,'item_progress':None,'source_kind':'audio'}

    def _ensure(self,*,require_model=True):
        if self.initialization_failed:raise AIUnavailable('音声検索の初期化に失敗しました。アプリを再起動してから、もう一度実行してください。')
        if self.closed or self.encoder is None:raise AIUnavailable('音声の内容検索に対応するAI環境がありません。')
        if require_model and not bool(getattr(self.encoder,'available',True)):raise AIUnavailable('音声検索のモデルが未準備です。')
        with self.init_lock:
            if self.closed:raise AIUnavailable('Audio feature is closing')
            if self.owner is None:
                if self.catalog.writer_fence.paused:raise AIBusy('バックアップ中です。完了後に音声検索を実行してください。')
                try:
                    owner=AudioDirectJobs(self.catalog,self.encoder,inference=self.inference,stage_parent=self.stage_parent,init_cancel=self.close_event)
                except (MediaDecodeCancelled,InterruptedError):
                    if self.closed:raise AIUnavailable('Audio feature is closing') from None
                    raise
                monitor=None
                try:
                    if self.closed:raise AIUnavailable('Audio feature is closing')
                    owner.configure(idle_release_seconds=self.idle_seconds)
                    monitor=IndexStamp(owner.index)
                    if self.closed:raise AIUnavailable('Audio feature is closing')
                except BaseException as error:
                    # Closing an encoder is permanent. Do not retry a partially
                    # initialized owner with that already-closed encoder.
                    self.initialization_failed=not self.closed
                    self.closed=True;self.close_event.set()
                    try:
                        if monitor is not None:monitor.close()
                        self._cleanup_locked(owner)
                    except Exception:
                        logging.getLogger(__name__).exception('Failed cleaning audio owner initialization')
                    if isinstance(error,Exception) and not isinstance(error,AIUnavailable):
                        raise AIUnavailable('音声検索の初期化に失敗しました。アプリを再起動してから、もう一度実行してください。') from error
                    raise
                self.owner=owner;self.monitor=monitor
            return self.owner

    def start(self,body):
        return self._start(body,'audio')

    def start_video_audio(self,body):return self._start(body,'video')

    def _start(self,body,source_kind):
        if type(body) is not dict or body.get('consent') is not True or set(body)-{'consent','conditions','limit'}:
            raise ValueError('Explicit audio indexing consent required')
        conditions=body.get('conditions')
        if conditions is not None:
            if type(conditions) is not dict or set(conditions)-{'view','root_id','root_ids','shelf','shelf_ids'}:
                raise ValueError('Invalid audio indexing scope')
            self.catalog.search(kind=source_kind,limit=1,**conditions)
        limit=body.get('limit',128)
        if type(limit) is not int or not 1<=limit<=1000:raise ValueError('Invalid audio indexing limit')
        self._ensure().start(body.get('conditions'),limit=body.get('limit',128),source_kind=source_kind)
        return self.status()

    def search(self,query,**options):
        return self._search(query,'audio',options)

    def search_video_audio(self,query,**options):return self._search(query,'video',options)

    def _search(self,query,source_kind,options):
        if not isinstance(query,str) or not 1<=len(query.strip())<=4096:raise ValueError('Invalid audio query')
        allowed={'view','root_id','root_ids','shelf','shelf_ids'}
        if set(options)-allowed-{'page','limit','cancelled','result_sink'}:raise ValueError('Invalid audio search options')
        self.catalog.search(kind=source_kind,limit=1,**{name:value for name,value in options.items() if name in allowed})
        return self._ensure().search(query,source_kind=source_kind,**options)
    def cancel(self):
        # Keep the original audio-file endpoint scoped to audio files, including
        # a stale panel click after another source has acquired the shared owner.
        result=self.owner.cancel(source_kind='audio') if self.owner is not None else {'cancel_requested':False}
        return {**self.status(),'cancel_requested':result['cancel_requested']}
    def cancel_video_audio(self):
        result=self.owner.cancel(source_kind='video') if self.owner is not None else {'cancel_requested':False}
        return {**self.status(),'cancel_requested':result['cancel_requested']}
    def similar(self,item_id,**options):return self._similar(item_id,'audio',options)
    def similar_video_audio(self,item_id,**options):return self._similar(item_id,'video',options)
    def _similar(self,item_id,source_kind,options):
        scope=validate_similarity_request(item_id,**options)
        self.catalog.search(kind=source_kind,limit=1,**scope)
        return self._ensure(require_model=False).similar(item_id,source_kind=source_kind,**options)
    def release(self):return self.owner.release() if self.owner is not None else {'released':False,'resident':False}
    def stamp(self):
        self._ensure(require_model=False)
        return self.monitor()

    def configure(self,*,idle_release_seconds=0):
        if type(idle_release_seconds) is not int or not 0<=idle_release_seconds<=3600:raise ValueError('Invalid audio idle release')
        self.idle_seconds=idle_release_seconds
        if self.owner is not None:self.owner.configure(idle_release_seconds=idle_release_seconds)

    def _cleanup_locked(self,owner=None):
        # init_lock serializes cleanup callers, while closed/close_event above
        # can interrupt initialization before this lock becomes available.
        if self.cleanup_done:return
        self.cleanup_done=True
        try:
            target=owner if owner is not None else self.owner
            if target is not None:target.close()
            elif self.encoder is not None:self.encoder.close()
        finally:
            if self.monitor is not None:self.monitor.close()

    def close(self):
        self.closed=True;self.close_event.set()
        with self.init_lock:self._cleanup_locked()
