"""Actual key routing on generated silent audio and the image settings menu."""
import json
import re
from native_ui_tools import nodes
import time


def audit(ui,tree,open_viewer,close_viewer,foreground,shot,wait,report,current_viewer):
    observations=[]
    open_viewer('silent-controls.wav','BtnOpenAudio','Aredoko — 音声再生')
    viewer=current_viewer()
    def key(value,target=None):
        report['physical_keyboard_attempted']=True
        foreground(viewer)
        if target:ui(viewer,'focus',target)
        ui(viewer,'send-keys',value,'--via','send-input')
    def number(identifier):
        if identifier!='VideoVolume':raise ValueError('Explicit player volume only')
        # This CLI's get-value falls back to a Slider's Name rather than its
        # RangeValue. Observe the user's displayed value, not a guessed schema.
        values=[]
        for item in nodes(json.loads(ui(viewer,'inspect','--depth','18','--json'))):
            match=re.fullmatch(r'(?:音量 |消音中（)([0-9]+)%(?:）)?',item.get('name',''))
            if match:values.append(int(match[1]))
        if len(values)!=1:raise RuntimeError('One visible native volume label required')
        report.setdefault('keyboard_values',[]).append(values[0]);return values[0]
    if report['control_state_only']:
        ui(viewer,'wait-for','VideoPlayPause','-p','IsEnabled','--value','True','-t','10000')
        if tree(viewer)['VideoPlayPause']['name']=='一時停止':ui(viewer,'invoke','VideoPlayPause')
        current=tree(viewer)
        observations.append(('native window title identifies the audio file',report['viewer_windows'][-1]['title'].endswith('silent-controls.wav')))
        observations.append(('player has one native title bar and a docked position label','VideoHeader' not in current and 'VideoClose' not in current and 'VideoPosition' in current and current['VideoPosition']['y'] >= current['VideoToolbar']['y']))
        before=number('VideoVolume');ui(viewer,'set-value','VideoVolume','75');after=number('VideoVolume')
        observations.append(('UIA slider updates the displayed volume',before==80 and after==75))
        ui(viewer,'invoke','VideoMute');state=tree(viewer)
        observations.append(('UIA mute remains independent of paused playback',state['VideoMute']['name']=='消音解除' and state['VideoPlayPause']['name']=='再生'))
        report['player_control_state']={'volume_before':before,'volume_after':after,'mute':state['VideoMute']['name'],'play':state['VideoPlayPause']['name']}
        shot('uia-player-controls');close_viewer()
        return observations
    key('f10');ui(viewer,'wait-for','VideoPlayPause','-p','IsEnabled','--value','True','-t','10000')
    if tree(viewer)['VideoPlayPause']['name']=='一時停止':ui(viewer,'invoke','VideoPlayPause')
    ui(viewer,'wait-for','VideoPlayPause','--value','再生','-t','5000')
    before=number('VideoVolume');key('left','VideoVolume');time.sleep(.2);after=number('VideoVolume')
    observations.append(('volume arrow changes native slider by five points',after==before-5))
    report['volume_key']={'before':before,'after':after,'expected':before-5};shot('keyboard-volume')
    # Reset only this generated player's value before an independent button case.
    ui(viewer,'set-value','VideoVolume','80')
    if tree(viewer)['VideoPlayPause']['name']=='一時停止':ui(viewer,'invoke','VideoPlayPause')
    key('space','VideoMute');time.sleep(.2);state=tree(viewer)
    report['mute_key']={'mute_name':state['VideoMute']['name'],'play_name':state['VideoPlayPause']['name']}
    observations.append(('Space activates focused mute without starting playback',state['VideoMute']['name']=='消音解除' and state['VideoPlayPause']['name']=='再生'))
    shot('keyboard-mute');close_viewer()
    open_viewer('a-center.png','BtnOpenImage','Aredoko — 画像ビューア')
    viewer=current_viewer()
    key('f10');ui(viewer,'invoke','ImageSettings');ui(viewer,'wait-for','ViewerAlwaysControls','-t','5000')
    key('right','ViewerAlwaysControls');time.sleep(.3);state=tree(viewer)
    report['image_menu_key']={'image':state.get('ViewerImage',{}).get('name'),'menu_still_open':not state.get('ViewerAlwaysControls',{}).get('isOffscreen',True)}
    observations.append(('image menu arrow does not navigate the underlying image',state.get('ViewerImage',{}).get('name')=='a-center.pngの画像'))
    shot('keyboard-image-menu');key('esc');close_viewer()
    report['keyboard_control_pass']=all(value for _,value in observations)
    report['keyboard_control_observations']=[{'name':name,'pass':value} for name,value in observations]
    return observations


def audit_notices(ui,tree,open_viewer,close_viewer,shot,report,current_viewer):
    """A real 503/retry on generated audio, no physical input or playback."""
    observations=[]
    open_viewer('silent-controls.wav','BtnOpenAudio','Aredoko — 音声再生')
    viewer=current_viewer()
    ui(viewer,'wait-for','VideoRetry','-p','IsEnabled','--value','True','-t','10000')
    failed=tree(viewer)
    observations.append(('temporary failure has visible retry guidance',not failed['VideoStatus']['isOffscreen'] and '少し待って再試行' in failed['VideoStatus']['name']))
    shot('player-temporary-failure')
    ui(viewer,'invoke','VideoRetry')
    ui(viewer,'wait-for','VideoPlayPause','-p','IsEnabled','--value','True','-t','10000')
    ready=tree(viewer)
    geometry=lambda state:[state['VideoToolbar'][key] for key in ('x','y','width','height')]
    report['notice_toolbar_geometry']={'failure':geometry(failed),'ready':geometry(ready)}
    observations.append(('retry keeps toolbar position and height',all(abs(a-b)<=1 for a,b in zip(geometry(failed),geometry(ready)))))
    observations.append(('successful retry clears notice and remains paused',('VideoStatus' not in ready or ready['VideoStatus']['isOffscreen']) and ready['VideoPlayPause']['name']=='再生'))
    shot('player-after-retry');close_viewer()
    return observations


def audit_autohide(ui,tree,open_viewer,close_viewer,shot,report,current_viewer):
    """Exercise real dispatcher timer and preference without mouse/key input."""
    open_viewer('silent-controls.wav','BtnOpenAudio','Aredoko — 音声再生')
    viewer=current_viewer()
    ui(viewer,'wait-for','VideoRetry','-p','IsEnabled','--value','True','-t','10000')
    time.sleep(1.3)
    failure=tree(viewer)
    observations=[('failure keeps retry controls available beyond hide delay',not failure['VideoToolbar']['isOffscreen'])]
    shot('failure-controls-held')
    ui(viewer,'invoke','VideoRetry')
    ui(viewer,'wait-for','VideoPlayPause','-p','IsEnabled','--value','True','-t','10000')
    expected=report['autohide_mode']=='automatic'
    if expected:ui(viewer,'wait-for','VideoToolbar','--gone','-t','5000')
    else:time.sleep(1.3)
    current=tree(viewer)
    offscreen='VideoToolbar' not in current or current['VideoToolbar']['isOffscreen']
    observations.append(('automatic hide or always-visible preference is respected',offscreen==expected))
    report['player_auto_hide']={'expected_hidden':expected,'observed_hidden':offscreen,'physical_input':False}
    shot('automatic-hidden' if expected else 'always-visible');close_viewer()
    return observations
