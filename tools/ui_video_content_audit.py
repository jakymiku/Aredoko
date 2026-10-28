"""Native video preparation/search wiring using generated silent clips only.

The real guarded decoder and owned jobs run on CPU. Supplied three-dimensional
vectors test UI/time contracts, not model quality. Never starts media playback.
"""
from dataclasses import replace
import subprocess
import threading
import time
import types

from ai_profiles import DEFAULT_PROFILE
from inference_ownership import InferenceOwnership
from video_direct_feature import VideoDirectFeature
from video_previews import _executable


def create_media(media):
    for name,duration,color in (('generated-001.mp4',3.3,'red'),('generated-002.mp4',17.5,'blue')):
        subprocess.run([_executable('ffmpeg'),'-nostdin','-v','error','-f','lavfi',
            '-i',f'color=c={color}:s=160x90:r=10:d={duration}','-an','-c:v','mpeg4',
            '-threads','1','-movflags','+faststart',str(media/name)],check=True,timeout=20,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def create_feature(catalog):
    release=threading.Event();reached=threading.Event();feature=None
    class Encoder:
        available=True;resident=False
        def __init__(self,profile):self.profile=profile;self.closed=False;self.calls=0
        def encode(self,operation,value):
            if self.closed:raise RuntimeError('Generated encoder closed')
            self.resident=True;self.calls+=1
            if operation=='video' and not release.is_set():
                reached.set();deadline=time.monotonic()+30
                while not release.wait(.05):
                    if feature.owner.cancelled.is_set():break
                    if time.monotonic()>deadline:raise TimeoutError('Generated video gate expired')
            return [1,0,0] if operation=='query' or value.start_ms>=16000 else [0,1,0]
        def release(self):self.resident=False;return {'released':True,'resident':False}
        def close(self):self.closed=True;self.resident=False
    profile=replace(DEFAULT_PROFILE,dimension=3);vision=Encoder(profile)
    group=InferenceOwnership();group.for_encoder(vision)
    image=types.SimpleNamespace(profile=profile,encoder=vision,inference_group=group)
    feature=VideoDirectFeature(catalog,image,encoder_factory=Encoder)
    return feature,release,reached


def audit(ui,tree,shot,report,check,catalog,feature,release,reached,*,input_guard,history_only=False):
    report['authorization']='Per-run human approval required: generated silent MP4s, dedicated DB, supplied CPU vectors; no playback/models/GPU'
    if history_only:return similar_history(ui,tree,shot,check,catalog,feature,input_guard=input_guard)
    ui('invoke','BtnSettings');ui('wait-for','BtnAIIndex','-t','10000');ui('invoke','BtnAIIndex')
    ui('wait-for','VideoContentOptions','-t','10000');ui('scroll-into-view','VideoContentOptions')
    ui('invoke','VideoContentOptions','--action','expand')
    ui('wait-for','StartVideoContent','-p','IsEnabled','--value','True','-t','10000')
    ui('wait-for','StartVideoContent','-p','IsOffscreen','--value','False','-t','10000');shot('video-preparation')
    check('opening video status does not initialize the model or index',feature.owner is None)
    ui('invoke','StartVideoContent');check('generated video reached first encode gate',reached.wait(8))
    ui('wait-for','VideoContentStatus','--value','動画を準備しています','--contains','-t','10000')
    ui('invoke','CancelVideoContent');ui('wait-for','VideoContentStatus','--value','中断しました','--contains','-t','10000')
    with feature.owner.index.store.connect() as db:
        check('cancel preserves absence of incomplete video',db.execute('SELECT count(*) FROM ai_video_direct_sources').fetchone()[0]==0)
    release.set();ui('wait-for','StartVideoContent','-p','IsEnabled','--value','True','-t','10000');ui('invoke','StartVideoContent')
    ui('wait-for','VideoContentStatus','--value','準備完了','--contains','-t','20000');shot('video-completed')
    check('both generated video items are ready',feature.status()['indexed']==2)
    ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','10000')
    from native_ui_tools import select_combo_item
    select_combo_item(ui,'CmbSearchMode','ModeVideoContent')
    ui('set-value','TxtQuery','生成した動画');ui('invoke','BtnSearch')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','15000')
    ui('wait-for','AIEvidence2','--value','動画の内容一致（0:16–0:17.5）','--contains','-t','15000');shot('video-query')
    check('video mode locks the video kind',tree()['CmbKind'].get('isEnabled') is False)
    if not input_guard():raise RuntimeError('Owned video test lost foreground; no input sent')
    ui('click','ItemTitle2');ui('wait-for','BtnDetails','-p','IsEnabled','--value','True','-t','10000');ui('invoke','BtnDetails')
    ui('wait-for','BtnOpenVideo','-p','IsEnabled','--value','True','-t','10000');shot('video-detail')
    ui('invoke','BtnCloseDetails')
    similar_history(ui,tree,shot,check,catalog,feature,input_guard=input_guard)


def similar_history(ui,tree,shot,check,catalog,feature,*,input_guard):
    feature.encoder.available=False;feature.encoder.resident=False;before=feature.encoder.calls
    if not input_guard():raise RuntimeError('Owned video test lost foreground; no input sent')
    ui('click','Item2','--right');ui('wait-for','FindSimilarVideoContent2','-t','5000')
    check('legacy representative-frame menu is retained','FindSimilar2' in tree())
    ui('invoke','FindSimilarVideoContent2')
    ui('wait-for','AIEvidence1','--value','起点 0:00–0:16 → 候補 0:00–0:03.3','--contains','-t','15000')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000');shot('video-similar')
    check('video origin is excluded','Item2' not in tree())
    check('cached video similarity does not load or infer',feature.encoder.calls==before and not feature.encoder.resident)
    # A normal text query needs the deliberately unavailable model. Use a
    # non-inference destination to isolate cached navigation restoration.
    ui('invoke','NavFolders');ui('wait-for','FolderList','-t','10000');shot('video-folder-hub')
    ui('invoke','BtnNavigationBack')
    ui('wait-for','AIEvidence1','--value','起点 0:00–0:16 → 候補 0:00–0:03.3','--contains','-t','15000')
    check('screen history restores direct video similarity','Item2' not in tree())
    check('generated tags unchanged',all(not row['tags'] for row in catalog.search()['items']))
