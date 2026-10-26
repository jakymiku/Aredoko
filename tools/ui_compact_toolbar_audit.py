"""Mixed generated media only: geometry and editing through the native toolbar."""

def audit(ui,tree,shot,report,check,catalog,first_id,*,input_guard):
    report['authorization']='Explicit GUI approval required: generated mixed media, no playback/GPU/models'
    def geometry(name):
        state=tree();query=state['TxtQuery'];kind=state['CmbKind'];mode=state['CmbSearchMode'];actions=[state[key] for key in ('BtnLayout','BtnItemSize','BtnDetails')]
        check(name+': search controls have accessible names',all(state[key].get('name') for key in ('TxtQuery','CmbKind','CmbSearchMode')))
        check(name+': toolbar buttons visible',all(not row.get('isOffscreen') and row.get('width',0)>0 for row in actions))
        check(name+': filters do not overlap',kind['x']+kind['width']<=mode['x']+1)
        # The measured layout may be inline or wrap once; neither may overlap.
        inline=abs(actions[0]['y']-mode['y'])<=2
        check(name+': view actions have their own space',actions[0]['x']>=mode['x']+mode['width']-1 if inline else actions[0]['y']>=mode['y']+mode['height']-1)
        check(name+': list starts below toolbar',state['ItemList']['y']>=max(row['y']+row['height'] for row in actions)-1)
        report.setdefault('toolbar_geometry',{})[name]={'query_height':query['height'],
            'query_to_list_gap':state['ItemList']['y']-query['y']-query['height'],
            'list_height':state['ItemList']['height'],'actions_inline':inline}
    geometry('full-width');shot('compact-toolbar')
    if not input_guard():raise RuntimeError('Owned toolbar test lost foreground; no pointer input sent')
    ui('click','ItemTitle'+str(first_id));ui('wait-for','BtnDetails','-p','IsEnabled','--value','True','-t','10000');ui('invoke','BtnDetails')
    ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
    geometry('details-open');shot('compact-toolbar-details')
    ui('set-value','TxtTags','toolbar-generated-draft');ui('invoke','BtnLayout')
    ui('wait-for','TxtTags','--value','toolbar-generated-draft','-t','10000')
    check('switching layout retains the unsaved tag',True);geometry('grid-details');shot('compact-toolbar-grid')
    ui('invoke','BtnSave');ui('wait-for','BtnSave','-p','IsEnabled','--value','False','-t','10000')
    check('save reaches only the selected generated item',catalog.get(first_id)['tags']==['toolbar-generated-draft'])
