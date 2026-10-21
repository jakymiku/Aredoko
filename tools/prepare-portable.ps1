$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$runtimeRelease = Join-Path $repo 'dist/alpha-0-msix-20261021-02'
if (-not (Test-Path -LiteralPath $runtimeRelease -PathType Container)) {
    Add-Type -AssemblyName System.Windows.Forms
    $picker = New-Object System.Windows.Forms.FolderBrowserDialog
    $picker.Description = 'Pythonと動画runtimeを同梱した既存のAredoko配布フォルダを選択してください（ダウンロードは行いません）'
    if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 2 }
    $runtimeRelease = $picker.SelectedPath
    $picker.Dispose()
}
$taskPython = Join-Path $runtimeRelease 'runtime/python/python.exe'
if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw '同梱Pythonが見つかりません。既存のruntime入り配布を選択してください。' }
# Reuse explicit existing assets; -B never writes pyc into the sealed snapshot.
$portableOutput = Join-Path $repo ('dist/portable-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
& $taskPython -I -B (Join-Path $repo 'tools/prepare_portable.py') --runtime-release $runtimeRelease --output $portableOutput --no-zip
if ($LASTEXITCODE -ne 0) { throw '準備に失敗しました。表示されたログを確認してください。依存の取得や再試行は行っていません。' }
# Open the output folder only; the user starts the check explicitly.
Start-Process -FilePath (Join-Path $portableOutput 'Aredoko')
