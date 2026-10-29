"""Small generated-only feedback and popup lifecycle scenario, UIA only."""
from native_ui_tools import inspect_element, select_combo_item


def audit(ui,tree,shot,report,check):
    def ready():ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    def menu_hidden(label):
        state=tree();check(label,'BtnReconnect' not in state or state['BtnReconnect']['isOffscreen'])
    def mode(identifier):
        select_combo_item(ui,'CmbSearchMode',identifier)
        ui('invoke','BtnSearch')
    ui('invoke','BrowseActions');ui('wait-for','BtnReconnect','-t','5000')
    ui('set-value','TxtQuery','no-such-filename');ui('invoke','BtnSearch');ready()
    ui('wait-for','TxtCount','--value','0 件','-t','10000')
    text=inspect_element(ui,'TxtEmpty')['name']
    check('literal miss explains file-name/tag search instead of AI indexing','ファイル名・タグに一致する作品はありません' in text and 'AI索引' not in text)
    menu_hidden('new query dismisses the browse popup');shot('literal-empty-guidance')
    mode('ModeSemantic');ui('wait-for','TxtCount','--value','—','-t','10000')
    ui('wait-for','TxtEmpty','--value','AI','--contains','-t','10000');text=inspect_element(ui,'TxtEmpty')['name']
    check('unavailable AI keeps its setup guidance','AI' in text and '設定' in text);shot('ai-unavailable-guidance')
    mode('ModeLiteral');ready();ui('wait-for','TxtCount','--value','0 件','-t','10000')
    check('return to literal search clears the misleading AI guidance','AI索引' not in inspect_element(ui,'TxtEmpty')['name'])
    ui('set-value','TxtQuery','image-0.png');ui('invoke','BtnSearch');ready();ui('wait-for','TxtCount','--value','1 件','-t','10000')
    ui('invoke','BrowseActions');ui('wait-for','BtnReconnect','-t','5000');ui('invoke','BtnRoots')
    ui('wait-for','TxtFolderFilter','-t','10000');menu_hidden('direct folder header navigation dismisses the browse popup')
    ui('invoke','BtnRoots');ready();ui('wait-for','TxtCount','--value','1 件','-t','10000')
    check('return from folders retains the filename query',inspect_element(ui,'TxtQuery')['value']=='image-0.png')
    ui('invoke','BrowseActions');ui('wait-for','BtnReconnect','-t','5000');ui('invoke','NavShelf')
    ui('wait-for','TxtShelfHubMessage','--value','棚を作成','--contains','-t','10000');menu_hidden('shelf navigation dismisses the browse popup')
    ui('invoke','NavAll');ready();ui('wait-for','TxtCount','--value','1 件','-t','10000');shot('literal-return')
    report['physical_input_requested']=False
    report['unverified']=['physical keyboard/hover','high contrast and physical DPI','real AI indexing/inference']
