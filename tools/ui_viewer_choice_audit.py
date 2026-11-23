"""U7: settings + safe fallback + internal activation, never a foreign app.

Only a generated fixture is removed after selection to guarantee shell launch
fails at the file-access guard, before Process.Start. No associations change.
"""
import ctypes
from ctypes import wintypes
import json
import time
from native_ui_tools import nodes


def audit(ui,cli,tree,shot,report,check,catalog,media,target,pid,main,*,input_guard,uia_only=False):
    report['authorization']=('Explicit approval required: dedicated viewer preference UIA-only persistence; no physical input, foreground, file deletion or external activation'
        if uia_only else 'Explicit per-run approval required: generated media/settings only; one generated fixture removed to test fallback; no external app/playback/GPU')
    preferences=target/'viewer-settings.json'
    def choose(external):
        ui('invoke','BtnSettings');ui('wait-for','SettingsDoubleClickViewer','-t','10000')
        if uia_only:
            ui('invoke','SettingsDoubleClickViewer','--action','expand')
            label='Windowsの既定アプリ' if external else 'Aredokoの内蔵ビューア（既定）'
            # A native item and its text share a name, and WinUI can expose the
            # same peer twice. Select one exact item slug from this live tree.
            choices={n['selector'] for n in nodes(json.loads(ui('inspect','--depth','18','--json')))
                if n.get('type') in ('ListItem','ComboBoxItem') and n.get('name')==label and n.get('selector') and not n.get('isOffscreen',True)}
            if len(choices)!=1:raise RuntimeError('Expected one visible viewer choice item')
            ui('invoke',choices.pop(),'--action','select')
            combos={n['selector'] for n in nodes(json.loads(ui('inspect','--depth','18','--json')))
                if n.get('type')=='ComboBox' and n.get('automationId')=='SettingsDoubleClickViewer' and n.get('selector') and not n.get('isOffscreen',True)}
            if len(combos)!=1:raise RuntimeError('Expected one visible viewer ComboBox peer')
            ui('invoke',combos.pop(),'--action','collapse')
        else:
            ui('focus','SettingsDoubleClickViewer');ui('invoke','SettingsDoubleClickViewer','--action','expand')
            if not input_guard():raise RuntimeError('Owned viewer settings lost foreground; no key sent')
            ui('send-keys','end enter' if external else 'home enter','--via','send-input')
        ui('invoke','SettingsSave');ui('wait-for','SettingsStatus','--value','保存しました','--contains','-t','10000')
        check('selected viewer preference saved: '+str(external),json.loads(preferences.read_text(encoding='utf-8'))['double_click_viewer']==('external' if external else 'internal'))
        shot('external-settings' if external else 'internal-settings')
        ui('invoke','CloseButton');ui('wait-for','SettingsDoubleClickViewer','--gone','-t','10000')
    choose(True)
    ui('invoke','BtnSettings');ui('wait-for','SettingsDoubleClickViewer','--value','Windowsの既定アプリ','-t','10000')
    check('reopened settings retains the external choice',True)
    ui('invoke','CloseButton');ui('wait-for','SettingsDoubleClickViewer','--gone','-t','10000')
    if uia_only:
        choose(False)
        ui('invoke','BtnSettings');ui('wait-for','SettingsDoubleClickViewer','--value','Aredokoの内蔵ビューア（既定）','-t','10000')
        check('reopened settings retains the internal choice',True)
        ui('invoke','CloseButton');ui('wait-for','SettingsDoubleClickViewer','--gone','-t','10000')
        report['physical_double_click_tested']=False;report['external_app_started']=False
        return None
    images=[row for row in catalog.search()['items'] if row['kind']=='image'];valid,removed=images
    ui('click','ItemTitle'+str(removed['id']));ui('wait-for','BtnDetails','-p','IsEnabled','--value','True','-t','10000')
    path=media/removed['title']
    if path.parent.resolve()!=media.resolve() or path.name not in ('image-0.png','image-1.png'):
        raise RuntimeError('Only the generated image fixture may be removed')
    path.unlink();report['intentionally_removed_generated_file']=path.name
    if not input_guard():raise RuntimeError('Owned viewer test lost foreground; no pointer input sent')
    ui('click','Preview'+str(removed['id']),'--double')
    ui('wait-for','ExternalViewerFallback','-t','10000');shot('external-fallback')
    check('failed external launch offers internal viewer',tree()['PrimaryButton']['name']=='内蔵ビューアで開く')
    ui('invoke','CloseButton');ui('wait-for','ExternalViewerFallback','--gone','-t','10000')
    choose(False)
    if not input_guard():raise RuntimeError('Owned viewer test lost foreground; no pointer input sent')
    ui('click','Preview'+str(valid['id']),'--double')
    child=None;deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        choices=[w for w in json.loads(cli('list-windows','-a',pid,'--json')) if str(w.get('hwnd'))!=main and '画像ビューア' in w.get('title','')]
        if len(choices)==1:child=str(choices[0]['hwnd']);break
        time.sleep(.15)
    check('internal double-click opens the owned image viewer',child is not None)
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    owner=wintypes.DWORD();user.GetWindowThreadProcessId(int(child),ctypes.byref(owner))
    if owner.value!=pid:raise RuntimeError('Viewer owner changed')
    cli('wait-for','ImageViewport','-w',child,'-t','10000')
    screen=target/'internal-viewer.png';cli('screenshot','--output',screen,'-w',child);report['screenshots'].append(str(screen))
    if not user.PostMessageW(int(child),0x10,0,0):raise ctypes.WinError(ctypes.get_last_error())
    check('generated tags unchanged',all(not row['tags'] for row in catalog.search()['items']))
    return path.name
