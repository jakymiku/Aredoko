"""Windowless modern-picker dependency probe using published deps/runtimeconfig.

Loads managed type metadata only. Does not create a picker, WinUI window,
AI process or GPU context. Old/fresh layouts are never otherwise modified.
"""
import argparse,json,shutil,subprocess,uuid
from xml.sax.saxutils import escape
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--layout',type=Path,required=True);parser.add_argument('--old-layout',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((REPO/'data').resolve()):parser.error('Probe evidence must stay in data')
    output.mkdir(parents=True,exist_ok=False)
    layouts=[('fresh',args.layout.resolve())]+([('old',args.old_layout.resolve())] if args.old_layout else [])
    for _,layout in layouts:
        if not layout.is_relative_to(REPO.resolve()):parser.error('Only repository-owned build layouts allowed')
        for name in ('Microsoft.Windows.Storage.Pickers.Projection.dll','Aredoko.WinUI.deps.json','Aredoko.WinUI.runtimeconfig.json'):
            if not (layout/name).is_file():parser.error('Missing layout input '+name)
    project=output/'Probe.csproj'
    project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><AssemblyName>Aredoko.PickerProbe</AssemblyName></PropertyGroup><ItemGroup><Reference Include="Microsoft.Windows.Storage.Pickers.Projection"><HintPath>'+escape(str(layouts[0][1]/'Microsoft.Windows.Storage.Pickers.Projection.dll'))+'</HintPath><Private>false</Private></Reference></ItemGroup></Project>',encoding='utf-8')
    (output/'Program.cs').write_text('using Microsoft.Windows.Storage.Pickers;\nConsole.WriteLine(typeof(FolderPicker).FullName);Console.WriteLine(typeof(FileOpenPicker).FullName);',encoding='utf-8')
    build=subprocess.run(['dotnet','build',str(project),'-c','Release','--ignore-failed-sources'],cwd=REPO,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
    (output/'build.log').write_text(build.stdout+build.stderr,encoding='utf-8')
    if build.returncode:raise RuntimeError('Probe build failed; inspect build.log')
    source=output/'bin/Release/net10.0/Aredoko.PickerProbe.dll';report={'pass':False,'gui_launched':False,'scenarios':[]}
    expected=['Microsoft.Windows.Storage.Pickers.FolderPicker','Microsoft.Windows.Storage.Pickers.FileOpenPicker']
    for label,layout in layouts:
        dest=layout/('Aredoko.PickerProbe-'+uuid.uuid4().hex+'.dll')
        if dest.exists():raise RuntimeError('Refuse to overwrite an existing probe')
        shutil.copyfile(source,dest)
        try:
            result=subprocess.run(['dotnet','exec','--depsfile',str(layout/'Aredoko.WinUI.deps.json'),'--runtimeconfig',str(layout/'Aredoko.WinUI.runtimeconfig.json'),str(dest),str(output/(label+'-messages.txt'))],cwd=layout,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        finally:dest.unlink()  # Only the one temporary file created above.
        (output/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        passed=result.returncode==0 and result.stdout.splitlines()==expected if label=='fresh' else result.returncode!=0 and 'Microsoft.Windows.Storage.Pickers.Projection' in result.stderr
        report['scenarios'].append({'layout':label,'exit_code':result.returncode,'expected_outcome':passed,'pickers_in_deps':'Microsoft.Windows.Storage.Pickers.Projection.dll' in (layout/'Aredoko.WinUI.deps.json').read_text(encoding='utf-8')})
    report['pass']=all(x['expected_outcome'] for x in report['scenarios'])
    (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    if not report['pass']:raise RuntimeError('Runtime probe did not produce the expected outcomes')

if __name__=='__main__':main()
