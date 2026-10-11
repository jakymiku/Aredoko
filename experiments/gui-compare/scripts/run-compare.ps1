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
$driverProject = Join-Path $root 'experiments/gui-compare/ui-automation/GuiDriver.csproj'
$driverDll = Join-Path $root 'experiments/gui-compare/ui-automation/bin/Release/net10.0-windows/GuiDriver.dll'
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6)
$runDir = Join-Path $root ('cache/gui-compare/runs/' + $runId)
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$backend = $null
$appProcessId = $null
$driverProcess = $null
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
    Ensure-Exists $script:driverProject 'Windows UI Automation driver'
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
    # Validate/compile the native Windows UI Automation program before launching any app.
    Write-Host 'GUIの自動操作プログラムを検証・ビルドしています...'
    & dotnet build $script:driverProject -c Release --nologo -v minimal
    Check-Native 'Windows UI Automation build'
    Ensure-Exists $script:driverDll 'Windows UI Automation driver DLL'
    & dotnet $script:driverDll --self-test true
    Check-Native 'Windows UI Automation self-test'
    # Safe updater backs up modified generated source and validates hashes.
    & (Join-Path $script:root 'experiments/gui-compare/winui3/update-winui.ps1')
    Write-Host '両方のGUIと自動操作ツールの準備が完了しました。' -ForegroundColor Green -ForegroundColor Green
}
function Run-GuiOperation([string]$variant, [string]$phase, [int]$duration, [int]$trial) {
    $stem = "$variant-$phase-$trial"
    $result = Join-Path $script:runDir "$stem-automation.json"
    $stdout = Join-Path $script:runDir "$stem-automation.stdout.txt"
    $stderr = Join-Path $script:runDir "$stem-automation.stderr.txt"
    $script:driverProcess = Start-Process -FilePath (Get-Command dotnet).Source -ArgumentList @(
        ('"' + $script:driverDll + '"'), '--pid', "$script:appProcessId", '--variant', $variant,
        '--phase', $phase, '--seconds', "$duration", '--result', ('"' + $result + '"')
    ) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    if ($phase -ne 'Check') {
        # CPU/RAM sampler and actual mouse/keyboard actions run at the same time.
        # The C# driver independently proves each GUI change using UIA + API.
        & $script:measure -Variant $variant -Phase $phase -AppPid $script:appProcessId -BackendPid $script:backend.Id -Seconds $duration -Trial $trial -OutputDirectory $script:runDir
    }
    $deadlineMs = [int](($duration + 45) * 1000)
    if (-not $script:driverProcess.WaitForExit($deadlineMs)) {
        Stop-Process -Id $script:driverProcess.Id -Force -ErrorAction SilentlyContinue
        throw "GUI自動操作が時間内に終わりませんでした。診断ログ: $stderr"
    }
    $exitCode = $script:driverProcess.ExitCode
    $script:driverProcess = $null
    if (-not (Test-Path -LiteralPath $result)) {
        throw "GUI自動操作の検証結果が作成されていません。ログ: $stderr / $stdout"
    }
    $checked = Get-Content -LiteralPath $result -Raw -Encoding utf8 | ConvertFrom-Json
    if ($exitCode -ne 0 -or $checked.success -ne $true) {
        $errText = $checked.error
        throw "GUI自動操作が失敗したため測定を中止します。$errText / 詳細: $result / $stdout"
    }
    if ($phase -ne 'Idle' -and $checked.verified -le 0) {
        throw "GUIの操作結果を検証できません。無効な測定として中止: $result"
    }
    Write-Host "確認済み: $variant $phase (操作検証: $($checked.verified) 回)" -ForegroundColor Green
}
function Measure-Variant([string]$variant) {
    Start-Variant $variant
    Write-Host ''
    Write-Host "==== $variant : 自動操作チェック ====" -ForegroundColor Cyan
    Write-Host '検索・スクロール・作品選択・タグ保存を自動実行し、画面とDBへの反映を確認します。'
    Run-GuiOperation -variant $variant -phase 'Check' -duration 12 -trial 0
    Add-Content -LiteralPath (Join-Path $script:runDir 'automatic-checks.txt') -Value "$variant : GUI自動操作の全チェックPASS ($((Get-Date).ToString('o')))"
    $tasks = @(
        @{ Name='Idle'; Description='待機（操作なし）' },
        @{ Name='Search'; Description='検索（「雨の街」を入力・クリア）' },
        @{ Name='Scroll'; Description='一覧を上下にスクロール' },
        @{ Name='Detail'; Description='3作品を順番に選択して詳細確認' },
        @{ Name='Edit'; Description='テストタグを編集・保存し、DB反映を検証' }
    )
    for ($trial = 1; $trial -le $script:Trials; $trial++) {
        foreach ($task in $tasks) {
            Write-Host ''
            Write-Host "[$variant / $trial / $script:Trials] $($task.Description)・$($script:Seconds) 秒を自動実行..." -ForegroundColor Yellow
            Ensure-AppAlive $script:appProcessId $variant
            Run-GuiOperation -variant $variant -phase $task.Name -duration $script:Seconds -trial $trial
        }
    }
    Write-Host "$variant の検証完了。起動したテストアプリだけを終了します。"
    Stop-OwnedApp
}

try {
    Start-Transcript -LiteralPath (Join-Path $runDir 'session.log') | Out-Null
    $transcriptOn = $true
    Write-Host '=== Aredoko Tauri vs WinUI GUI Compare ===' -ForegroundColor Cyan
    Write-Host "Results: $runDir"
    if ($Trials -eq 0) {
        $mode = Read-Host 'モードを選択: 1 = お試し（10秒×1回）、2 = 本測定（20秒×3回） [Enterで1]'
        if ($mode -eq '2') { $Trials = 3; $Seconds = 20 } else { $Trials = 1; $Seconds = 10 }
    }
    if ($Seconds -eq 0) { $Seconds = 20 }
    Write-Host "測定条件: $Trials 回 × 各操作 $Seconds 秒"
    Write-Host '個人ファイルは操作せず、架空のテストデータのみ使用します。'
    Write-Host '計測中は他のアプリを操作せず、同じ画面解像度・表示倍率・電源モードを保ってください。'
    Write-Host 'GUI入力を自動化し、結果の検証に失敗したら停止します。'
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
    Write-Host 'すべて完了！summary.json と summary.txt を送ってください。' -ForegroundColor Green
    Write-Host "Results: $runDir"
    Start-Process -FilePath explorer.exe -ArgumentList @([char]34 + $runDir + [char]34) | Out-Null
} catch {
    Write-Host "中断: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Any completed CSVs and logs were kept in: $runDir"
    exit 1
} finally {
    if ($null -ne $driverProcess) {
        if (Get-Process -Id $driverProcess.Id -ErrorAction SilentlyContinue) {
            Stop-Process -Id $driverProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Stop-OwnedApp
    if ($null -ne $backend) {
        if (Get-Process -Id $backend.Id -ErrorAction SilentlyContinue) {
            Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if ($transcriptOn) { Stop-Transcript | Out-Null }
}
