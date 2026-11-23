param(
 [Parameter(Mandatory=$true)][int]$OwnedPid,
 [Parameter(Mandatory=$true)][string]$Executable,
 [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference='Stop'
$aredokoExpected=[IO.Path]::GetFullPath($Executable)
$aredokoProcess=Get-Process -Id $OwnedPid
if (-not [string]::Equals($aredokoProcess.Path,$aredokoExpected,[StringComparison]::OrdinalIgnoreCase)) { throw 'Process executable does not match the explicit frontend' }
$aredokoStarted=$aredokoProcess.StartTime
$aredokoModules=@($aredokoProcess.Modules | ForEach-Object { $_.FileName } | Sort-Object -Unique)
$aredokoCurrent=Get-Process -Id $OwnedPid
if ($aredokoCurrent.StartTime -ne $aredokoStarted) { throw 'Owned process changed during inspection' }
$aredokoReport=@{owned_pid=$OwnedPid;frontend=$aredokoExpected;modules=$aredokoModules;clean_machine_verified=$false;scope='read-only native modules on development PC';captured_at=(Get-Date).ToString('o')}
$aredokoStream=[IO.File]::Open([IO.Path]::GetFullPath($Output),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try { $aredokoWriter=[IO.StreamWriter]::new($aredokoStream,[Text.UTF8Encoding]::new($false));try { $aredokoWriter.Write(($aredokoReport | ConvertTo-Json -Depth 5)) } finally { $aredokoWriter.Dispose() } } finally { $aredokoStream.Dispose() }
