"""Generated-only native shelf filtering and explicit save/cancel checks."""
from native_ui_tools import inspect_element


def prepare(catalog):
    shelves=[catalog.change_shelf('create',name=f'整理 {i:03}')['id'] for i in range(73)]
    background=catalog.change_shelf('create',name='背景資料')['id']
    sound=catalog.change_shelf('create',name='音声素材')['id']
    row=next(row for row in catalog.search()['items'] if row['title']=='image-0.png')
    initial=sorted([shelves[0],background])
    catalog.change_shelf('assign',entity='item',object_ids=[row['id']],shelf_ids=initial)
    return {'item':row['id'],'initial':initial,'sound':sound,'background':background}


def audit(ui,tree,shot,report,check,catalog):
    fixture=report['shelf_filter_fixture'];item=fixture['item'];initial=fixture['initial'];sound=fixture['sound']
    def count(value):ui('wait-for','ChooseShelfSelectionCount','--value',value,'-t','10000')
    def open_picker():
        ui('invoke','BtnChooseShelves');ui('wait-for','ChooseShelfFilter','-t','10000')
        count('75 件を表示・2 件を選択')
    def add_filtered():
        ui('set-value','ChooseShelfFilter','音声');count('1 件を表示・2 件を選択（表示外 2 件）')
        ui('invoke','ChooseShelf'+str(sound),'--action','select');count('1 件を表示・3 件を選択（表示外 2 件）')
    ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    ui('invoke','Item'+str(item),'--action','select');ui('invoke','BtnDetails');ui('wait-for','BtnChooseShelves','-p','IsEnabled','--value','True','-t','10000')
    ui('set-value','TxtTags','shelf-filter-draft');open_picker()
    ui('set-value','ChooseShelfFilter','no-such-shelf');count('0 件を表示・2 件を選択（表示外 2 件）')
    shot('shelf-filter-empty');add_filtered();shot('shelf-filter-hidden-selection')
    ui('invoke','CloseButton');ui('wait-for','ChooseShelfList','--gone','-t','10000')
    check('cancel keeps stored memberships and does not save the tag',catalog.get(item)['shelf_ids']==initial and catalog.get(item)['tags']==[])
    check('cancel keeps the unsaved tag',inspect_element(ui,'TxtTags')['value']=='shelf-filter-draft')
    open_picker();add_filtered();ui('invoke','PrimaryButton');ui('wait-for','ChooseShelfList','--gone','-t','10000')
    check('apply changes only the draft before explicit save',catalog.get(item)['shelf_ids']==initial and catalog.get(item)['tags']==[])
    ui('invoke','BtnSave');ui('wait-for','TxtEditStatus','--value','保存済み','-t','10000')
    expected=sorted(initial+[sound]);check('save preserves hidden memberships and adds the filtered shelf',catalog.get(item)['shelf_ids']==expected and catalog.get(item)['tags']==['shelf-filter-draft'])
    ui('invoke','BtnChooseShelves');ui('wait-for','ChooseShelfFilter','-t','10000');count('75 件を表示・3 件を選択')
    ui('set-value','ChooseShelfFilter','背景');count('1 件を表示・3 件を選択（表示外 2 件）');shot('shelf-filter-saved')
    ui('invoke','PrimaryButton');ui('wait-for','ChooseShelfList','--gone','-t','10000')
    check('filter-only apply keeps every stored membership',catalog.get(item)['shelf_ids']==expected)
    report['physical_input_requested']=False
    report['unverified']=['physical keyboard/hover','high contrast/physical DPI','initial folder and batch shelf routes','64-shelf limit via real input']
