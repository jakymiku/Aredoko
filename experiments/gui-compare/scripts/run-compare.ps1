# Aredoko GUI comparison orchestrator for Windows (run GUI-Compare.bat).
# Uses only the 50,000-row synthetic fixture. Does not inspect personal files.
param(
    [ValidateRange(0,3)][int]$Trials = 0,
    [ValidateRange(0,300)][int]$Seconds = 0
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$tauriDir = Join-Path $root 'experiments/gui-compare/tauri-react'
$tauriExe = Join-Path $tauriDir 'src-tauri/target/release/aredoko_tauri_bench.exe'
$winuiDir = Join-Path $root 'experiments/gui-compare/winui3/generated'
$measure = Join-Path $PSScriptRoot 'measure.ps1'
$report = Join-Path $PSScriptRoot 'report.py'
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6)
$runDir = Join-Path $root ('cache/gui-compare/runs/' + $runId)
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$backend = $null
$appProcessId = $null
$transcriptOn = $false
$port = 8768
$base = 'http://127.0.0.1:8768'

function Ensure-Exists([string]$path, [string]$label) {
    if (-not (Test-Path -LiteralPath $path)) { throw "$label not found: $path" }
}
function Check-Native([string]$label) {
    if ($LASTEXITCODE -ne 0) { throw "$label failed (exit $LASTEXITCODE)" }
}
function Check-Abort([string]$hint) {
    $answer = Read-Host $hint
    if ($answer -match '^(q|quit|x)$') { throw 'Cancelled by user' }
}
function Ensure-AppAlive([int]$id, [string]$label) {
    Start-Sleep -Seconds 2
    if (-not (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
        throw "$label exited before measurement; see its launch log and Windows Event Viewer"
    }
}
function Stop-OwnedApp {
    if ($null -ne $script:appProcessId) {
        $p = Get-Process -Id $script:appProcessId -ErrorAction SilentlyContinue
        if ($p) {
            Stop-Process -Id $script:appProcessId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        $script:appProcessId = $null
    }
}
function Start-Variant([string]$variant) {
    if ($variant -eq 'Tauri') {
        Ensure-Exists $script:tauriExe 'Tauri Release EXE'
        $p = Start-Process -FilePath $script:tauriExe -WorkingDirectory (Split-Path $script:tauriExe -Parent) -PassThru
        $script:appProcessId = [int]$p.Id
    } else {
        $winappLog = Join-Path $script:runDir 'winapp-launch.txt'
        Push-Location $script:winuiDir
        try {
            $output = @(& winapp run . -c Release --detach --json 2>&1)
            $output | Out-File -LiteralPath $winappLog -Encoding utf8
            Check-Native 'WinUI Release build/launch'
            $ids = [regex]::Matches(($output -join [Environment]::NewLine), '"ProcessId"\s*:\s*(\d+)')
            if ($ids.Count -eq 0) { throw "WinApp CLI did not return ProcessId. See $winappLog" }
            $script:appProcessId = [int]$ids[$ids.Count-1].Groups[1].Value
        } finally {
            Pop-Location
        }
    }
    Ensure-AppAlive $script:appProcessId $variant
    Write-Host "Started $variant (PID $script:appProcessId)" -ForegroundColor Green
}
function Start-Backend {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $script:port)
    try {
        $listener.Start()
    } catch {
        throw "Port $script:port is in use. Close the existing Aredoko Python server and rerun. ($_)"
    } finally {
        $listener.Stop()
    }
    $fixture = Join-Path $script:runDir 'synthetic.sqlite'
    $stdout = Join-Path $script:runDir 'backend.stdout.txt'
    $stderr = Join-Path $script:runDir 'backend.stderr.txt'
    $quotedDb = [char]34 + $fixture + [char]34
    $quotedDist = [char]34 + (Join-Path $script:tauriDir 'dist') + [char]34
    $python = (Get-Command python -ErrorAction Stop).Source
    $script:backend = Start-Process -FilePath $python -ArgumentList @(
        '-u', 'app/server.py', '--port', "$script:port",
        '--db', $quotedDb, '--benchmark-dist', $quotedDist
    ) -WorkingDirectory $script:root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    $ready = $false
    for ($i = 0; $i -lt 120; $i++) {
        if ($script:backend.HasExited) {
            throw "Python server exited. See $stderr and $stdout"
        }
        try {
            $session = Invoke-RestMethod -Uri ($script:base + '/api/session') -TimeoutSec 2
            if ($session.stats.total -eq 50000) { $ready = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Fixture server did not become ready. See $stderr" }
    Write-Host "Python API ready: 50,000 synthetic records (PID $($script:backend.Id))" -ForegroundColor Green
}
function Build-Benchmarks {
    Ensure-Exists (Join-Path $script:tauriDir 'package.json') 'React project'
    Ensure-Exists $script:measure 'measure.ps1'
    Ensure-Exists $script:report 'report.py'
    foreach ($exe in @('python','npm.cmd','cargo','dotnet','winapp')) {
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { throw "Missing tool: $exe" }
    }
    $oldApps = @(Get-Process -Name 'aredoko_tauri_bench','AredokoWinUiBench' -ErrorAction SilentlyContinue)
    if ($oldApps.Count -gt 0) {
        throw "Close all existing Tauri/WinUI Aredoko test windows first. PIDs: $(($oldApps.Id) -join ', ')"
    }
    Ensure-Exists $script:winuiDir 'generated WinUI project'
    Write-Host 'Building latest React/Tauri Release (may take a few minutes)...'
    Push-Location $script:tauriDir
    try {
        if (-not (Test-Path 'node_modules')) {
            & npm.cmd install --no-audit --no-fund --no-package-lock
            Check-Native 'npm install'
        }
        & npm.cmd run build
        Check-Native 'React Release build'
        $icon = Join-Path $script:tauriDir 'src-tauri/icons/icon.ico'
        $svg = Join-Path $script:tauriDir 'src-tauri/app-icon.svg'
        if (-not (Test-Path $icon)) {
            Ensure-Exists $svg 'Tauri icon source SVG'
            & npm.cmd run tauri icon -- $svg
            Check-Native 'Tauri icon generation'
        }
        & npm.cmd run tauri build -- --no-bundle
        Check-Native 'Tauri Release build'
    } finally { Pop-Location }
    # Safe updater backs up modified generated source and validates hashes.
    & (Join-Path $script:root 'experiments/gui-compare/winui3/update-winui.ps1')
    Write-Host 'Tauri and WinUI benchmark sources prepared.' -ForegroundColor Green
}
function Measure-Variant([string]$variant) {
    Start-Variant $variant
    Write-Host ''
    Write-Host "==== $variant : manual functionality check ====" -ForegroundColor Cyan
    Write-Host 'In the GUI: select several items; search; change page; edit a tag and SAVE it.'
    Write-Host 'Make sure the detail pane follows selection and the save is retained.'
    Check-Abort 'When functionality PASS, press Enter. If it fails type q then Enter'
    Add-Content -LiteralPath (Join-Path $script:runDir 'manual-checks.txt') -Value "$variant : manually marked PASS at $(Get-Date -Format o)"
    $tasks = @(
        @{ Name='Idle'; Message='Hands off mouse/keyboard; leave list visible.' },
        @{ Name='Search'; Message='During sampling, search for a title/tag (same text in both apps).' },
        @{ Name='Scroll'; Message='During sampling, scroll list up/down repeatedly.' },
        @{ Name='Detail'; Message='During sampling, select several different items.' },
        @{ Name='Edit'; Message='During sampling, edit a tag and save; only synthetic DB is changed.' }
    )
    for ($trial = 1; $trial -le $script:Trials; $trial++) {
        foreach ($task in $tasks) {
            Write-Host ''
            Write-Host "[$variant, run $trial/$script:Trials] $($task.Name): $($task.Message)" -ForegroundColor Yellow
            Check-Abort 'Prepare the GUI first; press Enter to start timed sampling (q to cancel)'
            Ensure-AppAlive $script:appProcessId $variant
            & $script:measure -Variant $variant -Phase $task.Name -AppPid $script:appProcessId -BackendPid $script:backend.Id -Seconds $script:Seconds -Trial $trial -OutputDirectory $script:runDir
        }
    }
    Write-Host "Completed $variant; closing only the benchmark app started by this tool."
    Stop-OwnedApp
}
try {
    Start-Transcript -LiteralPath (Join-Path $runDir 'session.log') | Out-Null
    $transcriptOn = $true
    Write-Host '=== Aredoko Tauri vs WinUI GUI Compare ===' -ForegroundColor Cyan
    Write-Host "Results: $runDir"
    if ($Trials -eq 0) {
        $mode = Read-Host 'Mode: 1 = quick (1 trial x 10s), 2 = full (3 trials x 20s). Default 1'
        if ($mode -eq '2') { $Trials = 3; $Seconds = 20 } else { $Trials = 1; $Seconds = 10 }
    }
    if ($Seconds -eq 0) { $Seconds = 20 }
    Write-Host "Selected $Trials trial(s), $Seconds seconds per phase."
    Write-Host 'Only fictional fixture data is used. Existing libraries and other files are untouched.'
    Write-Host 'Keep resolution, display scale and power mode identical for both apps.'
    Build-Benchmarks
    Start-Backend
    foreach ($variant in @('Tauri','WinUI')) { Measure-Variant $variant }
    $csv = @(Get-ChildItem -LiteralPath $runDir -Filter '*.csv' -File | Sort-Object Name)
    $expected = 2 * $Trials * 5
    if ($csv.Count -ne $expected) {
        throw "Incomplete measurements: expected $expected CSVs, got $($csv.Count)"
    }
    $summary = Join-Path $runDir 'summary.json'
    $summaryText = Join-Path $runDir 'summary.txt'
    $paths = @($csv | ForEach-Object { $_.FullName })
    & python $report @paths --json $summary | Tee-Object -FilePath $summaryText
    Check-Native 'report.py'
    Write-Host ''
    Write-Host 'Completed! Share summary.json and summary.txt for the comparison.' -ForegroundColor Green
    Write-Host "Results: $runDir"
    Start-Process -FilePath explorer.exe -ArgumentList @([char]34 + $runDir + [char]34) | Out-Null
} catch {
    Write-Host "STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Any completed CSVs and logs were kept in: $runDir"
    exit 1
} finally {
    Stop-OwnedApp
    if ($null -ne $backend) {
        if (Get-Process -Id $backend.Id -ErrorAction SilentlyContinue) {
            Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if ($transcriptOn) { Stop-Transcript | Out-Null }
}
