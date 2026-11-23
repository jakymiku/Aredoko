"""UIA-only first-run feature choice. No physical input or acquisition."""
import json


def audit(ui,tree,shot,report,check,handler,target,*,check_layout=False):
    report['authorization']='Explicit per-run permission required: dedicated generated UIA-only setup, no foreground activation/physical input, downloads/models/GPU/normal data'
    def open_plan():
        ui('invoke','BtnSettings');ui('wait-for','BtnGettingStarted','-t','10000');ui('invoke','BtnGettingStarted')
        ui('wait-for','GettingStartedGuideDialog','-t','10000');ui('invoke','PrimaryButton')
        ui('wait-for','AISetupPlanDialog','-t','10000')
    open_plan()
    if check_layout:
        from native_ui_tools import inspect_element
        names=('semantic','image_similarity','video','audio')
        labels=('ファイル名・タグの意味','画像の見た目・類似検索','動画の内容','音声・音楽の内容')
        choices=[inspect_element(ui,'SetupFeature'+name) for name in names]
        check('all AI choices expose clear purpose labels',all(node['name']==label and not node['isOffscreen'] for node,label in zip(choices,labels)))
        check('AI purposes use two aligned columns',abs(choices[0]['x']-choices[2]['x'])<=1 and abs(choices[1]['x']-choices[3]['x'])<=1 and choices[1]['x']>=choices[0]['x']+choices[0]['width']+8)
        check('AI purposes use two nonoverlapping rows',abs(choices[0]['y']-choices[1]['y'])<=1 and abs(choices[2]['y']-choices[3]['y'])<=1 and choices[2]['y']>=max(n['y']+n['height'] for n in choices[:2])+7)
        shot('setup-purpose-choices')
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
