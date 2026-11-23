# Explicit opt-in setup. Packages and model share a 6 MB/s bandwidth cap.
param([switch]$InstallAndDownload,[string]$AIProfile)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
if(-not $InstallAndDownload) {
    Write-Host 'Plan: project Python 3.11 venv; torch 2.9.1 CUDA12.8 + torchvision0.24.1; sentence-transformers6.1.0; transformers5.19.0; Pillow.'
    if($AIProfile){Write-Host 'Custom local profile: inspect its model/revision and download size before opt-in. Downloads capped at 6 MB/s.'}
    else {Write-Host 'EmbeddingGemma2 pinned revision, ~1.53GB. Allow ~10GB total. Downloads capped at 6 MB/s.'}
    if($AIProfile){Write-Host 'Explicit opt-in: setup-ai.ps1 -AIProfile <profile> -InstallAndDownload'}
    else {Write-Host 'Explicit opt-in: setup-ai.ps1 -InstallAndDownload'}
    exit 0
}
Push-Location $repo
try {
    $setupArguments=@('tools/setup_ai.py','--rate','6000000')
    if($AIProfile){$setupArguments+=@('--profile',[IO.Path]::GetFullPath($AIProfile))}
    & python @setupArguments
    if($LASTEXITCODE){throw 'AI setup failed'}
}
finally { Pop-Location }
