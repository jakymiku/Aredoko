"""Bounded owned Laya subprocess. Offline, opt-in and independent of retrieval."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from runtime_paths import worker_command
from laya_config import IDENTITY, REVISION, ARTIFACTS, CONTRACT
from search_intent import IntentUnavailable, validate_query,validate_decision
from intent_questions import get_questions,question_key

class LayaProcess:
    def __init__(self,python,model,*,cold_timeout=60,warm_timeout=5,question_set='v1',check_order=False):
        self.question_set=question_set;self.questions=get_questions(question_set)
        if type(check_order) is not bool:raise ValueError('Order check must be boolean')
        self.check_order=check_order;self.question_key=question_key(question_set)
        self.python,self.model=Path(python),Path(model)
        self.cold_timeout,self.warm_timeout=cold_timeout,warm_timeout
        self.process=None;self.responses=queue.Queue(maxsize=2)
        self.lock=threading.Lock();self.lifecycle=threading.Lock()
        self.closed=False;self.retry_after=0;self.device='';self.worker_pid=None;self.telemetry={}
    @property
    def available(self):
        if self.closed or not self.python.is_file():return False
        try:
            if ((self.model/'aredoko-revision.txt').stat().st_size>128 or
                    (self.model/'aredoko-source.json').stat().st_size>8192):return False
            return ((self.model/'aredoko-revision.txt').read_text(encoding='utf-8').strip()==REVISION
                    and json.loads((self.model/'aredoko-source.json').read_text(encoding='utf-8'))==IDENTITY
                    and all((self.model/name).is_file() for name in ARTIFACTS))
        except (OSError,ValueError):return False
    @staticmethod
    def _read(process,responses):
        try:
            while True:
                line=process.stdout.readline(32769)
                if not line or len(line)>32768: raise ValueError('Invalid worker output')
                result=json.loads(line)
                if not isinstance(result,dict): raise ValueError('Invalid worker object')
                responses.put_nowait(result)
        except (OSError,ValueError,queue.Full):
            try:responses.put_nowait({'error':'Worker stopped'})
            except queue.Full:pass
    def _response(self,timeout):
        try:response=self.responses.get(timeout=timeout)
        except queue.Empty:raise IntentUnavailable('Decision timeout') from None
        if not isinstance(response,dict) or 'error' in response:
            raise IntentUnavailable('Decision failed')
        return response
    def _start(self):
        with self.lifecycle:
            if self.closed:raise IntentUnavailable('Decision provider closed')
            if self.process and self.process.poll() is None:return
            if self.process:
                self.process.stdin.close();self.process.stdout.close();self.process=None
            if not self.available:raise IntentUnavailable('Local decision model unavailable')
            env=os.environ.copy()
            env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',
                       PYTHONIOENCODING='utf-8',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1')
            self.responses=queue.Queue(maxsize=2)
            command=worker_command(self.python,Path(__file__).with_name('laya_worker.py'),['--model',str(self.model.resolve()),'--parent-pid',str(os.getpid()),'--question-set',self.question_set])
            if self.check_order:command.append('--check-order')
            self.process=subprocess.Popen(command,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,text=True,encoding='utf-8',env=env,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            threading.Thread(target=self._read,args=(self.process,self.responses),daemon=True).start()
        hello=self._response(self.cold_timeout)
        if hello.get('ready') is not True or hello.get('identity')!=IDENTITY or hello.get('contract')!=CONTRACT:
            raise IntentUnavailable('Incompatible decision worker')
        if hello.get('question_key')!=self.question_key or hello.get('check_order') is not self.check_order:
            raise IntentUnavailable('Decision question contract mismatch')
        if hello.get('device') not in ('cpu','cuda','cuda:0'):raise IntentUnavailable('Invalid device')
        pid=hello.get('worker_pid')
        if isinstance(pid,bool) or not isinstance(pid,int) or pid<=0:raise IntentUnavailable('Invalid worker identity')
        self.worker_pid=pid
        self.device=hello['device']
        self.telemetry={k:hello[k] for k in ('load_ms','peak_memory_mib','network_blocked_calls') if k in hello}
    def decide(self,query):
        query=validate_query(query)
        if not query:raise ValueError('Empty decision query')
        if not self.lock.acquire(blocking=False):raise IntentUnavailable('Decision worker busy')
        try:
            if time.monotonic()<self.retry_after:raise IntentUnavailable('Decision cooldown')
            self._start()
            process=self.process
            if process is None:raise IntentUnavailable('Decision provider stopped')
            process.stdin.write(json.dumps({'query':query},ensure_ascii=False)+'\n');process.stdin.flush()
            result=self._response(self.warm_timeout)
            self.telemetry.update({k:result[k] for k in ('elapsed_ms','peak_memory_mib','network_blocked_calls') if k in result})
            if not isinstance(result.get('result'),dict):raise IntentUnavailable('Missing decision result')
            checked=validate_decision(result['result'],self.questions)
            if self.check_order and 'order_consistent' not in checked:raise IntentUnavailable('Missing order verification')
            return result['result']
        except (OSError,ValueError,TypeError,IntentUnavailable) as ex:
            self._stop();self.retry_after=time.monotonic()+30
            raise IntentUnavailable('Decision unavailable; manual search remains usable') from ex
        finally:self.lock.release()
    def _stop(self):
        with self.lifecycle:
            process,self.process=self.process,None
            self.device='';self.worker_pid=None
        if process:
            if process.poll() is None:process.kill()
            process.wait(timeout=10)
            process.stdin.close();process.stdout.close()
    def close(self):
        with self.lifecycle:self.closed=True
        self._stop()
