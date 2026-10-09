# Applies sample MainWindow only to a dedicated new official WinUI template; never edits user's existing projects.
param([string]$Root = (Join-Path $PSScriptRoot 'generated'))
$ErrorActionPreference = 'Stop'
if (-not (Get-Command winapp -ErrorAction SilentlyContinue)) { throw 'WinApp CLI 0.7+ is required. See docs/gui-compare.md.' }
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw '.NET SDK is required. See docs/gui-compare.md.' }
$Root = [IO.Path]::GetFullPath($Root)
if (Test-Path -LiteralPath $Root) { throw "Refusing to overwrite existing directory: $Root" }
& winapp new --name AredokoWinUiBench --output $Root --template winui --template-version latest --use-defaults
if ($LASTEXITCODE -ne 0) { throw 'Official WinUI scaffold failed' }
$xaml = @(Get-ChildItem -LiteralPath $Root -Filter MainWindow.xaml -Recurse -File)
$cs = @(Get-ChildItem -LiteralPath $Root -Filter MainWindow.xaml.cs -Recurse -File)
if ($xaml.Count -ne 1 -or $cs.Count -ne 1) { throw 'Unexpected official template layout; leave generated project unmodified and inspect it.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'overrides/MainWindow.xaml') -Destination $xaml[0].FullName
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'overrides/MainWindow.xaml.cs') -Destination $cs[0].FullName
Write-Host "WinUI benchmark prepared at $Root. Start common Python server first, then run: winapp run '$Root' -c Release --detach --json"
