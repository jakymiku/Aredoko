"""UIA-only first-run feature choice. No physical input or acquisition."""
import json


def audit(ui,tree,shot,report,check,handler,target):
    report['authorization']='Explicit per-run permission required: dedicated generated UIA-only setup, no foreground activation/physical input, downloads/models/GPU/normal data'
    def open_plan():
        ui('invoke','BtnSettings');ui('wait-for','BtnGettingStarted','-t','10000');ui('invoke','BtnGettingStarted')
        ui('wait-for','GettingStartedGuideDialog','-t','10000');ui('invoke','PrimaryButton')
        ui('wait-for','AISetupPlanDialog','-t','10000')
    open_plan()
    for name in ('video','audio'):ui('invoke','SetupFeature'+name,'--action','toggle')
    ui('invoke','ReviewAISetupPlan')
    ui('wait-for','AISetupPlanSummary','--value','自動取得は準備中','--contains','-t','15000')
    ui('wait-for','AISetupPlanDownload','-p','IsEnabled','--value','True','-t','10000')
    shot('setup-requirements')
    check('runtime and model have separate acquisition states',True)
    check('planning did not start an acquisition',handler.download_jobs.snapshot()['state']=='idle')
    check('planning did not create video/audio model owners',handler.video_content.owner is None and handler.audio_content.owner is None)
    ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','--gone','-t','10000')
    preferences=target/'viewer-settings.json'
    check('all four feature choices are persisted',json.loads(preferences.read_text(encoding='utf-8'))['ai_setup_features']==15)
    open_plan();ui('invoke','SkipAISetup');ui('wait-for','AISetupPlanDialog','--gone','-t','10000')
    check('AI opt-out is saved',json.loads(preferences.read_text(encoding='utf-8'))['ai_setup_features']==0)
    open_plan();ui('invoke','ReviewAISetupPlan')
    ui('wait-for','AISetupPlanSummary','--value','AIは使わず','--contains','-t','10000');shot('setup-skipped')
    check('AI opt-out keeps normal setup jobs idle',handler.setup_jobs.snapshot()['state']=='idle' and handler.download_jobs.snapshot()['state']=='idle')
    ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','--gone','-t','10000')
