# Explicit download; development only. Never called by the product bootstrap.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$version = '10.0.403'
# Microsoft release-metadata/10.0/releases.json, checked 2026-11-10.
$expected = '7a114c318fa7f1d9822991b534b2814d0e78386ceda816b371f5141acefe741d87ccb606ede06cadac8f9ac5070e32b708a67bbd1619ff5e5a7858a27874ef48'
$root = Join-Path (Split-Path $PSScriptRoot -Parent) 'data/development-tools'
$target = Join-Path $root "dotnet-$version"
$archive = Join-Path $root "dotnet-sdk-$version-win-x64.zip"
New-Item -ItemType Directory -Force $root | Out-Null
if (Test-Path -LiteralPath $target) {
    throw "SDK directory already exists; refusing overwrite: $target"
}
if (!(Test-Path -LiteralPath $archive)) {
    $partial = "$archive.partial"
    Invoke-WebRequest "https://builds.dotnet.microsoft.com/dotnet/Sdk/$version/dotnet-sdk-$version-win-x64.zip" -OutFile $partial
    if ((Get-FileHash -LiteralPath $partial -Algorithm SHA512).Hash.ToLowerInvariant() -ne $expected) {
        throw 'SDK SHA512 mismatch. Partial archive retained for diagnosis; nothing executed.'
    }
    Move-Item -LiteralPath $partial -Destination $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash.ToLowerInvariant() -ne $expected) {
    throw 'Cached SDK SHA512 mismatch; nothing extracted or executed.'
}
$stage = Join-Path $root ("sdk-stage-" + [Guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $archive -DestinationPath $stage
Move-Item -LiteralPath $stage -Destination $target
Write-Output "Verified SDK $version extracted. Use tools/dev-dotnet.ps1; no persistent PATH/registry changes."
