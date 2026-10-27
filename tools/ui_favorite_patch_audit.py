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
