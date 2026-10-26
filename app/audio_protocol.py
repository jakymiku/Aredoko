"""Bounded PCM messages for private audio workers; no file paths or handles."""
import base64
from audio_input import PCMWindow,validate_pcm,MAX_WINDOW_MS,SAMPLE_RATE

MAX_PCM_BYTES=MAX_WINDOW_MS*SAMPLE_RATE//1000*4
MAX_BASE64_CHARS=((MAX_PCM_BYTES+2)//3)*4
FIELDS=frozenset(('operation','audio','start_ms','duration_ms','sample_rate','channels','sample_format'))


def audio_request(window):
    validate_pcm(window)
    return {'operation':'audio','audio':base64.b64encode(window.data).decode('ascii'),
            'start_ms':window.start_ms,'duration_ms':window.requested_duration_ms,
            'sample_rate':window.sample_rate,'channels':window.channels,'sample_format':window.sample_format}


def parse_audio_request(request):
    if type(request) is not dict or set(request)!=FIELDS or request['operation']!='audio':raise ValueError('Invalid audio request fields')
    encoded=request['audio']
    if type(encoded) is not str or not 1<=len(encoded)<=MAX_BASE64_CHARS or not encoded.isascii():raise ValueError('Audio request exceeds source limit')
    data=base64.b64decode(encoded,validate=True)
    return validate_pcm(PCMWindow(request['start_ms'],request['duration_ms'],data,
                                 request['sample_rate'],request['channels'],request['sample_format']))
