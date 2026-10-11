"""Offline-only typed decision worker; no retrieval/catalog access."""
import argparse
import contextlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from ai_worker import monitor_parent
from laya_config import PACKAGE_VERSION, IDENTITY, CONTRACT, validate_artifacts
from search_intent import QUESTIONS, validate_query, validate_decision

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',required=True,type=Path)
    parser.add_argument('--parent-pid',type=int,default=os.getppid())
    args=parser.parse_args()
    # Windows venv python.exe may be a redirector with a second interpreter child.
    # Watch BOTH the API owner and immediate OS parent so killing the redirector
    # terminates an in-flight worker, not just its idle stdin loop.
    for owner in {args.parent_pid,os.getppid()}:
        threading.Thread(target=monitor_parent,args=(owner,),daemon=True).start()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    # Fail even unexpected socket connection attempts. Local inference needs no TCP socket.
    blocked=[0]
    def refuse_network(*a,**k):
        blocked[0]+=1;raise OSError('Network disabled in decision worker')
    socket.socket.connect=refuse_network;socket.socket.connect_ex=refuse_network
    socket.create_connection=refuse_network
    wire=sys.stdout
    started=time.perf_counter()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if importlib.metadata.version('laya')!=PACKAGE_VERSION:raise ValueError('Laya version mismatch')
            if not args.model.is_dir():raise ValueError('Local model directory missing')
            validate_artifacts(args.model,allow_tokenizer_fix=True)
            import torch
            import laya
            device='cuda' if torch.cuda.is_available() else 'cpu'
            if device=='cuda':torch.cuda.reset_peak_memory_stats()
            agent=laya.load(str(args.model.resolve()),device=device,backend='eager')
            # Full question definitions and a 300-character request must not truncate silently.
            agent.cfg['max_len']=1024
            agent.cfg['head_max_len']=512
        print(json.dumps({'ready':True,'identity':IDENTITY,'contract':CONTRACT,'device':str(agent.device),'worker_pid':os.getpid(),
            'load_ms':round((time.perf_counter()-started)*1000,2),
            'network_blocked_calls':blocked[0],
            'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,2) if device=='cuda' else 0}),file=wire,flush=True)
        while True:
            line=sys.stdin.readline(8193)
            if not line:return
            if len(line)>8192:raise ValueError('Protocol input limit')
            try:
                request=json.loads(line)
                if not isinstance(request,dict) or set(request)!={'query'}:raise ValueError('Invalid request')
                query=validate_query(request['query'])
                if not query:raise ValueError('Empty query')
                started=time.perf_counter()
                with contextlib.redirect_stdout(sys.stderr),torch.inference_mode():
                    result=agent.system_one(query,QUESTIONS,lang='ja',max_len=1024,head_max_len=512)
                    validate_decision(result)
                print(json.dumps({'result':result,'elapsed_ms':round((time.perf_counter()-started)*1000,2),
                    'network_blocked_calls':blocked[0],
                    'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,2) if device=='cuda' else 0},
                    ensure_ascii=False,allow_nan=False),file=wire,flush=True)
            except Exception:
                print(json.dumps({'error':'Decision failed'}),file=wire,flush=True)
    except Exception as ex:
        print('Laya startup failed: '+type(ex).__name__+': '+str(ex),file=sys.stderr,flush=True)
        print(json.dumps({'error':'Decision startup failed'}),file=wire,flush=True)

if __name__=='__main__':main()
