"""One owned FFmpeg decoder for known-duration direct-video coverage.

Use as a context manager around a validated, seekable file handle. Frames are
provisional until successful exhaustion verifies the decoder exit and source.
No model, source path/URL, output file, or index is opened here.
"""
import os
import queue
import stat
import subprocess
import threading
import time

from video_coverage import probe_video_duration_ms
from video_input import VideoWindow,validate_video,MAX_EDGE,MAX_FRAMES
from video_previews import (_executable,FORMATS,MAX_VIDEO_BYTES,MAX_VIDEO_PIXELS,
                            MediaDecodeCancelled)
from video_window_decode import VideoWindowUnavailable

WINDOW_SECONDS=20
READ_BYTES=65536
FRAME_BYTES=MAX_EDGE*MAX_EDGE*3


class VideoCoverageStream:
    def __init__(self,source,*,cancel=None,guard=None):
        if guard is not None and not callable(guard):raise ValueError('Invalid source guard')
        self.source,self.cancel,self.guard=source,cancel,guard
        self.total_duration_ms=None
        self.complete=False;self.closed=False;self.opened=False
        self.process=None;self.reader=None;self.initial=None
        self.stopped=threading.Event();self.messages=queue.Queue(maxsize=1)
        self.frames=0;self.expected=None

    @staticmethod
    def _identity(info):
        return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns

    def _check(self):
        if self.cancel is not None and self.cancel.is_set():raise MediaDecodeCancelled('Video stream cancelled')
        if self.initial is not None and self._identity(os.fstat(self.source.fileno()))!=self.initial:
            raise VideoWindowUnavailable('Video source changed during decoding')
        if self.guard is not None:self.guard()

    def __enter__(self):
        if self.opened or self.closed:raise VideoWindowUnavailable('Video stream cannot be reused')
        self.opened=True
        return self

    def _start(self):
        self._check()
        info=os.fstat(self.source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 1<=info.st_size<=MAX_VIDEO_BYTES:
            raise VideoWindowUnavailable('Video source exceeds stream limits')
        self.initial=self._identity(info)
        self.total_duration_ms=probe_video_duration_ms(self.source,cancel=self.cancel,guard=self.guard)
        self._check();self.expected=(self.total_duration_ms+999)//1000
        self.source.seek(0,os.SEEK_END);self.source.seek(0)
        display='iw*if(gt(sar,0),sar,1)';factor=f'min({MAX_EDGE}/({display}),{MAX_EDGE}/ih)'
        fit=f"scale=w='max(1,trunc(({display})*{factor}))':h='max(1,trunc(ih*{factor}))',setsar=1"
        # Only the authoritative tail is padded. The output count comes from
        # the probe, never from a short decode or a guessed duration.
        filtering=f'tpad=stop_mode=clone:stop_duration=1,fps=fps=1:start_time=0:round=up,{fit},pad={MAX_EDGE}:{MAX_EDGE}:(ow-iw)/2:(oh-ih)/2:color=black'
        args=[_executable('ffmpeg'),'-nostdin','-v','error','-max_alloc',str(64*1024*1024),
              '-protocol_whitelist','fd,pipe','-format_whitelist',FORMATS,
              '-probesize','1048576','-analyzeduration','1000000','-max_streams','16','-max_probe_packets','128',
              '-threads','1','-max_pixels',str(MAX_VIDEO_PIXELS),'-t',f'{self.total_duration_ms/1000:.3f}','-i','fd:',
              '-map','0:V:0','-an','-sn','-dn','-vf',filtering,'-frames:v',str(self.expected),
              '-threads','1','-c:v','rawvideo','-pix_fmt','rgb24','-f','rawvideo','pipe:1']
        environment={key:value for key,value in os.environ.items() if key.upper()!='FFREPORT'}
        self.process=subprocess.Popen(args,stdin=self.source,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            shell=False,env=environment,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.reader=threading.Thread(target=self._drain,name='video-rgb-reader',daemon=True)
        self.reader.start()

    def _put(self,message):
        while not self.stopped.is_set():
            try:self.messages.put(message,timeout=.05);return True
            except queue.Full:pass
        return False

    def _drain(self):
        pending=bytearray();total=0
        try:
            while not self.stopped.is_set():
                data=self.process.stdout.read(min(READ_BYTES,FRAME_BYTES-len(pending)))
                if not data:break
                total+=len(data)
                if total>self.expected*FRAME_BYTES:raise VideoWindowUnavailable('Video output exceeds the known duration')
                pending.extend(data)
                if len(pending)==FRAME_BYTES:
                    if not self._put(('frame',bytes(pending))):return
                    pending.clear()
            if self.stopped.is_set():return
            if pending:raise VideoWindowUnavailable('Incomplete packed video frame')
            self._put(('end',None))
        except BaseException as error:self._put(('error',error))

    def _message(self,deadline):
        while True:
            self._check()
            if time.monotonic()>deadline:raise VideoWindowUnavailable('Video decoder made no progress')
            try:kind,value=self.messages.get(timeout=.05)
            except queue.Empty:continue
            if kind=='error':raise VideoWindowUnavailable('Video stream output unavailable') from value
            return kind,value

    def __iter__(self):return self

    def __next__(self):
        if self.complete:raise StopIteration
        if self.closed or not self.opened:raise VideoWindowUnavailable('Video stream is not open')
        try:
            if self.process is None:self._start()
            self._check();deadline=time.monotonic()+WINDOW_SECONDS
            if self.frames==self.expected:
                kind,_=self._message(deadline)
                if kind!='end':raise VideoWindowUnavailable('Unexpected extra video frame')
                try:code=self.process.wait(timeout=max(.001,deadline-time.monotonic()))
                except subprocess.TimeoutExpired as error:raise VideoWindowUnavailable('Video decoder did not exit') from error
                self._check()
                if code:raise VideoWindowUnavailable('Video decoder failed after output')
                self.close();self._check();self.complete=True
                raise StopIteration
            start=self.frames*1000;frames=[]
            for _ in range(min(MAX_FRAMES,self.expected-self.frames)):
                kind,value=self._message(deadline)
                if kind!='frame':raise VideoWindowUnavailable('Incomplete video coverage')
                frames.append(value)
            self._check();self.frames+=len(frames)
            return validate_video(VideoWindow(start,min(self.frames*1000,self.total_duration_ms),MAX_EDGE,MAX_EDGE,tuple(frames)))
        except StopIteration:raise
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.closed:return
        self.closed=True;self.stopped.set()
        try:
            if self.process is not None:
                if self.process.poll() is None:self.process.kill()
                self.process.wait(timeout=5)
        finally:
            if self.reader is not None and self.reader.ident is not None:
                self.reader.join(5)
                if self.reader.is_alive():raise VideoWindowUnavailable('Owned video reader did not stop')
            if self.process is not None and self.process.stdout is not None:self.process.stdout.close()

    def __exit__(self,*exc):self.close()
