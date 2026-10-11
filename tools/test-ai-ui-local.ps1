# Native actual-model test. Fresh test DB + generated fixture directory only.
# RestartOnly checks the same dedicated 17-item DB after the full flow and app restart.
param([Parameter(Mandatory)][int]$AppPid,[Parameter(Mandatory)][string]$FixtureDirectory,[Parameter(Mandatory)][string]$ArtifactDirectory,[switch]$RestartOnly,[switch]$CheckFusion)
$ErrorActionPreference='Stop'
$previous=$env:WINAPP_UI_WORKFLOW_ID
$env:WINAPP_UI_WORKFLOW_ID=[guid]::NewGuid().ToString('N')
function UI([string[]]$Arguments) {
    $result=& winapp ui @Arguments -a $AppPid
    if($LASTEXITCODE -ne 0){throw "UI failed: $Arguments"}
    return $result
}
function SelectMode([string]$Id,[string]$Expected) {
    UI @('invoke','CmbSearchMode','--action','expand') | Out-Null
    for($attempt=0;$attempt -lt 30;$attempt++){
        $windows=(UI @('list-windows','--json') -join '') | ConvertFrom-Json
        $popup=@($windows | Where-Object {$_.title -eq 'PopupHost'})
        if($popup.Count -eq 1){break}
        Start-Sleep -Milliseconds 100
    }
    if($popup.Count -ne 1){throw 'Expected one search mode popup'}
    # WinUI exposes the same popup peer through two app windows. Scope selection
    # to the observed popup HWND so an AutomationId never matches twice.
    $output=& winapp ui invoke $Id --action select -w $popup[0].hwnd
    if($LASTEXITCODE -ne 0){throw "Popup selection failed: $Id ($output)"}
    $main=@($windows | Where-Object {$_.title -ne 'PopupHost' -and $_.ownerHwnd -eq 0})
    if($main.Count -ne 1){throw 'Expected one main window'}
    $output=& winapp ui wait-for CmbSearchMode --value $Expected -t 3000 -w $main[0].hwnd
    if($LASTEXITCODE -ne 0){throw "Search mode was not selected: $Expected ($output)"}
}
function Ready() {
    for($i=0;$i -lt 300;$i++){
        $property=(UI @('get-property','ItemList','--property','IsEnabled','--json') -join '') | ConvertFrom-Json
        if([string]$property.properties.IsEnabled -eq 'True'){Start-Sleep -Milliseconds 100;return}
        Start-Sleep -Milliseconds 100
    }
    throw 'Result list did not finish loading'
}
$result=@{status='FAIL';target='local';actual_model=$true;details=''}
try {
    New-Item -ItemType Directory -Force $ArtifactDirectory | Out-Null
    $hashes=@{};Get-ChildItem -LiteralPath $FixtureDirectory -File | ForEach-Object {$hashes[$_.Name]=(Get-FileHash -LiteralPath $_.FullName).Hash}
    if(-not $RestartOnly){
        UI @('invoke','BtnRoots') | Out-Null
        UI @('wait-for','RootPath','-t','5000') | Out-Null
        UI @('set-value','RootPath',([IO.Path]::GetFullPath($FixtureDirectory))) | Out-Null
        UI @('invoke','RootConsent','--action','toggle-on') | Out-Null
        UI @('invoke','AddRoot') | Out-Null
        Start-Sleep -Milliseconds 700
        UI @('invoke','ScanRoot') | Out-Null
        $session=Invoke-RestMethod 'http://127.0.0.1:8769/api/session'
        $headers=@{'X-Aredoko-Token'=$session.token;'Origin'='http://127.0.0.1:8769'}
        for($i=0;$i -lt 30;$i++){
            $scan=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/scan' -Headers $headers
            if($scan.state -eq 'complete'){break}
            Start-Sleep -Milliseconds 300
        }
        if($scan.state -ne 'complete'){throw 'Folder scan failed'}
        UI @('invoke','CloseButton') | Out-Null
        Ready
        UI @('invoke','BtnAIIndex') | Out-Null
        UI @('wait-for','StartAIIndex','-t','5000') | Out-Null
        UI @('invoke','StartAIIndex') | Out-Null
        for($i=0;$i -lt 180;$i++){
            $state=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/status' -Headers $headers
            if($state.state -in @('complete','failed')){break}
            Start-Sleep -Seconds 1
        }
        if($state.state -ne 'complete' -or $state.indexed -lt 15){throw "AI index failed: $($state | ConvertTo-Json -Compress)"}
        if($state.device -ne 'cuda'){throw 'Actual CUDA inference was not used'}
        UI @('invoke','CloseButton') | Out-Null
        Ready
        SelectMode 'ModeSemantic' 'AI意味検索'
        UI @('set-value','TxtQuery','傘が必要な暗い都会の景色') | Out-Null
        Start-Sleep -Milliseconds 500
        UI @('invoke','BtnSearch') | Out-Null
        $ranking=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/search' -Method Post -Headers $headers -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes('{"query":"傘が必要な暗い都会の景色","kind":"audio"}')) -TimeoutSec 45
        if($ranking.items[0].title -ne '雨の夜の街並み.wav'){throw 'Expected Japanese semantic hit not top-ranked'}
        $first=$ranking.items[0].id
        UI @('wait-for',"Item$first",'-t','10000') | Out-Null
        UI @('invoke',"Item$first",'--action','select') | Out-Null
        UI @('set-value','TxtTags','actual-ai-ui-proof') | Out-Null
        UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'semantic-result.png')) | Out-Null
        UI @('invoke','BtnSave') | Out-Null
        Start-Sleep -Milliseconds 500
        $saved=Invoke-RestMethod 'http://127.0.0.1:8769/api/items?q=actual-ai-ui-proof'
        if($saved.total -ne 1){throw 'AI result metadata save failed'}
        UI @('set-value','TxtTags','unsaved-ai-dialog-proof') | Out-Null
        UI @('invoke','BtnAIIndex') | Out-Null
        UI @('wait-for','PrimaryButton','-t','3000') | Out-Null
        UI @('invoke','CloseButton') | Out-Null
        $kept=UI @('get-value','TxtTags','--json')
        if(($kept -join '') -notmatch 'unsaved-ai-dialog-proof'){throw 'AI dialog keep lost unsaved edits'}
        UI @('set-value','TxtTags','actual-ai-ui-proof') | Out-Null
        # Switch back to literal search: previous behavior must remain usable.
        SelectMode 'ModeLiteral' '名前・タグ'
        UI @('set-value','TxtQuery','actual-ai-ui-proof') | Out-Null
        Start-Sleep -Milliseconds 600
        UI @('wait-for',"Item$first",'-t','5000') | Out-Null
        UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'literal-after-ai.png')) | Out-Null
        if($CheckFusion){
            SelectMode 'ModeSemantic' 'AI意味検索'
            UI @('set-value','TxtQuery','赤い表紙の本') | Out-Null
            Start-Sleep -Milliseconds 600
            UI @('invoke','BtnSearch') | Out-Null
            Ready
            $fused=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/search' -Method Post -Headers $headers -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes('{"query":"赤い表紙の本"}')) -TimeoutSec 45
            if($fused.ranking -ne 'mean-rrf' -or $fused.score_kind -ne 'reciprocal-rank' -or $fused.items[0].title -ne 'book-03.cbz'){throw 'Default fused red-cover ranking failed'}
            UI @('wait-for',"Item$($fused.items[0].id)",'-t','5000') | Out-Null
            UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'semantic-fused-red.png')) | Out-Null
            $legacy=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/search' -Method Post -Headers $headers -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes('{"query":"赤い表紙の本","ranking":"max"}')) -TimeoutSec 45
            if($legacy.ranking -ne 'max' -or $legacy.score_kind -ne 'cosine' -or $legacy.items[0].title -ne 'book-01.cbz'){throw 'Legacy ranking override failed'}
            @{fused=$fused;legacy=$legacy} | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $ArtifactDirectory 'fusion.json')
        }
        SelectMode 'ModeVisual' 'AI画像・表紙'
        UI @('set-value','TxtQuery','青い画像') | Out-Null
        Start-Sleep -Milliseconds 600
        UI @('invoke','BtnSearch') | Out-Null
        Start-Sleep -Seconds 2
        UI @('invoke','BtnLayout') | Out-Null
        UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'ai-search.png')) | Out-Null
    } else {
        $session=Invoke-RestMethod 'http://127.0.0.1:8769/api/session'
        $headers=@{'X-Aredoko-Token'=$session.token;'Origin'='http://127.0.0.1:8769'}
        $state=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/status' -Headers $headers
        if($state.state -ne 'complete' -or $state.indexed -ne 17){throw 'AI index did not survive restart'}
        Ready
        UI @('set-value','TxtQuery','actual-ai-ui-proof') | Out-Null
        Start-Sleep -Milliseconds 600
        Ready
        $saved=Invoke-RestMethod 'http://127.0.0.1:8769/api/items?q=actual-ai-ui-proof'
        if($saved.total -ne 1){throw 'Saved tag did not survive restart'}
        $first=$saved.items[0].id
        UI @('wait-for',"Item$first",'-t','5000') | Out-Null
        UI @('invoke',"Item$first",'--action','select') | Out-Null
        UI @('wait-for','TxtTags','--value','actual-ai-ui-proof','-t','3000') | Out-Null
        UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'restart-saved-tag.png')) | Out-Null
        UI @('set-value','TxtQuery','青い画像') | Out-Null
        SelectMode 'ModeVisual' 'AI画像・表紙'
        Start-Sleep -Milliseconds 600
        UI @('invoke','BtnSearch') | Out-Null
        Start-Sleep -Seconds 2
        Ready
        $ranking=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/search' -Method Post -Headers $headers -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes('{"query":"青い画像","source":"cover"}')) -TimeoutSec 45
        if($ranking.items[0].title -notin @('image-01.png','book-01.cbz')){throw 'Persisted visual index did not return a blue top hit'}
        UI @('wait-for',"Item$($ranking.items[0].id)",'-t','5000') | Out-Null
        UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'restart-visual-search.png')) | Out-Null
        $state=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/status' -Headers $headers
        if($state.device -ne 'cuda'){throw 'Restarted search did not use CUDA'}
    }
    foreach($file in Get-ChildItem -LiteralPath $FixtureDirectory -File){if($hashes[$file.Name] -ne (Get-FileHash -LiteralPath $file.FullName).Hash){throw 'Generated source changed'}}
    $state | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $ArtifactDirectory 'ai-state.json')
    $result.status='PASS'
    $result.details=if($RestartOnly){'Restarted GUI tag/vector persistence, CUDA cover query, source hashes'}else{'GUI CUDA index/search/save/mode/dirty keep/source hashes; fusion checked=' + $CheckFusion}
    "PASS: $($result.details)"
} catch {
    $result.details=$_.Exception.Message
    throw
} finally {
    $result | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $ArtifactDirectory 'result.json')
    winapp ui yield | Out-Null
    if($previous){$env:WINAPP_UI_WORKFLOW_ID=$previous}else{Remove-Item Env:WINAPP_UI_WORKFLOW_ID -ErrorAction SilentlyContinue}
}

