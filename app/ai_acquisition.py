"""Trusted, resumable artifact acquisition; no model execution or settings writes."""
from dataclasses import dataclass
import hashlib,json,os,re,shutil,time,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from ai_runtime import relative,object_pairs,digest,inspect_runtime,files
from storage_lease import plain_path,storage_parent,storage_lease

@dataclass(frozen=True)
class Artifact:
    path:str
    url:str
    size:int
    sha256:str
    role:str

@dataclass(frozen=True)
class Catalog:
    key:str
    kind:str
    revision:str
    license:str
    license_url:str
    hosts:tuple
    entries:tuple
    fingerprint:str
    test_loopback:bool=False

    @classmethod
    def parse(cls,raw,*,test_loopback=False):
        if not isinstance(raw,bytes) or len(raw)>32*1024**2:raise ValueError('Catalog exceeds limit')
        value=json.loads(raw,object_pairs_hook=object_pairs)
        if not isinstance(value,dict) or set(value)!={'format','id','revision','kind','license','license_url','allowed_hosts','entries'} or value['format']!='aredoko-acquisition-v1':raise ValueError('Unsupported acquisition catalog')
        if not isinstance(value['id'],str) or re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',value['id']) is None:raise ValueError('Invalid catalog ID')
        if not isinstance(value['revision'],str) or re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',value['revision']) is None or value['kind'] not in ('runtime','model'):raise ValueError('Immutable catalog revision required')
        if not isinstance(value['license'],str) or not 1<=len(value['license'])<=128 or any(ord(c)<32 for c in value['license']):raise ValueError('License declaration required')
        if not isinstance(value['license_url'],str) or len(value['license_url'])>8192:raise ValueError('Invalid license link')
        license_url=urlsplit(value['license_url'])
        if license_url.scheme!='https' or not license_url.hostname or license_url.username or license_url.fragment:raise ValueError('Official license link required')
        hosts=value['allowed_hosts']
        if not isinstance(hosts,list) or not 1<=len(hosts)<=16 or any(not isinstance(h,str) or re.fullmatch('[a-z0-9.-]{1,253}',h) is None for h in hosts) or len(set(hosts))!=len(hosts):raise ValueError('Invalid source hosts')
        entries=value['entries'];seen=set();items=[];total=0
        if not isinstance(entries,list) or not 1<=len(entries)<=100000:raise ValueError('Invalid catalog files')
        for item in entries:
            if not isinstance(item,dict) or set(item)!={'path','url','bytes','sha256','role'}:raise ValueError('Invalid artifact fields')
            name=relative(item['path'])
            if name.casefold() in seen:raise ValueError('Duplicate catalog path')
            seen.add(name.casefold())
            size=item['bytes'];checksum=item['sha256'];role=item['role']
            if type(size) is not int or size<0 or not isinstance(checksum,str) or re.fullmatch('[0-9a-f]{64}',checksum) is None:raise ValueError('Invalid artifact identity')
            if role not in ('runtime','weights','configuration','tokenizer','labels','license','inventory'):raise ValueError('Invalid artifact role')
            _source(item['url'],hosts,test_loopback)
            total+=size
            if total>64*1024**3:raise ValueError('Acquisition exceeds limit')
            items.append(Artifact(name,item['url'],size,checksum,role))
        ordered=sorted(seen,key=lambda name:name.split('/'))
        if any(right.startswith(left+'/') for left,right in zip(ordered,ordered[1:])):raise ValueError('Artifact path collision')
        canonical=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        return cls(value['id'],value['kind'],value['revision'],value['license'],value['license_url'],tuple(hosts),tuple(items),hashlib.sha256(canonical).hexdigest(),test_loopback)


def _source(url,hosts,test_loopback):
    if not isinstance(url,str) or len(url)>8192 or any(ord(c)<32 for c in url):raise ValueError('Invalid source URL')
    parsed=urlsplit(url)
    local=test_loopback and parsed.hostname=='127.0.0.1' and parsed.scheme=='http'
    if not (parsed.scheme=='https' or local) or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.fragment:raise ValueError('Untrusted source URL')
    if not parsed.hostname or not parsed.path.startswith('/'):raise ValueError('Invalid source location')
    return url

