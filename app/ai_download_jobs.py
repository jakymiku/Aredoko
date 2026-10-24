"""Owned optional AI acquisition jobs; HTTP clients select catalog IDs, never URLs."""
from copy import deepcopy
from pathlib import Path
import secrets,threading
from ai_acquisition import Catalog,acquire
from ai_model_pack import ModelPackValidator

ACTIVE={'waiting','downloading','verifying','publishing','cancelling'}
class DownloadBusy(RuntimeError):pass

class AIDownloadJobs:
    def __init__(self,root,*,specifications=(),download=acquire):
        self.root=Path(root);self.download=download;self.specs={}
        for catalog,validator in specifications:
            if not isinstance(catalog,Catalog) or not callable(validator) or catalog.fingerprint in self.specs:raise ValueError('Trusted catalog and validator required')
            if isinstance(validator,ModelPackValidator) and validator.catalog.fingerprint!=catalog.fingerprint:raise ValueError('Model validator/catalog binding mismatch')
            self.specs[catalog.fingerprint]=(catalog,validator)
        self.lock=threading.RLock();self.closed=False;self.thread=None;self.committed=False;self.cancelled=threading.Event()
        self.value={'job_id':None,'state':'idle','catalog_id':None,'bytes_received':0,'bytes_verified':0,'bytes_total':None,'published':False,'result':None,'error_code':None,'message':''}
    @property
    def supported(self):return bool(self.specs)
    def catalogs(self):
        rows=[]
        for c,validator in self.specs.values():
            row={'catalog_id':c.fingerprint,'name':c.key,'kind':c.kind,'revision':c.revision,'bytes':sum(a.size for a in c.entries),'license':c.license,'license_url':c.license_url,'source_hosts':list(c.hosts)}
            # Metadata comes only from the pinned source profile, never from a
            # catalog name, downloaded content, or an arbitrary callable attribute.
            if isinstance(validator,ModelPackValidator):
                row.update(model_target=validator.target.to_dict(),definition_sha256=validator.definition_sha256)
            rows.append(row)
        return {'download_supported':self.supported,'catalogs':rows}
    def snapshot(self):
        with self.lock:return deepcopy(self.value)
    def start(self,body):
        if not isinstance(body,dict) or set(body)!={'consent','catalog_id','bytes_per_second'} or body['consent'] is not True:raise ValueError('Explicit acquisition consent required')
        key=body['catalog_id'];rate=body['bytes_per_second']
        if not isinstance(key,str) or key not in self.specs:raise ValueError('Unknown trusted catalog')
        if rate is not None and (type(rate) is not int or not 1<=rate<=2**40):raise ValueError('Invalid optional bandwidth limit')
        catalog,validator=self.specs[key]
        with self.lock:
            if self.closed or self.thread is not None and self.thread.is_alive():raise DownloadBusy('Acquisition is already active')
            self.cancelled=threading.Event();self.committed=False
            self.value.update(job_id=secrets.token_hex(16),state='waiting',catalog_id=key,bytes_received=0,bytes_verified=0,bytes_total=sum(a.size for a in catalog.entries),published=False,result=None,error_code=None,message='AI環境の取得を準備しています。')
            self.thread=threading.Thread(target=self._run,args=(catalog,validator,rate),daemon=True,name='aredoko-acquisition')
            try:self.thread.start()
            except Exception as error:
                self.value.update(state='failed',error_code='worker_start_failed',message='取得を開始できませんでした。')
                raise DownloadBusy('Acquisition worker did not start') from error
            return self.snapshot()
    def _progress(self,value):
        with self.lock:
            self.value.update({k:value[k] for k in ('bytes_received','bytes_verified','bytes_total')})
            if self.value['state']!='cancelling':self.value['state']=value['stage']
            self.value['message']={'downloading':'AI環境をダウンロードしています。','verifying':'取得内容を確認しています。','publishing':'検証済みのAI環境を保存しています。'}.get(value['stage'],'取得を準備しています。')
    def _publish(self,operation):
        with self.lock:
            if self.closed or self.cancelled.is_set():raise InterruptedError('Acquisition owner cancelled')
            operation();self.committed=True;self.value['published']=True
    def _run(self,catalog,validator,rate):
        try:
            result=self.download(catalog,self.root,validate=validator,publish=self._publish,cancelled=self.cancelled.is_set,progress=self._progress,bytes_per_second=rate)
            with self.lock:self.value.update(state='complete',result=result,message=('取得済みのAI環境を確認しました。利用するには設定から選択してください。' if result.get('reused') else 'AI環境を取得しました。利用するには設定から選択してください。'))
        except Exception as error:
            with self.lock:
                if self.committed:self.value.update(state='complete',error_code='post_publish_failed',message='AI環境は保存済みです。状態を確認してください。')
                elif self.cancelled.is_set():self.value.update(state='cancelled',message='取得を中止しました。同じバージョンは途中から再開できます。')
                else:self.value.update(state='failed',error_code='transfer_failed' if isinstance(error,OSError) else 'validation_failed',message='取得または検証を完了できませんでした。既存のAI環境は保持しています。')
    def cancel(self,job_id):
        with self.lock:
            if not isinstance(job_id,str) or job_id!=self.value['job_id']:raise KeyError('Acquisition job changed')
            accepted=self.value['state'] in ACTIVE and not self.committed
            if accepted:self.cancelled.set();self.value.update(state='cancelling',message='取得を中止しています。')
            return {**self.snapshot(),'cancel_accepted':accepted}
    def close(self,timeout=10):
        with self.lock:
            self.closed=True
            if not self.committed:self.cancelled.set()
            thread=self.thread
        if thread is not None and thread.ident is not None and thread is not threading.current_thread():thread.join(timeout)
        return thread is None or not thread.is_alive()
