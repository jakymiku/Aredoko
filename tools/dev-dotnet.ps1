# Run SDK commands without installing .NET or changing persistent PATH/registry.
# Keep this a simple script: advanced-function common parameters would consume
# dotnet/MSBuild flags such as -p and -v before they reach the SDK.
$DotnetArguments = $args
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$tools = Join-Path $root 'data/development-tools'
$sdk = Join-Path $tools 'dotnet-10.0.403'
$executable = Join-Path $sdk 'dotnet.exe'
if (!(Test-Path -LiteralPath $executable)) {
    throw 'Local SDK missing. Run tools/prepare-dev-dotnet.ps1 first.'
}
$values = @{
    DOTNET_ROOT = $sdk
    DOTNET_ROOT_X64 = $sdk
    DOTNET_MULTILEVEL_LOOKUP = '0'
    DOTNET_CLI_HOME = (Join-Path $tools 'cli-home')
    DOTNET_CLI_TELEMETRY_OPTOUT = '1'
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
    DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
    DOTNET_ADD_GLOBAL_TOOLS_TO_PATH = '0'
    NUGET_PACKAGES = (Join-Path $tools 'nuget/packages')
    NUGET_HTTP_CACHE_PATH = (Join-Path $tools 'nuget/http-cache')
    PATH = "$sdk;$env:PATH"
}
$saved = @{}
try {
    foreach ($name in $values.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $values[$name], 'Process')
    }
    & $executable @DotnetArguments
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
if ($result -ne 0) { throw "Local dotnet exited with code $result" }
