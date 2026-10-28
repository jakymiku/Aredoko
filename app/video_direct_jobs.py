"""Explicit owned direct-video jobs and query lifecycle, independent of WinUI.

No automatic activation or model selection. Supply a video encoder and (when
coexisting with image AI) a role from InferenceOwnership. Completed item markers
allow the next explicit batch to skip fresh items after restart.
"""
from copy import deepcopy
import logging
import secrets
import threading
import time
from media_progress import item_title

from ai_process import AIUnavailable
from ai_search import AIBusy
from ai_score_spool import SearchCancelled
from video_direct_index import VideoDirectIndex
from video_direct_search import VideoDirectSearch,VideoSearchChanged
from video_previews import MediaDecodeCancelled
from inference_ownership import InferenceOwnership
from previews import PreviewUnavailable

ACTIVE={'planning','waiting','running','cancelling'}


class VideoDirectJobs:
    def __init__(self,catalog,encoder,*,inference=None,reader=None,stage_parent=None,init_cancel=None):
        self.catalog,self.encoder=catalog,encoder
        self.index=VideoDirectIndex(catalog,encoder,reader=reader,stage_parent=stage_parent,init_cancel=init_cancel)
        self.inference=inference if inference is not None else InferenceOwnership().for_encoder(encoder,role='video')
        self.guard=threading.RLock();self.publication_guard=threading.Lock();self.cancelled=threading.Event();self.thread=None
        self.closed=False;self.searching=False;self.last_used=time.monotonic()
        self.idle_seconds=0;self.idle_stop=threading.Event();self.idle_thread=None
        self.value={'job_id':None,'state':'idle','candidate_total':0,'target':0,'processed':0,
                    'indexed':0,'reused':0,'unavailable':0,'remaining_candidates':0,'error_code':None,'item_progress':None}

    def status(self):
        with self.guard:return {**deepcopy(self.value),'resident':bool(getattr(self.encoder,'resident',False)),
                                'profile':self.index.profile.key,'searching':self.searching,'closed':self.closed}

    def start(self,conditions=None,*,limit=128):
        conditions={} if conditions is None else conditions
        if (type(conditions) is not dict or set(conditions)-{'view','root_id','root_ids','shelf','shelf_ids'}
                or conditions.get('view','all') not in ('all','favorites','shelf')
                or type(limit) is not int or not 1<=limit<=1000):raise ValueError('Invalid video index scope or batch size')
        # Common catalog validation before any thread/model activation.
        self.catalog.search(kind='video',limit=1,**conditions)
        with self.guard:
            if self.closed:raise AIUnavailable('Video owner is closing')
            if self.searching or self.thread is not None and self.thread.is_alive():raise AIBusy('Video owner is busy')
            if not bool(getattr(self.encoder,'available',True)):raise AIUnavailable('Video model is unavailable')
            self.cancelled=threading.Event()
            self.value.update(job_id=secrets.token_hex(16),state='planning',candidate_total=0,target=0,processed=0,
                              indexed=0,reused=0,unavailable=0,remaining_candidates=0,error_code=None,item_progress=None)
            self.thread=threading.Thread(target=self._run,args=(deepcopy(conditions),limit),name='direct-video-index',daemon=True)
            try:self.thread.start()
            except BaseException:self.value.update(state='failed',error_code='worker_start_failed');raise
            return self.status()

    def _check(self,generation):
        if self.closed or self.cancelled.is_set():raise MediaDecodeCancelled('Video job cancelled')
        if self.catalog.result_generation()!=generation:raise VideoSearchChanged('Video scope changed; start a new batch')

    def _update(self,**changes):
        with self.guard:self.value.update(changes)

    def _published(self):
        # Called after commit while the cancellation gate is still held.
        with self.guard:
            self.value['processed']+=1;self.value['indexed']+=1;self.value['item_progress']=None
            if self.value['processed']==self.value['target']:self.value['state']='completed'

    def _run(self,conditions,limit):
        acquired=False;generation=self.catalog.result_generation()
        try:
            picks=[];seen=reused=unavailable=0
            def collect(fetch):
                nonlocal seen,reused,unavailable
                number=0
                while True:
                    self._check(generation);reply=fetch(number)
                    self._update(candidate_total=reply['total'])
                    for row in reply['items']:
                        self._check(generation);seen+=1
                        try:revision=self.index.reader.video_manifest(row['id'])['revision']
                        except PreviewUnavailable:unavailable+=1;continue
                        if self.index.fresh(row['id'],revision,cancel=self.cancelled):reused+=1
                        else:picks.append((row['id'],revision,item_title(row['title'])))
                        if len(picks)==limit:break
                    self._update(reused=reused,unavailable=unavailable,remaining_candidates=max(0,reply['total']-seen))
                    if len(picks)==limit or seen>=reply['total']:return
                    number+=1
            self.catalog.search(kind='video',limit=120,result_sink=collect,cancelled=self.cancelled.is_set,**conditions)
            with self.publication_guard:
                self._check(generation)
                self._update(target=len(picks),state='waiting' if picks else 'completed')
            if picks:
                while not self.inference.acquire(timeout=.05):self._check(generation)
                acquired=True;self._check(generation);self._update(state='running')
                for item,revision,title in picks:
                    self._check(generation)
                    self.index.index_item(item,revision,cancel=self.cancelled,validate=lambda:self._check(generation),
                                          publication_guard=self.publication_guard,on_published=self._published,
                                          progress=lambda value,title=title:self._update(item_progress={**value,'item_title':title}))
        except (MediaDecodeCancelled,SearchCancelled,InterruptedError):self._update(state='cancelled',error_code=None,item_progress=None)
        except VideoSearchChanged:self._update(state='failed',error_code='scope_changed',item_progress=None)
        except Exception:
            if self.closed or self.cancelled.is_set():self._update(state='cancelled',error_code=None,item_progress=None)
            else:
                logging.getLogger(__name__).exception('Owned direct-video index failed')
                self._update(state='failed',error_code='video_index_failed',item_progress=None)
        finally:
            if acquired:self.inference.release()
            self.last_used=time.monotonic()

    def cancel(self):
        with self.publication_guard:
            with self.guard:
                accepted=self.thread is not None and self.thread.is_alive() and self.value['state'] in ACTIVE
                if accepted:self.cancelled.set();self.value['state']='cancelling'
                return {'cancel_requested':accepted,**self.status()}

    def search(self,query,**options):
        cancelled=options.get('cancelled')
        if cancelled is not None and not callable(cancelled):raise ValueError('Invalid video search cancellation')
        options['cancelled']=lambda:self.closed or cancelled is not None and cancelled()
        with self.guard:
            if self.closed:raise AIUnavailable('Video owner is closing')
            if self.searching or self.thread is not None and self.thread.is_alive():raise AIBusy('Video owner is busy')
            self.searching=True
        acquired=False
        try:
            if not self.inference.acquire(blocking=False):raise AIBusy('Another AI owner is busy')
            acquired=True
            if self.closed:raise AIUnavailable('Video owner is closing')
            return VideoDirectSearch(self.index).search(query,**options)
        finally:
            if acquired:self.inference.release()
            with self.guard:self.searching=False;self.last_used=time.monotonic()

    def similar(self,item_id,**options):
        from video_direct_similarity import VideoDirectSimilarity
        cancelled=options.get('cancelled')
        if cancelled is not None and not callable(cancelled):raise ValueError('Invalid video similarity cancellation')
        options['cancelled']=lambda:self.closed or cancelled is not None and cancelled()
        with self.guard:
            if self.closed:raise AIUnavailable('Video owner is closing')
            if self.searching or self.thread is not None and self.thread.is_alive():raise AIBusy('Video owner is busy')
            self.searching=True
        try:return VideoDirectSimilarity(self.index).similar(item_id,**options)
        finally:
            with self.guard:self.searching=False;self.last_used=time.monotonic()

    def configure(self,*,idle_release_seconds=0):
        if type(idle_release_seconds) is not int or not 0<=idle_release_seconds<=3600:raise ValueError('Invalid video idle release')
        with self.guard:
            if self.closed:raise AIUnavailable('Video owner is closing')
            self.idle_seconds=idle_release_seconds
            if idle_release_seconds and self.idle_thread is None:
                self.idle_thread=threading.Thread(target=self._idle,name='direct-video-idle',daemon=True)
                try:self.idle_thread.start()
                except BaseException:self.idle_thread=None;raise

    def release(self):
        with self.guard:
            if self.closed:raise AIUnavailable('Video owner is closing')
            if self.searching or self.thread is not None and self.thread.is_alive():raise AIBusy('Video owner is busy')
            if not bool(getattr(self.encoder,'resident',False)):return {'released':False,'resident':False}
            if not self.inference.acquire(blocking=False):raise AIBusy('Another AI owner is busy')
            try:return self.encoder.release()
            finally:self.inference.release()

    def _idle(self):
        while not self.idle_stop.wait(.2):
            with self.guard:
                due=self.idle_seconds and not self.searching and self.value['state'] not in ACTIVE and time.monotonic()-self.last_used>=self.idle_seconds
            if not due or not bool(getattr(self.encoder,'resident',False)):continue
            try:
                acquired=self.inference.acquire(blocking=False)
            except (AIUnavailable,RuntimeError):
                continue
            if not acquired:continue
            try:
                with self.guard:
                    if (not self.closed and not self.searching and self.value['state'] not in ACTIVE
                            and self.idle_seconds and time.monotonic()-self.last_used>=self.idle_seconds):self.encoder.release()
            except (AIUnavailable,RuntimeError):pass  # A busy/closing worker is retried after the next idle check.
            finally:self.inference.release()

    def close(self):
        with self.publication_guard:
            with self.guard:
                if self.closed:return
                self.closed=True;self.cancelled.set();self.idle_stop.set()
        if self.idle_thread is not None and self.idle_thread.ident is not None:self.idle_thread.join()
        # Closing only our encoder must not wait behind the other owner's whole
        # index batch. EncoderProcess.close also cancels its pre-launch checks.
        # Its own lock serializes any in-flight encode; no peer is touched here.
        self.encoder.close()
        if self.thread is not None and self.thread.ident is not None:self.thread.join()
        self.index.store.checkpoint()
