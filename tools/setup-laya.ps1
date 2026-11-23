# No installation unless explicitly requested.
param([switch]$InstallAndDownload)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
Push-Location $repo
try {
    $python=Join-Path $repo '.venv-ai/Scripts/python.exe'
    if(-not (Test-Path -LiteralPath $python -PathType Leaf)){throw 'Set up the project AI environment first.'}
    $setupArguments=@('tools/setup_laya.py','--rate','6000000')
    if($InstallAndDownload){$setupArguments+='--install-and-download'}
    & $python @setupArguments
    if($LASTEXITCODE){throw 'Laya setup failed'}
}
finally{Pop-Location}
