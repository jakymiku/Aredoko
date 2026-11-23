"""Generated long names, actual caption slots and size changes; UIA only."""
import time
from native_ui_tools import inspect_element
from ui_detail_polish_audit import audit as audit_details,LONG_NAME


def audit(ui,tree,shot,report,check,catalog):
    audit_details(ui,tree,shot,report,check,catalog)
    report['authorization']='Current user approval: tests may run; dedicated generated PNG/DB, UIA only, no GPU/model/playback'
    ui('invoke','BtnCloseDetails');ui('set-value','TxtQuery','');ui('invoke','BtnSearch')
    rows=catalog.search()['items'];long=next(row for row in rows if row['title']==LONG_NAME)
    long_id=long['id'];ui('wait-for','Item'+str(long_id),'-t','15000')
    name='長い棚の名前を省略して読みやすくするための確認用の棚' * 2
    shelf=catalog.change_shelf('create',name=name)['id']
    catalog.change_shelf('assign',entity='item',object_ids=[long_id],shelf_ids=[shelf])
    report['caption_slots']=[]
    def fits(card_id,title_id,expected,label):
        card=inspect_element(ui,card_id);title=inspect_element(ui,title_id)
        check(label+' full accessible name',title['name']==expected)
        check(label+' caption stays inside card',title['width']>8 and title['x']>=card['x']+4
              and title['x']+title['width']<=card['x']+card['width']-4)
        check(label+' one caption line',0<title['height']<=26)
        report['caption_slots'].append({'label':label,'card':card,'title':title})
    for scale in (60,180):
        ui('invoke','BtnItemSize');ui('wait-for','ItemSizeSlider','-t','5000')
        ui('set-value','ItemSizeSlider',str(scale));ui('wait-for','ItemSizeLabel','--value',str(scale)+'%','-t','5000')
        # Use UIA navigation without injecting Escape or physical input.
        ui('invoke','NavShelf');ui('wait-for','ShelfTitle'+str(shelf),'-t','10000')
        ui('invoke','NavAll');ui('wait-for','Item'+str(long_id),'-t','15000')
        time.sleep(.3)
        fits('Item'+str(long_id),'ItemTitle'+str(long_id),LONG_NAME,'grid '+str(scale))
        shot('grid-caption-'+str(scale))
    ui('invoke','BtnLayout');time.sleep(.3)
    fits('Item'+str(long_id),'ItemTitle'+str(long_id),LONG_NAME,'list 180')
    shot('list-caption')
    ui('invoke','NavShelf');ui('wait-for','ShelfTitle'+str(shelf),'-t','10000')
    fits('ShelfRow'+str(shelf),'ShelfTitle'+str(shelf),name,'shelf list')
    ui('invoke','BtnShelfLayout');time.sleep(.3)
    fits('ShelfRow'+str(shelf),'ShelfTitle'+str(shelf),name,'shelf grid')
    shot('shelf-caption')
    check('caption navigation preserves shelf membership',shelf in catalog.get(long_id)['shelf_ids'])
    report['unverified']=['physical DPI/high contrast','actual tooltip hover/copy','general 50k-item performance']


def audit_menu(ui,tree,shot,report,check,catalog):
    report['authorization']='Current user test approval; dedicated generated PNG/DB, UIA-only remaining size-menu case'
    ui('invoke','BtnItemSize');ui('wait-for','ItemSizeSlider','-t','5000')
    ui('set-value','ItemSizeSlider','60');ui('wait-for','ItemSizeLabel','--value','60%','-t','5000')
    ui('invoke','NavShelf');ui('wait-for','ItemSizeSlider','--gone','-t','5000')
    check('navigation closes the old size menu',True)
    ui('invoke','NavAll');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('invoke','BtnItemSize');ui('wait-for','ItemSizeSlider','-t','5000')
    ui('invoke','BtnLayout');ui('wait-for','ItemSizeSlider','--gone','-t','5000')
    check('layout switch closes the size menu',True)
    row=next(x for x in catalog.search()['items'] if x['title']==LONG_NAME)
    ui('wait-for','ItemTitle'+str(row['id']),'-t','10000')
    check('full long title remains accessible after closing the menu',inspect_element(ui,'ItemTitle'+str(row['id']))['name']==LONG_NAME)
    shot('caption-menu-closed')
    report['unverified']=['physical input/hover','physical DPI/high contrast','general library performance']
