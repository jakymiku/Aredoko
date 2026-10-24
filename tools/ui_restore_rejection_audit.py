"""Two invalid generated ZIPs; native picker/start/failure/reselection, no switch consent."""
import json,time,zipfile
from native_ui_tools import nodes


def audit(ui,cli,tree,shot,check,request,pid,hwnd,target):
    paths=[target/'invalid-one.zip',target/'invalid-two.zip']
    for index,path in enumerate(paths):
        with zipfile.ZipFile(path,'x') as z:z.writestr('manifest.json',json.dumps({'format':'generated-invalid','version':1000+index}))
    original=request('/api/items')['items']
    ui('invoke','BtnSettings');ui('wait-for','BtnBackupGuide','-t','5000');ui('invoke','BtnBackupGuide')
    ui('wait-for','BackupDialog','-t','5000');ui('invoke','BackupRestoreGuide');ui('wait-for','RestoreDialog','-t','5000')
    for index,path in enumerate(paths):
        ui('invoke','RestoreChooseZip');deadline=time.monotonic()+10;picker=None
        while time.monotonic()<deadline:
            windows=json.loads(cli('ui','list-windows','-a',pid,'--json'))
            matches=[w for w in windows if str(w.get('hwnd'))!=hwnd and (str(w.get('ownerHwnd'))==hwnd or w.get('className')=='#32770')]
            if len(matches)==1:picker=str(matches[0]['hwnd']);break
            time.sleep(.1)
        check('owned ZIP picker '+str(index),picker is not None)
        all_nodes=list(nodes(json.loads(cli('ui','inspect','--depth','3','--json','-w',picker))))
        edits=[n for n in all_nodes if not n.get('isOffscreen',True) and n.get('type')=='Edit' and (n.get('automationId') in ('1148','FileNameControlHost') or n.get('name','').startswith(('ファイル名','File name')))]
        combos=[n for n in all_nodes if not n.get('isOffscreen',True) and n.get('automationId') in ('FileNameControlHost','1148')]
        buttons=[n for n in all_nodes if n.get('type') in ('Button','SplitButton') and n.get('isEnabled') and not n.get('isOffscreen',True) and n.get('automationId')=='1']
        choices=edits or combos;check('unambiguous picker controls '+str(index),bool(choices) and len(buttons)==1)
        cli('ui','set-value',choices[0].get('selector') or choices[0]['automationId'],str(path),'-w',picker)
        cli('ui','invoke',buttons[0].get('selector') or '1','--action','invoke','-w',picker)
        ui('wait-for','RestoreSource','--value',str(path),'-t','5000')
        if index==1:ui('invoke','RestoreOmitVectors','--action','toggle-off')
        ui('wait-for','PrimaryButton','-p','IsEnabled','--value','True','-t','5000');ui('invoke','PrimaryButton')
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            state=request('/api/library/restore')
            if state['state']=='failed':break
            time.sleep(.1)
        check('invalid backup rejected '+str(index),state['state']=='failed' and not state.get('restart_requested',False))
        check('retry uses newly selected source and policy '+str(index),state.get('source')==str(path) and state.get('without_vectors')==(index==0))
        ui('invoke','RestoreRefresh');ui('wait-for','RestoreStatus','--value','リストアに失敗しました。','-t','5000');shot('rejected-'+str(index))
        check('failure does not offer restart consent '+str(index),tree().get('RestoreConsent',{}).get('isOffscreen',True))
    ui('invoke','CloseButton');ui('wait-for','RestoreDialog','--gone','-t','5000')
    check('original library metadata unchanged after rejected backups',request('/api/items')['items']==original)
