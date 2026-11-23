"""Data-only binding for the single supported app-local MSVC component."""
import re
from urllib.parse import urlsplit

COMPONENT='THIRD_PARTY_NATIVE_LICENSES/msvc-v14'
CRT_NAMES=frozenset(('concrt140.dll','msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll',
    'msvcp140_atomic_wait.dll','msvcp140_codecvt_ids.dll','vcamp140.dll','vccorlib140.dll',
    'vcomp140.dll','vcruntime140.dll','vcruntime140_1.dll','vcruntime140_threads.dll'))


def validate_component(value,declared):
    fields={'format','source_sha256','version','license_document_sha256','license_url','redistribution_approved','dlls','notices'}
    if not isinstance(value,dict) or set(value)!=fields or value['format']!='aredoko-msvc-component-v1':
        raise ValueError('Unsupported native CRT component')
    for name in ('source_sha256','license_document_sha256'):
        if not isinstance(value[name],str) or re.fullmatch('[0-9a-f]{64}',value[name]) is None:
            raise ValueError('Invalid native CRT source binding')
    if (not isinstance(value['version'],str) or re.fullmatch(r'14\.\d+\.\d+\.\d+',value['version']) is None
            or value['redistribution_approved'] is not False or not isinstance(value['license_url'],str)):
        raise ValueError('Invalid native CRT version or approval claim')
    url=urlsplit(value['license_url'])
    if (url.scheme!='https' or url.netloc!='visualstudio.microsoft.com' or not url.path.startswith('/license-terms/')
            or url.query or url.fragment or any(c.isspace() for c in value['license_url'])):
        raise ValueError('Invalid native CRT terms source')
    notice_names={COMPONENT+'/'+name for name in ('runtime-license.docx','runtime-license.txt','NOTICE.txt')}
    for field,names,limit in (('dlls',CRT_NAMES,16*1024**2),('notices',notice_names,4*1024**2)):
        rows=value[field]
        if not isinstance(rows,list) or len(rows)!=len(names):raise ValueError('Incomplete native CRT component')
        seen=set()
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'path','bytes','sha256'}:raise ValueError('Invalid native CRT component entry')
            key=row['path']
            if (not isinstance(key,str) or key not in names or key in seen or type(row['bytes']) is not int
                    or not 1<=row['bytes']<=limit or not isinstance(row['sha256'],str)
                    or re.fullmatch('[0-9a-f]{64}',row['sha256']) is None):
                raise ValueError('Invalid native CRT component identity')
            seen.add(key);entry=declared.get(key.casefold())
            if entry is None or (entry['bytes'],entry['sha256'])!=(row['bytes'],row['sha256']):
                raise ValueError('Native CRT component differs from sealed inventory')
        if seen!=names:raise ValueError('Incomplete native CRT component')
    document=next(row for row in value['notices'] if row['path'].endswith('.docx'))
    if document['sha256']!=value['license_document_sha256']:raise ValueError('Native CRT original terms binding differs')
    return {'name':'Microsoft Visual C++ v14','version':value['version'],'source_sha256':value['source_sha256'],
        'notice_files':sorted(notice_names),'dll_files':sorted(CRT_NAMES),'redistribution_approved':False}
