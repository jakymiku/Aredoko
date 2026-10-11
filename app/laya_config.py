"""Pinned decision model, independent of embedding/vector profiles."""
import hashlib
import json
from pathlib import Path

PACKAGE_VERSION = '0.4.2'
MODEL_ID = 'convaiinnovations/laya-multilingual'
REVISION = '1720e3e3357cfe1e281542e223f8273b0890ca34'
MODEL_DIRECTORY = 'laya-multilingual'
WHEEL_SHA256 = '126284550840e8fc2445f9cd4c808e505d25d457242e7de5658b2cb9f9155b26'
WHEEL_BYTES = 380522
# Official pinned HF metadata. Only these five runtime artifacts are fetched.
ARTIFACTS = {
    'model.safetensors': (643835514, '9d628fd971b700382ac6f65920a86f149777b2e748e0c955fb3b19695aa8f204'),
    'tokenizer/tokenizer.json': (34363188, '609d8f4c067cd3950f88594c5a802616cea245823836ef5848ee4fc40aab5b6f'),
    'tokenizer/tokenizer_config.json': (502, '424b69444bf7b5809dc2cd2e36d0bd71b8055124dd24274d6db3c655d38205e7'),
    'encoder/config.json': (1938, '83f6916d13ef0f556ac461f28308dc2bffa7ebeadee8ec9e2db5812020ea5bb4'),
    'rl_agent_config.json': (472, '25061739243b617ad88d1219ba6f8a9c86c5881ca28df024fa2d9b3b2fcc30c6'),
}
MODEL_BYTES = sum(size for size, _ in ARTIFACTS.values())
CONTRACT = 'aredoko-search-intent-v1'
IDENTITY = {'model_id':MODEL_ID, 'revision':REVISION, 'package':PACKAGE_VERSION}

def model_path(repo):
    root=(Path(repo)/'models').resolve()
    target=(root/MODEL_DIRECTORY).resolve()
    if not target.is_relative_to(root): raise ValueError('Model directory escapes models')
    return target

def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk:=source.read(1024*1024): result.update(chunk)
    return result.hexdigest()

def validate_artifacts(target, *, allow_tokenizer_fix=False):
    target=Path(target).resolve()
    for name,(size,sha) in ARTIFACTS.items():
        path=(target/name).resolve()
        if not path.is_relative_to(target): raise ValueError('Artifact escapes model directory')
        # Upstream changes ONLY this small tokenizer config for transformers compatibility.
        if allow_tokenizer_fix and name=='tokenizer/tokenizer_config.json':
            if path.stat().st_size>2048: raise ValueError('Tokenizer config limit')
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()==sha: continue
            patched=json.loads(raw)
            if not isinstance(patched,dict):raise ValueError('Invalid tokenizer config')
            extra=patched.get('extra_special_tokens')
            if extra!={'extra_0':'<start_of_turn>', 'extra_1':'<end_of_turn>'}:
                raise ValueError('Unexpected tokenizer config')
            patched['extra_special_tokens']=['<start_of_turn>','<end_of_turn>']
            # Compare the entire original object, not just the changed field.
            original=json.dumps(patched,indent=2)
            if sha not in {hashlib.sha256((original+suffix).encode('utf-8')).hexdigest() for suffix in ('','\n')}:
                raise ValueError('Unexpected tokenizer config')
            continue
        if path.stat().st_size!=size or digest(path)!=sha:
            raise ValueError('Model artifact integrity mismatch: '+name)
