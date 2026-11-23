"""One bounded prepared-restore receipt; no directory scanning or auto-cutover."""
import hashlib,json,os,re,secrets
from pathlib import Path
from storage_lease import plain_path,identity,storage_parent

NAME='prepared.json'

def _object(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('Duplicate prepared field')
        value[key]=item
    return value

def _read(path,limit=16384):
    path=plain_path(path)
    if path.stat().st_size>limit:raise ValueError('Prepared receipt exceeds limit')
    return path.read_bytes()

def _digest(stage):
    return hashlib.sha256(_read(stage/'recovery.json',1048576)).hexdigest()

def save(base,job):
    base=plain_path(base,directory=True);stage=plain_path(job.staging_path,directory=True)
    if stage!=base/('restore_staging_'+job.job_id) or identity(stage)!=job._staging_identity:raise ValueError('Prepared ownership changed')
    value={'version':1,'job_id':job.job_id,'source':str(job.zip_path),'without_vectors':job.without_vectors,'identity':list(identity(stage)),'receipt_sha256':_digest(stage)}
    target=plain_path(base/NAME,missing=True)
    if target.exists():raise ValueError('A prepared receipt already exists')
    temporary=base/('.prepared-'+secrets.token_hex(16))
    try:
        with temporary.open('xb') as stream:
            stream.write((json.dumps(value,ensure_ascii=False)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary.exists():temporary.unlink()

def load(base):
    base=Path(base)
    if not (base/NAME).exists() and not (base/NAME).is_symlink():return None
    value=json.loads(_read(base/NAME),object_pairs_hook=_object)
    if not isinstance(value,dict) or set(value)!={'version','job_id','source','without_vectors','identity','receipt_sha256'} or type(value['version']) is not int or value['version']!=1:raise ValueError('Invalid prepared receipt')
    job=value['job_id'];source=value['source'];owned=value['identity'];digest=value['receipt_sha256']
    if not isinstance(job,str) or re.fullmatch('[0-9a-f]{32}',job) is None:raise ValueError('Invalid prepared ID')
    if not isinstance(source,str) or not 1<=len(source)<=4096 or not Path(source).is_absolute() or any(ord(c)<32 for c in source):raise ValueError('Invalid prepared source')
    if type(value['without_vectors']) is not bool or not isinstance(owned,list) or len(owned)!=2 or any(type(v) is not int for v in owned):raise ValueError('Invalid prepared policy/identity')
    if not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None:raise ValueError('Invalid prepared digest')
    stage=plain_path(base/('restore_staging_'+job),directory=True)
    if list(identity(stage))!=owned or _digest(stage)!=digest:raise ValueError('Prepared restore was replaced')
    # Payload hashing stays at explicit cutover; startup only reads bounded receipts.
    return value,stage

def forget(base,job_id):
    record=plain_path(Path(base)/NAME,missing=True)
    if not record.exists():return
    value=json.loads(_read(record),object_pairs_hook=_object)
    if not isinstance(value,dict) or value.get('job_id')!=job_id:raise ValueError('Prepared owner changed')
    record.unlink()
