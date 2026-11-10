"""Only the application-owned AI wheel cache is deletable here.

Models, environments, databases and mandatory CPython evidence are outside
this directory. Builders share cache_lease while acquiring/using these wheels.
"""
from copy import deepcopy
from pathlib import Path
import threading
from ai_runtime import inspect_runtime
from ai_runtime_preferences import read_preferences
from managed_ai_runtime import recipe
from storage_lease import plain_path, storage_lease


def cache_lease(data):
    return storage_lease(Path(data)/'runtime-cache-use')


class CacheBusy(RuntimeError):pass


class RuntimeCache:
    def __init__(self,settings,*,busy=lambda:False):
        self.settings=Path(settings);self.data=self.settings.parent
        self.root=self.data/'runtime-cache/wheels';self.busy=busy
        self.lock=threading.RLock();self.cancelled=threading.Event();self.closed=False;self.thread=None
        self.value={'state':'idle','files_done':0,'bytes_done':0,'error':'','message':''}

    def _files(self):
        if not self.root.exists():return []
        plain_path(self.root,directory=True)
        allowed={entry['filename'] for entry in recipe()['entries']}
        paths=[]
        for path in self.root.iterdir():
            if path.name not in allowed:raise ValueError('Unexpected files in wheel cache; nothing removed')
            paths.append(plain_path(path))
        return paths

    def describe(self):
        with self.lock:
            active=self.thread is not None and self.thread.is_alive()
        paths=self._files()
        settings=read_preferences(self.settings) if self.settings.exists() else {}
        usable=False
        if settings.get('ai_runtime_root') and settings.get('ai_runtime_manifest_sha256'):
            info=inspect_runtime(settings['ai_runtime_root'],expected=settings['ai_runtime_manifest_sha256'])
            if info.get('cache_required') is False:
                import json
                marker=Path(info['root'])/'aredoko-ai-runtime.json'
                usable=Path(json.loads(marker.read_text(encoding='utf8'))['wheel_cache'])==self.root
        return {'path':str(self.root),'exists':self.root.exists(),'files':len(paths),'bytes':sum(path.stat().st_size for path in paths),
                'can_delete':bool(paths) and usable and not active and not self.busy(),
                'message':('削除後も導入済みAI検索は利用できます。修復・再構築には再ダウンロードが必要です。' if usable
                           else 'AI環境の有効化が完了するまで、検証用キャッシュを保持します。'),
                'job':self.snapshot()}

    def snapshot(self):
        with self.lock:return deepcopy(self.value)

    def start(self,body):
        if not isinstance(body,dict) or body!={'consent':True} or body['consent'] is not True:raise ValueError('Explicit cache deletion consent required')
        with self.lock:
            if self.closed or self.thread is not None and self.thread.is_alive() or self.busy():raise CacheBusy('Setup is using the cache')
            self.cancelled=threading.Event()
            self.value={'state':'checking','files_done':0,'bytes_done':0,'error':'','message':'導入済み環境の整合性を確認しています。'}
            self.thread=threading.Thread(target=self._clear,daemon=True,name='aredoko-runtime-cache')
            try:self.thread.start()
            except Exception as error:
                self.thread=None;self.value.update(state='failed',error='worker_start_failed',message='削除処理を開始できませんでした。')
                raise CacheBusy('Cache cleanup worker did not start') from error
            return self.snapshot()

    def _progress(self,value):
        with self.lock:
            self.value.update({key:value[key] for key in ('files_done','files_total','bytes_done','bytes_total') if key in value})

    def _clear(self):
        try:
            with cache_lease(self.data),storage_lease(self.settings):
                if self.busy():raise CacheBusy('Setup is using the cache')
                settings=read_preferences(self.settings)
                if not settings.get('ai_runtime_root') or not settings.get('ai_runtime_manifest_sha256'):raise ValueError('No selected verified AI environment')
                info=inspect_runtime(settings['ai_runtime_root'],expected=settings['ai_runtime_manifest_sha256'],verify=True,
                                     cancelled=self.cancelled.is_set,progress=self._progress)
                if info.get('cache_required') is not False:raise ValueError('Selected runtime still needs original artifacts')
                import json
                marker=Path(info['root'])/'aredoko-ai-runtime.json'
                if Path(json.loads(marker.read_text(encoding='utf8'))['wheel_cache'])!=self.root:raise ValueError('Cache is not owned by this application location')
                paths=self._files()
                with self.lock:
                    if self.cancelled.is_set():raise InterruptedError('Cache cleanup cancelled')
                    self.value.update(state='deleting',message='不要な取得キャッシュを削除しています。',files_done=0,bytes_done=0,files_total=len(paths),bytes_total=sum(path.stat().st_size for path in paths))
                for path in paths:
                    size=plain_path(path).stat().st_size
                    path.unlink()
                    with self.lock:
                        self.value['files_done']+=1;self.value['bytes_done']+=size
                with self.lock:self.value.update(state='complete',message='取得キャッシュを削除しました。AI環境とモデルは保持しています。')
        except Exception as error:
            with self.lock:
                self.value.update(state='cancelled' if self.cancelled.is_set() else 'failed',error=type(error).__name__,
                                  message='削除を中止しました。' if self.cancelled.is_set() else '削除を完了できませんでした。残っているファイルと準備中の処理を確認してください。')

    def cancel(self):
        with self.lock:
            accepted=self.value['state']=='checking'
            if accepted:self.cancelled.set()
            return {**self.snapshot(),'cancel_accepted':accepted}

    def close(self,timeout=10):
        with self.lock:
            self.closed=True
            if self.value['state']=='checking':self.cancelled.set()
            thread=self.thread
        if thread is not None:thread.join(timeout)
        return thread is None or not thread.is_alive()
