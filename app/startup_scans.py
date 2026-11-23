"""One backend-owned startup queue after the frontend's first rendered screen."""
import threading,time


class StartupScans:
    def __init__(self,catalog):
        self.catalog=catalog;self.guard=threading.Lock();self.cancelled=threading.Event()
        self.worker=None;self.requested=False;self.closed=False;self.current_job=None
        self.phase='idle';self.entries=[];self.results=[];self.current_root=None
    def state(self):
        with self.guard:
            return {'state':self.phase,'total':len(self.entries),'processed':len(self.results),
                    'root_id':self.current_root,'results':[dict(row) for row in self.results]}
    def start(self):
        with self.guard:
            if self.closed:raise ValueError('Startup queue is closed')
            if not self.requested:
                self.entries=[(root['id'],root['startup_scan']) for root in self.catalog.registered_roots() if root['startup_scan']!='none']
                self.requested=True;self.phase='running' if self.entries else 'complete'
                if self.entries:
                    self.worker=threading.Thread(target=self._run,daemon=True,name='aredoko-startup-scan');self.worker.start()
        return self.state()
    def _run_root(self,root,mode):
        while not self.cancelled.is_set():
            try:
                reply=self.catalog.start_scan(root,mode=mode);break
            except ValueError:
                # Manual scans win; do not cancel or duplicate their work.
                worker=self.catalog._worker
                if worker is not None and worker.is_alive():worker.join(.1);continue
                raise
        else:return None
        job=reply['job_id']
        with self.guard:self.current_job=job
        while True:
            if self.cancelled.is_set():self.catalog.cancel_scan(expected_job_id=job)
            status=self.catalog.scan_state(job)
            if status.get('stage') not in ('list','ai') and status['state'] not in ('running','cancelling'):break
            time.sleep(.05)
        failed=status['state']=='failed' or status.get('ai_state') in ('failed','error','unknown')
        return {'root_id':root,'mode':mode,'state':'failed' if failed else status['state'],
                'ai_state':status.get('ai_state','none'),'discovered':status.get('discovered',0),
                'error':status.get('error') or status.get('ai_error','')}
    def _run(self):
        try:
            for root,mode in self.entries:
                if self.cancelled.is_set():break
                with self.guard:self.current_root=root
                try:result=self._run_root(root,mode)
                except Exception:
                    result={'root_id':root,'mode':mode,'state':'failed','error':'起動時の更新を完了できませんでした。登録フォルダの状態を確認してください。'}
                with self.guard:
                    if result is not None:self.results.append(result)
                    self.current_job=None
        finally:
            with self.guard:self.current_root=None;self.phase='cancelled' if self.cancelled.is_set() else 'complete'
    def cancel(self):
        self.cancelled.set()
        with self.guard:job=self.current_job
        if job is not None:self.catalog.cancel_scan(expected_job_id=job)
        return self.state()
    def close(self,timeout=10):
        with self.guard:self.closed=True
        self.cancel()
        if self.worker is not None and self.worker is not threading.current_thread():self.worker.join(timeout)
        return self.worker is None or not self.worker.is_alive()
