"""Dry-run by default; explicit project-only setup, one shared 6 MB/s cap."""
import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from tagger_profile import load_profile, RUNTIME_VERSION
from setup_ai import ThrottledProxy

PACKAGES={
    'onnxruntime':('1.23.2','902c756d8b633ce0dedd889b7c08459433fbcf35e9c38d1c03ddc020f0648c6e',13468349),
    'flatbuffers':('25.9.23','255538574d6cb6d0a79a17ec8bc0d30985913b87513a01cce8bcdb6b4c44d0e2',30869),
    'protobuf':('6.33.5','3093804752167bcab3998bec9f1048baae6e29505adaf1afd14a37bddede533c',437118),
    'coloredlogs':('15.0.1','612ee75c546f53e92e70049c9dbfcc18c935a2b9a53b66085ce9ef6a6e5c0934',46018),
    'humanfriendly':('10.0','1697e1a8a8f550fd43c2865cd84542fc175a61dcb779b6fee18cf6b6ccba1477',86794),
    'pyreadline3':('3.5.4','eaf8e6cc3c49bcccf145fc6067ba8643d1df34d604a1ec0eccbf7a18e6d3fae6',83178),
}


def inventory():
    return {d.metadata['Name'].lower().replace('_','-'):d.version for d in metadata.distributions()}


def requirements():
    return ''.join(f'{name}=={version} --hash=sha256:{digest}\n' for name,(version,digest,_) in PACKAGES.items())


def check_inventory(before,after):
    if any(after.get(name)!=version for name,version in before.items()):
        raise RuntimeError('Existing packages changed')
    if set(after)-set(before)-set(PACKAGES):raise RuntimeError('Unexpected new package')
    if any(after.get(name)!=value[0] for name,value in PACKAGES.items()):
        raise RuntimeError('Tagger package version mismatch')


def target_for_setup(profile):
    target=profile.directory(REPO)
    marker=target/'aredoko-source.json'
    if target.exists() and any(target.iterdir()):
        if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))!=profile.identity():
            raise ValueError('Refuse overwriting different model assets')
    return target


def download_model():
    if os.environ.get('AREDOKO_TAGGER_SETUP_ACTIVE')!='1':
        raise RuntimeError('Use the explicit --install-and-download setup')
    profile=load_profile(REPO)
    target=target_for_setup(profile)
    target.mkdir(parents=True,exist_ok=True)
    (target/'aredoko-source.json').write_text(json.dumps(profile.identity()),encoding='utf-8')
    from huggingface_hub import snapshot_download
    d=profile.data()
    snapshot_download(d['model_id'],revision=d['revision'],local_dir=target,
                      allow_patterns=list(d['artifacts']),max_workers=2)
    profile.verify(REPO,hashes=True)


def require_environment():
    if (Path(sys.prefix).resolve()!=(REPO/'.venv-ai').resolve() or os.name!='nt'
            or sys.version_info[:2]!=(3,11) or struct.calcsize('P')!=8):
        raise RuntimeError('Use only the existing project Windows x64 Python 3.11 venv')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--install-and-download',action='store_true')
    parser.add_argument('--rate',type=int,default=6_000_000)
    args=parser.parse_args()
    if not 1_000_000<=args.rate<=6_000_000:parser.error('Rate must be 1..6 million bytes/s')
    profile=load_profile(REPO)
    d=profile.data()
    plan={'model_id':d['model_id'],'revision':d['revision'],
          'model_bytes':sum(f['size'] for f in d['artifacts'].values()),
          'wheel_bytes':sum(v[2] for v in PACKAGES.values()),'packages':{k:v[0] for k,v in PACKAGES.items()},
          'aggregate_rate':args.rate,'runtime':'CPU only','existing_packages':'preserved; --no-deps; local venv only'}
    print(json.dumps(plan,ensure_ascii=False),flush=True)
    if not args.install_and_download:return
    require_environment()
    before=inventory()
    for name,(version,_,_) in PACKAGES.items():
        if name in before and before[name]!=version:raise RuntimeError('Refuse replacing '+name)
    for name in ('numpy','pillow','packaging','sympy','huggingface-hub'):
        if name not in before:raise RuntimeError('Required existing dependency missing: '+name)
    target=target_for_setup(profile)
    subprocess.run([sys.executable,'-m','pip','check'],check=True,cwd=REPO)
    proxy=ThrottledProxy(args.rate)
    threading.Thread(target=proxy.serve_forever,daemon=True).start()
    address=f'http://127.0.0.1:{proxy.server_address[1]}'
    env={**os.environ,'HTTPS_PROXY':address,'HTTP_PROXY':address,'ALL_PROXY':address,'NO_PROXY':'',
         'HF_HUB_DISABLE_XET':'1','HF_HUB_ENABLE_HF_TRANSFER':'0','HF_HUB_DISABLE_TELEMETRY':'1',
         'PIP_DISABLE_PIP_VERSION_CHECK':'1','HF_HUB_OFFLINE':'0','TRANSFORMERS_OFFLINE':'0',
         'AREDOKO_TAGGER_SETUP_ACTIVE':'1'}
    output=REPO/'data/wd-setup'
    output.mkdir(parents=True,exist_ok=True)
    req=output/'requirements.txt'
    req.write_text(requirements(),encoding='utf-8')
    started=time.monotonic()
    try:
        subprocess.run([sys.executable,'-m','pip','download','--no-deps','--only-binary=:all:',
            '--require-hashes','-r',str(req),'--dest',str(output/'wheels')],check=True,cwd=REPO,env=env)
        subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--require-hashes',
            '--find-links',str(output/'wheels'),'-r',str(req)],check=True,cwd=REPO,env=env)
        after=inventory()
        check_inventory(before,after)
        subprocess.run([sys.executable,'-m','pip','check'],check=True,cwd=REPO,env=env)
        subprocess.run([sys.executable,'-c',
            f'import onnxruntime as r; assert r.__version__=={RUNTIME_VERSION!r}; assert "CPUExecutionProvider" in r.get_available_providers()'],
            check=True,cwd=REPO,env=env)
        subprocess.run([sys.executable,str(Path(__file__)),'--download-child'],check=True,cwd=REPO,env=env)
        profile.verify(REPO,hashes=True)
        (target/'aredoko-runtime.json').write_text(json.dumps({'onnxruntime':RUNTIME_VERSION}),encoding='utf-8')
        report={**plan,'tls_bytes':proxy.gate.bytes,'elapsed_seconds':round(time.monotonic()-started,3),
                'existing_packages_unchanged':True}
        (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    finally:
        proxy.shutdown();proxy.server_close()


if __name__=='__main__':
    if sys.argv[1:]==['--download-child']:download_model()
    else:main()
