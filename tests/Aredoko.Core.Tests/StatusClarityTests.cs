using Aredoko.Core;
using System.Text.Json.Nodes;

static class StatusClarityTests
{
    public static void Run(Action<bool, string> check)
    {
        // 1. AISearchStatus Guidance
        var missingMsg = AISearchStatus.Guidance(AISearchStatus.ModelMissing);
        check(missingMsg.Contains("未導入") && missingMsg.Contains("文字検索"), "Guidance for ModelMissing explains normal search works");

        var unindexedMsg = AISearchStatus.Guidance(AISearchStatus.Unindexed, candidateTotal: 42, indexedTotal: 0);
        check(unindexedMsg.Contains("42件") && unindexedMsg.Contains("未索引"), "Guidance for Unindexed contains candidate count and action");

        var partialMsg = AISearchStatus.Guidance(AISearchStatus.PartiallyIndexed, candidateTotal: 100, indexedTotal: 35);
        check(partialMsg.Contains("100件中 35件完了"), "Guidance for PartiallyIndexed shows completion ratio");

        var outOfScopeMsg = AISearchStatus.Guidance(AISearchStatus.OutOfScope);
        check(outOfScopeMsg.Contains("対象作品がありません"), "Guidance for OutOfScope directs user to check folders/kinds");

        var workerFailedMsg = AISearchStatus.Guidance(AISearchStatus.WorkerFailed);
        check(workerFailedMsg.Contains("推論プロセス") && workerFailedMsg.Contains("文字検索は利用できます"), "Guidance for WorkerFailed reassures normal search works");

        var corruptMsg = AISearchStatus.Guidance(AISearchStatus.CorruptProfile);
        check(corruptMsg.Contains("プロファイル設定"), "Guidance for CorruptProfile directs user to reselect profile");

        var spaceMsg = AISearchStatus.Guidance(AISearchStatus.InsufficientSpace);
        check(spaceMsg.Contains("空き容量"), "Guidance for InsufficientSpace mentions disk space");

        var portMsg = AISearchStatus.Guidance(AISearchStatus.PortConflict);
        check(portMsg.Contains("ポートの競合"), "Guidance for PortConflict explains conflict");

        var readyNoHit = AISearchStatus.Guidance(AISearchStatus.Ready, query: "青い空");
        check(readyNoHit.Contains("青い空") && readyNoHit.Contains("一致するAI候補はありませんでした"), "Guidance for Ready with 0 hits names query");

        // 2. AISearchStatus StatusLabel
        check(AISearchStatus.StatusLabel("idle") == "未作成", "StatusLabel idle -> 未作成");
        check(AISearchStatus.StatusLabel("running") == "作成中", "StatusLabel running -> 作成中");
        check(AISearchStatus.StatusLabel("cancelling") == "中断待ち", "StatusLabel cancelling -> 中断待ち");
        check(AISearchStatus.StatusLabel("complete") == "準備完了", "StatusLabel complete -> 準備完了");
        check(AISearchStatus.StatusLabel("cancelled") == "中断済み", "StatusLabel cancelled -> 中断済み");
        check(AISearchStatus.StatusLabel("interrupted") == "前回中断", "StatusLabel interrupted -> 前回中断");
        check(AISearchStatus.StatusLabel("failed") == "失敗", "StatusLabel failed -> 失敗");
        check(AISearchStatus.StatusLabel("partial") == "一部完了", "StatusLabel partial -> 一部完了");

        // 3. SearchResponse.SearchStatus parsing
        var respUnindexed = Protocol.ParseSearch("""{"total":0,"items":[],"search_complete":true,"search_candidate_total":10,"indexed_total":0,"search_status":"unindexed"}""");
        check(respUnindexed.SearchStatus == "unindexed", "ParseSearch parses search_status unindexed");

        var respPartial = Protocol.ParseSearch("""{"total":5,"items":[],"search_complete":true,"search_candidate_total":10,"indexed_total":5,"search_status":"partially_indexed"}""");
        check(respPartial.SearchStatus == "partially_indexed", "ParseSearch parses search_status partially_indexed");

        var respDefault = Protocol.ParseSearch("""{"total":0,"items":[]}""");
        check(respDefault.SearchStatus == "", "ParseSearch defaults SearchStatus to empty string when missing");

        // 4. DiagnosticsReport redaction
        var rawPath = @"C:\Users\SecretUser\AppData\Local\Aredoko\catalog.sqlite";
        var redactedPath = DiagnosticsReport.RedactPath(rawPath);
        check(redactedPath == @"C:\Users\[USER]\AppData\Local\Aredoko\catalog.sqlite", "RedactPath replaces Windows username");
        check(!redactedPath.Contains("SecretUser"), "Redacted path does not contain original username");

        var rawLog = "Bearer token=SuperSecretTokenValue123 in request to C:\\Users\\Alice\\test";
        var redactedLog = DiagnosticsReport.RedactText(rawLog);
        check(!redactedLog.Contains("SuperSecretTokenValue123"), "RedactText hides bearer tokens");
        check(!redactedLog.Contains("Alice"), "RedactText hides username in log");
        check(redactedLog.Contains("[REDACTED]"), "RedactText replaces token with [REDACTED]");
        check(redactedLog.Contains("[USER]"), "RedactText replaces username with [USER]");

        var bearerHeader = "Authorization: Bearer mySecretToken12345 in header";
        var redactedHeader = DiagnosticsReport.RedactText(bearerHeader);
        check(!redactedHeader.Contains("mySecretToken12345") && redactedHeader.Contains("Bearer [REDACTED]"), "RedactText hides standalone Bearer authorization tokens");

        var xTokenHeader = "X-Aredoko-Token: sessionSecret67890 in request";
        var redactedXToken = DiagnosticsReport.RedactText(xTokenHeader);
        check(!redactedXToken.Contains("sessionSecret67890") && redactedXToken.Contains("X-Aredoko-Token: [REDACTED]"), "RedactText hides X-Aredoko-Token");

        var posixPath = "/home/developer/workspace/app";
        check(DiagnosticsReport.RedactPath(posixPath) == "/home/[USER]/workspace/app", "RedactPath masks /home/ user paths");

        var uncPath = @"\\fileserver\Users\shareduser\docs";
        check(DiagnosticsReport.RedactPath(uncPath) == @"\\fileserver\Users\[USER]\docs", "RedactPath masks UNC Users paths");

        if (!string.IsNullOrWhiteSpace(Environment.UserName) && Environment.UserName.Length >= 2)
        {
            var customDrivePath = $@"D:\Media\{Environment.UserName}\library";
            var redactedCustom = DiagnosticsReport.RedactPath(customDrivePath);
            check(!redactedCustom.Contains(Environment.UserName) && redactedCustom.Contains("[USER]"), "RedactPath masks current username on non-standard drives");
        }

        var staleMsg = AISearchStatus.Guidance(AISearchStatus.StaleIndex);
        check(staleMsg.Contains("索引が古くなっています"), "Guidance for StaleIndex directs user to update index");

        var limitMsg = AISearchStatus.Guidance(AISearchStatus.LimitReached);
        check(limitMsg.Contains("上限に達しました"), "Guidance for LimitReached explains limit");

        // 5. DiagnosticsReport.Generate
        var aiStatus = JsonNode.Parse("""
        {
            "available": true,
            "state": "complete",
            "status_code": "ready",
            "model": "EmbeddingGemma 2 (768D)",
            "model_id": "embedding-gemma-2",
            "resident": true,
            "device": "cuda:0",
            "modalities": ["text", "cover"],
            "error": "failed to read C:\\Users\\Alice\\SecretMedia\\item.png token=abc12345"
        }
        """);
        var aiScope = JsonNode.Parse("""
        {
            "root_ids": [1, 2]
        }
        """);

        var report = DiagnosticsReport.Generate(aiStatus, aiScope, roots: null, shelfCount: 5, termCount: 12, theme: "Dark",
            rootCount: 3, enabledRootCount: 2, basicRuntime: new("cpython","3.13.17",64,true));
        check(report.Contains("Aredoko 診断サマリー"), "DiagnosticsReport header generated");
        check(report.Contains("UIテーマ: Dark"), "DiagnosticsReport contains UI theme");
        check(report.Contains("基本Python: CPython 3.13.17（64ビット、仮想環境）"), "DiagnosticsReport identifies the basic Python runtime");
        check(report.Contains("登録フォルダ数: 3 件"), "DiagnosticsReport contains folder count");
        check(report.Contains("棚の数: 5 件"), "DiagnosticsReport contains shelf count");
        check(report.Contains("登録した関連語: 12 件"), "DiagnosticsReport contains related term count");
        check(!report.Contains("または保存"), "DiagnosticsReport only advertises clipboard copy");
        check(report.Contains("AI利用可否: 利用可能"), "DiagnosticsReport contains AI available");
        check(report.Contains("EmbeddingGemma 2"), "DiagnosticsReport contains model label");
        check(report.Contains("2 フォルダに制限"), "DiagnosticsReport contains scope information");
        check(!report.Contains("Alice"), "DiagnosticsReport redacts username in error message");
        check(!report.Contains("abc12345"), "DiagnosticsReport redacts token in error message");
        check(report.Contains("自動送信されません"), "DiagnosticsReport contains non-transmission privacy statement");

        // 6. DiagnosticsReport handles nulls gracefully
        var nullReport = DiagnosticsReport.Generate(null, null, roots: null);
        check(nullReport.Contains("Aredoko 診断サマリー"), "DiagnosticsReport handles null status/scope safely");
        check(nullReport.Contains("棚の数: 未確認") && nullReport.Contains("登録した関連語: 未確認"), "DiagnosticsReport distinguishes unconfirmed shelf/term counts from zero");
        check(nullReport.Contains("未設定または全フォルダ"), "DiagnosticsReport describes null scope safely");
        check(!nullReport.Contains("基本Python:"), "DiagnosticsReport keeps working with an older backend");

        // 7. SettingsDataStatus reflects live library coverage and unscoped folders instead of stale job counts
        var staleSixOfTwoHundred = AISearchStatus.SettingsDataStatus("complete", 6, 6, coverageTargetTotal: 211, coverageFreshTotal: 6);
        check(staleSixOfTwoHundred.Step3Status.Contains("6 / 211") && staleSixOfTwoHundred.Step3Status.Contains("未作成 205"),
            "SettingsDataStatus shows 6/211 partial coverage instead of stale 6/6 complete");
        check(staleSixOfTwoHundred.NextHint.Contains("205 件") && staleSixOfTwoHundred.NextHint.Contains("AI検索を設定"),
            "SettingsDataStatus guides user to index remaining 205 items");

        var scopedSixUnscopedRest = AISearchStatus.SettingsDataStatus("complete", 6, 6, coverageTargetTotal: 6, coverageFreshTotal: 6, unscopedPresentTotal: 205);
        check(scopedSixUnscopedRest.Step3Status.Contains("6/6") && scopedSixUnscopedRest.Step3Status.Contains("対象外 205"),
            "SettingsDataStatus warns when active folders have 205 items outside AI scope");
        check(scopedSixUnscopedRest.NextHint.Contains("対象範囲"),
            "SettingsDataStatus directs user to check AI scope when folders are excluded");

        var fullyReady = AISearchStatus.SettingsDataStatus("complete", 6, 6, coverageTargetTotal: 211, coverageFreshTotal: 211);
        check(fullyReady.Step3Status == "✓ 作成済み（211/211）" && fullyReady.NextHint.Contains("検索欄の［AI］"),
            "SettingsDataStatus shows complete checkmark only when all scoped items are indexed");

        var unindexedAll = AISearchStatus.SettingsDataStatus("idle", 0, 0, coverageTargetTotal: 211, coverageFreshTotal: 0);
        check(unindexedAll.Step3Status == "未作成（0 / 211 件）",
            "SettingsDataStatus shows exact target count when 0 items are indexed");

        var runningOverride = AISearchStatus.SettingsDataStatus("running", 12, 211, coverageTargetTotal: 211, coverageFreshTotal: 6);
        check(runningOverride.Step3Status == "作成中（12/211）",
            "SettingsDataStatus prioritizes live running progress over static coverage");

        // 8. FolderSummary mirrors compact AI status across states
        check(AISearchStatus.FolderSummary(false, "idle", 0, 0, false).Contains("未設定"), "FolderSummary reports unconfigured AI");
        check(AISearchStatus.FolderSummary(true, "running", 1200, 95000, false).Contains("1,200 / 95,000"), "FolderSummary reports live running progress");
        check(AISearchStatus.FolderSummary(true, "running", 1200, 95000, false, jobReused: 1000, jobIndexed: 1150).Contains("新規 150 / スキップ 1,000"), "FolderSummary shows new and skipped counts when reusing existing vectors");
        check(AISearchStatus.FolderSummary(true, "idle", 0, 0, false, coverageTargetTotal: 95000, coverageFreshTotal: 12000).Contains("未作成 83,000"), "FolderSummary reports partial coverage and remaining count");
        check(AISearchStatus.FolderSummary(true, "complete", 95000, 95000, false, coverageTargetTotal: 95000, coverageFreshTotal: 95000, bookPagesRemaining: 12, bookTargetTotal: 30).Contains("内部ページ未作成 12 冊"), "FolderSummary reports remaining inner book pages even when base is ready");
        check(AISearchStatus.FolderSummary(true, "complete", 95000, 95000, false, coverageTargetTotal: 95000, coverageFreshTotal: 95000).Contains("✓ 作成済み"), "FolderSummary reports ready when all scoped items are indexed");

        // 9. SettingsDataStatus shows reused progress and unindexed inner book pages clearly
        var reusedRunning = AISearchStatus.SettingsDataStatus("running", 1200, 95000, coverageTargetTotal: 95000, coverageFreshTotal: 1000, jobReused: 1000, jobIndexed: 1150);
        check(reusedRunning.Step3Status.Contains("新規 150 / スキップ 1,000") && reusedRunning.NextHint.Contains("作成済み 1,000 件は自動でスキップ"), "SettingsDataStatus shows new vs skipped counts while running");
        var baseReadyBooksPending = AISearchStatus.SettingsDataStatus("complete", 100, 100, coverageTargetTotal: 100, coverageFreshTotal: 100, bookPagesRemaining: 8, bookTargetTotal: 20);
        check(baseReadyBooksPending.Step3Status.Contains("内部ページ未作成 8 冊") && !baseReadyBooksPending.Step3Status.StartsWith("✓"), "SettingsDataStatus does not show ready checkmark when inner book pages are remaining");
        var partialPlusBooks = AISearchStatus.SettingsDataStatus("idle", 0, 0, coverageTargetTotal: 100, coverageFreshTotal: 40, bookPagesRemaining: 5, bookTargetTotal: 20);
        check(partialPlusBooks.Step3Status.Contains("未作成 60 件") && partialPlusBooks.Step3Status.Contains("内部ページ 5 冊"), "SettingsDataStatus reports both remaining items and remaining inner book pages");
    }
}
