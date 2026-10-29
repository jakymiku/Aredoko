"""Generated-only, UIA-only settings density and native footer persistence."""
import json
from native_ui_tools import inspect_element,nodes


def audit(ui,shot,report,check,target):
    ui('invoke','BtnSettings');ui('wait-for','SettingsWheel','-t','10000')
    ids=('BtnGettingStarted','BtnAIIndex','BtnRelatedTerms','BtnClearHistory','BtnBackupGuide','BtnDiagnostics')
    scroll=inspect_element(ui,'SettingsScroll')
    buttons=[inspect_element(ui,key) for key in ids]
    if any(b['isOffscreen'] or b['y']+b['height']>scroll['y']+scroll['height'] for b in buttons):
        ui('scroll','SettingsScroll','--to','bottom')
        buttons=[inspect_element(ui,key) for key in ids]
    for row in range(3):
        left,right=buttons[row*2:row*2+2]
        check('settings action pair '+str(row+1)+' shares one row',abs(left['y']-right['y'])<=1 and right['x']>=left['x']+left['width']+7)
        check('settings action pair '+str(row+1)+' stays legible',all(not b['isOffscreen'] and b['width']>=170 and b['height']>=32 for b in (left,right)))
    check('six settings actions occupy three compact rows',buttons[-1]['y']+buttons[-1]['height']-buttons[0]['y']<=120)
    save=inspect_element(ui,'SettingsSave');close=inspect_element(ui,'CloseButton')
    check('save and close remain in the native footer',not save['isOffscreen'] and not close['isOffscreen'] and abs(save['y']-close['y'])<=1)
    shot('settings-actions')
    scroll=inspect_element(ui,'SettingsScroll')
    wheel=inspect_element(ui,'SettingsWheel')
    if wheel['isOffscreen'] or wheel['y']<scroll['y']:ui('scroll','SettingsScroll','--to','top')
    ui('invoke','SettingsWheel','--action','expand')
    candidates={n['selector'] for n in nodes(json.loads(ui('inspect','--depth','18','--json')))
        if n.get('type') in ('ListItem','ComboBoxItem') and n.get('name')=='上に回す（下で戻る）' and n.get('selector') and not n.get('isOffscreen',True)}
    if len(candidates)!=1:raise RuntimeError('Expected one visible wheel choice')
    ui('invoke',candidates.pop(),'--action','select');ui('invoke','SettingsWheel','--action','collapse')
    ui('invoke','SettingsSave');ui('wait-for','SettingsStatus','--value','保存しました','--contains','-t','10000')
    preference=target/'viewer-settings.json'
    saved=json.loads(preference.read_text(encoding='utf-8'))
    check('footer save persists the selected wheel direction',saved['wheel_up_advances'] is True)
    check('saving settings retains the current list choice',saved['library_view']=='list')
    ui('invoke','CloseButton');ui('wait-for','SettingsDialog','--gone','-t','10000')
    ui('invoke','BtnSettings');ui('wait-for','SettingsWheel','--value','上に回す（下で戻る）','-t','10000')
    check('reopening settings retains the saved choice',True);shot('settings-reopened')
    ui('invoke','CloseButton');ui('wait-for','SettingsDialog','--gone','-t','10000')
    report['physical_input_requested']=False
    report['unverified']=['physical keyboard/tab order','high contrast and physical DPI','all destination screen actions']
