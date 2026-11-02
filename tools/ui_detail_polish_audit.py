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


def audit_fields(ui,tree,shot,report,check,catalog):
    """Wrapped editing, compact shelf row and picker cancellation, UIA only."""
    short=next(row for row in catalog.search()['items'] if row['title']=='image-0.png')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('invoke','Item'+str(short['id']),'--action','select');ui('invoke','BtnDetails')
    ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
    old=catalog.get(short['id']);baseline=inspect_element(ui,'TxtTags')['height']
    long_tags=', '.join(['夜の街並み','青い空と雲','静かな教室','星の見える丘','木漏れ日の森','日本語の少し長いタグ','水辺の背景素材','夕焼けの港町'])
    ui('set-value','TxtTags',long_tags);ui('wait-for','TxtTags','--value',long_tags,'-t','10000')
    tags=inspect_element(ui,'TxtTags')
    check('long tags wrap into a bounded taller field',baseline+14<tags['height']<=120)
    check('editing wrapped tags does not save implicitly',catalog.get(short['id'])['tags']==old['tags'])
    state=tree();shelf=state['TxtShelf'];button=state['BtnChooseShelves']
    check('shelf action remains visible without scrolling past wrapped tags',not button['isOffscreen'] and button['height']>=32)
    check('shelf selection button shares the current shelf row',abs(shelf['y']+shelf['height']-button['y']-button['height'])<=2 and button['x']>=shelf['x']+shelf['width']-1)
    ui('invoke','BtnChooseShelves');ui('wait-for','ChooseShelfList','-t','5000');ui('invoke','CloseButton')
    ui('wait-for','ChooseShelfList','--gone','-t','5000');ui('wait-for','TxtTags','--value',long_tags,'-t','10000')
    current=catalog.get(short['id'])
    check('cancelled shelf picker preserves tag draft and memberships',all(current[k]==old[k] for k in ('tags','shelf_ids','favorite')))
    shot('detail-wrapped-tags')
    ui('invoke','BtnLayout');ui('wait-for','TxtTags','--value',long_tags,'-t','10000')
    check('grid switch preserves the wrapped tag draft',True)
    ui('invoke','BtnSave');ui('wait-for','BtnSave','-p','IsEnabled','--value','False','-t','10000')
    check('wrapped tags save the same comma separated values',sorted(catalog.get(short['id'])['tags'])==sorted(v.strip() for v in long_tags.split(',')))
    shot('detail-fields-saved');report['unverified']=['physical text editing/copy','physical DPI/high contrast']


def audit_scroll(ui,tree,shot,report,check,catalog):
    """Different items start at top; reopening the same item keeps its scroll."""
    rows=catalog.search()['items']
    short=next(row for row in rows if row['title']=='image-0.png')
    long=next(row for row in rows if row['title']==LONG_NAME)
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('invoke','Item'+str(short['id']),'--action','select');ui('invoke','BtnDetails')
    ui('wait-for','DetailItemTitle','--value',short['title'],'-t','10000')
    ui('invoke','FileProperties','--action','expand')
    ui('scroll','DetailScroll','--to','bottom')
    ui('wait-for','DetailItemTitle','-p','IsOffscreen','--value','True','-t','10000')
    ui('invoke','BtnCloseDetails');ui('invoke','BtnDetails')
    ui('wait-for','DetailItemTitle','-p','IsOffscreen','--value','True','-t','10000')
    check('reopening the same item retains the scrolled detail position',True)
    ui('invoke','Item'+str(long['id']),'--action','select')
    ui('wait-for','DetailItemTitle','--value',long['title'],'-t','10000')
    ui('wait-for','DetailItemTitle','-p','IsOffscreen','--value','False','-t','10000')
    title=inspect_element(ui,'DetailItemTitle');viewport=inspect_element(ui,'DetailScroll')
    check('switching items in an open pane returns the title to the top',
          viewport['y']<=title['y']<viewport['y']+24)
    ui('invoke','FileProperties','--action','expand');ui('scroll','DetailScroll','--to','bottom')
    ui('wait-for','DetailItemTitle','-p','IsOffscreen','--value','True','-t','10000')
    ui('invoke','BtnCloseDetails')
    ui('invoke','Item'+str(short['id']),'--action','select');ui('invoke','BtnDetails')
    ui('wait-for','DetailItemTitle','--value',short['title'],'-t','10000')
    ui('wait-for','DetailItemTitle','-p','IsOffscreen','--value','False','-t','10000')
    check('switching items while the pane is closed resets on reopening',True)
    shot('detail-scroll-reset')
    report['unverified']=['physical wheel input','high contrast and DPI','same-item save and refresh scroll retention']
