"""Bounded native-video clip pixels from a caller-validated seekable handle.

One FFmpeg invocation per known interval. Does not infer duration/EOF, choose
the next interval, load models, write indexes, or open a source path/URL.
"""
import time

from video_input import VideoWindow,validate_video,MAX_FRAMES,MAX_EDGE,MAX_START_MS
from video_previews import _executable,_run,FORMATS,MAX_VIDEO_PIXELS,VideoPreviewUnavailable,MediaDecodeCancelled


class VideoWindowUnavailable(ValueError):pass


def validate_interval(start_ms,duration_ms,total_duration_ms):
    if (type(start_ms) is not int or type(duration_ms) is not int or not 0<=start_ms<MAX_START_MS
            or not 1<=duration_ms<=MAX_FRAMES*1000 or start_ms+duration_ms>MAX_START_MS):
        raise ValueError('Invalid native-video interval')
    if type(total_duration_ms) is not int or not start_ms+duration_ms<=total_duration_ms<=MAX_START_MS:
        raise ValueError('Interval exceeds known video duration')


def read_video_window(source,start_ms,duration_ms,*,total_duration_ms,cancel=None,guard=None):
    validate_interval(start_ms,duration_ms,total_duration_ms)
    if guard is not None and not callable(guard):raise ValueError('Invalid source guard')
    if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Video decode cancelled')
    if guard is not None:guard()
    count=(duration_ms+999)//1000;frame_bytes=MAX_EDGE*MAX_EDGE*3
    display='iw*if(gt(sar,0),sar,1)';factor=f'min({MAX_EDGE}/({display}),{MAX_EDGE}/ih)'
    fit=f"scale=w='max(1,trunc(({display})*{factor}))':h='max(1,trunc(ih*{factor}))',setsar=1"
    # fps rounds the final fractional second away on some builds. Only at the
    # authoritative known tail, hold the final decoded frame long enough to
    # sample that second; never infer successful EOF from a short decode.
    tail='tpad=stop_mode=clone:stop_duration=1,' if start_ms+duration_ms==total_duration_ms else ''
    filtering=f'{tail}fps=fps=1:start_time=0:round=up,{fit},pad={MAX_EDGE}:{MAX_EDGE}:(ow-iw)/2:(oh-ih)/2:color=black'
    try:
        command=[_executable('ffmpeg'),'-nostdin','-v','error','-max_alloc',str(64*1024*1024),
                 '-protocol_whitelist','fd,pipe','-format_whitelist',FORMATS,
                 '-probesize','1048576','-analyzeduration','1000000','-max_streams','16','-max_probe_packets','128',
                 '-threads','1','-max_pixels',str(MAX_VIDEO_PIXELS),'-ss',f'{start_ms/1000:.3f}',
                 '-t',f'{duration_ms/1000:.3f}','-i','fd:',
                 '-map','0:V:0','-an','-sn','-dn','-vf',filtering,
                 '-frames:v',str(count),'-threads','1','-c:v','rawvideo','-pix_fmt','rgb24','-f','rawvideo','pipe:1']
        data=_run(command,source,count*frame_bytes,time.monotonic()+20,cancel=cancel)
    except (VideoPreviewUnavailable,OSError) as error:
        raise VideoWindowUnavailable('Video interval could not be decoded within limits') from error
    if cancel is not None and cancel.is_set():raise MediaDecodeCancelled('Video decode cancelled')
    if guard is not None:guard()
    # The caller must plan the real tail from known media duration. A short
    # decode is not proof of successful whole-file EOF or permission to publish.
    if len(data)!=count*frame_bytes:raise VideoWindowUnavailable('Incomplete native-video interval')
    return validate_video(VideoWindow(start_ms,start_ms+duration_ms,MAX_EDGE,MAX_EDGE,
                                     tuple(data[i:i+frame_bytes] for i in range(0,len(data),frame_bytes))))
