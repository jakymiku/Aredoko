"""Validated local embedding profiles; no packages or model downloads."""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from runtime_paths import model_directory

LEGACY_REVISION = '914f7f89142e33e77833254d9c9b90c3cef7303b'
REVISION = LEGACY_REVISION
LEGACY_PROFILE = 'embeddinggemma-2:' + LEGACY_REVISION + ':text-vision:768:v1'
LEGACY_CONTRACT = 'normalized-f32:text4096:exif-rgb-image768:v1'
VECTOR_CONTRACT = LEGACY_CONTRACT
AUDIO_VECTOR_CONTRACT = 'normalized-f32:text4096:mono-f32le-16000hz-audio30000ms:v1'
VIDEO_VECTOR_CONTRACT = 'normalized-f32:text4096:rgb384-video1fps16frames-tokens140:v1'
# Historical compatibility must never follow a future DEFAULT_PROFILE change.
LEGACY_IDENTITY = {
    'model_id':'google/embeddinggemma-2','revision':LEGACY_REVISION,
    'adapter':'embeddinggemma2','dimension':768,'modalities':['text','cover'],
    'query_prompt_name':'SearchQuery','document_prompt_name':'Document',
    'query_prefix':'','document_prefix':'','precision':'auto-bf16'
}

@dataclass(frozen=True)
class ModelProfile:
    model_id: str = 'google/embeddinggemma-2'
    revision: str = REVISION
    label: str = 'EmbeddingGemma 2'
    directory: str = 'embeddinggemma-2'
    adapter: str = 'embeddinggemma2'
    dimension: int = 768
    modalities: tuple = ('text', 'cover')
    query_prompt_name: str | None = 'SearchQuery'
    document_prompt_name: str | None = 'Document'
    query_prefix: str = ''
    document_prefix: str = ''
    precision: str = 'auto-bf16'

    def __post_init__(self):
        if self.adapter not in ('embeddinggemma2', 'sentence-transformers'):
            raise ValueError('Unsupported embedding adapter')
        if type(self.dimension) is not int or not 1 <= self.dimension <= 4096:
            raise ValueError('Embedding dimension must be 1..4096')
        if self.modalities not in (('text',), ('text','cover'), ('text','audio'), ('text','video')):
            raise ValueError('Unsupported modalities')
        if self.adapter == 'sentence-transformers' and self.modalities != ('text',):
            raise ValueError('Generic adapter currently supports text only')
        if self.precision not in ('auto-bf16', 'float32'):
            raise ValueError('Unsupported precision')
        for value in (self.model_id, self.label):
            if not isinstance(value,str) or not 0 < len(value) <= 128 or any(ord(c)<32 for c in value):
                raise ValueError('Invalid model identity')
        if not isinstance(self.revision,str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',self.revision):
            raise ValueError('Use an immutable commit or content hash')
        if not isinstance(self.directory,str) or len(self.directory)>128:
            raise ValueError('Invalid model directory')
        path=PurePosixPath(self.directory)
        if not self.directory or path.is_absolute() or any(x in ('..','.') for x in self.directory.split('/')) or '\\' in self.directory or ':' in self.directory:
            raise ValueError('Model directory must be relative to models')
        for name,prefix in ((self.query_prompt_name,self.query_prefix),(self.document_prompt_name,self.document_prefix)):
            if name is not None and (not isinstance(name,str) or not 0<len(name)<=64):
                raise ValueError('Invalid prompt name')
            if not isinstance(prefix,str) or len(prefix)>256 or name is not None and prefix:
                raise ValueError('Choose prompt name or explicit prefix')

    def to_dict(self):
        data=asdict(self)
        data["modalities"]=list(self.modalities)
        return data

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict):
            raise ValueError('Expected profile object')
        unknown=set(data)-set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError('Unknown profile fields')
        values=dict(data)
        if 'modalities' in values:
            if not isinstance(values['modalities'],list):
                raise ValueError('Expected modalities list')
            values['modalities']=tuple(values['modalities'])
        try:
            return cls(**values)
        except TypeError as ex:
            raise ValueError('Invalid profile types') from ex

    def identity(self):
        data=self.to_dict()
        # UI labels and relocation do not change the vector space.
        data.pop('label');data.pop('directory')
        return data

    @property
    def vector_contract(self):
        return AUDIO_VECTOR_CONTRACT if 'audio' in self.modalities else VIDEO_VECTOR_CONTRACT if 'video' in self.modalities else VECTOR_CONTRACT

    @property
    def key(self):
        if self.vector_contract==LEGACY_CONTRACT and self.identity()==LEGACY_IDENTITY:
            return LEGACY_PROFILE
        payload={'contract':self.vector_contract,**self.identity()}
        return 'embedding-profile:'+hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

    def store_path(self,catalog):
        suffix='.ai.sqlite' if self.key==LEGACY_PROFILE else '.ai.'+hashlib.sha256(self.key.encode()).hexdigest()[:24]+'.sqlite'
        return Path(str(catalog)+suffix)

    def model_path(self,repo,*,models_root=None):
        return model_directory(repo,self.directory,models_root)

DEFAULT_PROFILE=ModelProfile()

def audio_profile_for(base=DEFAULT_PROFILE):
    """Explicit worker profile only; never changes the selected image profile."""
    if base.adapter!='embeddinggemma2':raise ValueError('Direct audio requires the registered EmbeddingGemma 2 adapter')
    return replace(base,modalities=('text','audio'),label=base.label[:110]+'（音声入力）')

def video_profile_for(base=DEFAULT_PROFILE):
    """Explicit native-video worker contract; selected legacy indexes stay intact."""
    if base.adapter!='embeddinggemma2':raise ValueError('Native video requires the registered EmbeddingGemma 2 adapter')
    return replace(base,modalities=('text','video'),label=base.label[:110]+'（動画入力）')

def load_profile(path=None):
    if path is None:
        return DEFAULT_PROFILE
    path=Path(path)
    if path.stat().st_size>8192:
        raise ValueError('Profile file exceeds limit')
    return ModelProfile.from_dict(json.loads(path.read_text(encoding='utf-8-sig')))
