"""Owned asynchronous backup jobs. Production activation requires a writer fence.

Job IDs/cancel/publication are local API data, never OS/UI handles. No restore
or live path switch is performed here.
"""
from copy import deepcopy
from pathlib import Path
import re,secrets,threading
from live_backup import capture_live,BackupSelection
from storage_lease import StorageBusyError

ACTIVE={'waiting','capturing','packing','publishing','cancelling'}
ID=re.compile(r'[0-9a-f]{32}\Z')
class BackupBusy(RuntimeError):pass

class BackupJobs:
    def __init__(self,catalog,*,quiesce,configuration=None,capture=capture_live):
        if not callable(quiesce):raise ValueError('Writer coordination required')
        self.catalog=catalog;self.quiesce=quiesce;self.configuration=configuration or (lambda:{})
        self.capture=capture;self.lock=threading.RLock();self.thread=None
        self.closed=False;self.committed=False;self.cancelled=threading.Event()
        self.value={'job_id':None,'state':'idle','stage':'idle','published':False,'cancel_requested':False,
                    'bytes_done':0,'bytes_total':None,'output':None,'selection':None,'result':None,'error_code':None,'message':''}
    @staticmethod
    def validate_id(value):
        if not isinstance(value,str) or ID.fullmatch(value) is None:raise ValueError('Invalid backup job ID')
    def snapshot(self,job_id=None):
        with self.lock:
            if job_id is not None:
                self.validate_id(job_id)
                if job_id!=self.value['job_id']:raise KeyError('Backup job is no longer current')
            return deepcopy(self.value)
    def start(self,body):
        if not isinstance(body,dict) or set(body)!={'consent','output','selection'} or body['consent'] is not True:raise ValueError('Explicit backup consent and destination required')
        destination=body['output'];selected=body['selection']
        if not isinstance(destination,str) or not 1<=len(destination)<=4096 or not Path(destination).is_absolute() or any(ord(char)<32 for char in destination):raise ValueError('Select an absolute backup directory')
        if not isinstance(selected,dict) or set(selected)!={'settings','history','reader_progress','vectors'}:raise ValueError('Invalid backup selection')
        selection=BackupSelection(**selected)
        with self.lock:
            if self.closed:raise BackupBusy('Backup owner is closing')
            if self.thread is not None and self.thread.is_alive():raise BackupBusy('Backup is already running')
            self.cancelled=threading.Event();self.committed=False
            self.value.update(job_id=secrets.token_hex(16),state='waiting',stage='waiting',published=False,cancel_requested=False,
                              bytes_done=0,bytes_total=None,output=destination,selection=dict(selected),result=None,error_code=None,message='バックアップの開始を待っています。')
            self.thread=threading.Thread(target=self._run,args=(Path(destination),selection),name='aredoko-backup',daemon=True)
            try:self.thread.start()
            except Exception as error:
                self.value.update(state='failed',stage='failed',error_code='worker_start_failed',message='バックアップを開始できませんでした。')
                raise BackupBusy('Backup worker did not start') from error
            return self.snapshot()
    def _progress(self,value):
        with self.lock:
            stage=value['stage'];self.value.update(stage=stage,bytes_done=value.get('bytes_done',0),bytes_total=value.get('bytes_total'))
            if self.value['state']!='cancelling':self.value['state']=stage
            self.value['message']={'waiting':'書き込み処理の区切りを待っています。','capturing':'データのスナップショットを作成しています。','packing':'バックアップを検査しています。'}.get(stage,'バックアップを作成しています。')
    def _publish(self,operation):
        # Exactly the same lock decides cancellation and manifest publication.
        with self.lock:
            if self.closed or self.cancelled.is_set():raise InterruptedError('Backup cancelled before publication')
            self.value.update(state='publishing',stage='publishing',message='バックアップを確定しています。')
            operation();self.committed=True;self.value['published']=True
    def _run(self,destination,selection):
        try:
            result=self.capture(self.catalog,destination,quiesce=self.quiesce,selection=selection,
                                cancelled=self.cancelled.is_set,progress=self._progress,publish=self._publish,**self.configuration())
            with self.lock:self.value.update(state='complete',stage='complete',result=result,message='バックアップを作成しました。')
        except Exception as error:
            with self.lock:
                if self.committed:self.value.update(state='complete',stage='complete',error_code='post_publish_cleanup_failed',message='バックアップは作成済みです。一時データの後処理を確認してください。')
                elif self.cancelled.is_set():self.value.update(state='cancelled',stage='cancelled',message='バックアップを中止しました。')
                else:
                    code='storage_busy' if isinstance(error,StorageBusyError) else 'filesystem_error' if isinstance(error,OSError) else 'validation_failed' if isinstance(error,ValueError) else 'backup_failed'
                    self.value.update(state='failed',stage='failed',error_code=code,message='バックアップを作成できませんでした。元のデータは保持しています。')
    def cancel(self,job_id):
        with self.lock:
            self.snapshot(job_id)
            accepted=self.value['state'] in ACTIVE and not self.committed
            if accepted:self.cancelled.set();self.value.update(state='cancelling',cancel_requested=True,message='バックアップを中止しています。')
            return {**self.snapshot(),'cancel_accepted':accepted}
    def close(self,timeout=10):
        with self.lock:
            self.closed=True
            if not self.committed:self.cancelled.set()
            thread=self.thread
        if thread is not None and thread.ident is not None and thread is not threading.current_thread():thread.join(timeout)
        # A blocking OS read cannot be killed. Closed owners cannot publish later.
        return thread is None or not thread.is_alive()
