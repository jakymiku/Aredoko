"""Mixed generated media only: geometry and editing through the native toolbar."""

def audit(ui,tree,shot,report,check,catalog,first_id,*,input_guard,uia_only=False,resize=None,wrap_only=False):
    report['authorization']='Explicit GUI approval required: generated mixed media, no playback/GPU/models'
    def geometry(name):
        state=tree();query=state['TxtQuery'];kind=state['CmbKind'];mode=state['CmbSearchMode'];actions=[state[key] for key in ('BtnLayout','BtnItemSize','BtnDetails')]
        check(name+': search controls have accessible names',all(state[key].get('name') for key in ('TxtQuery','CmbKind','CmbSearchMode')))
        check(name+': toolbar buttons visible',all(not row.get('isOffscreen') and row.get('width',0)>0 for row in actions))
        check(name+': filters do not overlap',kind['x']+kind['width']<=mode['x']+1)
        # The measured layout may be inline or wrap once; neither may overlap.
        # ComboBox UIA bounds include focus padding around its visual button.
        # Same-row controls overlap vertically; their top edges need not match.
        inline=max(actions[0]['y'],mode['y'])<min(actions[0]['y']+actions[0]['height'],mode['y']+mode['height'])
        check(name+': view actions have their own space',actions[0]['x']>=mode['x']+mode['width']-1 if inline else actions[0]['y']+actions[0]['height']<=mode['y']+1 or actions[0]['y']>=mode['y']+mode['height']-1)
        check(name+': query remains usable',query['width']>=180)
        check(name+': list starts below the search inputs',state['ItemList']['y']>=max(query['y']+query['height'],mode['y']+mode['height'])-1)
        check(name+': list starts below toolbar',state['ItemList']['y']>=max(row['y']+row['height'] for row in actions)-1)
        report.setdefault('toolbar_geometry',{})[name]={'query_height':query['height'],
            'query_to_list_gap':state['ItemList']['y']-query['y']-query['height'],
            'list_height':state['ItemList']['height'],'actions_inline':inline}
    if wrap_only:
        from native_ui_tools import select_combo_item
        for nav,heading in [('NavFolders','登録フォルダ'),('NavShelf','棚')]:
            ui('invoke',nav);ui('wait-for','LibraryHeading','--value',heading,'-t','10000')
            state=tree()
            check(heading+': library view actions hidden',all(k not in state or state[k].get('isOffscreen',True) for k in ('BtnLayout','BtnItemSize','BtnDetails')))
        ui('invoke','NavAll');ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
        ui('invoke','Item'+str(first_id),'--action','select');ui('invoke','BtnDetails')
        ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
        select_combo_item(ui,'CmbSearchMode','ModeText')
        for width in (1600,1100):
            resize(width,820);geometry('width-'+str(width));shot('width-'+str(width))
        ui('invoke','BtnCloseDetails');select_combo_item(ui,'CmbSearchMode','ModeLiteral');resize(1200,820)
        ui('wait-for','Item'+str(first_id),'-t','10000')
        check('search mode returns to literal with generated results',True)
        report['physical_input_requested']=False
        return
    for row in catalog.search()['items']:
        if row['kind']=='audio':
            ui('wait-for','PreviewPlaceholder'+str(row['id']),'-t','10000')
            check('audio without artwork has a named media icon',not tree()['PreviewPlaceholder'+str(row['id'])]['isOffscreen'])
        elif row['kind']=='image':
            ui('wait-for','PreviewStatus'+str(row['id']),'--gone','-t','10000')
            state=tree();key='PreviewPlaceholder'+str(row['id'])
            check('decoded image keeps real artwork instead of placeholder',key not in state or state[key]['isOffscreen'])
    geometry('full-width');shot('compact-toolbar')
    report['physical_input_requested']=not uia_only
    if uia_only:ui('invoke','Item'+str(first_id),'--action','select')
    else:
        if not input_guard():raise RuntimeError('Owned toolbar test lost foreground; no pointer input sent')
        ui('click','ItemTitle'+str(first_id))
    ui('wait-for','BtnDetails','-p','IsEnabled','--value','True','-t','10000');ui('invoke','BtnDetails')
    ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
    geometry('details-open');shot('compact-toolbar-details')
    ui('set-value','TxtTags','toolbar-generated-draft');ui('invoke','BtnLayout')
    ui('wait-for','TxtTags','--value','toolbar-generated-draft','-t','10000')
    check('switching layout retains the unsaved tag',True);geometry('grid-details');shot('compact-toolbar-grid')
    state=tree()
    # This fixture initially fits as a list. Switching to a taller tile layout
    # must retain the beginning, not reinterpret its zero offset as the end.
    check('grid switch keeps the first thumbnail fully visible',state['Preview'+str(first_id)]['height']>=state['Preview3']['height']-1)
    ui('invoke','BtnSave');ui('wait-for','BtnSave','-p','IsEnabled','--value','False','-t','10000')
    check('save reaches only the selected generated item',catalog.get(first_id)['tags']==['toolbar-generated-draft'])
