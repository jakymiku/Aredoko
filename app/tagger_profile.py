"""Local-only, replaceable WD-compatible ONNX classification profiles."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from runtime_paths import model_directory

DEFAULT_PATH = 'config/tagger-profiles/wd-swinv2-v3.json'
RUNTIME_VERSION = '1.23.2'


@dataclass(frozen=True)
class WDProfile:
    document: str  # Canonical JSON keeps caller-owned dictionaries immutable.

    @classmethod
    def from_dict(cls, value):
        fields = {'id','adapter','model_id','revision','model_directory','input_size',
                  'label_count','general_threshold','character_threshold','max_candidates',
                  'timeout_seconds','cpu_threads','artifacts'}
        if type(value) is not dict or set(value) != fields or value['adapter'] != 'wd-onnx-v1':
            raise ValueError('Invalid tagger profile')
        for name in ('id','model_id'):
            if type(value[name]) is not str or re.fullmatch(r'[A-Za-z0-9_./-]{1,160}',value[name]) is None:
                raise ValueError('Invalid tagger identity')
        if type(value['revision']) is not str or re.fullmatch(r'[0-9a-f]{40}',value['revision']) is None:
            raise ValueError('Pin a model revision')
        directory=value['model_directory']
        if (type(directory) is not str or '\\' in directory or ':' in directory
                or PurePosixPath(directory).parts[:1] != ('models',)
                or len(PurePosixPath(directory).parts)<2 or '..' in PurePosixPath(directory).parts):
            raise ValueError('Use a project models subdirectory')
        for name,low,high in (('input_size',224,1024),('label_count',1,100000),
                              ('max_candidates',1,30),('timeout_seconds',5,180),('cpu_threads',1,8)):
            if type(value[name]) is not int or not low<=value[name]<=high:
                raise ValueError('Invalid tagger limit')
        for name in ('general_threshold','character_threshold'):
            number=value[name]
            if type(number) not in (int,float) or not math.isfinite(number) or not 0<number<1:
                raise ValueError('Invalid classification threshold')
        artifacts=value['artifacts']
        if type(artifacts) is not dict or set(artifacts)!={'model.onnx','selected_tags.csv'}:
            raise ValueError('Two fixed artifacts required')
        for name,entry in artifacts.items():
            cap=1024**3 if name=='model.onnx' else 4*1024**2
            if (type(entry) is not dict or set(entry)!={'size','sha256'}
                    or type(entry['size']) is not int or not 1<=entry['size']<=cap
                    or type(entry['sha256']) is not str or re.fullmatch(r'[0-9a-f]{64}',entry['sha256']) is None):
                raise ValueError('Invalid tagger artifact')
        return cls(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False))

    def data(self): return json.loads(self.document)

    @property
    def key(self): return hashlib.sha256(self.document.encode()).hexdigest()

    def directory(self, repo, *, models_root=None):
        relative=PurePosixPath(self.data()['model_directory']).relative_to('models')
        return model_directory(repo,relative,models_root)

    def identity(self):
        d=self.data()
        return {k:d[k] for k in ('model_id','revision','artifacts')}

    def verify(self, repo, hashes=False, *, models_root=None):
        target=self.directory(repo,models_root=models_root)
        marker=target/'aredoko-source.json'
        if marker.is_symlink() or json.loads(marker.read_text(encoding='utf-8'))!=self.identity():
            raise ValueError('Tagger provenance mismatch')
        for name,entry in self.data()['artifacts'].items():
            path=target/name
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=entry['size']:
                raise ValueError('Tagger artifact mismatch')
            if hashes:
                with path.open('rb') as file:
                    digest=hashlib.file_digest(file,'sha256').hexdigest()
                if digest!=entry['sha256']:raise ValueError('Tagger checksum mismatch')
        return target


def load_profile(repo, path=None):
    return WDProfile.from_dict(json.loads((Path(path) if path else Path(repo)/DEFAULT_PATH).read_text(encoding='utf-8')))
