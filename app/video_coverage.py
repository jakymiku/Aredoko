"""Known-duration coverage for native-video windows from a validated handle.

Probes the container duration from the same seekable handle the interval
decoder reads, plans contiguous windows of at most MAX_FRAMES seconds, and
yields each decoded window one at a time so callers can encode or spool a
window before advancing; this layer never holds more than one window of
RGB. Duration is never inferred from decoded output, a short decode, or
caller guesswork: no usable duration fails, and a failed window raises
mid-iteration so the caller can discard anything spooled. Does not load
models, write indexes, or open a source path/URL.
"""
import json
import math
import time

from video_input import MAX_FRAMES,MAX_START_MS
from video_previews import _executable,_run,FORMATS,MAX_PROBE_BYTES,MAX_VIDEO_PIXELS,VIDEO_TIMEOUT,VideoPreviewUnavailable,MediaDecodeCancelled
from video_window_decode import read_video_window


class VideoCoverageUnavailable(ValueError):pass


def _duration_ms(raw):
    """Container duration in ms, or None when the value is unusable."""
    try:seconds=float(raw)
    except (TypeError,ValueError):return None
    if not math.isfinite(seconds) or seconds<=0:return None
    total_ms=int(round(seconds*1000))
    return total_ms if 1<=total_ms<=MAX_START_MS else None


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
        candidates=[streams[0].get('duration'),(document.get('format') or {}).get('duration')]
    except (ValueError,KeyError,TypeError,AttributeError) as error:
        raise VideoCoverageUnavailable('Video duration unavailable') from error
    # A present but unusable stream value ("N/A", 0, out of range) must not
    # shadow a usable format duration; only no usable value at all fails.
    for raw in candidates:
        total_ms=_duration_ms(raw)
        if total_ms is not None:return total_ms
    raise VideoCoverageUnavailable('Video duration unavailable')


def plan_video_coverage(total_duration_ms):
    if type(total_duration_ms) is not int or not 1<=total_duration_ms<=MAX_START_MS:
        raise ValueError('Invalid known video duration')
    step=MAX_FRAMES*1000
    return tuple((start,min(step,total_duration_ms-start)) for start in range(0,total_duration_ms,step))


def iter_video_coverage(source,*,cancel=None,guard=None):
    total_duration_ms=probe_video_duration_ms(source,cancel=cancel,guard=guard)
    for start,duration in plan_video_coverage(total_duration_ms):
        yield read_video_window(source,start,duration,total_duration_ms=total_duration_ms,cancel=cancel,guard=guard)
