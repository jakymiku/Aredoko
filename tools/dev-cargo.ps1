# Run Cargo/Rust commands without installing Rust globally or changing persistent PATH/registry.
# Keep this a simple script: advanced-function common parameters would consume
# cargo flags such as -p and -v before they reach Cargo.
$CargoArguments = $args
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$rust = Join-Path $root 'data/development-tools/rust'
$cargoHome = Join-Path $rust 'cargo'
$rustupHome = Join-Path $rust 'rustup'
$executable = Join-Path $cargoHome 'bin/cargo.exe'
if (!(Test-Path -LiteralPath $executable)) {
    throw 'Local Rust toolchain missing in data/development-tools/rust.'
}
$toolchainBin = Join-Path $rustupHome 'toolchains/stable-x86_64-pc-windows-gnu/bin'
$pathPrefix = "$cargoHome\bin"
if (Test-Path -LiteralPath $toolchainBin) {
    $pathPrefix = "$pathPrefix;$toolchainBin"
}
$values = @{
    RUSTUP_HOME = $rustupHome
    CARGO_HOME = $cargoHome
    PATH = "$pathPrefix;$env:PATH"
}
$saved = @{}
try {
    foreach ($name in $values.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $values[$name], 'Process')
    }
    & $executable @CargoArguments
    $result = $LASTEXITCODE
} finally {
    foreach ($name in $saved.Keys) {
        if ($null -eq $saved[$name]) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
        }
    }
}
if ($result -ne 0) { throw "Local cargo exited with code $result" }
