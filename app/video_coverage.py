"""Known-duration coverage for native-video windows from a validated handle.

Probes the container duration from the same seekable handle the interval
decoder reads, plans contiguous windows of at most MAX_FRAMES seconds, and
decodes every window in order. Duration is never inferred from decoded
output, a short decode, or caller guesswork: an unknown or out-of-range
duration fails, and any failed window discards the whole coverage. Does
not load models, write indexes, or open a source path/URL.
"""
import json
import math
import time

from video_input import MAX_FRAMES,MAX_START_MS
from video_previews import _executable,_run,FORMATS,MAX_PROBE_BYTES,MAX_VIDEO_PIXELS,VIDEO_TIMEOUT,VideoPreviewUnavailable,MediaDecodeCancelled
from video_window_decode import read_video_window


class VideoCoverageUnavailable(ValueError):pass


def probe_video_duration_ms(source,*,cancel=None,guard=None):
    if guard is not None and not callable(guard):raise ValueError('Invalid source guard')
    if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Video decode cancelled')
    if guard is not None:guard()
    try:
        command=[_executable('ffprobe'),'-v','error','-max_alloc',str(64*1024*1024),
                 '-protocol_whitelist','fd,pipe','-format_whitelist',FORMATS,
                 '-probesize','1048576','-analyzeduration','1000000','-max_streams','16','-max_probe_packets','128',
                 '-threads','1','-max_pixels',str(MAX_VIDEO_PIXELS),
                 '-select_streams','V:0','-show_entries','stream=duration:format=duration','-of','json','-i','fd:']
        data=_run(command,source,MAX_PROBE_BYTES,time.monotonic()+VIDEO_TIMEOUT,cancel=cancel)
    except (VideoPreviewUnavailable,OSError) as error:
        raise VideoCoverageUnavailable('Video duration could not be probed within limits') from error
    if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Video decode cancelled')
    if guard is not None:guard()
    try:
        document=json.loads(data)
        streams=document['streams']
        if not isinstance(streams,list) or len(streams)!=1:raise ValueError('Video stream unavailable')
        raw=streams[0].get('duration')
        if raw is None:raw=(document.get('format') or {}).get('duration')
        seconds=float(raw)
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        raise VideoCoverageUnavailable('Video duration unavailable') from error
    if not math.isfinite(seconds) or seconds<=0:raise VideoCoverageUnavailable('Video duration unavailable')
    total_ms=int(round(seconds*1000))
    if not 1<=total_ms<=MAX_START_MS:raise VideoCoverageUnavailable('Video duration out of range')
    return total_ms


def plan_video_coverage(total_duration_ms):
    if type(total_duration_ms) is not int or not 1<=total_duration_ms<=MAX_START_MS:
        raise ValueError('Invalid known video duration')
    step=MAX_FRAMES*1000
    return tuple((start,min(step,total_duration_ms-start)) for start in range(0,total_duration_ms,step))


def read_video_coverage(source,*,cancel=None,guard=None):
    total_duration_ms=probe_video_duration_ms(source,cancel=cancel,guard=guard)
    return tuple(read_video_window(source,start,duration,total_duration_ms=total_duration_ms,cancel=cancel,guard=guard)
                 for start,duration in plan_video_coverage(total_duration_ms))
