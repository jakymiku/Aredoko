# Run only against an app launched with a fresh, dedicated test database.
param([Parameter(Mandatory)][int]$AppPid)
$ErrorActionPreference='Stop'
$env:WINAPP_UI_WORKFLOW_ID=[guid]::NewGuid().ToString('N')
$output=Join-Path (Get-Location) ('data/mvp-ui/'+[guid]::NewGuid().ToString('N'))
$fixture=Join-Path $output 'fixture'
New-Item -ItemType Directory -Force $fixture | Out-Null
1..75 | ForEach-Object { [IO.File]::WriteAllText((Join-Path $fixture ('sample-{0:D3}.cbz' -f $_)),'generated test fixture') }
function UI([string[]]$Arguments) {
    $result=& winapp ui @Arguments -a $AppPid
    if($LASTEXITCODE -ne 0){throw "UI command failed: $Arguments"}
    return $result
}
try {
    UI @('wait-for','BtnRoots','-t','5000') | Out-Null
    UI @('invoke','BtnRoots') | Out-Null
    UI @('wait-for','RootPath','-t','5000') | Out-Null
    UI @('set-value','RootPath',$fixture) | Out-Null
    UI @('invoke','RootConsent','--action','toggle-on') | Out-Null
    UI @('invoke','AddRoot') | Out-Null
    Start-Sleep -Seconds 1
    UI @('invoke','ScanRoot') | Out-Null
    $session=Invoke-RestMethod 'http://127.0.0.1:8769/api/session'
    $headers=@{'X-Aredoko-Token'=$session.token}
    for($i=0;$i -lt 20;$i++){
        $state=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/scan' -Headers $headers
        if($state.state -eq 'complete'){break}
        Start-Sleep -Milliseconds 300
    }
    if($state.state -ne 'complete'){throw "Scan failed: $($state.state)"}
    UI @('invoke','CloseButton') | Out-Null
    UI @('wait-for','Item1','-t','5000') | Out-Null
    UI @('invoke','Item1','--action','select') | Out-Null
    UI @('wait-for','TxtTags','-t','3000') | Out-Null
    $status=UI @('get-property','TxtEditStatus','--property','Name','--json')
    $status | Set-Content (Join-Path $output 'selection-status.json')
    if(($status -join '') -notmatch '保存済み|\\u4FDD\\u5B58\\u6E08'){throw 'Selection did not start clean'}
    UI @('set-value','TxtTags','mvp-ui-proof, 夜') | Out-Null
    UI @('invoke','ChkFavorite','--action','toggle-on') | Out-Null
    UI @('invoke','BtnSave') | Out-Null
    Start-Sleep -Milliseconds 700
    $saved=Invoke-RestMethod 'http://127.0.0.1:8769/api/items?q=mvp-ui-proof'
    if($saved.total -ne 1 -or -not $saved.items[0].favorite){throw 'GUI metadata was not persisted'}
    UI @('set-value','TxtQuery','mvp-ui-proof') | Out-Null
    Start-Sleep -Milliseconds 700
    UI @('invoke','BtnSearch') | Out-Null
    UI @('wait-for','Item1','-t','5000') | Out-Null
    UI @('invoke','BtnLayout') | Out-Null
    UI @('invoke','Item1','--action','select') | Out-Null
    UI @('screenshot','--output',(Join-Path $output 'product.png')) | Out-Null
    UI @('set-value','TxtQuery','sample') | Out-Null
    Start-Sleep -Milliseconds 700
    UI @('invoke','BtnNext') | Out-Null
    Start-Sleep -Milliseconds 500
    $page=UI @('get-property','PageNumber','--property','Name','--json')
    if(($page -join '') -notmatch '2 / 2'){throw 'Second page did not render'}
    UI @('invoke','BtnPrevious') | Out-Null
    Start-Sleep -Milliseconds 500
    UI @('invoke','Item1','--action','select') | Out-Null
    UI @('set-value','TxtTags','unsaved-test') | Out-Null
    UI @('invoke','NavFavorites','--action','select') | Out-Null
    UI @('wait-for','PrimaryButton','-t','3000') | Out-Null
    UI @('invoke','CloseButton') | Out-Null
    $kept=UI @('get-value','TxtTags','--json')
    if(($kept -join '') -notmatch 'unsaved-test'){throw 'Dirty cancellation lost edit'}
    UI @('invoke','NavFavorites','--action','select') | Out-Null
    UI @('invoke','PrimaryButton') | Out-Null
    Start-Sleep -Milliseconds 500
    UI @('invoke','Item1','--action','select') | Out-Null
    $restored=UI @('get-value','TxtTags','--json')
    if(($restored -join '') -notmatch 'mvp-ui-proof'){throw 'Discard did not restore saved value'}
    'PASS: GUI registration, scan, selection clean, tag/favorite save, search, tiles, pagination, dirty keep/discard' | Tee-Object (Join-Path $output 'result.txt')
} finally { winapp ui yield | Out-Null; Remove-Item Env:WINAPP_UI_WORKFLOW_ID }
