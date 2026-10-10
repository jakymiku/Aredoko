# Safely update the existing generated WinUI benchmark. Never delete/re-scaffold it.
param([string]$Root = (Join-Path $PSScriptRoot 'generated'))
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath($Root)
if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw "WinUI project not found at $Root. Run setup-winui.ps1 only for a new project."
}
$mainCandidates = @(Get-ChildItem -LiteralPath $Root -Filter MainWindow.xaml.cs -Recurse -File |
    Where-Object { $_.FullName -notmatch '[\\/]obj[\\/]|[\\/]bin[\\/]' })
if ($mainCandidates.Count -ne 1) { throw "Expected exactly one project MainWindow.xaml.cs; found $($mainCandidates.Count)" }
$destinationDir = $mainCandidates[0].DirectoryName
$sourceDir = Join-Path $PSScriptRoot 'overrides'
$mainSource = Join-Path $sourceDir 'MainWindow.xaml.cs'
if (-not ((Get-Content -LiteralPath $mainSource -Raw).Contains('BuildTag = "EDITOR-v6"'))) {
    throw 'Expected EDITOR-v6 source marker is missing. Fetch the latest PR #3 source before updating.'
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($name in @('MainWindow.xaml.cs', 'MainWindow.xaml', 'BenchJson.cs', 'EditorState.cs')) {
    $src = Join-Path $sourceDir $name
    $dest = Join-Path $destinationDir $name
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Source missing: $src" }
    if (Test-Path -LiteralPath $dest -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $src).Hash -eq (Get-FileHash -LiteralPath $dest).Hash) {
            Write-Host "Unchanged: $name"
            continue
        }
        Copy-Item -LiteralPath $dest -Destination "$dest.bak-$stamp" -ErrorAction Stop
    }
    Copy-Item -LiteralPath $src -Destination $dest -Force -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $src).Hash -ne (Get-FileHash -LiteralPath $dest).Hash) {
        throw "Hash mismatch after copying $name"
    }
    Write-Host "Updated: $name"
}
Write-Host 'WinUI EDITOR-v6 rows and JSON sources are installed. Close the old app and run: winapp run . -c Release --detach --json'
