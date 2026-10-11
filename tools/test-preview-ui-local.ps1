# Fresh dedicated test DB and tools/create_preview_fixture.py output only.
param([Parameter(Mandatory)][int]$AppPid,[Parameter(Mandatory)][string]$FixtureDirectory,[Parameter(Mandatory)][string]$ArtifactDirectory)
$ErrorActionPreference='Stop'
$previous=$env:WINAPP_UI_WORKFLOW_ID
$env:WINAPP_UI_WORKFLOW_ID=[guid]::NewGuid().ToString('N')
function UI([string[]]$Arguments) {
    $result=& winapp ui @Arguments -a $AppPid
    if($LASTEXITCODE -ne 0){throw "UI failed: $Arguments"}
    return $result
}
function Search([string]$query) {
    UI @('set-value','TxtQuery',$query) | Out-Null
    Start-Sleep -Milliseconds 500
    UI @('invoke','BtnSearch') | Out-Null
}
try {
    New-Item -ItemType Directory -Force $ArtifactDirectory | Out-Null
    $FixtureDirectory=[IO.Path]::GetFullPath($FixtureDirectory)
    $before=@{};Get-ChildItem -LiteralPath $FixtureDirectory -File | ForEach-Object {$before[$_.Name]=(Get-FileHash -LiteralPath $_.FullName).Hash}
    UI @('invoke','BtnRoots') | Out-Null
    UI @('wait-for','RootPath','-t','5000') | Out-Null
    UI @('set-value','RootPath',$FixtureDirectory) | Out-Null
    UI @('invoke','RootConsent','--action','toggle-on') | Out-Null
    UI @('invoke','AddRoot') | Out-Null
    Start-Sleep -Milliseconds 500
    UI @('invoke','ScanRoot') | Out-Null
    $session=Invoke-RestMethod 'http://127.0.0.1:8769/api/session'
    $headers=@{'X-Aredoko-Token'=$session.token}
    for($i=0;$i -lt 30;$i++){
        $state=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/scan' -Headers $headers
        if($state.state -eq 'complete'){break};Start-Sleep -Milliseconds 200
    }
    if($state.state -ne 'complete'){throw "Scan failed: $($state.state)"}
    UI @('invoke','CloseButton') | Out-Null
    $items=(Invoke-RestMethod 'http://127.0.0.1:8769/api/items').items
    $image=($items | Where-Object title -eq 'image-01.png').id
    $book=($items | Where-Object title -eq 'book-01.cbz').id
    $broken=($items | Where-Object title -eq 'broken.png').id
    UI @('wait-for',"PreviewStatus$image",'--value','画像プレビュー','-t','10000') | Out-Null
    UI @('wait-for',"PreviewStatus$book",'--value','先頭画像','-t','10000') | Out-Null
    UI @('invoke','BtnLayout') | Out-Null
    UI @('wait-for',"PreviewStatus$book",'--value','先頭画像','-t','5000') | Out-Null
    UI @('invoke',"Item$book",'--action','select') | Out-Null
    UI @('wait-for','DetailPreview','--property','IsOffscreen','--value','false','-t','5000') | Out-Null
    UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'tiles.png')) | Out-Null
    Search 'broken.png'
    UI @('wait-for',"PreviewStatus$broken",'--value','プレビューなし','-t','5000') | Out-Null
    # Rapid final-query changes must leave the matching book selected/displayed.
    UI @('set-value','TxtQuery','image') | Out-Null
    UI @('set-value','TxtQuery','book-01') | Out-Null
    Start-Sleep -Milliseconds 700
    UI @('wait-for',"Item$book",'-t','5000') | Out-Null
    UI @('invoke',"Item$book",'--action','select') | Out-Null
    UI @('set-value','TxtTags','preview-gui-proof') | Out-Null
    UI @('invoke','BtnSave') | Out-Null
    Start-Sleep -Milliseconds 500
    $saved=Invoke-RestMethod 'http://127.0.0.1:8769/api/items?q=preview-gui-proof'
    if($saved.total -ne 1){throw 'Save regressed'}
    # Resize only our app window; this does not change OS DPI or display settings.
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class PreviewTestWindow {
 [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd,IntPtr after,int x,int y,int width,int height,uint flags);
}
'@
    $windows=UI @('list-windows','--json') | ConvertFrom-Json
    $hwnd=[IntPtr]($windows | Where-Object ownerHwnd -eq 0 | Select-Object -First 1).hwnd
    if(-not [PreviewTestWindow]::SetWindowPos($hwnd,[IntPtr]::Zero,100,100,700,820,4)){throw 'Resize failed'}
    Start-Sleep -Milliseconds 500
    UI @('invoke','BtnDetails') | Out-Null
    UI @('invoke','BtnCloseDetails') | Out-Null
    UI @('wait-for',"Item$book",'-t','3000') | Out-Null
    UI @('invoke',"Item$book",'--action','select') | Out-Null
    UI @('wait-for','TxtTags','--property','IsOffscreen','--value','false','-t','3000') | Out-Null
    UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'narrow.png')) | Out-Null
    [PreviewTestWindow]::SetWindowPos($hwnd,[IntPtr]::Zero,100,100,1200,820,4) | Out-Null
    Search ''
    foreach($file in Get-ChildItem -LiteralPath $FixtureDirectory -File){if((Get-FileHash -LiteralPath $file.FullName).Hash -ne $before[$file.Name]){throw 'Source file changed'}}
    'PASS: image and CBZ covers, tiles/detail, corrupt fallback, final search, tag save, 700px drawer, sources unchanged' | Tee-Object (Join-Path $ArtifactDirectory 'result.txt')
} finally {
    winapp ui yield | Out-Null
    if($previous){$env:WINAPP_UI_WORKFLOW_ID=$previous}else{Remove-Item Env:WINAPP_UI_WORKFLOW_ID -ErrorAction SilentlyContinue}
}
