"""UIA-only details density and unsaved-edit check over generated PNGs."""
from create_preview_fixture import png
from native_ui_tools import inspect_element

LONG_NAME='long-'+'image-file-name-'*7+'end.png'


def create_media(media):
    (media/'image-0.png').write_bytes(png())
    nested=media/'generated-subfolder';nested.mkdir()
    (nested/LONG_NAME).write_bytes(png(color=(120,80,160)))


def audit(ui,tree,shot,report,check,catalog):
    report['authorization']='Explicit approval: generated PNGs/dedicated DB/UIA only; no physical input/foreground request/GPU/playback'
    rows=catalog.search()['items'];short=next(row for row in rows if row['title']=='image-0.png');long=next(row for row in rows if row['title']==LONG_NAME)
    def select(row):
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
        ui('invoke','Item'+str(row['id']),'--action','select');ui('invoke','BtnDetails')
        ui('wait-for','DetailItemTitle','--value',row['title'],'-t','10000')
    select(short)
    ui('wait-for','DetailItemLocation','--gone','-t','10000')
    normal_height=inspect_element(ui,'DetailItemTitle')['height']
    ui('set-value','TxtTags','polish-unsaved');ui('invoke','BtnLayout')
    ui('wait-for','TxtTags','--value','polish-unsaved','-t','10000')
    check('layout switch retains unsaved tag without saving it',catalog.get(short['id'])['tags']==short['tags'])
    shot('detail-no-duplicate')
    ui('set-value','TxtTags',', '.join(short['tags']));ui('invoke','BtnCloseDetails')
    ui('set-value','TxtQuery',LONG_NAME);ui('invoke','BtnSearch')
    ui('wait-for','Item'+str(long['id']),'-t','15000');select(long)
    expected='generated-subfolder/'+LONG_NAME
    ui('wait-for','DetailItemLocation','--value',expected,'-t','10000')
    title=inspect_element(ui,'DetailItemTitle')
    check('long title retains its full accessible filename',title['name']==LONG_NAME)
    check('long title occupies at most three normal lines',normal_height>0 and 0<title['height']<=normal_height*3+2)
    check('nested location remains available',inspect_element(ui,'DetailItemLocation')['name']==expected)
    shot('detail-long-name')
    ui('invoke','BtnCloseDetails');ui('set-value','TxtQuery','image-0.png');ui('invoke','BtnSearch')
    ui('wait-for','Item'+str(short['id']),'-t','15000');select(short)
    ui('wait-for','DetailItemLocation','--gone','-t','10000')
    check('moving back to a root file clears the previous nested location',True)
    report['unverified']=['actual pointer tooltip','text selection/copy input','physical DPI/high contrast','runtime error dialog']
