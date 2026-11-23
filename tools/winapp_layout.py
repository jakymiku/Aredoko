"""Choose an immutable development layout from the actual app payload.

WinApp's default AppX folder may keep an old trimmed deps.json. Separate
layouts by code/dependency/resource bytes; unchanged payloads reuse a layout.
"""
import argparse,hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]

def fingerprint(paths,base):
    digest=hashlib.sha256()
    for path in sorted(paths,key=lambda p:p.relative_to(base).as_posix()):
        if not path.is_file():raise ValueError('Build the WinUI payload first: '+path.name)
        data=path.read_bytes();name=path.relative_to(base).as_posix().encode('utf-8')
        digest.update(len(name).to_bytes(4,'big'));digest.update(name)
        digest.update(len(data).to_bytes(8,'big'));digest.update(data)
    return digest.hexdigest()[:20]

def layout(configuration='Release',arch='x64'):
    if configuration not in ('Release','Debug') or arch not in ('x64','x86','arm64'):raise ValueError('Unsupported configuration/architecture')
    project=REPO/'src/Aredoko.WinUI'
    framework=ET.parse(project/'Aredoko.WinUI.csproj').getroot().findtext('.//TargetFramework')
    output=project/'bin'/arch/configuration/framework/('win-'+arch)
    inputs=[output/name for name in ('Aredoko.WinUI.dll','Aredoko.Core.dll','Aredoko.WinUI.deps.json','Aredoko.WinUI.runtimeconfig.json')]
    if (output/'resources.pri').is_file():inputs.append(output/'resources.pri')
    inputs.extend(p for p in (project/'Assets').rglob('*') if p.is_file())
    inputs.extend(p for p in project.glob('*.appxmanifest') if p.is_file())
    inputs.append(project/'Aredoko.WinUI.csproj')
    inputs.extend(p for p in (project/'Properties/PublishProfiles').glob('*.pubxml') if p.is_file())
    result=REPO/'data/winapp-layout'/f'{configuration}-{arch}-v2-{fingerprint(inputs,project)}'
    if not result.resolve().is_relative_to((REPO/'data/winapp-layout').resolve()):raise ValueError('Layout outside build cache')
    return result


def verify_payload(expected, deployed):
    """Compare actual staged bytes; a cache name alone is not proof of freshness."""
    deployed=Path(deployed)
    checked={}
    for name,source in expected.items():
        destination=deployed/name
        if not source.is_file() or not destination.is_file():
            raise ValueError('Incomplete WinUI payload: '+name)
        expected_hash=hashlib.sha256(source.read_bytes()).hexdigest()
        if hashlib.sha256(destination.read_bytes()).hexdigest()!=expected_hash:
            raise ValueError('Stale or mismatched WinUI deployment: '+name)
        checked[name]=expected_hash
    return checked

def verify_deployment(deployed,configuration='Release',arch='x64'):
    # This project stages trimmed ReadyToRun assemblies in Release; comparing
    # them to the untrimmed bin/*.dll would incorrectly reject a current build.
    layout(configuration,arch) # Validate configuration/architecture and raw build.
    project=REPO/'src/Aredoko.WinUI'
    framework=ET.parse(project/'Aredoko.WinUI.csproj').getroot().findtext('.//TargetFramework')
    output=project/'bin'/arch/configuration/framework/('win-'+arch)
    assemblies=project/'obj'/arch/configuration/framework/('win-'+arch)/'R2R' if configuration=='Release' else output
    expected={name:assemblies/name for name in ('Aredoko.WinUI.dll','Aredoko.Core.dll')}
    for name,path in expected.items():
        if not path.is_file() or path.stat().st_mtime_ns<(output/name).stat().st_mtime_ns:
            raise ValueError('Build current WinUI deployment assemblies first: '+name)
    expected['Aredoko.WinUI.runtimeconfig.json']=output/'Aredoko.WinUI.runtimeconfig.json'
    dependency_source=assemblies.parent if configuration=='Release' else output
    expected['Aredoko.WinUI.deps.json']=dependency_source/'Aredoko.WinUI.deps.json'
    if (output/'resources.pri').is_file():expected['resources.pri']=output/'resources.pri'
    return verify_payload(expected,deployed)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--configuration',choices=('Release','Debug'),default='Release');parser.add_argument('--arch',choices=('x64','x86','arm64'),default='x64')
    parser.add_argument('--verify',type=Path,help='Verify staged bytes against this configuration before interacting with its UI')
    args=parser.parse_args()
    try:print(json.dumps(verify_deployment(args.verify,args.configuration,args.arch)) if args.verify else layout(args.configuration,args.arch))
    except (ValueError,OSError,ET.ParseError) as error:parser.error(str(error))
