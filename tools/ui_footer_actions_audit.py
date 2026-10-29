"""Narrow UIA-only library footer acceptance; no physical input or playback."""
import re
from native_ui_tools import inspect_element


def audit(ui,tree,shot,report,check,catalog):
    def ready():ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    def extent():
        text=inspect_element(ui,'TxtPageNumber')['name'].replace(',','')
        match=re.fullmatch(r'(\d+)–(\d+) / (\d+)',text)
        if not match:raise AssertionError('Expected current loaded range: '+text)
        return tuple(map(int,match.groups()))
    def open_actions():
        ui('invoke','BrowseActions');ui('wait-for','BtnReconnect','--value','接続と一覧を更新','-t','5000')
    rows=catalog.search(limit=120)['items'];first=rows[0]
    ui('set-value','TxtQuery','generated');ui('invoke','BtnSearch');ready()
    ui('wait-for','Item'+str(first['id']),'-t','10000');initial=extent()
    check('footer reports a loaded range within the full145 results',initial[0]==1 and 0<initial[1]<initial[2]==145)
    ui('invoke','Item'+str(first['id']),'--action','select')
    ui('wait-for','FooterSelection','--value','1 件選択','-t','10000');ui('invoke','BtnDetails')
    ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000');ui('wait-for','DetailItemTitle','--value',first['title'],'-t','10000');ui('set-value','TxtTags','footer-unsaved')
    current=tree()
    check('range actions stay out of the normal footer',all(key not in current or current[key]['isOffscreen'] for key in ('BtnPrevious','BtnNext','BtnReconnect')))
    page=inspect_element(ui,'TxtPageNumber');selection=inspect_element(ui,'FooterSelection');button=inspect_element(ui,'BrowseActions')
    check('range, selection and menu fit without overlap',page['x']+page['width']<=selection['x']+1 and selection['x']+selection['width']<=button['x']+1)
    shot('footer-selected')
    for command in ('BtnNext','BtnReconnect'):
        open_actions();ui('invoke',command)
        ui('wait-for','CloseButton','--value','編集を続ける','-t','10000');ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','10000')
        ui('wait-for','TxtTags','--value','footer-unsaved','-t','10000')
        check(command+' cancellation retains range and unsaved tags',extent()==initial and catalog.get(first['id'])['tags']==[])
    shot('footer-draft-retained');ui('set-value','TxtTags','');ui('wait-for','TxtTags','--value','','-t','10000')
    open_actions();ui('wait-for','BtnPrevious','-p','IsEnabled','--value','False','-t','5000')
    ui('wait-for','BtnNext','-p','IsEnabled','--value','True','-t','5000');shot('footer-actions-menu')
    ui('invoke','BtnNext');ready();ui('wait-for','Item'+str(rows[initial[1]]['id']),'-t','10000')
    following=extent();check('next range follows the existing search order',following[0]==initial[1]+1 and following[2]==initial[2])
    ui('wait-for','FooterSelection','--value','1 件選択','-t','10000')
    check('offscreen selected item remains counted',True)
    open_actions();ui('invoke','BtnPrevious');ready();ui('wait-for','Item'+str(first['id']),'-t','10000')
    check('previous range returns to the same query range',extent()==initial)
    open_actions();ui('invoke','BtnReconnect');ready();ui('wait-for','Item'+str(first['id']),'-t','10000')
    check('refresh keeps the generated query and result count',inspect_element(ui,'TxtQuery')['value']=='generated' and extent()==initial)
    ui('set-value','TxtQuery','footer-no-match');ui('invoke','BtnSearch');ready();ui('wait-for','TxtCount','--value','0 件','-t','10000')
    open_actions();ui('wait-for','BtnPrevious','-p','IsEnabled','--value','False','-t','5000');ui('wait-for','BtnNext','-p','IsEnabled','--value','False','-t','5000')
    check('empty results keep refresh available',inspect_element(ui,'BtnReconnect')['isEnabled'])
    shot('footer-empty-actions');ui('invoke','BtnReconnect');ready();ui('wait-for','TxtCount','--value','0 件','-t','10000')
    report['physical_input_requested']=False
    report['unverified']=['physical keyboard/hover input','high contrast and physical DPI','backend process disconnection recovery']
