"""Optional real-runtime GUI audit; accepts only our generated two-item fixture."""
import hashlib
import json
from pathlib import Path
import sqlite3

from ai_runtime import inspect_runtime
from storage_lease import plain_path


def prepare(data,fixture,runtime,models,repo):
    fixture=plain_path(fixture,directory=True);runtime=plain_path(runtime,directory=True)
    if not fixture.is_relative_to(repo/'data/ai-ui') or not runtime.is_relative_to(repo/'data/ai-ui') or models.resolve()!=repo/'models':
        raise ValueError('Existing repository fixture/runtime/models only')
    proof=json.loads((fixture/'report.json').read_text(encoding='utf-8'))
    if proof.get('pass') is not True or proof.get('generated_only') is not True:raise ValueError('A passing generated GPU fixture is required')
    with sqlite3.connect((fixture/'catalog.sqlite').as_uri()+'?mode=ro',uri=True) as old:
        roots=old.execute('SELECT path FROM library_roots').fetchall()
        if not roots or any(not Path(row[0]).resolve().is_relative_to(fixture/'media') for row in roots):
            raise ValueError('Generated media roots only')
    files=[plain_path(p) for p in fixture.glob('catalog.sqlite*') if p.name=='catalog.sqlite' or p.name.startswith('catalog.sqlite.ai.') and not p.name.endswith(('-wal','-shm'))]
    if len(files)<2:raise ValueError('Generated catalog and vectors required')
    for source in files:
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(data/source.name) as new:old.backup(new)
    info=inspect_runtime(runtime)
    return {'ai_runtime_root':str(runtime),'ai_runtime_manifest_sha256':info['manifest_sha256'],'models_root':str(models.resolve())}


def audit(phase,ui,tree,shot,check,request,settings,report):
    status=request('/api/library/ai/status')
    check('existing AI assets available without transfer',status['available'])
    if phase==0:
        check('default startup verification is active',status['runtime_verification']['state']=='verifying')
        ui('wait-for','RuntimeVerifyCard','-p','IsOffscreen','--value','False','-t','10000');shot('runtime-verifying')
    else:
        check('opt-out skips only full runtime hashes',status['runtime_verification']['state']=='skipped')
        check('opt-out starts without a resident model',not status['resident'])
    ui('invoke','CmbSearchMode')
    # WinUI exposes a popup option through both the combo and PopupHost. The
    # stable element slug avoids the CLI's duplicate AutomationId matches.
    ui('invoke',tree()['ModeVisual']['selector'],'--action','select')
    ui('set-value','TxtQuery','雨の日の青い画像')
    if phase==0:
        ui('wait-for','TxtCount','--value','AI環境を照合中','--contains','-t','10000')
        ui('invoke','BtnCancelSearch');ui('wait-for','BtnCancelSearch','--gone','-t','10000')
        check('verification wait cancelled without loading GPU model',not request('/api/library/ai/status')['resident'])
        ui('invoke','BtnSettings');ui('wait-for','SettingsAdvanced','-t','10000');ui('invoke','SettingsAdvanced')
        check('advanced verification defaults on',tree()['SettingsVerifyAIRuntime']['toggleState']=='on')
        ui('invoke','SettingsVerifyAIRuntime');ui('invoke','SettingsSave');ui('wait-for','SettingsStatus','--value','保存しました','--contains','-t','10000')
        check('next-start opt-out is saved',json.loads(settings.read_text())['verify_ai_runtime'] is False)
        check('current backend policy stays on',request('/api/library/ai/setup')['active_verify_ai_runtime'])
        shot('runtime-opt-out-next-start');ui('invoke','CloseButton');ui('wait-for','SettingsDialog','--gone','-t','10000')
        report['closed_during_verification']=request('/api/library/ai/status')['runtime_verification']['state']=='verifying'
    else:
        ui('wait-for','RuntimeVerifyTitle','--value','AIモデルを読み込み中','--contains','-t','10000');shot('model-loading')
        ui('wait-for','BtnCancelSearch','--gone','-t','120000')
        ui('wait-for','TxtCount','--value','2 件','--contains','-t','10000')
        status=request('/api/library/ai/status')
        check('normal ZIP entry executes Japanese visual search on CUDA',status['resident'] and status['device']=='cuda')
        shot('actual-ai-results')
        report['actual_gpu']=True
