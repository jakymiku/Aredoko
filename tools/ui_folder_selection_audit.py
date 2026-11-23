"""UIA-only file-properties and filtered folder-selection audit on generated data."""
from native_ui_tools import inspect_element, select_combo_item


def prepare(catalog, target):
    original = catalog.registered_roots()[0]['id']
    active_path = target / 'extra-active-xyz'; active_path.mkdir()
    inactive_path = target / 'extra-inactive-xyz'; inactive_path.mkdir()
    active = catalog.add_root(str(active_path))
    inactive = catalog.add_root(str(inactive_path))
    catalog.unregister_root(inactive)
    return {'original': original, 'active': active, 'inactive': inactive}


def audit(ui, tree, shot, report, check, catalog):
    fixture = report['folder_selection_fixture']
    original, active, inactive = (fixture[key] for key in ('original', 'active', 'inactive'))
    first = catalog.search()['items'][0]['id']
    ui('invoke', 'Item' + str(first), '--action', 'select')
    ui('invoke', 'BtnDetails')
    ui('scroll-into-view', 'FileProperties')
    ui('invoke', 'FileProperties', '--action', 'expand')
    for identifier in ('OpenFileLocation', 'CopySelectedFilePath'):
        ui('scroll-into-view', identifier)
        ui('wait-for', identifier, '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
        check(identifier + ' is available for a present item', not inspect_element(ui, identifier)['isOffscreen'])
    shot('file-properties-actions')
    ui('invoke', 'BtnCloseDetails')
    ui('invoke', 'BtnRoots')
    ui('wait-for', 'LibraryHeading', '--value', '登録フォルダ', '-t', '10000')
    ui('wait-for', 'FolderList', '-p', 'IsOffscreen', '--value', 'False', '-t', '10000')
    ui('wait-for', 'ChkFolder' + str(original), '-t', '10000')
    ui('invoke', 'ChkFolder' + str(original), '--action', 'toggle-on')
    select_combo_item(ui, 'CmbFolderState', 'FolderStateAll')
    ui('set-value', 'TxtFolderFilter', 'extra-')
    ui('wait-for', 'ChkFolder' + str(active), '-t', '10000')
    ui('wait-for', 'ChkFolder' + str(inactive), '-p', 'IsEnabled', '--value', 'False', '-t', '10000')
    ui('invoke', 'ConfigFolder' + str(active))
    ui('scroll-into-view', 'RootExclusionsSection')
    ui('invoke', 'RootExclusionsSection', '--action', 'expand')
    ui('set-value', 'RootExcludes', 'pending-audit')
    ui('wait-for', 'TxtFolderEditStatus', '--value', '未保存', '--contains', '-t', '10000')
    ui('invoke', 'FolderSelectionMenu'); ui('invoke', 'SelectVisibleFolders')
    ui('wait-for', 'ChkFolder' + str(active), '--value', 'On', '-t', '10000')
    ui('wait-for', 'TxtFolderSelectionSummary', '--value', '選択中: 2 フォルダ', '--contains', '-t', '10000')
    ui('wait-for', 'RootExcludes', '--value', 'pending-audit', '-t', '10000')
    check('select visible skips inactive and retains hidden selection and draft', True)
    shot('folder-filtered-select')
    ui('invoke', 'FolderSelectionMenu'); ui('invoke', 'DeselectVisibleFolders')
    ui('wait-for', 'ChkFolder' + str(active), '--value', 'Off', '-t', '10000')
    ui('wait-for', 'TxtFolderSelectionSummary', '--value', '選択中: 1 フォルダ', '--contains', '-t', '10000')
    ui('wait-for', 'RootExcludes', '--value', 'pending-audit', '-t', '10000')
    check('deselect visible retains the hidden selection and draft', True)
    ui('invoke', 'FolderSelectionMenu'); ui('invoke', 'ClearAllFolderSelections')
    ui('wait-for', 'TxtFolderSelectionSummary', '--value', 'フォルダを選ぶと', '--contains', '-t', '10000')
    ui('wait-for', 'RootExcludes', '--value', 'pending-audit', '-t', '10000')
    ui('invoke', 'BtnClearFolderFilters')
    ui('wait-for', 'ChkFolder' + str(original), '--value', 'Off', '-t', '10000')
    check('clear all removes the hidden selection without changing the draft', True)
    shot('folder-selection-cleared')
    report['physical_input_requested'] = False
    report['external_actions_invoked'] = False
    report['unverified'] = ['Explorer and clipboard actions', 'physical keyboard and pointer input', 'high contrast and physical DPI']
