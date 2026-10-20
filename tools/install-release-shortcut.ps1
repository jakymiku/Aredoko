# Run explicitly after extracting the staging folder to its permanent location.
# This creates only a current-user desktop shortcut; it does not register MSIX.
param([string]$Destination = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Aredoko Alpha.lnk'))
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native-arguments.ps1')
$python = Join-Path $PSScriptRoot 'runtime/python/python.exe'
$pythonw = Join-Path $PSScriptRoot 'runtime/python/pythonw.exe'
$launcher = Join-Path $PSScriptRoot 'tools/launch_release.py'
if (Test-Path -LiteralPath $Destination) { throw 'The shortcut already exists. Choose a new destination.' }
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) { throw 'The bundled Python runtime is missing.' }
& $python -B $launcher --check
if ($LASTEXITCODE -ne 0) { throw 'Release checks failed. No shortcut was created.' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut([IO.Path]::GetFullPath($Destination))
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = Join-AredokoNativeArguments -Values @('-B', $launcher)
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = (Join-Path $PSScriptRoot 'bin/Aredoko.WinUI.exe') + ',0'
$shortcut.Description = 'Aredoko Alpha'
$shortcut.Save()
Write-Host 'Aredoko Alpha shortcut created. Windows activation still requires validation.'
