# Production / Standalone launcher for Aredoko.
# Does NOT require dotnet SDK, winapp CLI, or source git checkout.
param(
    [string]$Database = (Join-Path $env:LOCALAPPDATA 'Aredoko/catalog.sqlite'),
    [string]$AIProfile,
    [string]$AISettings,
    [string]$AIProfilesDirectory,
    [string]$ViewerSettings,
    [string]$TaggerProfile,
    [ValidateSet('max','mean-rrf')][string]$AIRanking = 'mean-rrf',
    [ValidateSet('system','light','dark')][string]$UITheme = 'system'
)
$ErrorActionPreference = 'Stop'
$distRoot = $PSScriptRoot
$logDirectory = Join-Path $env:LOCALAPPDATA 'Aredoko/logs'
New-Item -ItemType Directory -Force $logDirectory | Out-Null

# Verify python
$pythonCmd = $null
if (Test-Path (Join-Path $distRoot 'venv/Scripts/python.exe')) {
    $pythonCmd = (Join-Path $distRoot 'venv/Scripts/python.exe')
} elseif (Test-Path (Join-Path $distRoot '../.venv-ai/Scripts/python.exe')) {
    $pythonCmd = (Resolve-Path (Join-Path $distRoot '../.venv-ai/Scripts/python.exe')).Path
} elseif (Get-Command 'python' -ErrorAction SilentlyContinue) {
    $pythonCmd = 'python'
} else {
    throw 'Python 3.10+ is required to run the Aredoko backend. Please install Python or set up a venv.'
}

# Verify WinUI binary and backend script (supports standalone dist and repo checkout)
$winuiExe = $null
$serverScript = $null
if (Test-Path (Join-Path $distRoot 'bin/Aredoko.WinUI.exe')) {
    $winuiExe = Join-Path $distRoot 'bin/Aredoko.WinUI.exe'
    $serverScript = Join-Path $distRoot 'backend/app/production_server.py'
} elseif (Test-Path (Join-Path $distRoot '../src/Aredoko.WinUI/bin/x64/Release/net10.0-windows10.0.26100.0/win-x64/Aredoko.WinUI.exe')) {
    $winuiExe = (Resolve-Path (Join-Path $distRoot '../src/Aredoko.WinUI/bin/x64/Release/net10.0-windows10.0.26100.0/win-x64/Aredoko.WinUI.exe')).Path
    $serverScript = (Resolve-Path (Join-Path $distRoot '../app/production_server.py')).Path
} else {
    throw "WinUI executable not found at: $winuiExe"
}

$backend = $null
try {
    # Check port 8769 availability
    $probe = [Net.Sockets.TcpClient]::new()
    try {
        $probe.Connect('127.0.0.1', 8769)
        throw 'Port 8769 is already in use. Please close the other running Aredoko instance before starting.'
    } catch [Net.Sockets.SocketException] {
        # Expected: port is free
    } finally {
        $probe.Dispose()
    }

    $databasePath = [IO.Path]::GetFullPath($Database).TrimEnd('\')
    $backendArgs = @(
        $serverScript,
        '--db', ('"' + $databasePath + '"'),
        '--ai-ranking', $AIRanking
    )
    if ($AIProfile) {
        $profilePath = [IO.Path]::GetFullPath($AIProfile).TrimEnd('\')
        $backendArgs += @('--ai-profile', ('"' + $profilePath + '"'))
    }
    if ($AISettings) {
        $settingsPath = [IO.Path]::GetFullPath($AISettings).TrimEnd('\')
        $backendArgs += @('--ai-settings', ('"' + $settingsPath + '"'))
    }
    if ($AIProfilesDirectory) {
        $profilesDir = [IO.Path]::GetFullPath($AIProfilesDirectory).TrimEnd('\')
        $backendArgs += @('--ai-profiles-dir', ('"' + $profilesDir + '"'))
    }
    if ($TaggerProfile) {
        $taggerPath = [IO.Path]::GetFullPath($TaggerProfile).TrimEnd('\')
        $backendArgs += @('--tagger-profile', ('"' + $taggerPath + '"'))
    }

    $backendOutLog = Join-Path $logDirectory 'backend.log'
    $backendErrLog = Join-Path $logDirectory 'backend-error.log'
    $backend = Start-Process -FilePath $pythonCmd -ArgumentList $backendArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $backendOutLog -RedirectStandardError $backendErrLog

    # Wait for backend session probe
    $connected = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($backend.HasExited) {
            throw "Backend terminated unexpectedly. Check logs at: $backendErrLog"
        }
        try {
            $session = Invoke-RestMethod 'http://127.0.0.1:8769/api/session' -TimeoutSec 1
            if ($session.mode -eq 'production') {
                $connected = $true
                break
            }
        } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $connected) {
        throw "Backend connection timed out on port 8769. Check logs at: $backendErrLog"
    }

    # Launch published WinUI application
    $appArgs = @('--ui-theme', $UITheme)
    if ($ViewerSettings) {
        $appArgs += @('--viewer-settings', [IO.Path]::GetFullPath($ViewerSettings))
    }

    Write-Host "Starting Aredoko..."
    $appProcess = Start-Process -FilePath $winuiExe -ArgumentList $appArgs -PassThru
    Wait-Process -Id $appProcess.Id -ErrorAction SilentlyContinue
} finally {
    if ($backend -and -not $backend.HasExited) {
        Write-Host "Stopping Aredoko backend..."
        Stop-Process -InputObject $backend -Force -ErrorAction SilentlyContinue
    }
}
