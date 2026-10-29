"""Fixed CPython 3.11.9 notice binding; no supplier or legal approval claims."""
import re
from urllib.parse import urlsplit

COMPONENT='THIRD_PARTY_NATIVE_LICENSES/cpython-3.11.9'
NATIVE_NAMES=frozenset(('python.exe','pythonw.exe','python3.dll','python311.dll',*(
    'DLLs/'+name for name in ('_asyncio.pyd','_bz2.pyd','_ctypes.pyd','_ctypes_test.pyd','_decimal.pyd',
    '_elementtree.pyd','_hashlib.pyd','_lzma.pyd','_msi.pyd','_multiprocessing.pyd','_overlapped.pyd',
    '_queue.pyd','_socket.pyd','_sqlite3.pyd','_ssl.pyd','_testbuffer.pyd','_testcapi.pyd',
    '_testconsole.pyd','_testimportmultiple.pyd','_testinternalcapi.pyd','_testmultiphase.pyd',
    '_tkinter.pyd','_uuid.pyd','_zoneinfo.pyd','libcrypto-3.dll','libffi-8.dll','libssl-3.dll',
    'pyexpat.pyd','select.pyd','sqlite3.dll','tcl86t.dll','tk86t.dll','unicodedata.pyd','winsound.pyd'))))
SOURCE_NAMES=frozenset(('python-upstream-LICENSE.txt','python-doc-license.rst','openssl-LICENSE.txt',
    'openssl-AUTHORS.md','libffi-LICENSE.txt','bzip2-LICENSE.txt','xz-COPYING.txt','zlib-README.txt',
    'expat-COPYING.txt','mpdecimal-LICENSE.txt','sqlite-copyright.html','tcl-license.terms','tk-license.terms'))
NOTICE_NAMES=SOURCE_NAMES|{'python-installed-LICENSE.txt','sources.json','reference.json','NOTICE.txt'}


