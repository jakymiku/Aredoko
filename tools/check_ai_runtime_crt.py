"""Owned CPU-only native imports in an explicit local CRT test pack.

Production runtime verification remains enabled. No model, installer, GPU
inference, GUI, download, normal DB or settings. This is not clean Windows.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_runtime import MARKER
from storage_lease import plain_path,storage_parent
from runtime_paths import bind_runtime,worker_command,runtime_verification_status,configure_runtime_verification
from release_runtime import runtime_environment
from prepare_ai_runtime_crt import CRT_NAMES


def child(mode,root):
    import ctypes
    from ctypes import wintypes
    if mode=='torch':
        import torch
        import transformers
        result={'mode':mode,'version':torch.__version__,'module':torch.__file__,
                'cpu_sum':torch.ones(2,device='cpu').sum().item(),'transformers':transformers.__version__}
    else:
        import onnxruntime
        result={'mode':mode,'version':onnxruntime.__version__,'module':onnxruntime.__file__,
                'providers':onnxruntime.get_available_providers()}
    if not Path(result['module']).is_relative_to(root):raise AssertionError('Module escaped selected runtime')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.K32EnumProcessModulesEx.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.HMODULE),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),wintypes.DWORD]
    kernel.K32EnumProcessModulesEx.restype=wintypes.BOOL
    kernel.GetModuleFileNameW.argtypes=[wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD]
    kernel.GetModuleFileNameW.restype=wintypes.DWORD
    modules=(wintypes.HMODULE*4096)();needed=wintypes.DWORD()
    if not kernel.K32EnumProcessModulesEx(kernel.GetCurrentProcess(),modules,ctypes.sizeof(modules),ctypes.byref(needed),3):
        raise ctypes.WinError(ctypes.get_last_error())
    if needed.value>ctypes.sizeof(modules):raise RuntimeError('Native module inventory exceeds limit')
    rows=[]
    for module in modules[:needed.value//ctypes.sizeof(wintypes.HMODULE)]:
        name=ctypes.create_unicode_buffer(32768);length=kernel.GetModuleFileNameW(module,name,len(name))
        if not length or length>=len(name):raise ctypes.WinError(ctypes.get_last_error())
        path=Path(name.value)
        if path.name.casefold() not in CRT_NAMES:continue
        local=path.parent==root
        rows.append({'name':path.name,'path':str(path),'app_local':local,
                     'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    required={'vcruntime140.dll','msvcp140.dll'}
    if mode=='onnxruntime':required.add('msvcp140_1.dll')
    if not required<={row['name'].casefold() for row in rows} or not all(row['app_local'] for row in rows):
        raise AssertionError('Native CRT resolved outside the selected root or required CRT was not loaded')
    component=json.loads((root/'THIRD_PARTY_NATIVE_LICENSES/msvc-v14/component.json').read_text(encoding='utf-8'))
    expected={row['path']:row['sha256'] for row in component['dlls']}
    if any(expected.get(row['name'].casefold())!=row['sha256'] for row in rows):raise AssertionError('Loaded CRT differs from bound component')
    return {**result,'crt_modules':rows,'pass':True,'gpu_inference':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--native-load-consent',action='store_true')
    parser.add_argument('--child',choices=('torch','onnxruntime'),help=argparse.SUPPRESS)
    args=parser.parse_args();root=plain_path(args.source,directory=True)
    if not args.native_load_consent:parser.error('Explicit native CPU test consent required')
    if args.child:
        print(json.dumps(child(args.child,root),ensure_ascii=False));return 0
    if args.output is None:parser.error('New dedicated output required')
    output=Path(os.path.abspath(args.output));allowed=ROOT/'data/ai-ui'
    if not root.is_relative_to(allowed) or not output.is_relative_to(allowed) or root.is_relative_to(output) or output.is_relative_to(root):
        parser.error('Separate dedicated repository inputs/output required')
    plain_path(output,missing=True);storage_parent(output);output.mkdir()
    report={'pass':False,'cpu_only':True,'gui':False,'normal_data_used':False,'os_modified':False,
            'clean_windows_verified':False,'children':[],'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    before=(root/MARKER).read_bytes();report['runtime_manifest_sha256']=hashlib.sha256(before).hexdigest()
    env=runtime_environment();env['PATH']=str(root)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32')
    for name in ('LOCALAPPDATA','APPDATA','TEMP','TMP','HF_HOME','XDG_CACHE_HOME'):
        directory=output/name.lower();directory.mkdir();env[name]=str(directory)
    configure_runtime_verification(True);bind_runtime(root,report['runtime_manifest_sha256'])
    try:
        deadline=time.monotonic()+600;start=time.monotonic()
        for mode in ('torch','onnxruntime'):
            command=worker_command(root/'python.exe',Path(__file__),['--source',str(root),'--native-load-consent','--child',mode],cancelled=lambda:time.monotonic()>deadline)
            if 'verification' not in report:
                report['verification']=runtime_verification_status(root/'python.exe')
                report['verification_seconds']=round(time.monotonic()-start,3)
            start_import=time.monotonic()
            result=subprocess.run(command,cwd=output,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
            (output/(mode+'-stdout.log')).write_text(result.stdout,encoding='utf-8')
            (output/(mode+'-stderr.log')).write_text(result.stderr,encoding='utf-8')
            result.check_returncode();value=json.loads(result.stdout)
            report['children'].append({**value,'exit_code':result.returncode,'import_seconds':round(time.monotonic()-start_import,3)})
            print(mode+' native imports and app-local CRT passed',flush=True)
        report['manifest_unchanged']=before==(root/MARKER).read_bytes()
        report['pass']=report['manifest_unchanged'] and all(row['pass'] for row in report['children'])
    except Exception:report['error']=traceback.format_exc();print(report['error'],flush=True)
    finally:(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
