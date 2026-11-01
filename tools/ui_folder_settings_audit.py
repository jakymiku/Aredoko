"""Folder settings hierarchy and draft safety on a generated catalog only."""
import json

from native_ui_tools import inspect_element, nodes


def prepare(catalog, target, *, remaining=False):
    first = catalog.registered_roots()[0]['id']
    extra = target / 'folder-settings-empty-root'
    extra.mkdir()
    second = catalog.add_root(str(extra))
    catalog.set_root_shelf(first, '')
    shelf_a = catalog.shelf_store.create('監査用の棚A')
    shelf_b = catalog.shelf_store.create('監査用の棚B')
    catalog.set_root_shelf(second, '監査用の棚B')
    if remaining:
        catalog.set_root_shelf(first, '監査用の新しい棚')
        catalog.set_excludes(first, ['cache','*.tmp'])
    return {'roots': [first, second], 'shelves': [shelf_a, shelf_b], 'default_excludes': catalog.registered_roots()[0]['excludes']}


def audit(ui, tree, shot, report, check, catalog, *, remaining=False):
    first, second = report['folder_settings_fixture']['roots']
    saved_excludes=list(dict.fromkeys([*report['folder_settings_fixture']['default_excludes'],'cache','*.tmp']))
    def wait(identifier, value):
        ui('wait-for', identifier, '--value', value, '--contains', '-t', '10000')
    def show(identifier):
        ui('scroll-into-view', identifier)
    def expand(identifier):
        show(identifier)
        ui('invoke', identifier, '--action', 'expand')
    def choose_new_shelf():
        show('RootInitialShelf')
        ui('invoke', 'RootInitialShelf', '--action', 'expand')
        state = json.loads(ui('inspect', '--depth', '18', '--json'))
        choices = {n['selector'] for n in nodes(state)
                   if n.get('type') in ('ListItem', 'ComboBoxItem')
                   and n.get('name') == '新しい棚を作成' and n.get('selector')
                   and not n.get('isOffscreen', True)}
        if len(choices) != 1:
            raise RuntimeError('Expected one visible new-shelf option')
        ui('invoke', choices.pop(), '--action', 'select')
        state = json.loads(ui('inspect', '--depth', '18', '--json'))
        combos = {n['selector'] for n in nodes(state)
                  if n.get('type') == 'ComboBox' and n.get('automationId') == 'RootInitialShelf'
                  and n.get('selector') and not n.get('isOffscreen', True)}
        if len(combos) != 1:
            raise RuntimeError('Expected one visible initial-shelf combo')
        ui('invoke', combos.pop(), '--action', 'collapse')
    def roots():
        return {row['id']: row for row in catalog.registered_roots()}

    ui('invoke', 'BtnRoots')
    ui('wait-for','LibraryHeading','--value','登録フォルダ','-t','10000')
    ui('wait-for','FolderList','-p','IsOffscreen','--value','False','-t','10000')
    ui('wait-for', 'ConfigFolder' + str(first), '-t', '10000')
    ui('invoke', 'ConfigFolder' + str(first))
    ui('wait-for', 'ScanRoot', '-t', '10000')
    if not remaining:
        check('single folder exposes scan and starts with settings sections collapsed',
              not inspect_element(ui, 'ScanRoot')['isOffscreen'] and
              all(inspect_element(ui, section).get('expandState') == 'collapsed'
                  for section in ('RootShelfSettings', 'RootExclusionsSection', 'RootStartupSection', 'RootRemovalSection')))
        shot('folder-settings-initial')

        expand('RootShelfSettings')
        choose_new_shelf()
        ui('set-value', 'RootNewShelf', '監査用の新しい棚')
        show('FillUnsetShelf'); ui('invoke', 'FillUnsetShelf', '--action', 'toggle-on')
        expand('RootExclusionsSection')
        ui('set-value', 'RootExcludes', 'cache, *.tmp')
        show('SaveExcludes'); ui('invoke', 'SaveExcludes')
        wait('TxtFolderEditStatus', '除外ルールを保存しました')
        ui('wait-for', 'SaveExcludes', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        show('RootNewShelf')
        wait('RootNewShelf', '監査用の新しい棚')
        ui('wait-for', 'FillUnsetShelf', '--value', 'On', '-t', '10000')
        check('exclusion save retains new shelf and fill draft and persists exclusions',
              roots()[first]['excludes'] == saved_excludes and not roots()[first]['shelf_ids'])

        show('RootExcludes'); ui('set-value', 'RootExcludes', 'cache, *.tmp, pending')
        show('SaveRootShelf'); ui('invoke', 'SaveRootShelf')
        ui('wait-for', 'SaveRootShelf', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        wait('TxtFolderEditStatus', '未保存')
        check('shelf section remains expanded after saving', inspect_element(ui, 'RootShelfSettings').get('expandState') == 'expanded')
        saved = roots()[first]
        new_shelf = next(row['id'] for row in catalog.shelf_descriptors() if row['name'] == '監査用の新しい棚')
        check('shelf membership is saved while exclusion edits remain pending',
              saved['shelf_ids'] == [new_shelf] and saved['excludes'] == saved_excludes)
        show('RootExcludes'); wait('RootExcludes', 'cache, *.tmp, pending')
        shot('folder-settings-pending-exclusion')

    else:
        expand('RootShelfSettings'); expand('RootExclusionsSection')
        ui('set-value','RootExcludes','cache, *.tmp, pending')
        new_shelf=next(row['id'] for row in catalog.shelf_descriptors() if row['name']=='監査用の新しい棚')
    ui('invoke', 'BtnCloseDetails')
    ui('invoke', 'ConfigFolder' + str(first))
    show('RootExcludes'); wait('RootExcludes', 'cache, *.tmp, pending')
    wait('TxtFolderEditStatus', '未保存')
    check('hiding and same-folder settings re-entry keeps the draft', roots()[first]['excludes'] == saved_excludes)
    ui('invoke','ConfigFolder'+str(second))
    ui('wait-for','CloseButton','-t','10000');ui('invoke','CloseButton')
    show('RootExcludes');wait('RootExcludes','cache, *.tmp, pending')
    check('cancelled folder switch retains the unsaved exclusion draft',True)
    shot('folder-settings-retained-draft')
    ui('invoke','ConfigFolder'+str(second));ui('wait-for','PrimaryButton','-t','10000');ui('invoke','PrimaryButton')
    wait('TxtFolderTargetTitle','folder-settings-empty-root')
    ui('invoke','BtnCloseDetails')
    ui('invoke', 'ChkFolder' + str(first), '--action', 'toggle-on')
    ui('invoke', 'ChkFolder' + str(second), '--action', 'toggle-on')
    ui('invoke', 'BtnEditSelectedFolders')
    wait('TxtCurrentShelfSummary', '複数の設定値')
    check('batch settings keep mixed shelves and open the shelf section',
          inspect_element(ui, 'RootShelfSettings').get('expandState') == 'expanded' and
          roots()[first]['shelf_ids'] == [new_shelf] and bool(roots()[second]['shelf_ids']))
    shot('folder-settings-batch')
    report['physical_input_requested'] = False
    report['unverified'] = ['physical keyboard and pointer input', 'high contrast and physical DPI', 'real user folders']
