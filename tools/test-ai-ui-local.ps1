# Native actual-model test. Fresh test DB + generated fixture directory only.
param([Parameter(Mandatory)][int]$AppPid,[Parameter(Mandatory)][string]$FixtureDirectory,[Parameter(Mandatory)][string]$ArtifactDirectory)
$ErrorActionPreference='Stop'
$previous=$env:WINAPP_UI_WORKFLOW_ID
$env:WINAPP_UI_WORKFLOW_ID=[guid]::NewGuid().ToString('N')
function UI([string[]]$Arguments) {
    $result=& winapp ui @Arguments -a $AppPid
    if($LASTEXITCODE -ne 0){throw "UI failed: $Arguments"}
    return $result
}
function Ready() {
    for($i=0;$i -lt 50;$i++){
        $property=(UI @('get-property','ItemList','--property','IsEnabled','--json') -join '') | ConvertFrom-Json
        if($property.properties.IsEnabled){Start-Sleep -Milliseconds 100;return}
        Start-Sleep -Milliseconds 100
    }
    throw 'Result list did not finish loading'
}
$result=@{status='FAIL';target='local';actual_model=$true;details=''}
try {
    New-Item -ItemType Directory -Force $ArtifactDirectory | Out-Null
    $hashes=@{};Get-ChildItem -LiteralPath $FixtureDirectory -File | ForEach-Object {$hashes[$_.Name]=(Get-FileHash -LiteralPath $_.FullName).Hash}
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
    UI @('invoke','CmbSearchMode','--action','expand') | Out-Null
    UI @('invoke','ModeSemantic','--action','select') | Out-Null
    UI @('set-value','TxtQuery','傘が必要な暗い都会の景色') | Out-Null
    Start-Sleep -Milliseconds 500
    UI @('invoke','BtnSearch') | Out-Null
    $ranking=Invoke-RestMethod 'http://127.0.0.1:8769/api/library/ai/search' -Method Post -Headers $headers -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes('{"query":"傘が必要な暗い都会の景色","kind":"audio"}')) -TimeoutSec 45
    if($ranking.items[0].title -ne '雨の夜の街並み.wav'){throw 'Expected Japanese semantic hit not top-ranked'}
    $first=$ranking.items[0].id
    UI @('wait-for',"Item$first",'-t','10000') | Out-Null
    UI @('invoke',"Item$first",'--action','select') | Out-Null
    UI @('set-value','TxtTags','actual-ai-ui-proof') | Out-Null
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
    UI @('invoke','CmbSearchMode','--action','expand') | Out-Null
    UI @('invoke','ModeLiteral','--action','select') | Out-Null
    UI @('set-value','TxtQuery','actual-ai-ui-proof') | Out-Null
    Start-Sleep -Milliseconds 600
    UI @('wait-for',"Item$first",'-t','5000') | Out-Null
    UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'literal-after-ai.png')) | Out-Null
    UI @('invoke','CmbSearchMode','--action','expand') | Out-Null
    UI @('invoke','ModeVisual','--action','select') | Out-Null
    UI @('set-value','TxtQuery','青い画像') | Out-Null
    Start-Sleep -Milliseconds 600
    UI @('invoke','BtnSearch') | Out-Null
    Start-Sleep -Seconds 2
    UI @('invoke','BtnLayout') | Out-Null
    UI @('screenshot','--output',(Join-Path $ArtifactDirectory 'ai-search.png')) | Out-Null
    foreach($file in Get-ChildItem -LiteralPath $FixtureDirectory -File){if($hashes[$file.Name] -ne (Get-FileHash -LiteralPath $file.FullName).Hash){throw 'Generated source changed'}}
    $state | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $ArtifactDirectory 'ai-state.json')
    $result.status='PASS'
    $result.details='GUI CUDA index/search/save/mode/dirty keep/source hashes'
    'PASS: actual CUDA index via GUI, AI mode/query/result selection, metadata save, literal mode, source hashes unchanged'
} catch {
    $result.details=$_.Exception.Message
    throw
} finally {
    $result | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $ArtifactDirectory 'result.json')
    winapp ui yield | Out-Null
    if($previous){$env:WINAPP_UI_WORKFLOW_ID=$previous}else{Remove-Item Env:WINAPP_UI_WORKFLOW_ID -ErrorAction SilentlyContinue}
}

