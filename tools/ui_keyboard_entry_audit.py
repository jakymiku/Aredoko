"""Bounded real Enter keys to the owned window and generated registration only."""
import hashlib
import time
from pathlib import Path
from create_preview_fixture import png


def audit(ui,shot,report,check,handler,catalog,target,*,input_guard):
    report['physical_input_requested']=True
    report['authorization']='Current user permits GUI tests after ComfyUI processing; generated data and owned-window Enter keys only'
    calls=[];original=handler.results.provider
    def provider(*args,**kwargs):
        calls.append(1)
        return original(*args,**kwargs)
    handler.results.provider=provider
    try:
        ui('focus','TxtQuery')
        if not input_guard():raise RuntimeError('Owned window is not foreground; no search key sent')
        ui('send-keys','ctrl+enter','--via','send-input')
        time.sleep(.4)
        check('modified Enter does not submit an unchanged query',not calls)
        if not input_guard():raise RuntimeError('Owned window is not foreground; no search key sent')
        ui('send-keys','enter','--via','send-input')
        deadline=time.monotonic()+10
        while not calls and time.monotonic()<deadline:time.sleep(.05)
        check('plain Enter submits an unchanged query through the result provider',bool(calls))
        ui('wait-for','ItemList','-p','IsEnabled','--value','True','-t','10000')
        check('search keeps the generated library scope',catalog.search()['total']==2)
        ui('invoke','BtnRoots');ui('wait-for','LibraryHeading','--value','登録フォルダ','-t','10000')
        ui('invoke','BtnToggleAddFolder');ui('wait-for','RootPath','-t','10000')
        folder=target/'enter-registration';folder.mkdir()
        source=folder/'generated.png';source.write_bytes(png(width=32,height=32));before=hashlib.sha256(source.read_bytes()).hexdigest()
        ui('set-value','RootPath',str(folder));ui('focus','RootPath')
        if not input_guard():raise RuntimeError('Owned window is not foreground; no registration key sent')
        ui('send-keys','enter','--via','send-input')
        ui('wait-for','PostRegistrationScanDialog','-t','20000')
        ui('invoke','CloseButton');ui('wait-for','PostRegistrationScanDialog','--gone','-t','10000')
        ui('wait-for','AddRoot','-p','IsEnabled','--value','True','-t','10000')
        check('Enter registers the explicit generated folder',any(Path(r['path'])==folder for r in catalog.registered_roots()))
        check('post-registration later choice leaves media unscanned',catalog.search()['total']==2)
        check('generated registration original remains unchanged',hashlib.sha256(source.read_bytes()).hexdigest()==before)
        shot('keyboard-entry-complete')
        report['unverified']=['real Japanese IME candidate commit/cancellation','high contrast and DPI']
    finally:handler.results.provider=original
