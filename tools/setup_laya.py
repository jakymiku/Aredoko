"""Explicit opt-in Laya setup. Preserve every existing package; shared 6 MB/s cap."""
import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from laya_config import (PACKAGE_VERSION, MODEL_ID, REVISION, IDENTITY, ARTIFACTS,
                         MODEL_BYTES, WHEEL_BYTES, WHEEL_SHA256, model_path, validate_artifacts)
from setup_ai import ThrottledProxy

def inventory():
    return {d.metadata['Name'].lower().replace('_','-'):d.version for d in metadata.distributions()}

def check_dependencies():
    from packaging.version import Version
    for name,floor in {'torch':'2.0','transformers':'4.48','safetensors':'0.4',
                       'huggingface-hub':'0.20','numpy':'1.20'}.items():
        if Version(metadata.version(name))<Version(floor):
            raise RuntimeError('Existing dependency too old: '+name)
    subprocess.run([sys.executable,'-m','pip','check'],check=True,cwd=REPO)

def download_model(target, snapshot):
    target=Path(target)
    source=target/'aredoko-source.json'
    if target.exists() and any(target.iterdir()):
        if not source.is_file() or json.loads(source.read_text(encoding='utf-8'))!=IDENTITY:
            raise ValueError('Refuse overwriting a different checkpoint')
    target.mkdir(parents=True,exist_ok=True)
    source.write_text(json.dumps(IDENTITY),encoding='utf-8')
    snapshot(MODEL_ID,revision=REVISION,local_dir=target,allow_patterns=list(ARTIFACTS),max_workers=2)
    validate_artifacts(target,allow_tokenizer_fix=True)
    (target/'aredoko-revision.txt').write_text(REVISION,encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--install-and-download',action='store_true')
    parser.add_argument('--rate',type=int,default=6_000_000)
    args=parser.parse_args()
    if not 1_000_000<=args.rate<=6_000_000: parser.error('Rate must be 1..6 million bytes/s')
    plan={'package':'laya=='+PACKAGE_VERSION,'model_id':MODEL_ID,'revision':REVISION,
          'model_bytes':MODEL_BYTES,'wheel_bytes':WHEEL_BYTES,'aggregate_rate':args.rate,
          'existing_dependencies':'unchanged; --no-deps; no new venv/system changes'}
    print(json.dumps(plan,ensure_ascii=False),flush=True)
    if not args.install_and_download: return
    if Path(sys.prefix).resolve()!=(REPO/'.venv-ai').resolve():
        raise RuntimeError('Run only with project .venv-ai Python')
    check_dependencies()
    before=inventory()
    if 'laya' in before and before['laya']!=PACKAGE_VERSION:
        raise RuntimeError('Refuse replacing existing Laya version')
    target=model_path(REPO)
    # Reject different provenance before touching the environment.
    source=target/'aredoko-source.json'
    if target.exists() and any(target.iterdir()) and (not source.is_file() or
            json.loads(source.read_text(encoding='utf-8'))!=IDENTITY):
        raise ValueError('Refuse overwriting a different checkpoint')
    proxy=ThrottledProxy(args.rate)
    threading.Thread(target=proxy.serve_forever,daemon=True).start()
    env=os.environ.copy()
    address=f'http://127.0.0.1:{proxy.server_address[1]}'
    env.update(HTTPS_PROXY=address,HTTP_PROXY=address,ALL_PROXY=address,NO_PROXY='',
               HF_HUB_DISABLE_XET='1',HF_HUB_ENABLE_HF_TRANSFER='0',HF_HUB_DISABLE_TELEMETRY='1',
               PIP_DISABLE_PIP_VERSION_CHECK='1',HF_HUB_OFFLINE='0',TRANSFORMERS_OFFLINE='0')
    started=time.monotonic()
    try:
        requirement=REPO/'data/laya-setup/requirements.txt'
        requirement.parent.mkdir(parents=True,exist_ok=True)
        requirement.write_text(f'laya=={PACKAGE_VERSION} --hash=sha256:{WHEEL_SHA256}\n',encoding='utf-8')
        subprocess.run([sys.executable,'-m','pip','install','--no-deps','--only-binary=:all:',
                        '--require-hashes','-r',str(requirement)],check=True,env=env,cwd=REPO)
        after=inventory()
        if any(after.get(k)!=v for k,v in before.items()):
            raise RuntimeError('Existing package inventory changed')
        if set(after)-set(before)-{'laya'}: raise RuntimeError('Unexpected additional package')
        subprocess.run([sys.executable,'-m','pip','check'],check=True,env=env,cwd=REPO)
        # Import in a child AFTER proxy/offline variables are applied.
        subprocess.run([sys.executable,str(Path(__file__)), '--download-child'],check=True,env=env,cwd=REPO)
        report={**plan,'tls_bytes':proxy.gate.bytes,'elapsed_s':round(time.monotonic()-started,2),
                'existing_packages_unchanged':True,'installed_laya':after.get('laya')}
        (requirement.parent/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    finally:
        proxy.shutdown();proxy.server_close()

if __name__=='__main__':
    if sys.argv[1:]==['--download-child']:
        from huggingface_hub import snapshot_download
        download_model(model_path(REPO),snapshot_download)
    else: main()
