"""Physical model placements, separate from vector namespaces and live workers."""
from dataclasses import asdict,dataclass
from pathlib import Path,PurePosixPath
import re
from ai_runtime import relative
from ai_profiles import ModelProfile
from tagger_profile import WDProfile

FIELD='model_locations'
LIMIT=32

@dataclass(frozen=True)
class ModelTarget:
    role:str
    model_id:str
    revision:str
    directory:str

    @classmethod
    def from_dict(cls,value):
        if not isinstance(value,dict) or set(value)!={'role','model_id','revision','directory'}:
            raise ValueError('Invalid model placement identity')
        role=value['role'];identifier=value['model_id'];revision=value['revision'];directory=value['directory']
        if role not in ('embedding','tagger'):raise ValueError('Unsupported bound model role')
        if not isinstance(identifier,str) or not 1<=len(identifier)<=160 or any(ord(c)<32 for c in identifier):raise ValueError('Invalid model identity')
        if not isinstance(revision,str) or re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',revision) is None:raise ValueError('Pin a model revision')
        if not isinstance(directory,str) or len(directory)>128:raise ValueError('Invalid model directory')
        relative(directory)
        return cls(role,identifier,revision,directory)

    @classmethod
    def for_profile(cls,role,profile):
        if role=='embedding' and isinstance(profile,ModelProfile):
            return cls.from_dict({'role':role,'model_id':profile.model_id,'revision':profile.revision,'directory':profile.directory})
        if role=='tagger' and isinstance(profile,WDProfile):
            data=profile.data()
            return cls.from_dict({'role':role,'model_id':data['model_id'],'revision':data['revision'],
                                 'directory':str(PurePosixPath(data['model_directory']).relative_to('models'))})
        raise ValueError('Model profile does not match its role')

    def to_dict(self):return asdict(self)


def parse_locations(value):
    if not isinstance(value,list) or len(value)>LIMIT:raise ValueError('Model placements exceed limit')
    result=[];seen=set()
    for row in value:
        if not isinstance(row,dict) or set(row)!={'role','model_id','revision','directory','root'}:raise ValueError('Invalid model placement')
        target=ModelTarget.from_dict({key:row[key] for key in ('role','model_id','revision','directory')})
        root=row['root']
        if not isinstance(root,str) or len(root)>4096 or not Path(root).is_absolute() or any(ord(c)<32 for c in root):raise ValueError('Select an absolute model placement')
        if target in seen:raise ValueError('Duplicate model placement')
        seen.add(target);result.append((target,root))
    return tuple(result)


def serialize_locations(values):return [target.to_dict()|{'root':root} for target,root in values]
