# Explicit native acquisition probe, not yet connected to the first-run GUI.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$Package = 'download'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$build = Join-Path $root 'data/development-tools'
New-Item -ItemType Directory -Force $build | Out-Null
$compiler = Join-Path ([Environment]::GetFolderPath('Windows')) 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$executable = Join-Path $build ('PythonSetup-' + [Guid]::NewGuid().ToString('N') + '.exe')
& $compiler /nologo /target:exe /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll "/out:$executable" (Join-Path $root 'src/Aredoko.Bootstrap/PythonSetup.cs')
if ($LASTEXITCODE -ne 0) { throw 'Native acquisition helper compilation failed' }
& $executable $OutputDirectory $Package
if ($LASTEXITCODE -ne 0) { throw 'Python preparation failed; incomplete staging retained, environment not published' }