def checksum(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def notice_bindings():
    common=['python-installed-LICENSE.txt','python-upstream-LICENSE.txt','python-doc-license.rst','NOTICE.txt']
    special={
        'python311.dll':['zlib-README.txt'],
        'DLLs/_bz2.pyd':['bzip2-LICENSE.txt'], 'DLLs/_decimal.pyd':['mpdecimal-LICENSE.txt'],
        'DLLs/_lzma.pyd':['xz-COPYING.txt'], 'DLLs/pyexpat.pyd':['expat-COPYING.txt'],
        'DLLs/_hashlib.pyd':['openssl-LICENSE.txt','openssl-AUTHORS.md'],
        'DLLs/_ssl.pyd':['openssl-LICENSE.txt','openssl-AUTHORS.md'],
        'DLLs/libcrypto-3.dll':['openssl-LICENSE.txt','openssl-AUTHORS.md'],
        'DLLs/libssl-3.dll':['openssl-LICENSE.txt','openssl-AUTHORS.md'],
        'DLLs/libffi-8.dll':['libffi-LICENSE.txt'], 'DLLs/_ctypes.pyd':['libffi-LICENSE.txt'],
        'DLLs/_ctypes_test.pyd':['libffi-LICENSE.txt'], 'DLLs/sqlite3.dll':['sqlite-copyright.html'],
        'DLLs/_sqlite3.pyd':['sqlite-copyright.html'], 'DLLs/tcl86t.dll':['tcl-license.terms'],
        'DLLs/tk86t.dll':['tk-license.terms','tcl-license.terms'],
        'DLLs/_tkinter.pyd':['tcl-license.terms','tk-license.terms']}
    return {name:sorted(COMPONENT+'/'+n for n in common+special.get(name,[])) for name in sorted(NATIVE_NAMES)}


def validate_sources(value):
    if (not isinstance(value,dict) or set(value)!={'format','version','date','redistribution_approved','source_executed','entries'}
        or value['format']!='aredoko-cpython-notice-sources-v1' or value['version']!='3.11.9'
        or value['redistribution_approved'] is not False or value['source_executed'] is not False
        or not isinstance(value['date'],str) or re.fullmatch(r'\d{4}-\d{2}-\d{2}',value['date']) is None):
        raise ValueError('Invalid CPython notice sources')
    entries=value['entries'];seen=set();total=0
    if not isinstance(entries,list) or len(entries)!=len(SOURCE_NAMES):raise ValueError('Incomplete CPython notice sources')
    for row in entries:
        if not isinstance(row,dict) or set(row)!={'path','bytes','sha256','source_url','source_bytes','source_sha256','extraction','mutable_source_snapshot'}:
            raise ValueError('Invalid CPython notice source entry')
        name=row['path'];total+=row['bytes'] if type(row['bytes']) is int else 0
        if (not isinstance(name,str) or name not in SOURCE_NAMES or name in seen or type(row['bytes']) is not int
            or not 1<=row['bytes']<=1024**2 or type(row['source_bytes']) is not int or not row['bytes']<=row['source_bytes']<=1024**2
            or not checksum(row['sha256']) or not checksum(row['source_sha256']) or not isinstance(row['source_url'],str)):
            raise ValueError('Invalid CPython notice source binding')
        url=urlsplit(row['source_url'])
        if url.query or url.fragment or any(c.isspace() for c in row['source_url']):raise ValueError('Invalid notice source URL')
        if name=='sqlite-copyright.html':
            if row['source_url']!='https://sqlite.org/copyright.html' or row['mutable_source_snapshot'] is not True:raise ValueError('Invalid SQLite notice source')
        elif (url.scheme!='https' or url.netloc!='raw.githubusercontent.com' or row['mutable_source_snapshot'] is not False or
              re.fullmatch(r'/(?:python/cpython|python/cpython-source-deps|openssl/openssl)/[0-9a-f]{40}/[^?#]+',url.path) is None):
            raise ValueError('Commit-pinned upstream notice URL required')
        expected='leading-c-license-comment' if name=='mpdecimal-LICENSE.txt' else 'none'
        if row['extraction']!=expected:raise ValueError('Unexpected notice extraction')
        if expected=='none' and (row['bytes'],row['sha256'])!=(row['source_bytes'],row['source_sha256']):
            raise ValueError('Original notice bytes must be retained')
        seen.add(name)
    if total>256*1024:raise ValueError('CPython notice sources exceed limit')
    return entries


def validate_reference(value,parent_sha,declared):
    if (not isinstance(value,dict) or value.get('format')!='aredoko-cpython-native-reference-v1'
        or value.get('runtime_manifest_sha256')!=parent_sha
        or any(value.get(k) is not False for k in ('redistribution_approved','version_resources_are_supplier_proof','source_executed','registry_enabled'))):
        raise ValueError('CPython reference belongs to another source or claims approval')
    rows=value.get('entries');seen=set();total=0
    if not isinstance(rows,list) or len(rows)!=len(NATIVE_NAMES):raise ValueError('Complete CPython reference required')
    versions={'DLLs/libcrypto-3.dll':'3.0.13','DLLs/libssl-3.dll':'3.0.13','DLLs/libffi-8.dll':None,
              'DLLs/sqlite3.dll':'3.45.1.0','DLLs/tcl86t.dll':'8.6.12','DLLs/tk86t.dll':'8.6.12'}
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Invalid CPython native reference')
        key=row.get('path');entry=declared.get(key.casefold()) if isinstance(key,str) else None
        if (not isinstance(key,str) or key not in NATIVE_NAMES or key in seen or type(row.get('bytes')) is not int or not 1<=row['bytes']<=32*1024**2
            or entry is None or (row['bytes'],row.get('sha256'))!=(entry['bytes'],entry['sha256'])
            or row.get('file_version')!=versions.get(key,'3.11.9') or row.get('product_version')!=versions.get(key,'3.11.9')):
            raise ValueError('CPython native reference differs from source')
        seen.add(key);total+=row['bytes']
    if total>128*1024**2:raise ValueError('CPython native reference exceeds limit')
    return rows


def validate_component(value,declared):
    fields={'format','version','source_runtime_manifest_sha256','reference_sha256','notice_sources_sha256',
            'redistribution_approved','supplier_binary_hashes_verified','notice_coverage_reviewed','natives','notices','file_notice_bindings'}
    if (not isinstance(value,dict) or set(value)!=fields or value['format']!='aredoko-cpython-component-v1' or value['version']!='3.11.9'
        or any(value[k] is not False for k in ('redistribution_approved','supplier_binary_hashes_verified','notice_coverage_reviewed'))
        or not all(checksum(value[k]) for k in ('source_runtime_manifest_sha256','reference_sha256','notice_sources_sha256'))):
        raise ValueError('Invalid CPython native component or approval claim')
    for field,names,limit in (('natives',NATIVE_NAMES,32*1024**2),('notices',{COMPONENT+'/'+n for n in NOTICE_NAMES},4*1024**2)):
        rows=value[field];seen=set()
        if not isinstance(rows,list) or len(rows)!=len(names):raise ValueError('Incomplete CPython component')
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'path','bytes','sha256'}:raise ValueError('Invalid CPython component entry')
            key=row['path']
            if (not isinstance(key,str) or key not in names or key in seen or type(row['bytes']) is not int
                or not 1<=row['bytes']<=limit or not checksum(row['sha256'])):raise ValueError('Invalid CPython component identity')
            entry=declared.get(key.casefold())
            if entry is None or (row['bytes'],row['sha256'])!=(entry['bytes'],entry['sha256']):raise ValueError('CPython component differs from sealed inventory')
            seen.add(key)
    if value['file_notice_bindings']!=notice_bindings():raise ValueError('Incomplete per-file CPython notice bindings')
    source=next(x for x in value['notices'] if x['path']==COMPONENT+'/sources.json')
    reference=next(x for x in value['notices'] if x['path']==COMPONENT+'/reference.json')
    if reference['sha256']!=value['reference_sha256']:raise ValueError('CPython reference hash differs')
    installed=next(x for x in value['notices'] if x['path']==COMPONENT+'/python-installed-LICENSE.txt')
    original=declared.get('license.txt')
    if source['sha256']!=value['notice_sources_sha256'] or original is None or (installed['bytes'],installed['sha256'])!=(original['bytes'],original['sha256']):
        raise ValueError('CPython source or installed license binding differs')
    return {'name':'CPython Windows distribution','version':'3.11.9','source_runtime_manifest_sha256':value['source_runtime_manifest_sha256'],
            'reference_sha256':value['reference_sha256'],'native_files':sorted(NATIVE_NAMES),
            'notice_files':sorted(COMPONENT+'/'+n for n in NOTICE_NAMES),'file_notice_bindings':value['file_notice_bindings'],
            'supplier_binary_hashes_verified':False,'notice_coverage_reviewed':False,'redistribution_approved':False}
