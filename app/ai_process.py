"""Bounded private subprocess protocol; no external inference endpoint."""
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from ai_profiles import DEFAULT_PROFILE, REVISION
from runtime_paths import worker_command
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
        self._closed = False
        self.last_used = time.monotonic()
    @property
    def available(self):
        marker = self.model/'aredoko-revision.txt'
        try: return self.python.is_file() and marker.is_file() and marker.read_text(encoding='utf-8').strip()==self.profile.revision
        except OSError: return False
    @property
    def resident(self):
        return self.process is not None and self.process.poll() is None

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
        if self._closed:
            raise AIUnavailable('AI worker is closed')
        if self.process and self.process.poll() is None: return
        # A previously exited worker must not leave stale CUDA/device telemetry.
        self.device = ''
        self.telemetry = {}
        if not self.available: raise AIUnavailable('AI runtime/model is not installed')
        env=os.environ.copy()
        env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
        self.responses=queue.Queue(maxsize=2)
        try:command=worker_command(self.python,Path(__file__).with_name('ai_worker.py'),['--model',str(self.model),'--parent-pid',str(os.getpid()),'--profile-json',json.dumps(self.profile.to_dict())],cancelled=lambda:self._closed)
        except (ValueError,OSError,RuntimeError) as error:raise AIUnavailable('AI runtime validation failed') from error
        if self._closed:raise AIUnavailable('AI worker is closed')
        self.process=subprocess.Popen(command,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,text=True,encoding='utf-8',env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        threading.Thread(target=self._read,args=(self.process,self.responses),daemon=True).start()
        hello=self._response()
        if hello.get('dimension')!=self.profile.dimension or hello.get('profile')!=self.profile.key:
            self._stop();raise AIUnavailable('Incompatible AI worker')
        self.device=hello['device']
    def encode(self, operation, value):
        audio_message=None
        if operation=='audio':
            if 'audio' not in self.profile.modalities:raise AIUnavailable('Selected profile does not support audio input')
            from audio_protocol import audio_request
            audio_message=audio_request(value)  # Reject malformed input before loading a model.
        with self.lock:
            self._start()
            request=audio_message if audio_message is not None else {'operation':operation}
            if audio_message is None:request['image' if operation=='image' else 'text']=base64.b64encode(value).decode('ascii') if operation=='image' else value
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
            finally:
                self.last_used = time.monotonic()
    def _stop(self):
        self.device = ''
        self.telemetry = {}
        if self.process:
            process,self.process=self.process,None
            if process.poll() is None: process.kill()
            process.wait(timeout=10)
            process.stdin.close();process.stdout.close()
    def release(self):
        """Drop only this owner's idle worker; next encode may relaunch it."""
        if not self.lock.acquire(blocking=False):
            raise AIUnavailable('AI worker is busy')
        try:
            if self._closed:
                raise AIUnavailable('AI worker is closed')
            was_resident = self.resident
            self._stop()
            self.last_used = time.monotonic()
            return {'released': was_resident, 'resident': False}
        finally:
            self.lock.release()

    def close(self):
        """Permanent shutdown: no in-flight encode can relaunch after return."""
        self._closed = True  # Also interrupt an in-flight pre-launch hash pass.
        with self.lock:
            self._stop()

