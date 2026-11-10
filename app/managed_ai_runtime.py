"""Receipts derived from verified official wheels; supports cache-free reuse.

Selection pins the receipt digest in the existing launch preferences. This is
not a publisher signature or protection against replacement of both app and
preferences by the same Windows user.
"""
import hashlib
import json
import os
import re
import secrets
import zipfile
from pathlib import Path

from ai_runtime import MARKER, LIMIT, REQUIRED_MODULES, relative, object_pairs, digest, files, validate_abi
from ai_wheel_runtime import verify_wheels
from storage_lease import plain_path, storage_lease

FORMAT = 'aredoko-managed-ai-runtime-v1'
GENERATED={'.gitignore','pyvenv.cfg','aredoko-ai-environment-draft.json',
           'Scripts/python.exe','Scripts/pythonw.exe','Scripts/activate','Scripts/activate.bat',
           'Scripts/activate.fish','Scripts/Activate.ps1','Scripts/deactivate.bat'}
RECIPE_SHA256 = '2d99a5178762590aabc384ee27aecb66e6614241219b3321365b31631f707858'
CPYTHON_SHA512 = '0e667928bb4f19573c6cd88f65133b2e07b243a5c716f335b56aa66bb9ec6f82328256d22c3a29e23a0276ac5c6a6d786211feab524890ad1e56629196c6b29c'


def recipe():
    path = plain_path(Path(__file__).resolve().parents[1] / 'config/ai-runtime-recipes/cp313-cu128-draft.json')
    if path.stat().st_size > 1024**2:raise ValueError('AI recipe exceeds limit')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECIPE_SHA256:raise ValueError('AI recipe changed')
    return json.loads(raw, object_pairs_hook=object_pairs)


def verify_base(home, package, *, full=False, cancelled=lambda:False):
    home = plain_path(home, directory=True);package = plain_path(package)
    if package.stat().st_size > 128 * 1024**2:raise ValueError('Base package exceeds limit')
    with package.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha512').hexdigest() != CPYTHON_SHA512:
            raise ValueError('Official CPython package changed')
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            expected = set()
            for item in archive.infolist():
                if not item.filename.startswith('tools/') or item.is_dir():continue
                name = relative(item.filename[6:]);expected.add(name)
                critical = name in {'python.exe','python313.dll','vcruntime140.dll','vcruntime140_1.dll','Lib/site.py',
                                    'Lib/venv/scripts/nt/venvlauncher.exe','Lib/venv/scripts/nt/venvwlauncher.exe'}
                if not full and not critical:continue
                if cancelled():raise InterruptedError('Base verification cancelled')
                target = plain_path(home / name)
                with archive.open(item) as source:
                    original = hashlib.file_digest(source, 'sha256').hexdigest()
                if target.stat().st_size != item.file_size or digest(target, cancelled) != original:
                    raise ValueError('Managed base Python changed: ' + name)
    if full and {path.relative_to(home).as_posix() for path in files(home,cancelled,include_cache=True)} != expected:
        raise ValueError('Unlisted managed base Python files')


def verify_binding(root, home):
    cfg = plain_path(root/'pyvenv.cfg').read_text(encoding='utf-8')
    values = {}
    for line in cfg.splitlines():
        key,value = line.split(' = ',1)
        if key in values:raise ValueError('Duplicate venv configuration')
        values[key]=value
    if (values.get('include-system-site-packages')!='false' or values.get('version')!='3.13.17'
            or Path(values.get('home',''))!=home or Path(values.get('executable',''))!=home/'python.exe'):
        raise ValueError('Managed venv base binding changed')
    for name,original in (('python.exe','venvlauncher.exe'),('pythonw.exe','venvwlauncher.exe')):
        if plain_path(root/'Scripts'/name).read_bytes()!=plain_path(home/'Lib/venv/scripts/nt'/original).read_bytes():
            raise ValueError('Managed venv launcher changed')


