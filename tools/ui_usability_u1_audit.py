"""Focused native usability checks; caller owns the app, fixture and request gate."""
import json
import time
from native_ui_tools import nodes


def audit(ui, tree, shot, check, first_id, gate, cat, interactive=True,favorite=False):
    key='Item'+str(first_id)
    ui('wait-for','LibraryHeading','--value','ライブラリ','-t','10000')
    if interactive:
        ui('focus','BtnLayout')
        ui('hover','LibraryHeading');time.sleep(.9)
        raw=json.loads(ui('inspect','--depth','18','--json'))
        check('page hover does not expose a global Ctrl Home tooltip',not any(
            str(n.get('type','')).lower()=='tooltip' and 'Home' in str(n.get('name','')) for n in nodes(raw)))
    for nav,title in ([] if favorite else [('NavFavorites','お気に入り'),('NavHistory','閲覧履歴'),('NavAll','ライブラリ')]):
        gate.clear()
        try:
            ui('invoke',nav)
            ui('wait-for','LibraryHeading','--value',title,'-t','3000')
            ui('wait-for','ItemList','-p','IsEnabled','--value','False','-t','3000')
            check(title+' heading updates before blocked search completes',True)
        finally:gate.set()
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('wait-for',key,'-t','10000')
    ui('invoke',key,'--action','select')
    check('single selection leaves details closed',tree().get('TxtTags',{}).get('isOffscreen',True))
    ui('invoke','BtnLayout')
    if interactive:
        ui('invoke','BtnItemSize');ui('set-value','ItemSizeSlider','60')
        ui('send-keys','escape','--via','send-input')
        ui('wait-for',key,'-t','10000');shot('small-grid-selected')
        ui('click',key,'--right');ui('wait-for','OpenDetails'+str(first_id),'-t','3000')
        ui('invoke','OpenDetails'+str(first_id))
    else:
        shot('grid-selected');ui('invoke','BtnDetails')
    ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
    ui('set-value','TxtTags','u1-unsaved-draft')
    ui('invoke','BtnCloseDetails');ui('invoke',key,'--action','select')
    ui('invoke','BtnDetails');ui('wait-for','TxtTags','--value','u1-unsaved-draft','-t','5000')
    check('explicit detail reopening preserves unsaved edits',cat.get(first_id)['tags']==[])
    if favorite:
        for action,value in [('toggle-on',True),('toggle-off',False)]:
            ui('invoke','ChkFavorite','--action',action)
            ui('wait-for','ChkFavorite','-p','IsEnabled','--value','True','-t','10000')
            ui('wait-for','TxtTags','--value','u1-unsaved-draft','-t','5000')
            check('favorite '+str(value)+' saved without saving draft',cat.get(first_id)['favorite']==value and cat.get(first_id)['tags']==[])
            title=tree()['ItemTitle'+str(first_id)]['name']
            check('target caption reflects favorite '+str(value),title.startswith('★ ')==value)
            if value:shot('favorite-updated')
    shot('explicit-details')
    ui('set-value','TxtTags','');ui('invoke','BtnCloseDetails')
    if interactive:
        ui('hover','CmbSearchMode');time.sleep(.9);shot('search-mode-hint')
        ui('focus','BtnLayout');ui('send-keys','ctrl+end','--via','send-input')
        ui('wait-for','TxtPageNumber','--value','26–145 / 145','-t','10000')
        ui('send-keys','ctrl+home','--via','send-input')
        ui('wait-for','TxtPageNumber','--value','1–120 / 145','-t','10000')
        check('Ctrl Home and End remain functional',True)
