# Diagnostic wrapper. The installed shortcut calls bundled pythonw directly.
param(
    [string]$Database,
    [string]$AIProfile,
    [string]$AISettings,
    [string]$AIProfilesDirectory,
    [string]$ViewerSettings,
    [string]$TaggerProfile,
    [string]$AIPython,
    [string]$ModelsRoot,
    [ValidateSet('max','mean-rrf')][string]$AIRanking,
    [ValidateSet('system','light','dark')][string]$UITheme,
    [switch]$Check
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot 'runtime/python/python.exe'
$launcher = Join-Path $PSScriptRoot 'tools/launch_release.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The bundled Python runtime is missing. Rebuild the release with --python-runtime. No system Python fallback is used.'
}
$arguments = @('-B', $launcher)
$paths = @{
    '--database' = $Database; '--ai-profile' = $AIProfile; '--ai-settings' = $AISettings
    '--ai-profiles-dir' = $AIProfilesDirectory; '--viewer-settings' = $ViewerSettings
    '--tagger-profile' = $TaggerProfile; '--ai-python' = $AIPython; '--models-root' = $ModelsRoot
}
foreach ($key in $paths.Keys) {
    if ($paths[$key]) { $arguments += @($key, [IO.Path]::GetFullPath($paths[$key])) }
}
if ($AIRanking) { $arguments += @('--ai-ranking', $AIRanking) }
if ($UITheme) { $arguments += @('--ui-theme', $UITheme) }
if ($Check) { $arguments += '--check' }
& $python @arguments
exit $LASTEXITCODE
