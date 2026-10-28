"""Generated video PCM native wiring; CPU vectors, no playback or real model."""
import json
import subprocess
from ui_audio_content_audit import create_feature as create_audio_feature
from native_ui_tools import nodes
from video_previews import _executable


def create_feature(catalog):
    feature,release,reached=create_audio_feature(catalog)
    encode=feature.encoder.encode
    def supplied(operation,value):
        encode(operation,value)
        return [1,0,0] if operation=='query' or value.start_ms>=30000 else [0,1,0]
    feature.encoder.encode=supplied
    feature.encoder.calls=0
    original=feature.encoder.encode
    def counted(*args):
        feature.encoder.calls+=1
        return original(*args)
    feature.encoder.encode=counted
    return feature,release,reached


def create_media(media):
    for number,duration,audio in ((1,3.2,True),(2,31.25,True),(3,3.2,False)):
        args=[_executable('ffmpeg'),'-nostdin','-v','error','-f','lavfi','-i',f'color=c=blue:s=160x90:r=4:d={duration}']
        if audio:args+=['-f','lavfi','-i',f'sine=frequency=440:sample_rate=16000:duration={duration}','-c:a','pcm_s16le']
        else:args+=['-an']
        subprocess.run([*args,'-c:v','mpeg4','-threads','1',str(media/f'generated-{number:03}.mkv')],check=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def select_mode(ui,label):
    ui('invoke','CmbSearchMode','--action','expand')
    choices={node['selector'] for node in nodes(json.loads(ui('inspect','--depth','18','--json')))
        if node.get('type') in ('ListItem','ComboBoxItem') and node.get('name')==label and node.get('selector') and not node.get('isOffscreen',True)}
    if len(choices)!=1:raise RuntimeError('Expected one exact visible search method')
    ui('invoke',choices.pop(),'--action','select')
    combos={node['selector'] for node in nodes(json.loads(ui('inspect','--depth','18','--json')))
        if node.get('type')=='ComboBox' and node.get('automationId')=='CmbSearchMode' and node.get('selector') and not node.get('isOffscreen',True)}
    if len(combos)!=1:raise RuntimeError('Expected one visible search ComboBox')
    ui('invoke',combos.pop(),'--action','collapse')


def audit(ui,tree,shot,report,check,catalog,feature,release,reached,*,input_guard):
    report['authorization']='Explicit per-run approval: generated video PCM/CPU vectors/dedicated DB; no playback, model, GPU or normal data'
    rows={row['title']:row for row in catalog.search()['items']}
    short=rows['generated-001.mkv']['id'];long=rows['generated-002.mkv']['id'];silent=rows['generated-003.mkv']['id']
    ui('invoke','BtnSettings');ui('invoke','BtnAIIndex');ui('wait-for','VideoAudioContentOptions','-t','10000')
    ui('scroll-into-view','VideoAudioContentOptions');ui('invoke','VideoAudioContentOptions','--action','expand')
    ui('wait-for','StartVideoAudioContent','-p','IsEnabled','--value','True','-t','10000')
    check('opening video audio preparation is lazy',feature.owner is None)
    ui('invoke','StartVideoAudioContent');check('generated video PCM reached encode gate',reached.wait(8))
    ui('wait-for','VideoAudioContentStatus','--value','未保存','--contains','-t','10000');shot('video-audio-preparing')
    ui('invoke','CancelVideoAudioContent');ui('wait-for','VideoAudioContentStatus','--value','中断しました','--contains','-t','10000')
    check('cancel did not publish partial PCM',feature.status()['processed']==0)
    release.set();ui('wait-for','StartVideoAudioContent','-p','IsEnabled','--value','True','-t','10000');ui('invoke','StartVideoAudioContent')
    ui('wait-for','VideoAudioContentStatus','--value','準備完了','--contains','-t','20000')
    check('two videos indexed and no-track video skipped',feature.status()['indexed']==2 and feature.status()['unavailable']==1)
    shot('video-audio-completed');ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','10000')
    select_mode(ui,'動画内の音声（AI）');ui('set-value','TxtQuery','生成した動画の音');ui('invoke','BtnSearch')
    ui('wait-for','AIEvidence'+str(long),'--value','動画内の音声一致（0:30–0:31.25）','--contains','-t','15000')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    check('video audio method locks the video kind',tree()['CmbKind'].get('isEnabled') is False)
    ui('invoke','Item'+str(long),'--action','select');ui('invoke','BtnDetails')
    ui('wait-for','BtnOpenVideo','-p','IsEnabled','--value','True','-t','10000');shot('video-audio-query-detail')
    ui('invoke','BtnCloseDetails')
    feature.encoder.available=False;feature.encoder.resident=False;calls=feature.encoder.calls
    if not input_guard():raise RuntimeError('Owned video audio test is not foreground; no pointer input sent')
    ui('click','Item'+str(long),'--right');ui('wait-for','FindSimilarVideoAudio'+str(long),'-t','5000')
    check('video visual and legacy similarity entries retained','FindSimilarVideoContent'+str(long) in tree() and 'FindSimilar'+str(long) in tree())
    ui('invoke','FindSimilarVideoAudio'+str(long))
    expected='起点 0:00–0:30 → 候補 0:00–0:03.2'
    ui('wait-for','AIEvidence'+str(short),'--value',expected,'--contains','-t','15000')
    check('origin and trackless video are absent','Item'+str(long) not in tree() and 'Item'+str(silent) not in tree())
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000');shot('video-audio-similar')
    ui('invoke','NavFolders');ui('wait-for','FolderList','-t','10000');ui('invoke','BtnNavigationBack')
    ui('wait-for','AIEvidence'+str(short),'--value',expected,'--contains','-t','15000')
    check('screen history restores cached video audio with no inference',calls==feature.encoder.calls and not feature.encoder.resident)
    shot('video-audio-history')
    report['unverified']=['actual playback/seek','real model quality','multiple tracks','physical DPI/high contrast']
