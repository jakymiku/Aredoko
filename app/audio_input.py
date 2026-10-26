"""Model-independent, bounded PCM from a caller-validated open media handle.

No recognition or embeddings. No source pathname, output file, device, or
network protocol is passed to FFmpeg. Silence remains ordinary PCM data.
"""
from dataclasses import dataclass
import math
import struct
import time
from video_previews import _executable,_run,MediaDecodeCancelled,VideoPreviewUnavailable

SAMPLE_RATE=16000
CHANNELS=1
MAX_WINDOW_MS=30000
MAX_START_MS=86400000
MAX_AUDIO_BYTES=512*1024*1024
FORMATS='wav,mp3,flac,ogg,mov,aac,asf'


class AudioInputUnavailable(ValueError):pass


def validate_window(start_ms,duration_ms):
    if (type(start_ms) is not int or not 0<=start_ms<=MAX_START_MS or
        type(duration_ms) is not int or not 1<=duration_ms<=MAX_WINDOW_MS or start_ms+duration_ms>MAX_START_MS):
        raise AudioInputUnavailable('Invalid bounded audio interval')


@dataclass(frozen=True)
class PCMWindow:
    start_ms:int
    requested_duration_ms:int
    data:bytes
    sample_rate:int=SAMPLE_RATE
    channels:int=CHANNELS
    sample_format:str='f32le'

    @property
    def frame_count(self):return len(self.data)//4


def read_window(source,start_ms,duration_ms,cancel=None):
    validate_window(start_ms,duration_ms)
    if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Media decode cancelled')
    limit=duration_ms*SAMPLE_RATE//1000*4
    try:
        arguments=[_executable('ffmpeg'),'-nostdin','-v','error','-max_alloc',str(64*1024*1024),
                   '-protocol_whitelist','fd,pipe','-format_whitelist',FORMATS,
                   '-probesize','1048576','-analyzeduration','1000000','-max_streams','16',
                   '-max_probe_packets','128','-threads','1','-ss',f'{start_ms/1000:.3f}','-i','fd:',
                   '-t',f'{duration_ms/1000:.3f}','-map','0:a:0','-vn','-sn','-dn','-ac','1',
                   '-ar',str(SAMPLE_RATE),'-threads','1','-c:a','pcm_f32le','-f','f32le','pipe:1']
        data=_run(arguments,source,limit,time.monotonic()+10,cancel=cancel)
    except (VideoPreviewUnavailable,OSError) as error:raise AudioInputUnavailable('Audio input unavailable or exceeds limits') from error
    if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Media decode cancelled')
    if not data or len(data)%4 or len(data)>limit or any(not math.isfinite(value[0]) for value in struct.iter_unpack('<f',data)):
        raise AudioInputUnavailable('Invalid or empty PCM output')
    return PCMWindow(start_ms,duration_ms,data)