class _Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,catalog):self.catalog=catalog
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        _source(newurl,self.catalog.hosts,self.catalog.test_loopback)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def acquire(catalog,root,*,validate,publish,cancelled=lambda:False,progress=None,bytes_per_second=None):
    """Only call with an application-owned catalog and cancellation/publication gate."""
    if not isinstance(catalog,Catalog) or not callable(validate) or not callable(publish):raise ValueError('Trusted catalog, validator and publication owner required')
    if bytes_per_second is not None and (type(bytes_per_second) is not int or bytes_per_second<=0):raise ValueError('Invalid download speed limit')
    root=Path(os.path.abspath(root));storage_parent(root/'marker');plain_path(root,directory=True)
    stage=root/('.acquire-'+catalog.fingerprint);target=root/(catalog.key+'-'+catalog.fingerprint[:24])
    # The catalog is immutable: do not rescan every entry for each 64KiB report.
    total_bytes=sum(item.size for item in catalog.entries)
    def check():
        if cancelled():raise InterruptedError('Acquisition cancelled')
    def report(stage_name,done,verified):
        if progress:progress({'stage':stage_name,'bytes_received':done,'bytes_verified':verified,'bytes_total':total_bytes})
    with storage_lease(root/('acquire-'+catalog.fingerprint)):
        check()
        if target.exists() or target.is_symlink():raise FileExistsError('Published version already exists')
        storage_parent(stage/'payload/marker');plain_path(stage,directory=True)
        payload=plain_path(stage/'payload',directory=True);parts=storage_parent(stage/'parts/marker')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_Redirect(catalog))
        done=verified=network_bytes=0;started=time.monotonic()
        for index,item in enumerate(catalog.entries):
            check();destination=payload/item.path;storage_parent(destination)
            destination=plain_path(destination,missing=True)
            if destination.exists() and destination.stat().st_size==item.size and digest(destination,cancelled=cancelled)==item.sha256:
                done+=item.size;verified+=item.size;report('downloading',done,verified);continue
            if destination.exists():destination.unlink()
            partial=plain_path(parts/(str(index)+'.part'),missing=True)
            offset=partial.stat().st_size if partial.exists() else 0
            if offset>item.size:partial.unlink();offset=0
            if shutil.disk_usage(root).free<item.size-offset+16*1024**2:raise OSError('Insufficient acquisition space')
            base_done=done
            if offset<item.size:
                headers={'Accept-Encoding':'identity'}
                if offset:headers['Range']='bytes='+str(offset)+'-'
                request=urllib.request.Request(item.url,headers=headers)
                with opener.open(request,timeout=10) as response:
                    _source(response.geturl(),catalog.hosts,catalog.test_loopback)
                    if response.status==206:
                        expected=f'bytes {offset}-{item.size-1}/{item.size}'
                        if response.headers.get('Content-Range')!=expected:raise ValueError('Unexpected resumed range')
                    elif response.status==200:offset=0
                    else:raise ValueError('Unexpected artifact response')
                    if response.headers.get('Content-Encoding','identity')!='identity':raise ValueError('Encoded artifact response')
                    length=response.headers.get('Content-Length')
                    if length is not None and (not length.isdigit() or int(length)!=item.size-offset):raise ValueError('Artifact length mismatch')
                    with partial.open('ab' if offset else 'wb') as stream:
                        done=base_done+offset;report('downloading',done,verified)
                        while offset<item.size:
                            check();chunk=response.read(min(65536,item.size-offset))
                            if not chunk:raise OSError('Artifact connection ended early')
                            stream.write(chunk);offset+=len(chunk);network_bytes+=len(chunk);done=base_done+offset
                            if bytes_per_second:
                                while network_bytes/bytes_per_second>time.monotonic()-started:
                                    check();time.sleep(max(0,min(.05,network_bytes/bytes_per_second-(time.monotonic()-started))))
                            report('downloading',done,verified)
                        if response.read(1):raise ValueError('Artifact exceeded declared length')
                        stream.flush();os.fsync(stream.fileno())
            elif not partial.exists():
                with partial.open('xb'):pass
            check();report('verifying',base_done+item.size,verified)
            if partial.stat().st_size!=item.size or digest(partial,cancelled=cancelled)!=item.sha256:
                partial.unlink();raise ValueError('Artifact checksum mismatch')
            partial.replace(destination);done=base_done+item.size;verified+=item.size
        check()
        actual={p.relative_to(payload).as_posix() for p in files(payload,cancelled)}
        if actual!={item.path for item in catalog.entries}:raise ValueError('Acquisition inventory mismatch')
        validate(payload,cancelled);check();report('publishing',done,verified)
        def commit():
            check();plain_path(payload,directory=True)
            if target.exists() or target.is_symlink():raise FileExistsError('Published version already exists')
            payload.rename(target)
        publish(commit)
        return {'root':str(target),'catalog_sha256':catalog.fingerprint,'revision':catalog.revision,'kind':catalog.kind,'bytes':done}


def validate_runtime(root,cancelled):
    return inspect_runtime(root,verify=True,cancelled=cancelled)
