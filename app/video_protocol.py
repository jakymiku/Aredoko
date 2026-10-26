"""Bounded private video wire. Carries RGB pixels, never file locations."""
import base64
import binascii

from video_input import VideoWindow,validate_video,MAX_FRAMES,MAX_EDGE,MAX_RGB_BYTES


def video_request(value):
    validate_video(value)
    return {'operation':'video','start_ms':value.start_ms,'end_ms':value.end_ms,
            'width':value.width,'height':value.height,
            'frames':[base64.b64encode(frame).decode('ascii') for frame in value.frames]}


def parse_video_request(message):
    if type(message) is not dict or set(message)!={'operation','start_ms','end_ms','width','height','frames'} or message['operation']!='video':
        raise ValueError('Invalid video request')
    width,height=message['width'],message['height'];frames=message['frames']
    if type(width) is not int or type(height) is not int or not 1<=width<=MAX_EDGE or not 1<=height<=MAX_EDGE:
        raise ValueError('Invalid video dimensions')
    if type(frames) is not list or not 1<=len(frames)<=MAX_FRAMES:raise ValueError('Invalid video frames')
    size=width*height*3;encoded_size=4*((size+2)//3)
    if size*len(frames)>MAX_RGB_BYTES:raise ValueError('Video RGB limit')
    # Validate types/times/lengths before base64 allocation.
    if (type(message['start_ms']) is not int or type(message['end_ms']) is not int
            or not 0<=message['start_ms']<message['end_ms']<=86_400_000
            or (message['end_ms']-message['start_ms']+999)//1000!=len(frames)):
        raise ValueError('Invalid video times')
    if any(type(frame) is not str or len(frame)!=encoded_size for frame in frames):raise ValueError('Invalid video wire size')
    try:decoded=tuple(base64.b64decode(frame,validate=True) for frame in frames)
    except (binascii.Error,ValueError):raise ValueError('Invalid video pixels') from None
    return validate_video(VideoWindow(message['start_ms'],message['end_ms'],width,height,decoded))
