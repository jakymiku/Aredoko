"""UIA checkbox path shares the context-menu handler; no physical input."""
import time


def audit(ui,tree,shot,report,check,handler,catalog,item_id):
    report['authorization']='Explicit approval required: dedicated generated UIA-only favorite patch, no foreground/physical input/GPU/model/playback/normal data'
    previous=catalog.get(item_id);sessions=set(handler.results.sessions);calls=[]
    original=handler.results.provider
    def provider(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    handler.results.provider=provider
    try:
        ui('invoke','Item'+str(item_id),'--action','select');ui('invoke','BtnDetails')
        ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000');ui('set-value','TxtTags','favorite-patch-unsaved')
        for value in (not previous['favorite'],previous['favorite']):
            ui('invoke','ChkFavorite','--action','toggle-on' if value else 'toggle-off')
            deadline=time.monotonic()+10
            while catalog.get(item_id)['favorite']!=value:
                if time.monotonic()>deadline:raise TimeoutError('Favorite was not saved')
                time.sleep(.05)
            ui('wait-for','ChkFavorite','-p','IsEnabled','--value','True','-t','10000')
            ui('wait-for','TxtTags','--value','favorite-patch-unsaved','-t','10000')
            check('favorite change did not rebuild search results',not calls and set(handler.results.sessions)==sessions)
            check('favorite change did not save the tag draft',catalog.get(item_id)['tags']==previous['tags'])
            check('updated caption shows the current favorite flag',tree()['ItemTitle'+str(item_id)]['name'].startswith('★ ')==value)
        shot('favorite-kept-session')
        ui('set-value','TxtTags',', '.join(previous['tags']));ui('invoke','BtnCloseDetails')
    finally:handler.results.provider=original



def audit_bulk(ui,tree,shot,report,check,handler,catalog,*,input_guard):
    from native_ui_tools import inspect_element
    report['authorization']='Explicit per-run approval: generated library, bulk retained favorites, owned physical Shift input; no playback/GPU/normal data'
    rows=catalog.search(limit=120)['items'];ids=[row['id'] for row in rows[:2]]
    ui('invoke','Item'+str(ids[0]),'--action','select');ui('focus','Item'+str(ids[0]))
    if not input_guard():raise RuntimeError('Owned bulk test is not foreground; no key sent')
    ui('send-keys','shift+down','--via','send-input');ui('wait-for','SelectionCountText','--value','2 件選択','--contains','-t','10000')
    for _ in range(14):
        ui('scroll','ItemList','--to','bottom')
        if '一覧外 2 件' in inspect_element(ui,'SelectionCountText').get('name',''):break
        time.sleep(.25)
    ui('wait-for','SelectionCountText','--value','一覧外 2 件','--contains','-t','10000')
    ui('invoke','BtnDetails');ui('wait-for','SelectionFavoriteAdd','-t','10000')
    sessions=set(handler.results.sessions);calls=[];provider=handler.results.provider
    def counted(*args,**kwargs):calls.append(1);return provider(*args,**kwargs)
    handler.results.provider=counted
    try:
        before_range=tree().get('TxtPageNumber',{}).get('name')
        for value,button in ((True,'SelectionFavoriteAdd'),(False,'SelectionFavoriteRemove')):
            ui('invoke',button);ui('wait-for','SelectionEditStatus','--value','保存しました','--contains','-t','15000')
            check('bulk metadata saved for both selected items',all(catalog.get(item)['favorite']==value for item in ids))
            check('bulk favorite retains frozen session without provider',not calls and set(handler.results.sessions)==sessions)
            ui('wait-for','SelectionCountText','--value','一覧外 2 件','--contains','-t','10000')
            check('bulk favorite retains the visible metadata window',tree().get('TxtPageNumber',{}).get('name')==before_range)
        shot('bulk-kept-session');ui('invoke','SelectionFavoriteAdd');ui('wait-for','SelectionEditStatus','--value','保存しました','--contains','-t','15000')
        ui('invoke','BtnCloseDetails');ui('invoke','NavFavorites');ui('wait-for','Item'+str(ids[0]),'-t','15000');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','15000')
        ui('invoke','Item'+str(ids[0]),'--action','select');ui('focus','Item'+str(ids[0]))
        if not input_guard():raise RuntimeError('Owned bulk fallback test is not foreground; no key sent')
        ui('send-keys','shift+down','--via','send-input');ui('wait-for','SelectionCountText','--value','2 件選択','--contains','-t','10000')
        ui('invoke','BtnDetails');before_calls=len(calls);ui('invoke','SelectionFavoriteRemove')
        ui('wait-for','TxtEmpty','--value','お気に入りはまだありません','--contains','-t','15000')
        check('favorites view rebuilds and removes saved items',len(calls)>before_calls and all(not catalog.get(item)['favorite'] for item in ids))
        shot('bulk-favorites-fallback')
    finally:handler.results.provider=provider
