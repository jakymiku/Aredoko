"""Purpose guide return paths, UIA only; never starts downloads or AI work."""
import json


def audit(ui,tree,shot,report,check,handler,target,*,profiles=None,recovery=False,skip_download=False):
    report['authorization']='Explicit per-run approval required: dedicated generated UIA-only guide return paths; no foreground, physical input, acquisition, model, GPU or normal data'
    ui('invoke','BtnSettings');ui('wait-for','BtnGettingStarted','-t','10000');ui('invoke','BtnGettingStarted')
    ui('wait-for','GettingStartedGuideDialog','-t','10000');ui('invoke','PrimaryButton')
    ui('wait-for','AISetupPlanDialog','-t','10000')
    for name in ('video','audio'):ui('invoke','SetupFeature'+name,'--action','toggle')
    ui('invoke','ReviewAISetupPlan')
    ui('wait-for','AISetupNextSteps','--value','動画の準備欄','--contains','-t','15000')
    if not skip_download:
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
    if recovery:
        ui('invoke','AISetupRecovery','--action','expand')
        ui('wait-for','AISetupRecoveryText','--value','基本検索と閲覧を継続','--contains','-t','10000')
        ui('invoke','AISetupDiagnostics');ui('wait-for','DiagnosticsDialog','-t','10000')
        # No clipboard operation; the diagnostic remains local and visible only.
        ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','-t','10000')
        ui('wait-for','AISetupNextSteps','--value','音声の準備欄','--contains','-t','15000')
        check('safe recovery opens existing diagnostics and returns without resetting data',True)
        from ai_profiles import DEFAULT_PROFILE
        profiles.folder.mkdir(exist_ok=True);(profiles.folder/'generated-next.json').write_text(json.dumps(DEFAULT_PROFILE.to_dict()),encoding='utf-8')
        definition=profiles.active_definition;profiles.choose('local:generated-next.json')
        ui('invoke','ReviewAISetupPlan')
        ui('wait-for','AISetupPlanSummary','--value','モデルの変更待ち','--contains','-t','15000')
        ui('wait-for','AISetupPlanDownload','-p','IsEnabled','--value','False','-t','10000')
        check('saved next profile does not hot swap or recommend an old-model download',profiles.active_definition==definition)
        shot('profile-restart-required')
    check('all selected purposes survived all destination round trips',json.loads((target/'viewer-settings.json').read_text(encoding='utf-8'))['ai_setup_features']==15)
    check('acquisition and placement jobs stayed idle',handler.download_jobs.snapshot()['state']=='idle' and handler.setup_jobs.snapshot()['state']=='idle')
    check('no audio or video model owner was created',handler.audio_content.owner is None and handler.video_content.owner is None)
    ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','--gone','-t','10000')
