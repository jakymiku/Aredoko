"""Remaining native shelf actions, generated-only; old create/rename flow is not replayed."""
import time


def audit(ui,tree,shot,check,cat,first,a,b):
    initial_count=cat.search()['total']
    def saved(name,predicate):
        end=time.monotonic()+12
        while time.monotonic()<end:
            if predicate():check(name,True);return
            time.sleep(.1)
        check(name,False)
    def more_delete(shelf):
        ui('invoke','ShelfMore'+str(shelf));ui('wait-for','ShelfDelete'+str(shelf),'-t','5000')
        ui('invoke','ShelfDelete'+str(shelf));ui('wait-for','CloseButton','-t','5000')
    ui('invoke','NavShelf');ui('wait-for','ShelfOpen'+str(a),'-t','10000')
    ui('invoke','BtnShelfLayout');ui('wait-for','ShelfOpen'+str(a),'-t','5000');shot('shelf-grid')
    check('three generated shelves shown',len([key for key in tree() if key.startswith('ShelfRow')])==3)
    ui('invoke','ShelfOpen'+str(a));ui('wait-for','TxtCount','--value','1 件','-t','10000')
    ui('wait-for','Item'+str(first),'-t','5000');ui('invoke','Item'+str(first),'--action','select')
    ui('wait-for','BtnChooseShelves','-p','IsEnabled','--value','True','-t','5000');ui('invoke','BtnChooseShelves')
    ui('wait-for','ChooseShelf'+str(a),'-t','5000');ui('click','ChooseShelf'+str(a))
    ui('invoke','PrimaryButton');ui('wait-for','ChooseShelfList','--gone','-t','5000');ui('invoke','BtnSave')
    saved('remove only selected membership',lambda:cat.get(first)['shelf_ids']==[b])
    ui('wait-for','TxtCount','--value','0 件','-t','10000');ui('wait-for','TxtEmpty','--value','この棚には作品がありません。作品の詳細で所属する棚を選択できます。','-t','5000');shot('empty-scoped-shelf')
    ui('invoke','BtnShelfList');ui('wait-for','ShelfMore'+str(b),'-t','10000');more_delete(b)
    ui('invoke','CloseButton');ui('wait-for','CloseButton','--gone','-t','5000')
    check('cancelled deletion keeps shelf and membership',cat.get(first)['shelf_ids']==[b] and any(x['id']==b for x in cat.shelf_descriptors()))
    more_delete(b);ui('invoke','PrimaryButton');ui('wait-for','CloseButton','--gone','-t','5000')
    saved('delete only shelf membership, keep media',lambda:cat.get(first)['shelf_ids']==[] and not any(x['id']==b for x in cat.shelf_descriptors()))
    ui('wait-for','ShelfOpen'+str(a),'-t','5000');shot('after-shelf-delete')
    ui('invoke','ShelfOpen'+str(a));ui('wait-for','TxtCount','--value','0 件','-t','10000')
    ui('invoke','BtnClearShelfScope');ui('wait-for','TxtCount','--value',f'{initial_count} 件','-t','10000')
    check('clear shelf scope restores all rows',cat.search()['total']==initial_count)
