"""Explicit setup-owner step after official payload and real model probe.

Does not alter launch settings. Keeps the small base package as mandatory
verification evidence; AI wheel caches can be removed after selection.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/('backend/app' if (ROOT/'backend/app').is_dir() else 'app')))
from managed_ai_runtime import seal

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--wheels',type=Path,required=True)
    parser.add_argument('--base-home',type=Path,required=True)
    parser.add_argument('--base-package',type=Path,required=True)
    parser.add_argument('--probe',type=Path,required=True)
    args=parser.parse_args()
    last=[None,-1]
    def progress(value):
        key=(value.get('stage'),value.get('bytes_done',0)//(256*1024**2))
        if list(key)!=last:print(json.dumps(value),flush=True);last[:]=key
    result=seal(args.runtime,args.wheels,args.base_home,args.base_package,
                json.loads(args.probe.read_text(encoding='utf8')),progress=progress)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
