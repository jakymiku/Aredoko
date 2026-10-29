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


def audit_guide(ui,shot,report,check,catalog,handler,target):
    before=catalog.search()['total']
    def open_guide():
        ui('invoke','BtnSettings');ui('wait-for','BtnGettingStarted','-t','10000');ui('invoke','BtnGettingStarted')
        ui('wait-for','GuideAddFolder','-t','10000')
    open_guide()
    folder=inspect_element(ui,'GuideAddFolder');more=inspect_element(ui,'GuideDetails')
    footer=inspect_element(ui,'PrimaryButton')
    check('folder and optional AI entries are visible in the concise guide',not folder['isOffscreen'] and not footer['isOffscreen'] and folder['height']>=32)
    check('collapsed detailed guidance remains reachable',not more['isOffscreen'] and more['height']>=40)
    shot('guide-overview')
    ui('invoke','GuideDetails','--action','expand')
    expanded=json.loads(ui('inspect','GuideDetails','--depth','15','--json'))
    names={n.get('name') for n in nodes(expanded) if n.get('type')=='TextBlock' or n.get('type')=='Text'}
    expected=('1. フォルダを登録する','2. 検索して開く','3. AI検索を準備する（任意）','4. 内容から探す・整理する','閲覧・データ保護')
    check('all five original detailed sections remain available',all(v in names for v in expected))
    ui('invoke','GuideDetails','--action','collapse');ui('invoke','GuideAddFolder')
    ui('wait-for','GettingStartedGuideDialog','--gone','-t','10000');ui('wait-for','RootPath','-p','IsEnabled','--value','True','-t','10000')
    check('guide opens the folder registration form directly',not inspect_element(ui,'RootPath')['isOffscreen'])
    check('opening registration does not scan or alter the generated catalog',catalog.search()['total']==before)
    shot('guide-folder-entry')
    ui('invoke','BtnRoots');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    open_guide();ui('invoke','PrimaryButton');ui('wait-for','AISetupPlanDialog','-t','10000')
    check('optional AI guidance retains the purpose selection entry',True)
    check('following guidance starts no downloads or inference',handler.setup_jobs.snapshot()['state']=='idle' and handler.download_jobs.snapshot()['state']=='idle')
    ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','--gone','-t','10000')
    shot('guide-return');report['physical_input_requested']=False
    report['unverified']=['physical keyboard/tab order','high contrast and physical DPI','real folder registration/model installation']


def audit_diagnostics(ui,shot,report,check):
    ui('invoke','BtnSettings');ui('wait-for','BtnDiagnostics','-t','10000');ui('invoke','BtnDiagnostics')
    ui('wait-for','DiagnosticsDialog','-t','10000');ui('wait-for','CloseButton','-t','10000')
    dialog=json.loads(ui('inspect','DiagnosticsDialog','--depth','12','--json'))
    closers={n.get('selector') for n in nodes(dialog) if n.get('type')=='Button' and n.get('name')=='閉じる' and not n.get('isOffscreen',True)}
    check('diagnostics exposes one native close action',len(closers)==1)
    close=inspect_element(ui,'CloseButton');copy=inspect_element(ui,'BtnCopyDiagnostics')
    check('close uses the footer below the copy action',not close['isOffscreen'] and close['height']>=32 and close['y']>copy['y']+copy['height'])
    check('diagnostic text remains available',not inspect_element(ui,'TxtDiagnostics')['isOffscreen'])
    value=ui('get-value','TxtDiagnostics')
    check('diagnostics retains its multiline report and build identity','ビルド元コミット:' in value and '配布種別:' in value and value.count('\n')>=5)
    shot('diagnostic-native-footer');ui('invoke','CloseButton');ui('wait-for','DiagnosticsDialog','--gone','-t','10000')
    check('native diagnostic close returns to the library',True)
    report['physical_input_requested']=False;report['clipboard_requested']=False
    report['unverified']=['physical Esc/Tab keys','clipboard operation','high contrast and physical DPI']


def audit_folder_toolbar(ui,shot,report,check):
    ui('invoke','NavFolders');ui('wait-for','TxtFolderFilter','-t','10000')
    state=json.loads(ui('inspect','--depth','14','--json'))
    back={n.get('selector') for n in nodes(state) if n.get('type')=='Button' and n.get('name')=='作品一覧へ戻る' and not n.get('isOffscreen',True)}
    check('folder screen exposes a single return-to-library action',len(back)==1)
    check('common header return is visible',not inspect_element(ui,'BtnRoots')['isOffscreen'])
    ui('invoke','BtnToggleAddFolder');ui('wait-for','RootPath','-p','IsEnabled','--value','True','-t','10000')
    check('folder registration remains directly reachable',not inspect_element(ui,'RootPath')['isOffscreen'])
    shot('folder-single-return');ui('invoke','BtnRoots');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('wait-for','BtnRoots','--value','フォルダ管理','-t','10000')
    check('same header returns and restores the library action',True)
    report['physical_input_requested']=False;report['unverified']=['physical keyboard/tab order','high contrast and physical DPI']
