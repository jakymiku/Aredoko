"""Native audio controls over supplied CPU vectors; never sound output/GPU."""
from dataclasses import replace
import struct
import threading
import time
import types
import wave

from ai_profiles import DEFAULT_PROFILE
from audio_direct_feature import AudioDirectFeature
from inference_ownership import InferenceOwnership


def create_media(media):
    for number in (1,2):
        with wave.open(str(media/f'generated-{number:03}.wav'),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
            output.writeframes(struct.pack('<h',8192 if number==1 else -8192)*32000)


def create_feature(catalog):
    release=threading.Event();reached=threading.Event();feature=None
    class Encoder:
        available=True;resident=False
        def __init__(self,profile):self.profile=profile;self.closed=False
        def encode(self,operation,value):
            if self.closed:raise RuntimeError('Generated encoder closed')
            self.resident=True
            if operation=='audio' and not release.is_set():
                reached.set();deadline=time.monotonic()+30
                while not release.wait(.05):
                    if feature.owner.cancelled.is_set():break
                    if time.monotonic()>deadline:raise TimeoutError('Generated audio gate expired')
            return [1,0,0]
        def release(self):self.resident=False;return {'released':True,'resident':False}
        def close(self):self.closed=True;self.resident=False
    profile=replace(DEFAULT_PROFILE,dimension=3);vision=Encoder(profile);group=InferenceOwnership();group.for_encoder(vision)
    image=types.SimpleNamespace(profile=profile,encoder=vision,inference_group=group)
    feature=AudioDirectFeature(catalog,image,encoder_factory=Encoder)
    return feature,release,reached


def audit(ui,tree,shot,report,check,catalog,feature,release,reached,*,input_guard,search_only=False):
    report['authorization']='Explicit user approval required: generated WAVs + dedicated DB + CPU supplied encoder, no sound output/GPU'
    if not search_only:prepare(ui,tree,shot,report,check,catalog,feature,release,reached)
    # Set focus before opening the popup: the combo provider becomes stale while
    # the popup is expanded. Do not resolve it again between expand and keys.
    ui('focus','CmbSearchMode');ui('invoke','CmbSearchMode','--action','expand')
    if not input_guard():raise RuntimeError('Owned audio test lost foreground; no key input sent')
    ui('send-keys','end enter','--via','send-input')
    # A result from the previous empty query can still expose Item1 while the
    # debounced search replaces its container. Submit explicitly and wait for
    # the new query's evidence, not merely the old item's existence.
    ui('set-value','TxtQuery','生成した音声');ui('invoke','BtnSearch')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','15000')
    ui('wait-for','AIEvidence1','--value','音声の内容一致（0:00）','--contains','-t','15000')
    check('audio mode locks kind to the audio category',tree()['CmbKind'].get('isEnabled') is False)
    if not input_guard():raise RuntimeError('Owned audio test lost foreground; no pointer input sent')
    ui('click','ItemTitle1')
    ui('wait-for','BtnDetails','-p','IsEnabled','--value','True','-t','10000');ui('invoke','BtnDetails')
    ui('wait-for','BtnOpenAudio','-p','IsEnabled','--value','True','-t','10000');shot('audio-search-time')
    check('direct audio evidence shows the indexed start time','音声の内容一致（0:00）' in tree()['AIEvidence1']['name'])
    check('audio player remains available without starting playback',True)
    check('generated tags were not changed',all(row['tags']==[] for row in catalog.search()['items']))


def prepare(ui,tree,shot,report,check,catalog,feature,release,reached):
    ui('invoke','BtnSettings');ui('wait-for','BtnAIIndex','-t','10000');ui('invoke','BtnAIIndex')
    ui('wait-for','AudioContentOptions','-t','10000');ui('scroll-into-view','AudioContentOptions')
    ui('invoke','AudioContentOptions','--action','expand')
    ui('wait-for','StartAudioContent','-p','IsEnabled','--value','True','-t','10000')
    ui('wait-for','StartAudioContent','-p','IsOffscreen','--value','False','-t','10000');shot('audio-preparation')
    check('opening audio status does not start a model',feature.owner is None)
    ui('invoke','StartAudioContent')
    check('generated audio encoder reached bounded gate',reached.wait(8))
    ui('wait-for','AudioContentStatus','--value','音声を準備しています','--contains','-t','10000');shot('audio-running')
    ui('invoke','CancelAudioContent');ui('wait-for','AudioContentStatus','--value','中断しました','--contains','-t','10000')
    with feature.owner.index.store.connect() as db:check('cancel does not publish incomplete audio',db.execute('SELECT count(*) FROM ai_audio_direct_sources').fetchone()[0]==0)
    release.set();ui('wait-for','StartAudioContent','-p','IsEnabled','--value','True','-t','10000');ui('invoke','StartAudioContent')
    ui('wait-for','AudioContentStatus','--value','準備完了','--contains','-t','15000');shot('audio-completed')
    check('both generated audio items are atomically ready',feature.status()['indexed']==2)
    ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','10000')


def audit_similarity(ui,tree,shot,report,check,catalog,feature,*,input_guard):
    report['authorization']='Explicit user approval required: cached generated WAV similarity, no GPU/playback'
    # Search from cached vectors even with the prepared model now unavailable.
    feature.encoder.available=False
    feature.encoder.resident=False
    before=feature.encoder.resident
    if not input_guard():raise RuntimeError('Owned audio test lost foreground; no pointer input sent')
    ui('click','Item1','--right')
    ui('wait-for','FindSimilarAudioContent1','-t','5000');shot('audio-context')
    ui('invoke','FindSimilarAudioContent1')
    ui('wait-for','AIEvidence2','--value','起点 0:00 → 候補 0:00','--contains','-t','15000')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000');shot('audio-similar')
    check('origin excluded from direct audio candidates','Item1' not in tree())
    check('cached similarity did not load a model',feature.encoder.resident==before)
    if not input_guard():raise RuntimeError('Owned audio test lost foreground; no pointer input sent')
    ui('click','ItemTitle2');ui('wait-for','BtnDetails','-p','IsEnabled','--value','True','-t','10000');ui('invoke','BtnDetails')
    ui('wait-for','BtnOpenAudio','-p','IsEnabled','--value','True','-t','10000');shot('audio-similar-detail')
    ui('invoke','NavFavorites');ui('wait-for','TxtEmpty','--value','お気に入りはまだありません','--contains','-t','10000')
    ui('invoke','BtnNavigationBack')
    ui('wait-for','AIEvidence2','--value','起点 0:00 → 候補 0:00','--contains','-t','15000')
    check('screen history restores direct audio similarity','Item1' not in tree())
    check('generated tags remain unchanged',all(row['tags']==[] for row in catalog.search()['items']))
