"""Run the local handoff gates once, optionally the isolated native batch.

Windows: python tools/check_similarity_local.py --native
Never installs dependencies, restores packages, dispatches CI or scans user media.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

REPO=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--native',action='store_true',help='Windows only: one Light/Dark generated-media native batch')
    parser.add_argument('--skip-python',action='store_true',help='Use only when this exact code already passed Python; record the skip')
    args=parser.parse_args()
    if args.native and os.name!='nt':parser.error('--native needs Windows; no checks run')
    target=(args.output or REPO/'data/ai-ui'/('similarity-check-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])).resolve()
    if not target.is_relative_to((REPO/'data/ai-ui').resolve()):parser.error('--output must be inside data/ai-ui')
    target.mkdir(parents=True,exist_ok=False)
    report={'pass':False,'native_requested':args.native,'visual_review':'not performed; inspect native PNGs','checks':[],
        'installs':0,'downloads':0,'ci_dispatch':0,'platform':sys.platform,'python':sys.version.split()[0]}
    def run(name,command):
        started=time.monotonic();print('Running '+name,flush=True)
        result=subprocess.run(command,cwd=REPO,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (target/(name+'.log')).write_text(result.stdout,encoding='utf-8')
        report['checks'].append({'name':name,'command':command,'exit_code':result.returncode,'seconds':round(time.monotonic()-started,3)})
        if result.returncode:raise RuntimeError(name+' failed; see '+str(target/(name+'.log')))
        print(name+' PASS',flush=True)
    try:
        git=subprocess.run(['git','status','--short','--branch'],cwd=REPO,capture_output=True,text=True)
        (target/'git-status.txt').write_text(git.stdout+git.stderr,encoding='utf-8')
        run('diff-check',['git','diff','--check'])
        if not args.skip_python:run('python-tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'])
        else:report['checks'].append({'name':'python-tests','status':'explicitly skipped'})
        if shutil.which('dotnet'):
            # No package restore: an absent SDK/cache is an explicit handoff gap.
            run('core-tests',['dotnet','run','--project','tests/Aredoko.Core.Tests','-c','Release','--no-restore'])
        else:raise RuntimeError('dotnet SDK is unavailable. Core/Windows checks remain unverified; no dependency was installed.')
        if os.name=='nt':
            run('winui-release',['dotnet','build','src/Aredoko.WinUI/Aredoko.WinUI.csproj','-c','Release','-p:Platform=x64','-p:SelfContained=true','--no-restore'])
        else:report['checks'].append({'name':'winui-release','status':'unverified: Windows required'})
        if args.native:
            if not shutil.which('winapp'):raise RuntimeError('Existing winapp CLI is required; no install attempted')
            run('native',[sys.executable,'tools/test_similarity_ui.py','--output',str(target/'native')])
        report['pass']=True
    except Exception as ex:
        report['error']=str(ex);print(str(ex),file=sys.stderr)
    finally:
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Evidence: '+str(target),flush=True)
    return 0 if report['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
