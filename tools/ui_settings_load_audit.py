"""UIA-only settings responsiveness with a bounded generated server gate."""
import threading


def audit(ui,shot,report,check,handler):
    entered=threading.Event();release=threading.Event();original=handler.do_GET
    def held(request):
        if request.path=='/api/library/ai/setup':
            entered.set()
            release.wait(30)
        return original(request)
    handler.do_GET=held
    try:
        ui('invoke','BtnSettings')
        ui('wait-for','SettingsDialog','-t','10000')
        check('settings appears before the held verification response',entered.wait(2) and not release.is_set())
        ui('wait-for','SettingsTheme','-p','IsEnabled','--value','True','-t','10000')
        ui('scroll','SettingsScroll','--to','bottom')
        ui('invoke','SettingsAdvanced','--action','expand')
        ui('wait-for','SettingsVerifyAIRuntime','-p','IsEnabled','--value','False','-t','10000')
        ui('invoke','SettingsSave')
        ui('wait-for','SettingsStatus','--value','保存しました','--contains','-t','10000')
        check('local settings can save while verification is loading',not release.is_set())
        shot('settings-verification-loading')
        ui('invoke','CloseButton');ui('wait-for','SettingsDialog','--gone','-t','10000')
        check('settings can close without waiting for the held response',not release.is_set())
        release.set();handler.do_GET=original
        ui('invoke','BtnSettings');ui('wait-for','SettingsDialog','-t','10000')
        ui('scroll','SettingsScroll','--to','bottom');ui('invoke','SettingsAdvanced','--action','expand')
        ui('wait-for','SettingsVerifyAIRuntime','-p','IsEnabled','--value','True','-t','10000')
        ui('wait-for','SettingsVerifyAIRuntime','--value','On','-t','10000')
        check('reopened settings obtains the enabled verification default',True)
        shot('settings-verification-ready')
        ui('invoke','CloseButton');ui('wait-for','SettingsDialog','--gone','-t','10000')
        report['physical_input_requested']=False
        report['unverified']=['real disconnected backend','physical keyboard and pointer','high contrast and DPI']
    finally:
        release.set();handler.do_GET=original
