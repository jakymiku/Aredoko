"""Choose an immutable development layout from the actual app payload.

WinApp's default AppX folder may keep an old trimmed deps.json. Separate
layouts by code/dependency/resource bytes; unchanged payloads reuse a layout.
"""
import argparse,hashlib,xml.etree.ElementTree as ET
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
    result=REPO/'data/winapp-layout'/f'{configuration}-{arch}-{fingerprint(inputs,project)}'
    if not result.resolve().is_relative_to((REPO/'data/winapp-layout').resolve()):raise ValueError('Layout outside build cache')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--configuration',choices=('Release','Debug'),default='Release');parser.add_argument('--arch',choices=('x64','x86','arm64'),default='x64')
    args=parser.parse_args()
    try:print(layout(args.configuration,args.arch))
    except (ValueError,OSError,ET.ParseError) as error:parser.error(str(error))
