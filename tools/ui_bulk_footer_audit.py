"""One UIA-only audit of the library multi-selection footer."""
import subprocess


def audit(ui, tree, shot, report, check, catalog, hwnd):
    rows = catalog.search()['items'][:2]
    ids = [row['id'] for row in rows]
    ui('invoke', 'Item' + str(ids[0]), '--action', 'select')
    ui('wait-for', 'FooterSelection', '--value', '1 件選択', '-t', '10000')
    # UIA SelectionItem.AddToSelection is semantic and does not send keyboard or pointer input.
    script = '''Add-Type -AssemblyName UIAutomationClient
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]::new(%d))
$condition = [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'Item%d')
$item = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
if ($null -eq $item) { throw 'Owned item not found' }
$pattern = $item.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
$pattern.AddToSelection()
''' % (int(hwnd), ids[1])
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                   check=True, capture_output=True, text=True, timeout=15)
    ui('wait-for', 'FooterSelection', '--value', '2 件選択', '-t', '10000')
    ui('wait-for', 'SelectionBulkActions', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
    ui('wait-for', 'ClearLibrarySelection', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
    check('duplicate footer bulk bar stays hidden', 'FooterBulkActions' not in tree())
    shot('bulk-footer-selected')
    ui('invoke', 'SelectionBulkActions')
    ui('wait-for', 'BulkFavoriteAdd', '--value', 'お気に入りに登録', '-t', '10000')
    ui('wait-for', 'BulkShelfAdd', '--value', '棚に追加…', '-t', '10000')
    check('floating selection pill menu exposes existing favorite and shelf actions', True)
    shot('bulk-footer-menu')
    ui('invoke', 'BulkFavoriteAdd')
    ui('wait-for', 'SelectionInlineStatus', '--value', '保存しました', '--contains', '-t', '20000')
    check('bulk favorite saves the selected pair', all(catalog.get(item)['favorite'] for item in ids))
    ui('wait-for', 'FooterSelection', '--value', '2 件選択', '-t', '10000')
    check('bulk favorite keeps selection', True)
    ui('invoke', 'SelectionBulkActions')
    ui('wait-for', 'BulkShelfAdd', '-t', '10000')
    ui('invoke', 'BulkShelfAdd')
    ui('wait-for', 'CloseButton', '-t', '10000')
    ui('invoke', 'CloseButton')
    ui('wait-for', 'FooterSelection', '--value', '2 件選択', '-t', '10000')
    check('cancelled shelf choice keeps the selected pair', all(catalog.get(item)['favorite'] for item in ids))
    ui('invoke', 'ClearLibrarySelection')
    ui('wait-for', 'FooterSelection', '--gone', '-t', '10000')
    check('selection clear removes the multi-selection', True)
    shot('bulk-footer-cleared')
    report['physical_input_requested'] = False
    report['unverified'] = ['physical keyboard and pointer input', 'high contrast and physical DPI', 'real user data']
