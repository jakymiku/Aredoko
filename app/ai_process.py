"""Bounded private subprocess protocol; no external inference endpoint."""
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from ai_profiles import DEFAULT_PROFILE, REVISION
from ai_vectors import normalized
PROFILE = DEFAULT_PROFILE.key
class AIUnavailable(RuntimeError): pass
class EncoderProcess:
    def __init__(self, python, model, profile=DEFAULT_PROFILE):
        self.python,self.model = Path(python),Path(model)
        self.profile=profile
        self.process = None
        self.lock = threading.Lock()
        self.responses = queue.Queue(maxsize=2)
        self.device = ''
        self.telemetry = {}
    @property
    def available(self):
        marker = self.model/'aredoko-revision.txt'
        try: return self.python.is_file() and marker.is_file() and marker.read_text(encoding='utf-8').strip()==self.profile.revision
        except OSError: return False
    def _read(self, process, responses):
        try:
            while True:
                line = process.stdout.readline(100_001)
                if not line or len(line)>100_000:
                    responses.put({'error':'Worker stopped'})
                    return
                responses.put(json.loads(line))
        except (ValueError,OSError):
            responses.put({'error':'Invalid worker response'})
    def _response(self, timeout=180):
        try: result=self.responses.get(timeout=timeout)
        except queue.Empty:
            self._stop()
            raise AIUnavailable('AI worker timed out')
        if 'error' in result: raise AIUnavailable('AI inference failed: '+result['error'])
        return result
    def _start(self):
        if self.process and self.process.poll() is None: return
        if not self.available: raise AIUnavailable('AI runtime/model is not installed')
        env=os.environ.copy()
        env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONIOENCODING='utf-8')
        self.responses=queue.Queue(maxsize=2)
        self.process=subprocess.Popen([str(self.python),'-u',str(Path(__file__).with_name('ai_worker.py')),'--model',str(self.model),'--parent-pid',str(os.getpid()),'--profile-json',json.dumps(self.profile.to_dict())],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,text=True,encoding='utf-8',env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        threading.Thread(target=self._read,args=(self.process,self.responses),daemon=True).start()
        hello=self._response()
        if hello.get('dimension')!=self.profile.dimension or hello.get('profile')!=self.profile.key:
            self._stop();raise AIUnavailable('Incompatible AI worker')
        self.device=hello['device']
    def encode(self, operation, value):
        with self.lock:
            self._start()
            request={'operation':operation}
            request['image' if operation=='image' else 'text']=base64.b64encode(value).decode('ascii') if operation=='image' else value
            try:
                self.process.stdin.write(json.dumps(request,ensure_ascii=False)+'\n')
                self.process.stdin.flush()
                result=self._response()
                self.telemetry={k:result[k] for k in ('elapsed_ms','peak_memory_mib') if k in result}
                vector=result.get('vector')
                if vector is not None:
                    try: vector=normalized(vector,self.profile.dimension)
                    except (TypeError,ValueError) as ex:
                        self._stop();raise AIUnavailable('Invalid embedding from worker') from ex
                elif not (operation=='image' and result.get('skip') is True):
                    raise AIUnavailable('Missing embedding')
                return vector
            except (OSError,KeyError) as ex:
                self._stop();raise AIUnavailable('AI worker disconnected') from ex
    def _stop(self):
        if self.process:
            process,self.process=self.process,None
            if process.poll() is None: process.kill()
            process.wait(timeout=10)
            process.stdin.close();process.stdout.close()
    def close(self):
        # Kill the owned child promptly even if the index thread is waiting.
        self._stop()

