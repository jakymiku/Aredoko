"""Generated-session UIA audit of persistent settings save feedback."""
import json
from native_ui_tools import inspect_element, nodes


def audit(ui, shot, report, check):
    ui('invoke', 'BtnSettings')
    ui('wait-for', 'SettingsDoubleClickViewer', '-t', '10000')
    ui('wait-for','SettingsTheme','--value','ライト' if report['theme']=='light' else 'ダーク','-t','10000')
    ui('scroll', 'SettingsScroll', '--to', 'top')
    combo = 'SettingsDoubleClickViewer'
    choice = 'Windowsの既定アプリ'
    ui('invoke', combo, '--action', 'expand')
    state = json.loads(ui('inspect', '--depth', '18', '--json'))
    options = {n['selector'] for n in nodes(state)
               if n.get('type') in ('ListItem', 'ComboBoxItem') and n.get('name') == choice
               and n.get('selector') and not n.get('isOffscreen', True)}
    if len(options) != 1:
        raise RuntimeError('Expected one visible viewer option')
    ui('invoke', options.pop(), '--action', 'select')
    state = json.loads(ui('inspect', '--depth', '18', '--json'))
    combos = {n['selector'] for n in nodes(state)
              if n.get('type') == 'ComboBox' and n.get('automationId') == combo
              and n.get('selector') and not n.get('isOffscreen', True)}
    if len(combos) != 1:
        raise RuntimeError('Expected one visible viewer combo')
    ui('invoke', combos.pop(), '--action', 'collapse')
    ui('invoke', 'SettingsSave')
    ui('wait-for', 'SettingsStatus', '--value', '保存しました', '--contains', '-t', '10000')
    ui('wait-for', 'SettingsSave', '-p', 'IsEnabled', '--value', 'True', '-t', '10000')

    def feedback_position(label):
        scroll = inspect_element(ui, 'SettingsScroll')
        status = inspect_element(ui, 'SettingsStatus')
        save = inspect_element(ui, 'SettingsSave')
        close = inspect_element(ui, 'CloseButton')
        check(label, not status['isOffscreen'] and status['height'] > 0
              and status['y'] >= scroll['y'] + scroll['height']
              and status['y'] + status['height'] <= min(save['y'], close['y']))

    feedback_position('save feedback stays between settings content and native footer at top')
    shot('settings-feedback-top')
    ui('scroll', 'SettingsScroll', '--to', 'bottom')
    feedback_position('save feedback remains visible at bottom')
    shot('settings-feedback-bottom')
    ui('scroll', 'SettingsScroll', '--to', 'top')
    feedback_position('save feedback remains visible after returning to top')
    ui('invoke', 'CloseButton'); ui('wait-for', 'SettingsDialog', '--gone', '-t', '10000')
    ui('invoke', 'BtnSettings'); ui('wait-for', combo, '--value', choice, '--contains', '-t', '10000')
    check('saved viewer preference persists when settings reopen', True)
    ui('invoke', 'CloseButton'); ui('wait-for', 'SettingsDialog', '--gone', '-t', '10000')
    report['physical_input_requested'] = False
    report['unverified'] = ['physical keyboard and pointer input', 'high contrast and physical DPI']
