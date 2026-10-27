"""Purpose guide return paths, UIA only; never starts downloads or AI work."""
import json


def audit(ui,tree,shot,report,check,handler,target):
    report['authorization']='Explicit per-run approval required: dedicated generated UIA-only guide return paths; no foreground, physical input, acquisition, model, GPU or normal data'
    ui('invoke','BtnSettings');ui('wait-for','BtnGettingStarted','-t','10000');ui('invoke','BtnGettingStarted')
    ui('wait-for','GettingStartedGuideDialog','-t','10000');ui('invoke','PrimaryButton')
    ui('wait-for','AISetupPlanDialog','-t','10000')
    for name in ('video','audio'):ui('invoke','SetupFeature'+name,'--action','toggle')
    ui('invoke','ReviewAISetupPlan')
    ui('wait-for','AISetupNextSteps','--value','動画の準備欄','--contains','-t','15000')
    ui('invoke','AISetupPlanDownload');ui('wait-for','AIDownloadDialog','-t','10000')
    ui('wait-for','AIDownloadInformation','--value','容量','--contains','-t','10000')
    # No consent toggle and no PrimaryButton invocation in the download dialog.
    ui('invoke','CloseButton')
    ui('wait-for','AISetupPlanDialog','-t','10000')
    ui('wait-for','AISetupNextSteps','--value','音声の準備欄','--contains','-t','15000')
    check('return from download refreshes selected-purpose next steps',True);shot('after-download')
    ui('invoke','AISetupPlanExisting');ui('wait-for','AIEnvironmentDialog','-t','10000')
    ui('wait-for','AIEnvironmentDiagnostic','--value','実行環境','--contains','-t','15000')
    ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','-t','10000')
    ui('wait-for','AISetupNextSteps','--value','不足する実行環境','--contains','-t','15000')
    check('return from placement reports missing requirements without saving',True)
    ui('invoke','PrimaryButton');ui('wait-for','AISettingsDialog','-t','15000')
    ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','-t','15000')
    ui('wait-for','AISetupNextSteps','--value','音声の準備欄','--contains','-t','15000')
    check('return from index settings awaits dialog completion',True);shot('after-index-settings')
    check('all selected purposes survived all destination round trips',json.loads((target/'viewer-settings.json').read_text(encoding='utf-8'))['ai_setup_features']==15)
    check('acquisition and placement jobs stayed idle',handler.download_jobs.snapshot()['state']=='idle' and handler.setup_jobs.snapshot()['state']=='idle')
    check('no audio or video model owner was created',handler.audio_content.owner is None and handler.video_content.owner is None)
    ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','--gone','-t','10000')
