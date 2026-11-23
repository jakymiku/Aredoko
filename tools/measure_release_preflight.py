"""Measure full preflight using staged or current tools, without GUI/model inference.

Run with the staged Python and -I -B to keep the interpreter consistent. This
does not modify a release or its manifest; only a NEW external JSON is written.
"""
import sys
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import threading
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--implementation',choices=('staged','current'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    release=args.release.absolute()
    if args.output.exists() or not args.output.parent.is_dir() or args.output.resolve().is_relative_to(release.resolve()):
        parser.error('Use a new output JSON in an existing directory outside the release')
    source=release/'tools' if args.implementation=='staged' else Path(__file__).resolve().parent
    sys.path.insert(0,str(source))
    import release_runtime as runtime
    import launch_release as launch
    if Path(runtime.__file__).resolve().parent!=source.resolve() or Path(launch.__file__).resolve().parent!=source.resolve():
        parser.error('Implementation differs from the selected tools directory')
    runtime.plain_path(args.output.parent,directory=True)
    counts={};lock=threading.Lock();restore=[]
    def measured(name,callback):
        def invoke(*positional,**keywords):
            started=time.perf_counter()
            try:return callback(*positional,**keywords)
            finally:
                elapsed=time.perf_counter()-started
                with lock:
                    item=counts.setdefault(name,{'calls':0,'seconds':0})
                    item['calls']+=1;item['seconds']+=elapsed
        return invoke
    for module,names in ((runtime,('plain_path','digest')),(launch,('verify_release','python_layout','media_layout'))):
        for name in names:
            original=getattr(module,name);restore.append((module,name,original))
            setattr(module,name,measured(name,original))
    report={'pass':False,'implementation':args.implementation,'source':str(runtime.__file__),
            'timing_note':'plain_path/digest seconds sum overlapping calls; phase seconds are wall durations',
            'native_gui_tested':False,'model_inference_tested':False}
    started=time.perf_counter()
    try:
        manifest=launch.preflight(release)
        report.update({'pass':True,'version':manifest['version'],'files':manifest['files_count']})
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
    finally:
        report.update(total_seconds=time.perf_counter()-started,timings=counts)
        for module,name,original in restore:setattr(module,name,original)
        with args.output.open('x',encoding='utf-8') as output:json.dump(report,output,indent=2)
        print(json.dumps(report,indent=2))
    return 0 if report['pass'] else 1


if __name__=='__main__':sys.exit(main())
