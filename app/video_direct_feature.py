"""Lazy production-facing video feature. Status does not create a DB/worker."""
import threading

from ai_process import AIUnavailable,EncoderProcess
from ai_profiles import video_profile_for
from ai_search import AIBusy
from video_direct_jobs import VideoDirectJobs
from video_previews import MediaDecodeCancelled
from result_sessions import IndexStamp


class VideoDirectFeature:
    def __init__(self,catalog,image_ai,*,encoder_factory=None,stage_parent=None):
        self.catalog,self.image_ai=catalog,image_ai
        self.stage_parent=stage_parent;self.owner=None;self.monitor=None;self.closed=False
        self.init_lock=threading.Lock();self.close_event=threading.Event();self.idle_seconds=getattr(image_ai,'_idle_seconds',0);self.encoder=None;self.inference=None
        group=getattr(image_ai,'inference_group',None)
        if (group is not None and image_ai.profile.adapter=='embeddinggemma2'
                and (encoder_factory is not None or isinstance(image_ai.encoder,EncoderProcess))):
            profile=video_profile_for(image_ai.profile)
            self.encoder=(encoder_factory(profile) if encoder_factory is not None else
                          EncoderProcess(image_ai.encoder.python,image_ai.encoder.model,profile,
                              gpu_budget_mib=image_ai.encoder.gpu_budget_mib))
            try:self.inference=group.for_encoder(self.encoder,role='video')
            except BaseException:
                self.encoder.close()
                raise

    def status(self):
        available=self.encoder is not None and bool(getattr(self.encoder,'available',True)) and not self.closed
        if self.owner is not None:return {'supported':True,'available':available,'initialized':True,**self.owner.status()}
        return {'supported':self.encoder is not None,'available':available,'state':'idle','resident':False,
                'initialized':False,'candidate_total':0,'target':0,'processed':0,'indexed':0,
                'reused':0,'unavailable':0,'remaining_candidates':0,'job_id':None,'error_code':None}

    def _ensure(self,*,require_model=True):
        if self.closed or self.encoder is None:raise AIUnavailable('動画の内容検索に対応するAI環境がありません。')
        if require_model and not bool(getattr(self.encoder,'available',True)):raise AIUnavailable('動画検索のモデルが未準備です。')
        with self.init_lock:
            if self.closed:raise AIUnavailable('Video feature is closing')
            if self.owner is None:
                if self.catalog.writer_fence.paused:raise AIBusy('バックアップ中です。完了後に動画検索を実行してください。')
                try:
                    owner=VideoDirectJobs(self.catalog,self.encoder,inference=self.inference,stage_parent=self.stage_parent,init_cancel=self.close_event)
                except (MediaDecodeCancelled,InterruptedError):
                    if self.closed:raise AIUnavailable('Video feature is closing') from None
                    raise
                if self.closed:owner.close();raise AIUnavailable('Video feature is closing')
                try:
                    owner.configure(idle_release_seconds=self.idle_seconds)
                    monitor=IndexStamp(owner.index)
                except BaseException:
                    owner.close()
                    raise
                self.owner=owner;self.monitor=monitor
            return self.owner

    def start(self,body):
        if type(body) is not dict or body.get('consent') is not True or set(body)-{'consent','conditions','limit'}:
            raise ValueError('Explicit video indexing consent required')
        conditions=body.get('conditions')
        if conditions is not None:
            if type(conditions) is not dict or set(conditions)-{'view','root_id','root_ids','shelf','shelf_ids'}:
                raise ValueError('Invalid video indexing scope')
            self.catalog.search(kind='video',limit=1,**conditions)
        limit=body.get('limit',128)
        if type(limit) is not int or not 1<=limit<=1000:raise ValueError('Invalid video indexing limit')
        self._ensure().start(body.get('conditions'),limit=body.get('limit',128))
        return self.status()

    def search(self,query,**options):
        if not isinstance(query,str) or not 1<=len(query.strip())<=4096:raise ValueError('Invalid video query')
        allowed={'view','root_id','root_ids','shelf','shelf_ids'}
        if set(options)-allowed-{'page','limit','cancelled','result_sink'}:raise ValueError('Invalid video search options')
        self.catalog.search(kind='video',limit=1,**{name:value for name,value in options.items() if name in allowed})
        return self._ensure().search(query,**options)
    def cancel(self):
        result=self.owner.cancel() if self.owner is not None else {'cancel_requested':False}
        return {**self.status(),'cancel_requested':result['cancel_requested']}
    def similar(self,item_id,**options):return self._ensure(require_model=False).similar(item_id,**options)
    def release(self):return self.owner.release() if self.owner is not None else {'released':False,'resident':False}
    def stamp(self):
        self._ensure(require_model=False)
        return self.monitor()

    def configure(self,*,idle_release_seconds=0):
        if type(idle_release_seconds) is not int or not 0<=idle_release_seconds<=3600:raise ValueError('Invalid video idle release')
        self.idle_seconds=idle_release_seconds
        if self.owner is not None:self.owner.configure(idle_release_seconds=idle_release_seconds)

    def close(self):
        self.closed=True;self.close_event.set()
        with self.init_lock:
            if self.owner is not None:self.owner.close()
            elif self.encoder is not None:self.encoder.close()
            if self.monitor is not None:self.monitor.close()
