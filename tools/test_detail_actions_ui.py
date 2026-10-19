"""Owned, generated-only current-payload UI checks (no AI inference).

Uses the existing development WinApp activation, isolated backend and settings.
Each invocation requires a NEW evidence directory. Never attaches to another app.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
import wave
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from create_preview_fixture import png
from native_ui_tools import nodes
from winapp_layout import layout, verify_deployment


def digest(folder):
    return {p.name: [hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns]
            for p in folder.iterdir() if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--daily-only',action='store_true',help='Audit list/grid/folders/settings/viewers using this same verified activation')
    parser.add_argument('--size-only',action='store_true',help='New user-authorized display-size feature flow')
    parser.add_argument('--quiet-only',action='store_true',help='User-requested viewer/footer and plain-language follow-up')
    parser.add_argument('--narrow',action='store_true',help='Explicit compact-window regression; normal desktop size is the default')
    args = parser.parse_args()
    if sum((args.size_only,args.daily_only,args.quiet_only))>1:parser.error('Select one flow')
    target = Path(os.path.abspath(args.output))
    if not target.is_relative_to(REPO / 'data/ai-ui'):
        parser.error('Evidence must be inside data/ai-ui')
    target.mkdir(parents=True, exist_ok=False)
    report = {'target': 'local', 'actual_model': False, 'pass': False, 'checks': [],
              'screenshots': [], 'visual_review': 'pending', 'themes': [],
              'source_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              'authorization': '2026-10-20 user explicitly requested continuing work and checking current UI'}
    env = {**os.environ, 'WINAPP_UI_WORKFLOW_ID': 'aredoko-detail-' + uuid.uuid4().hex}
    owned_pid = hwnd = cat = server = worker = None
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def check(name, condition):
        report['checks'].append({'name': name, 'pass': bool(condition)})
        print(json.dumps({'check': name, 'pass': bool(condition)}, ensure_ascii=False), flush=True)
        if not condition:
            raise AssertionError(name)

    def cli(*args):
        result = subprocess.run(['winapp', *map(str, args)], cwd=REPO, env=env,
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
        with (target / 'commands.log').open('a', encoding='utf-8') as log:
            log.write(json.dumps({'args': list(map(str, args)), 'exit': result.returncode, 'stdout': result.stdout,
                                  'stderr': result.stderr}, ensure_ascii=False) + '\n')
        if result.returncode:
            raise RuntimeError(result.stderr + result.stdout)
        return result.stdout

    def ui(*args):
        return cli('ui', *args, '-w', hwnd)

    def owned_window():
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(owner))
        if owner.value != owned_pid:
            raise RuntimeError('Window no longer belongs to this test')

    def close():
        nonlocal owned_pid, hwnd
        if not owned_pid:
            return
        owned_window()
        # The owner is disabled while a native viewer is open. On failure,
        # close only children verified to belong to this owned test PID first.
        for candidate in json.loads(cli('ui','list-windows','-a',owned_pid,'--json')):
            child=int(candidate.get('hwnd',0));owner=wintypes.DWORD()
            if not child or str(child)==str(hwnd) or candidate.get('title')=='PopupHost':continue
            user32.GetWindowThreadProcessId(child,ctypes.byref(owner))
            if owner.value==owned_pid:user32.PostMessageW(child,0x10,0,0)
        time.sleep(.3)
        handle = kernel32.OpenProcess(0x100000, False, owned_pid)
        if not handle:
            raise RuntimeError('Cannot observe owned test process')
        try:
            if not user32.PostMessageW(int(hwnd), 0x10, 0, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            check('owned app closes gracefully', kernel32.WaitForSingleObject(handle, 10000) == 0)
        finally:
            kernel32.CloseHandle(handle)
        owned_pid = hwnd = None

    def screenshot(name):
        path = target / (name + '.png')
        if path.exists():
            raise FileExistsError(path)
        ui('screenshot', '--output', path)
        check(name + ' screenshot delivered', path.is_file() and path.stat().st_size > 0)
        report['screenshots'].append(str(path))

    def inspect():
        tree = json.loads(ui('inspect', '--depth', '16', '--json'))
        return {n['automationId']: n for n in nodes(tree) if n.get('automationId')}

    try:
        probe = socket.socket()
        try:
            probe.bind(('127.0.0.1', 8769))
        finally:
            probe.close()
        existing = subprocess.run(['powershell', '-NoProfile', '-Command',
            'if(Get-Process Aredoko.WinUI -ErrorAction SilentlyContinue){exit 1}'], capture_output=True)
        check('no other Aredoko instance or occupied backend', existing.returncode == 0)
        media = target / 'media'
        media.mkdir()
        (media / 'image.png').write_bytes(png(width=6144 if args.quiet_only else 180,height=4096 if args.quiet_only else 240,color=(45,115,195)))
        if args.daily_only or args.size_only or args.quiet_only:(media/'second.png').write_bytes(png(color=(85,165,115)))
        with wave.open(str(media / 'audio.wav'), 'wb') as sound:
            sound.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            sound.writeframes(b'\0\0' * 16000)
        with zipfile.ZipFile(media / 'book.cbz', 'w') as book:
            book.writestr('page.png',png(width=4096 if args.quiet_only else 180,height=3072 if args.quiet_only else 240,color=(185,125,60)))
            if args.daily_only or args.size_only or args.quiet_only:
                book.writestr('page2.png',png(width=4096 if args.quiet_only else 180,height=3072 if args.quiet_only else 240,color=(135,155,195)))
                book.writestr('page3.png',png(color=(165,95,175)))
        if args.quiet_only:
            (media/'broken.jpg').write_bytes(b'not an image')
            ffmpeg=shutil.which('ffmpeg')
            if not ffmpeg:raise RuntimeError('Existing local FFmpeg is required; no download')
            subprocess.run([ffmpeg,'-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=1:d=30',
                '-threads','1','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(media/'clip.mp4')],check=True,timeout=20)
        before = digest(media)
        cat = ProductionCatalog(target / 'catalog.sqlite')
        root = cat.add_root(str(media))
        cat.start_scan(root)
        if cat._worker:
            cat._worker.join(10)
        rows = {row['title']: row for row in cat.search()['items']}
        check('only generated image/audio/book indexed', len(rows) == (6 if args.quiet_only else 4 if args.daily_only or args.size_only else 3))
        profiles = AIProfileSettings(REPO, target / 'ai-settings.json', profile_directory=target / 'profiles')
        handler = production_handler(cat, secrets.token_hex(32), ai=DisabledAI(),
                                     profiles=profiles, tagger=DisabledTagger())
        if args.quiet_only:
            # A bounded, controllable response delay verifies loading notices.
            # This wraps only our isolated fixture server, never real data.
            cat._ui_test_preview_gate=threading.Event();cat._ui_test_preview_gate.set()
            base_handler=handler
            class QuietHandler(base_handler):
                def do_GET(self):
                    if self.path==f"/api/library/preview/{rows['image.png']['id']}/original":
                        if not cat._ui_test_preview_gate.wait(20):return self.send(503,{'error':'Fixture delay timeout'})
                    return super().do_GET()
            handler=QuietHandler
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(('127.0.0.1', 8769), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        if args.size_only:
            (target/'viewer-settings.json').write_text('{"version":1,"wheel_up_advances":true}',encoding='utf-8')
        for theme in ('Light', 'Dark'):
            launch = json.loads(cli('run', REPO / 'src/Aredoko.WinUI/Aredoko.WinUI.csproj',
                '-c', 'Release', '--arch', 'x64', '-p', 'Platform=x64', '-p', 'SelfContained=true', '--no-build', '--no-restore',
                '--output-appx-directory', layout(), '--detach', '--json', '--',
                '--ui-theme', theme.lower(), '--viewer-settings', str(target / 'viewer-settings.json')))
            owned_pid = int(launch.get('ProcessId', 0))
            check(theme + ' development launch has local PID', owned_pid > 0 and launch.get('ProcessScope', 'local') == 'local')
            for _ in range(80):
                windows = json.loads(cli('ui', 'list-windows', '-a', owned_pid, '--json'))
                main_windows = [w for w in windows if w.get('title') and w['title'] != 'PopupHost']
                if len(main_windows) == 1:
                    hwnd = str(main_windows[0]['hwnd'])
                    break
                time.sleep(.1)
            if not hwnd:
                raise RuntimeError('No unique owned main window')
            owned_window()
            process = kernel32.OpenProcess(0x1000,False,owned_pid)
            if not process:raise RuntimeError('Cannot verify launched process image')
            try:
                buffer=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(buffer))
                if not kernel32.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(length)):
                    raise ctypes.WinError(ctypes.get_last_error())
                image=Path(buffer.value)
            finally:kernel32.CloseHandle(process)
            check(theme+' actual process uses expected current layout',image.parent==layout())
            report.setdefault('payloads', []).append({'image':str(image),'files':verify_deployment(image.parent)})
            width,height=(700,620) if args.narrow else (1200,820)
            if not user32.SetWindowPos(int(hwnd), None, 0, 0, width, height, 0x2 | 0x4 | 0x10):
                raise ctypes.WinError(ctypes.get_last_error())
            report['themes'].append({'theme': theme, 'width': width, 'height': height,
                                     'dpi': user32.GetDpiForWindow(int(hwnd)), 'pid': owned_pid})
            ui('wait-for','Item'+str(rows['image.png']['id']),'-t','15000')
            time.sleep(.3)
            navigation=inspect()['NavAll']
            check(theme+' startup navigation matches width',navigation['width']<=48 if args.narrow else navigation['width']>=140)
            if args.quiet_only:
                from ui_quiet_viewer_audit import audit
                audit(cli,hwnd,owned_pid,theme,rows,cat,target,report,check)
                close()
                continue
            if args.size_only:
                from ui_item_size_audit import audit
                audit(cli,hwnd,owned_pid,theme,rows,cat,target,report,check)
                close()
                continue
            if args.daily_only:
                from ui_daily_audit import audit
                audit(cli,hwnd,owned_pid,theme,rows,cat,target,report,check)
                close()
                continue
            for name, enabled in (('image.png', 'BtnOpenImage'), ('audio.wav', 'BtnOpenAudio'), ('book.cbz', 'BtnOpenBook')):
                current = inspect()
                if current.get('BtnCloseDetails') and not current['BtnCloseDetails'].get('isOffscreen', True):
                    ui('invoke', 'BtnCloseDetails')
                ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '15000')
                ui('set-value', 'TxtQuery', name)
                time.sleep(.7)
                ui('invoke', 'BtnSearch')
                ui('wait-for', 'ItemList', '-p', 'IsEnabled', '--value', 'True', '-t', '15000')
                ui('wait-for', 'Item' + str(rows[name]['id']), '-t', '10000')
                ui('invoke', 'Item' + str(rows[name]['id']), '--action', 'select')
                ui('invoke', 'BtnDetails')
                ui('wait-for', 'DetailScroll', '-t', '10000')
                ui('scroll', 'DetailScroll', '--to', 'top')
                identifiers = ('BtnOpenImage', 'BtnOpenVideo', 'BtnOpenAudio')
                required=tuple(dict.fromkeys((*identifiers,enabled)))
                for _ in range(12):
                    tree = inspect()
                    visible = all(tree.get(k) and not tree[k].get('isOffscreen', True)
                                  and tree[k]['height'] >= 32 and tree[k]['width'] >= (64 if k=='BtnOpenBook' else 80)
                                  and tree[k]['y'] >= tree['BtnCloseDetails']['y'] + tree['BtnCloseDetails']['height'] + 8
                                  and tree[k]['y'] + tree[k]['height'] <= tree['TxtEditStatus']['y'] - 12 for k in required)
                    if visible:
                        break
                    ui('scroll', 'DetailScroll', '--direction', 'down')
                ui('wait-for', enabled, '-p', 'IsEnabled', '--value', 'True', '-t', '10000')
                # UIA can return a clipped rectangle even with IsOffscreen=False.
                bounds = {key: tree.get(key) for key in required}
                report.setdefault('bounds', []).append({'theme': theme, 'item': name, 'buttons': bounds})
                check(theme + '/' + name + ' all open actions have full size', visible)
                scroll = tree['DetailScroll']
                check(theme + '/' + name + ' right-edge buttons inside scroll viewport', all(
                    b['x'] >= scroll['x'] and b['x'] + b['width'] <= scroll['x'] + scroll['width'] - 8
                    for b in bounds.values()))
                for button in identifiers:
                    ui('wait-for', button, '-p', 'IsEnabled', '--value',
                       'True' if button == enabled else 'False', '-t', '3000')
                if name == 'audio.wav':
                    ui('wait-for', 'AudioSearchHint', '--value', '自動索引は未対応', '--contains', '-t', '3000')
                    check(theme + ' accurate audio indexing hint', True)
                else:
                    check(theme + '/' + name + ' audio hint hidden', 'AudioSearchHint' not in tree or tree['AudioSearchHint'].get('isOffscreen', True))
                screenshot(theme + '-' + name.split('.')[0])
            close()
        check('generated sources unchanged in bytes and mtime', digest(media) == before)
        report['pass'] = all(check['pass'] for check in report['checks'])
    except Exception:
        report['error'] = traceback.format_exc()
        if hwnd:
            try:
                screenshot('failure')
            except Exception:
                pass
    finally:
        try:
            close()
        except Exception:
            report['cleanup_error'] = traceback.format_exc()
            report['pass'] = False
        try:
            cli('ui', 'yield')
        except Exception:
            report['yield_error'] = traceback.format_exc()
            report['pass'] = False
        if args.quiet_only and cat and hasattr(cat,'_ui_test_preview_gate'):cat._ui_test_preview_gate.set()
        if server:
            server.shutdown()
            server.server_close()
        if worker:
            worker.join(5)
        if cat:
            cat.close()
        (target / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report.get(k) for k in ('pass', 'error', 'cleanup_error')}, ensure_ascii=False), flush=True)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
