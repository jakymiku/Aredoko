"""Owned, predecoded RGB clip input. No path, URL or native decoder here."""
from dataclasses import dataclass

MAX_FRAMES=16
MAX_EDGE=384
FRAME_INTERVAL_MS=1000
MAX_START_MS=86_400_000
MAX_RGB_BYTES=8*1024*1024


@dataclass(frozen=True)
class VideoWindow:
    start_ms:int
    end_ms:int
    width:int
    height:int
    frames:tuple[bytes,...]


def validate_video(value):
    if type(value) is not VideoWindow:raise ValueError('Expected a typed video window')
    if (type(value.start_ms) is not int or type(value.end_ms) is not int
            or not 0<=value.start_ms<value.end_ms<=MAX_START_MS):raise ValueError('Invalid video times')
    if (type(value.width) is not int or type(value.height) is not int
            or not 1<=value.width<=MAX_EDGE or not 1<=value.height<=MAX_EDGE):raise ValueError('Invalid video dimensions')
    if type(value.frames) is not tuple or not 1<=len(value.frames)<=MAX_FRAMES:raise ValueError('Invalid video frame count')
    duration=value.end_ms-value.start_ms
    if (duration+FRAME_INTERVAL_MS-1)//FRAME_INTERVAL_MS!=len(value.frames):raise ValueError('Video requires one frame per second')
    size=value.width*value.height*3
    if size*len(value.frames)>MAX_RGB_BYTES:raise ValueError('Video RGB limit')
    if any(type(frame) is not bytes or len(frame)!=size for frame in value.frames):raise ValueError('Invalid packed RGB frame')
    return value
