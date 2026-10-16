"""Open a named production tool through the owned app's native overflow menu."""
import json
import time

TOOL_IDS = frozenset(('BtnAIIndex', 'BtnRelatedTerms'))

def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)

def invoke_tool(cli, app_pid, hwnd, identifier):
    if identifier not in TOOL_IDS:
        raise ValueError('Unknown production tool')
    cli('ui', 'invoke', 'BtnTools', '-w', hwnd)
    for _ in range(20):
        windows = json.loads(cli('ui', 'list-windows', '-a', app_pid, '--json'))
        for window in windows:
            handle = str(window.get('hwnd', ''))
            if not handle or handle == '0':
                continue
            try:
                tree = json.loads(cli('ui', 'inspect', '--json', '--depth', '12', '-w', handle))
            except RuntimeError as ex:
                if 'AppNotFoundException' in str(ex):
                    continue
                raise
            if any(n.get('automationId') == identifier and not n.get('isOffscreen', True) for n in nodes(tree)):
                return cli('ui', 'invoke', identifier, '-w', handle)
        time.sleep(.1)
    raise RuntimeError('Production tool was not visible in the owned menu: ' + identifier)
