"""Read-only MSVC acquisition receipt; never runs or extracts the selected EXE.

Windows metadata comes from Get-AuthenticodeSignature and FileVersionInfo.
A valid Microsoft signature is provenance evidence, not redistribution consent,
DLL inventory, clean-machine acceptance or proof of the claimed download URL.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from storage_lease import plain_path,storage_parent
from inspect_runtime_native import pe_machine

MAX_BYTES=96*1024*1024


def metadata(path):
    if os.name!='nt':raise RuntimeError('Authenticode inspection requires Windows')
    from prepare_portable import windows_directory
    powershell=windows_directory()/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script="""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$signature=Get-AuthenticodeSignature -LiteralPath $env:AREDOKO_REVIEW_FILE
$version=(Get-Item -LiteralPath $env:AREDOKO_REVIEW_FILE).VersionInfo
$signer=$signature.SignerCertificate
[ordered]@{
    status=$signature.Status.ToString()
    signer_name=$(if($null -ne $signer){$signer.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false)}else{''})
    signer_thumbprint=$(if($null -ne $signer){$signer.Thumbprint}else{''})
    product_name=$version.ProductName
    file_description=$version.FileDescription
    file_version=$version.FileVersion
    product_version=$version.ProductVersion
} | ConvertTo-Json -Compress
"""
    # A parent PowerShell 7 PSModulePath can make inbox Windows PowerShell load
    # incompatible PS7 modules. Resolve only this interpreter's inbox modules;
    # no execution policy or system/user environment is changed.
    environment={**os.environ,'AREDOKO_REVIEW_FILE':str(path),'PSModulePath':str(powershell.parent/'Modules')}
    result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-Command',script],shell=False,
        env=environment,capture_output=True,text=True,encoding='utf-8-sig',timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode or len(result.stdout.encode('utf-8'))>16384:raise RuntimeError('Windows signature inspection failed')
    return json.loads(result.stdout)


def inspect(path,source_url):
    path=plain_path(path)
    location=urlsplit(source_url)
    if (location.scheme!='https' or location.hostname not in ('aka.ms','download.visualstudio.microsoft.com')
        or location.username or location.password or location.fragment or any(c.isspace() for c in source_url)):
        raise ValueError('Declare an official Microsoft HTTPS source URL')
    stamp=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    initial=path.stat()
    if path.suffix.casefold()!='.exe' or not stat.S_ISREG(initial.st_mode) or not 1<=initial.st_size<=MAX_BYTES:
        raise ValueError('Expected a bounded ordinary redistributable EXE')
    hasher=hashlib.sha256();total=0
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno())
        while block:=stream.read(1024*1024):
            total+=len(block)
            if total>MAX_BYTES:raise ValueError('Installer exceeds inspection byte limit')
            hasher.update(block)
        if stamp(before)!=stamp(os.fstat(stream.fileno())):raise RuntimeError('Installer changed while hashing')
    machine=pe_machine(path)
    if machine not in ('x86','amd64','arm64'):raise ValueError('Expected a PE installer')
    value=metadata(path)
    if stamp(initial)!=stamp(plain_path(path).stat()) or total!=initial.st_size:raise RuntimeError('Installer changed during metadata inspection')
    fields=('status','signer_name','signer_thumbprint','product_name','file_description','file_version','product_version')
    if type(value) is not dict or any(not isinstance(value.get(key),str) or len(value[key])>1024 for key in fields):
        raise ValueError('Invalid signature/version metadata')
    if value['status']!='Valid' or value['signer_name']!='Microsoft Corporation' or not re.fullmatch('[0-9A-Fa-f]{40}',value['signer_thumbprint']):
        raise ValueError('A currently valid Microsoft Authenticode signature is required')
    if ('Microsoft Visual C++' not in value['product_name'] or '(x64)' not in value['product_name']
        or not re.fullmatch(r'14\.\d+\.\d+(?:\.\d+)?',value['file_version'])):
        raise ValueError('Expected Microsoft Visual C++ v14 x64 product metadata')
    return {'format':'aredoko-msvc-acquisition-review-v1','bytes':total,'sha256':hasher.hexdigest(),
        'declared_source_url':source_url,'download_origin_verified':False,'metadata':value,
        'installer_pe_machine':machine,'payload_architecture_verified':False,
        'installer_executed':False,'payload_extracted':False,'os_modified':False,
        'redistribution_approved':False,'clean_windows_verified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--source-url',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=Path(os.path.abspath(args.output));source=plain_path(args.source)
    if output==source:parser.error('Receipt must not overwrite the installer')
    storage_parent(output);plain_path(output,missing=True)
    review=inspect(source,args.source_url)
    with output.open('x',encoding='utf-8') as stream:json.dump(review,stream,ensure_ascii=False,indent=2)
    print(json.dumps({key:review[key] for key in ('bytes','sha256','installer_executed','redistribution_approved')}))


if __name__=='__main__':main()
