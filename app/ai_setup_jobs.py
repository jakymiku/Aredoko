"""One owned background location-validation job; no downloads or inference."""
from copy import deepcopy
from pathlib import Path
import re
import secrets
import threading
from ai_runtime_preferences import UNSET, MODEL_ROOT_FIELDS
from model_locations import ModelTarget
from storage_lease import StorageBusyError

ACTIVE={'validating','cancelling','saving'}
ID=re.compile(r'[0-9a-f]{32}\Z')


class SetupBusy(RuntimeError):pass


class AISetupJobs:
    def __init__(self,preferences):
        self.preferences=preferences
        self.lock=threading.RLock();self.cancelled=threading.Event()
        self.thread=None;self.closed=False;self.committed=False
        self.value={'job_id':None,'state':'idle','stage':'idle','saved':False,
                    'cancel_requested':False,'files_done':0,'files_total':None,
                    'bytes_done':0,'bytes_total':None,'error_code':None,
                    'message':'','result':None}

    @staticmethod
    def validate_id(value):
        if not isinstance(value,str) or ID.fullmatch(value) is None:raise ValueError('Invalid setup job ID')

    def snapshot(self):
        with self.lock:return deepcopy(self.value)

    def start(self,body):
        if (not isinstance(body,dict) or body.get('consent') is not True
                or set(body)-{'consent','runtime_root','models_root','model_role','model_target'}
                or not {'runtime_root','models_root'}&set(body)):
            raise ValueError('Explicit location selection and consent are required')
        for key in ('runtime_root','models_root'):
            value=body.get(key)
            if value is not None and (not isinstance(value,str) or len(value)>4096
                    or not Path(value).is_absolute() or any(ord(c)<32 for c in value)):
                raise ValueError('Select an absolute folder')
        selection={key:body.get(key,UNSET) for key in ('runtime_root','models_root')}
        if 'model_role' in body:
            role=body['model_role']
            if not isinstance(role,str) or role not in MODEL_ROOT_FIELDS or 'models_root' not in body:raise ValueError('Explicit model role and folder required')
            selection['model_role']=role
        if 'model_target' in body:
            if 'model_role' in body or 'models_root' not in body:raise ValueError('Select one explicit model target')
            selection['model_target']=ModelTarget.from_dict(body['model_target']).to_dict()

        with self.lock:
            if self.closed:raise SetupBusy('Setup is closing')
            if self.thread is not None and self.thread.is_alive():raise SetupBusy('Setup is already running')
            self.cancelled=threading.Event();self.committed=False
            self.value.update(job_id=secrets.token_hex(16),state='validating',stage='validating',saved=False,
                cancel_requested=False,files_done=0,files_total=None,bytes_done=0,bytes_total=None,
                error_code=None,message='選択したフォルダを確認しています。',result=None)
            self.thread=threading.Thread(target=self._run,args=(selection,),name='ai-setup-validation',daemon=True)
            try:self.thread.start()
            except Exception as error:
                self.value.update(state='failed',stage='failed',error_code='worker_start_failed',message='確認処理を開始できませんでした。')
                raise SetupBusy('Setup worker did not start') from error
            return self.snapshot()

    def _progress(self,counts):
        with self.lock:
            if not self.cancelled.is_set():self.value.update(counts)

    def _publish(self,operation):
        # Cancellation and settings publication have one ordering point. A
        # successful cancel can never be followed by a saved selection.
        with self.lock:
            if self.closed or self.cancelled.is_set():raise RuntimeError('Runtime selection cancelled')
            self.value.update(state='saving',stage='saving',message='設定を保存しています。')
            operation()
            self.committed=True;self.value['saved']=True

    def _run(self,selection):
        try:
            result=self.preferences.select(**selection,consent=True,cancelled=self.cancelled.is_set,
                progress=self._progress,publish=self._publish)
            with self.lock:self.value.update(state='complete',stage='complete',result=result,
                message='設定を保存しました。次回起動時に反映します。')
        except Exception as error:
            with self.lock:
                if self.committed:
                    # Saving succeeded but a later diagnostic failed. Do not
                    # claim cancellation/rollback of already published data.
                    self.value.update(state='complete',stage='complete',error_code='diagnostics_failed',
                        message='設定は保存済みです。状態の再確認が必要です。')
                elif self.cancelled.is_set():
                    self.value.update(state='cancelled',stage='cancelled',message='確認を中止しました。設定は変更していません。')
                else:
                    code=('settings_busy' if isinstance(error,StorageBusyError) else
                          'filesystem_error' if isinstance(error,OSError) else
                          'validation_failed' if isinstance(error,ValueError) else 'validation_error')
                    self.value.update(state='failed',stage='failed',error_code=code,
                        message='確認または保存を完了できませんでした。以前の設定を保持しています。')

    def cancel(self,job_id):
        self.validate_id(job_id)
        with self.lock:
            if self.value['job_id']!=job_id:raise KeyError('Setup job is no longer current')
            accepted=self.value['state'] in ACTIVE and not self.committed
            if accepted:
                self.cancelled.set();self.value.update(state='cancelling',cancel_requested=True,
                    message='確認を中止しています。')
            return {**self.snapshot(),'cancel_accepted':accepted}

    def close(self,timeout=10):
        with self.lock:
            self.closed=True
            if not self.committed:self.cancelled.set()
            thread=self.thread
        if thread is not None and thread.ident is not None and thread is not threading.current_thread():thread.join(timeout=timeout)
        # A blocked filesystem read cannot be forcibly interrupted, but closed
        # jobs cannot subsequently commit preferences. Retain this ownership.
        return thread is None or not thread.is_alive()
