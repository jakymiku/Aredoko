"""Favorite folder menu over generated roots; no shell or private data access."""
from native_ui_tools import inspect_element


def prepare(catalog,target,*,file_favorite=True):
    first=next(row for row in catalog.search()['items'] if row['title']=='image-0.png')['id']
    root=catalog.registered_roots()[0]['id'];extra=target/'extra-favorite-root';extra.mkdir()
    second=catalog.add_root(str(extra));catalog.set_root_favorite(root,True);catalog.set_root_favorite(second,True)
    catalog.update([first],{'favorite':file_favorite})
    return {'first':first,'roots':[root,second]}


def audit(ui,tree,shot,report,check,catalog,*,remaining=False):
    fixture=report['favorite_root_fixture'];first=fixture['first'];a,b=fixture['roots']
    def ready(total):
        ui('wait-for','TxtCount','--value',f'{total} 件','-t','10000');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
    def menu(root):
        ui('invoke','FavoriteRootActions'+str(root));ui('wait-for','FavoriteRootManage'+str(root),'-t','10000')
    ui('invoke','NavFavorites');ready(0 if remaining else 1)
    if not remaining:
        ui('invoke','Item'+str(first),'--action','select');ui('invoke','BtnDetails');ui('wait-for','TxtTags','-t','10000')
        ui('set-value','TxtTags','favorite-folder-draft');menu(a);shot('favorite-folder-menu')
        ui('invoke','FavoriteRootManage'+str(a));ui('wait-for','CloseButton','-t','10000');ui('invoke','CloseButton')
        ui('wait-for','TxtTags','--value','favorite-folder-draft','-t','10000')
        check('cancelled folder settings keeps the unsaved item tag',catalog.get(first)['tags']==[])
        ui('set-value','TxtTags','');menu(a);ui('invoke','FavoriteRootManage'+str(a))
        ui('wait-for','TxtFolderTargetTitle','--value','media','--contains','-t','10000');shot('favorite-folder-settings')
        check('folder settings opens directly from favorites',True)
        ui('invoke','BtnCloseDetails');ui('invoke','NavAll');ready(2);ui('invoke','NavFavorites');ready(1)
        ui('invoke','Item'+str(first),'--action','select');ui('invoke','BtnDetails');ui('wait-for','ChkFavorite','-t','10000')
        ui('invoke','ChkFavorite','--action','toggle-off');ready(0)
    check('folder-only favorites gives a contextual empty message','上のお気に入りフォルダ' in inspect_element(ui,'TxtEmpty')['name'])
    for root in (a,b):
        menu(root);ui('invoke','FavoriteRootRemove'+str(root));ui('wait-for','FavoriteRootActions'+str(root),'--gone','-t','10000');ready(0)
    state=tree();check('last favorite folder hides the folder area','FavoriteRootArea' not in state or state['FavoriteRootArea']['isOffscreen'])
    check('last folder removal restores the ordinary empty guidance','上のお気に入りフォルダ' not in inspect_element(ui,'TxtEmpty')['name'])
    roots={row['id']:row for row in catalog.registered_roots()}
    check('removal keeps both roots registered and all media',all(roots[root]['enabled'] and not roots[root]['favorite'] for root in (a,b)) and catalog.search()['total']==2)
    check('item draft was never saved and favorite removal persisted',catalog.get(first)['tags']==[] and not catalog.get(first)['favorite'])
    shot('favorite-folders-removed')
    report['physical_input_requested']=False
    report['unverified']=['physical right click/keyboard','high contrast/physical DPI','native model placement wording','recycling across many favorite folders']
