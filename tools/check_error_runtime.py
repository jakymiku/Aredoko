"""Windowless probe using the staged app's own deps/runtimeconfig.

This is not WinUI/native UI validation. It reproduces the missing Regex
assembly under the old layout and checks Japanese errors under a fresh one.
"""
import argparse,json,shutil,subprocess,uuid
from pathlib import Path
from xml.sax.saxutils import escape
REPO=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--layout',type=Path,required=True);parser.add_argument('--old-layout',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to((REPO/'data').resolve()):parser.error('Probe evidence must stay in data')
    output.mkdir(parents=True,exist_ok=False)
    layouts=[('fresh',args.layout.resolve())]+([('old',args.old_layout.resolve())] if args.old_layout else [])
    for _,layout in layouts:
        if not layout.is_relative_to(REPO.resolve()):parser.error('Only repository-owned build layouts allowed')
        for name in ('Aredoko.Core.dll','Aredoko.WinUI.deps.json','Aredoko.WinUI.runtimeconfig.json'):
            if not (layout/name).is_file():parser.error('Missing layout input '+name)
    project=output/'Probe.csproj'
    project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><AssemblyName>Aredoko.ErrorProbe</AssemblyName></PropertyGroup><ItemGroup><ProjectReference Include="'+escape(str(REPO/'src/Aredoko.Core/Aredoko.Core.csproj'))+'" /></ItemGroup></Project>',encoding='utf-8')
    (output/'Program.cs').write_text(r'''using Aredoko.Core;
File.AppendAllText(args[0],string.Join("\n",new[]{
    ErrorText.Localize("Use at most 16 search words"),
    ErrorText.Localize("Entry 3: aliases must be a single word without spaces"),
    ErrorText.FromResponse("[]",503)}));
''',encoding='utf-8')
    build=subprocess.run(['dotnet','publish',str(project),'-c','Release','-r','win-x64','-p:SelfContained=true','-p:PublishTrimmed=true','--ignore-failed-sources'],cwd=REPO,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
    (output/'build.log').write_text(build.stdout+build.stderr,encoding='utf-8')
    if build.returncode:raise RuntimeError('Probe build failed; inspect build.log')
    source=output/'bin/Release/net10.0/win-x64/publish/Aredoko.ErrorProbe.dll';report={'pass':False,'gui_launched':False,'scenarios':[]}
    expected=['検索語は16語までにしてください。','3件目: 別名に空白は入れられません（1語ずつ「、」で区切ってください）。','バックエンドでエラーが起きました（503）。']
    for label,layout in layouts:
        dest=layout/('Aredoko.ErrorProbe-'+uuid.uuid4().hex+'.dll')
        if dest.exists():raise RuntimeError('Refuse to overwrite an existing probe')
        shutil.copyfile(source,dest)
        try:
            result=subprocess.run(['dotnet','exec','--depsfile',str(layout/'Aredoko.WinUI.deps.json'),'--runtimeconfig',str(layout/'Aredoko.WinUI.runtimeconfig.json'),str(dest),str(output/(label+'-messages.txt'))],cwd=layout,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        finally:dest.unlink()  # Only the one temporary file created above.
        (output/(label+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        passed=result.returncode==0 and (output/(label+'-messages.txt')).is_file() and (output/(label+'-messages.txt')).read_text(encoding='utf-8-sig').splitlines()==expected if label=='fresh' else result.returncode!=0 and 'System.Text.RegularExpressions' in result.stderr
        report['scenarios'].append({'layout':label,'exit_code':result.returncode,'expected_outcome':passed,'regex_in_deps':'System.Text.RegularExpressions.dll' in (layout/'Aredoko.WinUI.deps.json').read_text(encoding='utf-8')})
    report['pass']=all(x['expected_outcome'] for x in report['scenarios'])
    (output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    if not report['pass']:raise RuntimeError('Runtime probe did not produce the expected outcomes')

if __name__=='__main__':main()
