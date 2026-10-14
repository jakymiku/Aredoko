"""C#-only compile check for the WinUI project on machines without Windows.

The real WinUI build needs the Windows-only XAML compiler (XamlCompiler.exe).
This tool copies the hand-written C# sources into a throwaway project under
data/ (ignored), replaces XAML code generation with field stubs derived from
x:Name elements, and compiles against the Windows App SDK reference
assemblies with EnableWindowsTargeting. It catches C# syntax/type/API errors
in code-behind and code-only controls.

It does NOT validate XAML markup, bindings, resources, event-handler wiring,
packaging, trimming or runtime behaviour, and is never a substitute for the
documented Windows x64 Release build or native GUI checks.

Usage: python tools/compile_check_winui.py [--output data/winui-compile-check]
Requires a .NET 10 SDK on PATH (or DOTNET env var). Restores NuGet packages.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
WINUI = ROOT / 'src' / 'Aredoko.WinUI'
CORE = ROOT / 'src' / 'Aredoko.Core' / 'Aredoko.Core.csproj'
PRESENTATION = 'http://schemas.microsoft.com/winfx/2006/xaml/presentation'
X_NS = 'http://schemas.microsoft.com/winfx/2006/xaml'
# Named element types that do not live in Microsoft.UI.Xaml.Controls.
TYPE_NAMESPACES = {
    'KeyboardAccelerator': 'Microsoft.UI.Xaml.Input',
    'MicaBackdrop': 'Microsoft.UI.Xaml.Media',
    'SolidColorBrush': 'Microsoft.UI.Xaml.Media',
    'RowDefinition': 'Microsoft.UI.Xaml.Controls',
    'ColumnDefinition': 'Microsoft.UI.Xaml.Controls',
}


def csharp_type(tag: str) -> str:
    if tag.startswith('{'):
        namespace, local = tag[1:].split('}', 1)
    else:
        namespace, local = PRESENTATION, tag
    if namespace == PRESENTATION:
        return f'global::{TYPE_NAMESPACES.get(local, "Microsoft.UI.Xaml.Controls")}.{local}'
    if namespace.startswith('using:'):
        return f'global::{namespace[6:]}.{local}'
    raise ValueError(f'unsupported XAML namespace for named element: {namespace}')


def stub_for(xaml: pathlib.Path) -> str:
    root = ET.parse(xaml).getroot()
    cls = root.get(f'{{{X_NS}}}Class')
    if not cls:
        raise ValueError(f'{xaml.name}: missing x:Class')
    namespace, name = cls.rsplit('.', 1)
    fields = []
    seen = set()
    for element in root.iter():
        field = element.get(f'{{{X_NS}}}Name')
        if field and field not in seen:
            seen.add(field)
            fields.append(f'    internal {csharp_type(element.tag)} {field} = null!;')
    body = '\n'.join(fields)
    return (f'// generated stub for {xaml.name}; compile check only\n#nullable enable\n'
            f'namespace {namespace};\npartial class {name}\n{{\n{body}\n'
            '    private void InitializeComponent() { }\n}\n')


PROJECT = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Library</OutputType>
    <TargetFramework>net10.0-windows10.0.26100.0</TargetFramework>
    <TargetPlatformMinVersion>10.0.17763.0</TargetPlatformMinVersion>
    <EnableWindowsTargeting>true</EnableWindowsTargeting>
    <RootNamespace>Aredoko_WinUI</RootNamespace>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <WindowsAppSDKSelfContained>false</WindowsAppSDKSelfContained>
    <WindowsPackageType>None</WindowsPackageType>
    <EnableMsixTooling>false</EnableMsixTooling>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <EnableCoreMrtTooling>false</EnableCoreMrtTooling>
    <AppxGeneratePriEnabled>false</AppxGeneratePriEnabled>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.WindowsAppSDK" Version="{sdk}" />
  </ItemGroup>
  <ItemGroup><ProjectReference Include="{core}" /></ItemGroup>
</Project>
'''


def sdk_version() -> str:
    tree = ET.parse(WINUI / 'Aredoko.WinUI.csproj')
    for ref in tree.getroot().iter('PackageReference'):
        if ref.get('Include') == 'Microsoft.WindowsAppSDK':
            return ref.get('Version')
    raise SystemExit('Microsoft.WindowsAppSDK version not found in Aredoko.WinUI.csproj')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--output', default='data/winui-compile-check')
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    data = (ROOT / 'data').resolve()
    if data not in output.parents:
        raise SystemExit('--output must be inside the ignored data/ folder')
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for source in sorted(WINUI.glob('*.cs')):
        shutil.copy2(source, output / source.name)
    for xaml in sorted(WINUI.glob('*.xaml')):
        (output / f'{xaml.stem}.g.stub.cs').write_text(stub_for(xaml), encoding='utf-8')
    (output / 'CompileCheck.csproj').write_text(
        PROJECT.format(sdk=sdk_version(), core=CORE.as_posix()), encoding='utf-8')
    dotnet = os.environ.get('DOTNET', 'dotnet')
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    result = subprocess.run([dotnet, 'build', str(output / 'CompileCheck.csproj'), '-c', 'Release', '-nologo'],
                            cwd=output, env=env, text=True, encoding='utf-8', errors='replace', capture_output=True)
    log = result.stdout + result.stderr
    (output / 'build.log').write_text(log, encoding='utf-8')
    diagnostics = sorted({line.strip() for line in log.splitlines() if ': error ' in line or ': warning CS' in line})
    for line in diagnostics:
        print(line.replace(str(output) + os.sep, ''))
    print(f'compile-check exit={result.returncode} diagnostics={len(diagnostics)} (XAML/runtime NOT validated)')
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