def seal(root, artifacts, home, base_package, model_probe, *, cancelled=lambda:False, progress=None):
    """Only the setup owner calls this after a generated model inference probe."""
    from ai_profiles import DEFAULT_PROFILE
    if (model_probe.get('pass') is not True or model_probe.get('profile')!=DEFAULT_PROFILE.key
            or model_probe.get('device') not in ('cpu','cuda')):
        raise ValueError('A successful supported-model probe is required')
    root=plain_path(root,directory=True);home=plain_path(home,directory=True)
    marker=plain_path(root/MARKER,missing=True)
    if marker.exists():raise FileExistsError('Existing runtime receipt is never overwritten')
    verify_base(home,base_package,full=True,cancelled=cancelled)
    verify_binding(root,home)
    entries=[]
    verify_wheels(root,artifacts,recipe(),cancelled=cancelled,progress=progress,inventory=entries)
    official={entry['path'] for entry in entries}
    for path in files(root,cancelled,include_cache=True):
        name=path.relative_to(root).as_posix()
        if name in official:continue
        # Generated venv launch files are bound to the verified CPython above.
        # No other executable/module can be learned from the installed tree.
        if name not in GENERATED:
            raise ValueError('Unexpected generated runtime file: '+name)
        entries.append({'path':name,'bytes':path.stat().st_size,'sha256':digest(path,cancelled)})
    entries.sort(key=lambda entry:entry['path'])
    document={'format':FORMAT,'recipe_sha256':RECIPE_SHA256,'home':str(home),'base_package':str(Path(base_package).absolute()),'wheel_cache':str(Path(artifacts).absolute()),
              'probe':{'profile':model_probe['profile'],'device':model_probe['device']},
              'abi':{'python':'3.13','architecture':'x64','engine':'pytorch','compute':'cuda','torch':'2.9.1+cu128','cuda':'12.8','modules':list(REQUIRED_MODULES)},
              'entries':entries,'files_count':len(entries),'total_bytes':sum(entry['bytes'] for entry in entries)}
    with storage_lease(root.with_name(root.name+'-seal')):
        plain_path(marker,missing=True)
        if marker.exists():raise FileExistsError('Existing runtime receipt is never overwritten')
        temporary=root/('receipt-'+secrets.token_hex(12)+'.tmp')
        try:
            with temporary.open('x',encoding='utf-8') as stream:
                json.dump(document,stream,ensure_ascii=False,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
            if cancelled():raise InterruptedError('Runtime publication cancelled')
            plain_path(temporary);plain_path(marker,missing=True)
            os.replace(temporary,marker)
        finally:
            if temporary.exists():plain_path(temporary).unlink()
    return inspect(root,expected=digest(marker),verify=True,cancelled=cancelled,progress=progress)


def inspect(root, *, expected=None, verify=False, cancelled=lambda:False, progress=None):
    root=plain_path(root,directory=True);marker=plain_path(root/MARKER)
    if marker.stat().st_size>LIMIT:raise ValueError('Managed receipt exceeds limit')
    raw=marker.read_bytes();checksum=hashlib.sha256(raw).hexdigest()
    if expected is not None and checksum!=expected:raise ValueError('Selected runtime inventory changed')
    value=json.loads(raw,object_pairs_hook=object_pairs)
    if (not isinstance(value,dict) or set(value)!={'format','recipe_sha256','home','base_package','wheel_cache','probe','abi','entries','files_count','total_bytes'}
            or value['format']!=FORMAT or value['recipe_sha256']!=RECIPE_SHA256):raise ValueError('Invalid managed runtime receipt')
    lock=recipe();abi=validate_abi(value['abi'])
    if (abi['python']!='3.13' or abi['torch']!='2.9.1+cu128' or abi['compute']!='cuda'
            or abi['cuda']!='12.8' or abi['modules']!=list(REQUIRED_MODULES)):raise ValueError('Managed runtime ABI changed')
    from ai_profiles import DEFAULT_PROFILE
    if (not isinstance(value['probe'],dict) or set(value['probe'])!={'profile','device'}
            or value['probe']['profile']!=DEFAULT_PROFILE.key or value['probe']['device'] not in ('cpu','cuda')):
        raise ValueError('Managed runtime lacks model probe')
    for field in ('home','base_package','wheel_cache'):
        if not isinstance(value[field],str) or len(value[field])>4096 or any(ord(c)<32 for c in value[field]) or not Path(value[field]).is_absolute():raise ValueError('Invalid managed path')
    home=Path(value['home']);package=Path(value['base_package'])
    if not home.is_absolute() or not package.is_absolute():raise ValueError('Explicit managed base paths required')
    entries=value['entries']
    if not isinstance(entries,list) or not 1<=len(entries)<=100000:raise ValueError('Invalid managed entries')
    names=set();total=0
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!={'path','bytes','sha256'}:raise ValueError('Invalid managed entry')
        name=relative(entry['path'])
        if name.casefold() in names or name.casefold()==MARKER or type(entry['bytes'])is not int or entry['bytes']<0 or not isinstance(entry['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',entry['sha256']):
            raise ValueError('Invalid managed entry identity')
        names.add(name.casefold());total+=entry['bytes']
    required={'scripts/python.exe','scripts/pythonw.exe','pyvenv.cfg',*(f'lib/site-packages/{name}/__init__.py'.casefold() for name in abi['modules'])}
    if not required<=names or type(value['files_count'])is not int or value['files_count']!=len(entries) or type(value['total_bytes'])is not int or value['total_bytes']!=total or total>64*1024**3:
        raise ValueError('Incomplete managed runtime inventory')
    verify_base(home,package,full=verify,cancelled=cancelled);verify_binding(root,home)
    if expected is None:
        # An arbitrary selected folder cannot certify itself. Initial selection
        # requires the original verified wheels. Later use is bound to the
        # receipt digest stored by the settings publication owner.
        cache=Path(value['wheel_cache'])
        if not cache.is_absolute() or not cache.exists():raise ValueError('Original wheel cache required for first runtime selection')
        original=[]
        verify_wheels(root,cache,lock,cancelled=cancelled,progress=progress,inventory=original)
        authoritative={entry['path']:entry for entry in original}
        for entry in entries:
            name=entry['path']
            if name in authoritative:
                if entry!=authoritative[name]:raise ValueError('Receipt differs from original official wheel')
            elif name not in GENERATED:raise ValueError('Unrecognized generated runtime file')
    done=size=0
    for entry in entries:
        name=entry['path']
        if not verify and name.casefold() not in required:continue
        path=plain_path(root/name)
        if path.stat().st_size!=entry['bytes'] or digest(path,cancelled)!=entry['sha256']:raise ValueError('Managed runtime changed: '+name)
        done+=1;size+=entry['bytes']
        if progress:progress({'stage':'checking_runtime','files_done':done,'files_total':len(entries),'bytes_done':size,'bytes_total':total})
    if verify and {path.relative_to(root).as_posix().casefold() for path in files(root,cancelled,include_cache=True)}!=names|{MARKER}:
        raise ValueError('Unlisted or missing managed runtime files')
    if digest(marker,cancelled)!=checksum:raise ValueError('Managed receipt changed during verification')
    return {'root':str(root),'python':str(root/'Scripts/python.exe'),'manifest_sha256':checksum,'abi':abi,'files':len(entries),'bytes':total,
            'verification':'full' if verify else 'core_only','model_loaded':False,'driver_tested':value['probe']['device']=='cuda','cache_required':False}
