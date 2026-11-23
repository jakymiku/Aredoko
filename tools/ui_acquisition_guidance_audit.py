"""Display-only acquisition guidance and one native recovery close button."""
from native_ui_tools import inspect_element, invoke_tool


def audit(ui,tree,shot,report,check,handler):
    ui('invoke','BtnSettings');ui('wait-for','BtnAIIndex','-t','10000');ui('invoke','BtnAIIndex')
    ui('wait-for','AIModelDownloadOpen','-t','10000');ui('invoke','AIModelDownloadOpen')
    ui('wait-for','AIDownloadDialog','-t','10000');ui('wait-for','AIDownloadInformation','--value','容量','--contains','-t','10000')
    text=inspect_element(ui,'AIDownloadIntroduction')['name']
    check('acquisition separates the required model and runtime from optional tagging','検索モデルと実行環境が必要' in text and '画像タグ付けモデルは追加機能' in text)
    state=tree();check('optional speed input is initially collapsed','AIDownloadSpeed' not in state or state['AIDownloadSpeed']['isOffscreen'])
    ui('wait-for','PrimaryButton','-p','IsEnabled','--value','False','-t','10000');shot('acquisition-guidance')
    ui('invoke','AIDownloadSettings','--action','expand');ui('wait-for','AIDownloadSpeed','-t','10000');shot('optional-download-speed')
    ui('invoke','AIDownloadSettings','--action','collapse');ui('invoke','CloseButton');ui('wait-for','AIDownloadDialog','--gone','-t','10000')
    check('viewing acquisition settings did not start a download',handler.download_jobs.snapshot()['state']=='idle')
    ui('invoke','BtnSettings');ui('wait-for','BtnBackupGuide','-t','10000');ui('invoke','BtnBackupGuide')
    ui('wait-for','BackupRecoveryHelp','-t','10000');ui('invoke','BackupRecoveryHelp');ui('wait-for','BackupGuideDialog','-t','10000')
    state=tree();check('recovery guide uses only its native close button','CloseButton' in state and 'BtnCloseBackupGuide' not in state)
    shot('recovery-guide-footer');ui('invoke','CloseButton');ui('wait-for','BackupGuideDialog','--gone','-t','10000')
    check('guide did not start a backup',handler.backup_jobs.snapshot()['state']=='idle')
