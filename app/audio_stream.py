"""One owned decoder, bounded PCM windows and explicit successful EOF.

The caller owns the already validated input handle and must use a context
manager. Yielded windows are provisional: only `complete` permits atomic index
publication. No model, catalog, path, network or output file is opened here.
"""
import os
import queue
import stat
import subprocess
import threading
import time

from audio_input import (AudioInputUnavailable, PCMWindow, SAMPLE_RATE,
                         MAX_WINDOW_MS, MAX_START_MS, MAX_AUDIO_BYTES,
                         FORMATS, validate_pcm, validate_window)
from video_previews import (_executable,MediaDecodeCancelled,FORMATS as VIDEO_FORMATS,
                            MAX_VIDEO_BYTES,MAX_VIDEO_PIXELS)

IDLE_SECONDS=10
SESSION_SECONDS=1800
READ_BYTES=65536


class PCMStream:
    """Use `with PCMStream(validated_handle, guard=...) as stream: ...`.

    `guard` rechecks the caller's source identity/registration, not an OS path
    supplied to this decoder. It runs before launch, each yield and completion.
    The input handle is never closed. Close, failure and early break reap the
    owned child and reader; a silent or short window does not mean EOF.
    input_kind='video' explicitly selects the existing video container/size
    policy. The default audio policy is unchanged; only track 0 is decoded.
    """
    def __init__(self,source,*,window_ms=MAX_WINDOW_MS,cancel=None,guard=None,input_kind='audio'):
        validate_window(0,window_ms)
        if guard is not None and not callable(guard):raise AudioInputUnavailable('Invalid source guard')
        if type(input_kind) is not str or input_kind not in ('audio','video'):raise AudioInputUnavailable('Invalid PCM input kind')
        self._video_input=input_kind=='video'
        self.source,self.window_ms,self.cancel,self.guard=source,window_ms,cancel,guard
        self.complete=False
        self.closed=False
        self.process=None
        self.reader=None
        self.stopped=threading.Event()
        self.messages=queue.Queue(maxsize=1)
        self.frames=0
        self.deadline=None
        self.initial=None

    @staticmethod
    def _identity(info):
        return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns

    def _check(self):
        if self.cancel is not None and self.cancel.is_set():raise MediaDecodeCancelled('Audio stream cancelled')
        if self.deadline is not None and time.monotonic()>self.deadline:
            raise AudioInputUnavailable('Audio stream session deadline exceeded')
        if self.initial is not None and self._identity(os.fstat(self.source.fileno()))!=self.initial:
            raise AudioInputUnavailable('Audio source changed during decoding')
        if self.guard is not None:self.guard()

    def __enter__(self):
        if self.closed or self.process is not None:raise AudioInputUnavailable('Audio stream cannot be reused')
        try:
            self._check()
            info=os.fstat(self.source.fileno())
            maximum=MAX_VIDEO_BYTES if self._video_input else MAX_AUDIO_BYTES
            if not stat.S_ISREG(info.st_mode) or not 1<=info.st_size<=maximum:
                raise AudioInputUnavailable('Audio source exceeds stream limits')
            self.initial=self._identity(info)
            self.source.seek(0,os.SEEK_END);self.source.seek(0)
            args=[_executable('ffmpeg'),'-nostdin','-v','error','-max_alloc',str(64*1024*1024),
                  '-protocol_whitelist','fd,pipe','-format_whitelist',VIDEO_FORMATS if self._video_input else FORMATS,
                  '-probesize','1048576','-analyzeduration','1000000','-max_streams','16',
                  '-max_probe_packets','128','-threads','1',
                  *(['-max_pixels',str(MAX_VIDEO_PIXELS)] if self._video_input else []),'-i','fd:',
                  '-map','0:a:0','-vn','-sn','-dn','-ac','1','-ar',str(SAMPLE_RATE),
                  # Preserve timestamp gaps as silence on the decoded timeline;
                  # never infer EOF by repeatedly seeking an empty interval.
                  '-af','aresample=async=1:first_pts=0','-threads','1',
                  '-c:a','pcm_f32le','-f','f32le','pipe:1']
            environment={key:value for key,value in os.environ.items() if key.upper()!='FFREPORT'}
            self.process=subprocess.Popen(args,stdin=self.source,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,shell=False,env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.deadline=time.monotonic()+SESSION_SECONDS
            self.reader=threading.Thread(target=self._drain,name='audio-pcm-reader',daemon=True)
            self.reader.start()
            return self
        except BaseException:
            self.close()
            raise

    def _put(self,message):
        while not self.stopped.is_set():
            try:self.messages.put(message,timeout=.05);return True
            except queue.Full:pass
        return False

    def _drain(self):
        pending=bytearray()
        maximum=MAX_START_MS*SAMPLE_RATE//1000*4
        window_bytes=self.window_ms*SAMPLE_RATE//1000*4
        total=0
        try:
            while not self.stopped.is_set():
                data=self.process.stdout.read(min(READ_BYTES,window_bytes-len(pending)))
                if not data:break
                total+=len(data)
                if total>maximum:raise AudioInputUnavailable('Decoded audio exceeds 24 hours')
                pending.extend(data)
                if len(pending)==window_bytes:
                    if not self._put(('data',bytes(pending))):return
                    pending.clear()
            if self.stopped.is_set():return
            if pending and not self._put(('data',bytes(pending))):return
            # EOF is not success until the actual decoder exit was checked.
            self._put(('end',None))
        except BaseException as error:
            self._put(('error',error))

    def __iter__(self):return self

    def __next__(self):
        if self.complete:raise StopIteration
        if self.closed or self.process is None:raise AudioInputUnavailable('Audio stream is not open')
        try:
            self._check()
            deadline=min(self.deadline,time.monotonic()+IDLE_SECONDS)
            while True:
                self._check()
                if time.monotonic()>deadline:raise AudioInputUnavailable('Audio decoder made no progress')
                try:kind,value=self.messages.get(timeout=.05);break
                except queue.Empty:pass
            if kind=='error':raise AudioInputUnavailable('Audio stream output unavailable') from value
            if kind=='end':
                remaining=min(deadline,self.deadline)-time.monotonic()
                try:code=self.process.wait(timeout=max(.001,remaining))
                except subprocess.TimeoutExpired as error:raise AudioInputUnavailable('Audio decoder did not exit') from error
                self._check()
                if code or not self.frames:raise AudioInputUnavailable('Audio stream is empty or decoder failed')
                self.close()
                self._check()
                self.complete=True
                raise StopIteration
            start_ms=self.frames*1000//SAMPLE_RATE
            window=validate_pcm(PCMWindow(start_ms,min(self.window_ms,MAX_START_MS-start_ms),value))
            self._check()
            self.frames+=window.frame_count
            return window
        except StopIteration:raise
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.closed:return
        self.closed=True
        self.stopped.set()
        try:
            if self.process is not None:
                if self.process.poll() is None:self.process.kill()
                self.process.wait(timeout=5)
        finally:
            if self.reader is not None and self.reader.ident is not None:
                self.reader.join(5)
                if self.reader.is_alive():raise AudioInputUnavailable('Owned audio reader did not stop')
            if self.process is not None and self.process.stdout is not None:self.process.stdout.close()

    def __exit__(self,*exc):self.close()
