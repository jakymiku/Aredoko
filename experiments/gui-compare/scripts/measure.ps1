# Samples the real app process, verified child processes, and Python backend separately.
# Usage: .\measure.ps1 -Variant Tauri -Phase Scroll -AppPid 1234 -BackendPid 5678 -Seconds 20 -Trial 1
param(
    [Parameter(Mandatory)][ValidateSet('Tauri','WinUI')][string]$Variant,
    [Parameter(Mandatory)][ValidateSet('Idle','Search','Scroll','Edit','Detail')][string]$Phase,
    [Parameter(Mandatory)][ValidateRange(1,2147483647)][int]$AppPid,
    [Parameter(Mandatory)][ValidateRange(1,2147483647)][int]$BackendPid,
    [ValidateRange(3,300)][int]$Seconds = 20,
    [ValidateRange(1,30)][int]$Trial = 1,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\..\..\cache\gui-compare')
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $root | Out-Null
if ($AppPid -eq $BackendPid) { throw 'App PID and backend PID cannot be the same.' }
if (-not (Get-Process -Id $AppPid -ErrorAction SilentlyContinue)) { throw "App PID $AppPid not found" }
if (-not (Get-Process -Id $BackendPid -ErrorAction SilentlyContinue)) { throw "Backend PID $BackendPid not found" }
$records = [Collections.Generic.List[object]]::new()
$allCounters = [Collections.Generic.Dictionary[int, object]]::new()
$started = [DateTime]::UtcNow
$end = $started.AddSeconds($Seconds)
Write-Host "Sampling $Variant / $Phase / Trial $Trial for $Seconds seconds. Perform the same actions for both apps now."

while ([DateTime]::UtcNow -lt $end) {
    $all = @(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId)
    $descendants = [Collections.Generic.HashSet[int]]::new()
    [void]$descendants.Add($AppPid)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($entry in $all) {
            if ($descendants.Contains([int]$entry.ParentProcessId) -and -not $descendants.Contains([int]$entry.ProcessId)) {
                [void]$descendants.Add([int]$entry.ProcessId)
                $changed = $true
            }
        }
    }
    $time = [DateTime]::UtcNow.ToString('o')
    foreach ($pidValue in $descendants) {
        if ($pidValue -eq $BackendPid) { continue }
        $p = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if (-not $p) { continue }
        $records.Add([pscustomobject]@{
            timestamp=$time; variant=$Variant; phase=$Phase; trial=$Trial;
            component='ui-tree'; pid=[int]$p.Id; process_name=$p.ProcessName;
            working_set_bytes=[long]$p.WorkingSet64;
            private_bytes=[long]$p.PrivateMemorySize64;
            cpu_seconds=[double]$p.CPU
        })
    }
    $backend = Get-Process -Id $BackendPid -ErrorAction SilentlyContinue
    if ($backend) {
        $records.Add([pscustomobject]@{
            timestamp=$time; variant=$Variant; phase=$Phase; trial=$Trial;
            component='python'; pid=[int]$backend.Id; process_name=$backend.ProcessName;
            working_set_bytes=[long]$backend.WorkingSet64;
            private_bytes=[long]$backend.PrivateMemorySize64;
            cpu_seconds=[double]$backend.CPU
        })
    }
    Start-Sleep -Milliseconds 1000
}
if (-not $records.Count) { throw 'No samples: app may have exited' }
$name = "$Variant-$Phase-$Trial-$(Get-Date -Format 'yyyyMMdd-HHmmss').csv"
$path = Join-Path $root $name
$records.ToArray() | Export-Csv -NoTypeInformation -Path $path -Encoding utf8
Write-Host "Saved raw per-process measurements: $path ($($records.Count) records)"
Write-Host 'WorkingSet totals are upper-bound sums of possibly shared pages; do not call them unique RAM.'
