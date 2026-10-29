"""UIA-only route out of AI-unavailable results; generated two-image library."""
from native_ui_tools import inspect_element, select_combo_item


def audit(ui,tree,shot,report,check,handler):
    report['authorization']='Explicit permission for generated dedicated data; UIA only, no acquisition/inference or physical input'
    ui('set-value','TxtQuery','image-0.png');ui('invoke','BtnSearch')
    ui('wait-for','TxtCount','--value','1 件','-t','10000')
    select_combo_item(ui,'CmbSearchMode','ModeSemantic');ui('invoke','BtnSearch')
    ui('wait-for','EmptyPrepareAI','-t','10000');ui('wait-for','EmptyLiteralSearch','-t','10000')
    check('missing AI gives actionable preparation guidance','準備が必要' in inspect_element(ui,'TxtEmpty')['name'])
    state=tree();check('missing AI does not show a duplicate error bar','StatusBar' not in state or state['StatusBar']['isOffscreen'])
    prepare=inspect_element(ui,'EmptyPrepareAI');literal=inspect_element(ui,'EmptyLiteralSearch')
    check('recovery actions stay below the guidance without overlapping',literal['x']>=prepare['x']+prepare['width']+7 and abs(prepare['y']-literal['y'])<=1)
    shot('ai-recovery-actions')
    ui('invoke','EmptyPrepareAI');ui('wait-for','AISetupPlanDialog','-t','10000')
    check('direct preparation preserves the query',inspect_element(ui,'TxtQuery')['value']=='image-0.png')
    shot('direct-ai-setup');ui('invoke','CloseButton');ui('wait-for','AISetupPlanDialog','--gone','-t','10000')
    ui('invoke','EmptyLiteralSearch');ui('wait-for','TxtCount','--value','1 件','-t','10000')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    check('literal recovery keeps the same query',inspect_element(ui,'TxtQuery')['value']=='image-0.png')
    state=tree();check('recovery actions disappear after literal results',all(key not in state or state[key]['isOffscreen'] for key in ('EmptyPrepareAI','EmptyLiteralSearch')))
    check('literal recovery selects filename and tag search','ファイル名・タグ' in inspect_element(ui,'CmbSearchMode')['name'])
    check('no download or model owners were started',handler.download_jobs.snapshot()['state']=='idle' and handler.audio_content.owner is None and handler.video_content.owner is None)
    shot('literal-recovered')
    report['physical_input_requested']=False
    report['unverified']=['physical hover/keyboard','high contrast/physical DPI','real AI or generic connection failure']
