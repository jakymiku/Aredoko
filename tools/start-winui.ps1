# Development launcher: no dependency installation, no media scanning.
param([string]$Database = (Join-Path $env:LOCALAPPDATA 'Aredoko/catalog.sqlite'),[string]$AIProfile,[switch]$LayaIntent)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$logDirectory = Join-Path $env:LOCALAPPDATA 'Aredoko/logs'
New-Item -ItemType Directory -Force $logDirectory | Out-Null
foreach ($command in @('python','dotnet','winapp')) { Get-Command $command -ErrorAction Stop | Out-Null }
$backend = $null
Push-Location $repo
try {
    # Refuse to attach to an unknown service/database on our reserved port.
    $probe = [Net.Sockets.TcpClient]::new()
    try { $probe.Connect('127.0.0.1',8769); throw 'Port 8769 is in use. Close the other Aredoko launcher before starting.' }
    catch [Net.Sockets.SocketException] { } finally { $probe.Dispose() }
    $databasePath = [IO.Path]::GetFullPath($Database)
    if ($databasePath.Contains('"')) { throw 'Invalid database path' }
    $backendArguments=@('app/production_server.py','--db',('"'+$databasePath+'"'))
    if($AIProfile){
        $profilePath=[IO.Path]::GetFullPath($AIProfile)
        if($profilePath.Contains('"') -or -not (Test-Path -LiteralPath $profilePath -PathType Leaf)){throw 'Invalid AI profile path'}
        $backendArguments+=@('--ai-profile',('"'+$profilePath+'"'))
    }
    if($LayaIntent){$backendArguments+='--laya-intent'}
    $backend = Start-Process python -ArgumentList $backendArguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'backend.log') -RedirectStandardError (Join-Path $logDirectory 'backend-error.log')
    $connected = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        if ($backend.HasExited) { throw 'Backend stopped. See backend-error.log.' }
        try { $session=Invoke-RestMethod 'http://127.0.0.1:8769/api/session'; if ($session.mode -eq 'production') { $connected=$true;break } } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $connected) { throw 'Backend connection timed out.' }
    $result = & winapp run src/Aredoko.WinUI -c Release --detach --json
    if ($LASTEXITCODE -ne 0) { throw 'WinUI build/launch failed.' }
    $launch = ($result -join "`n") | ConvertFrom-Json
    if (-not $launch.ProcessId) { throw 'No application process returned.' }
    Write-Host 'Aredoko is running. Close the app to stop its backend.'
    Wait-Process -Id $launch.ProcessId -ErrorAction SilentlyContinue
} finally {
    if ($backend -and -not $backend.HasExited) { Stop-Process -InputObject $backend }
    Pop-Location
}
