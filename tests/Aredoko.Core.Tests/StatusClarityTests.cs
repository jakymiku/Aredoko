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

        var report = DiagnosticsReport.Generate(aiStatus, aiScope, roots: null, shelfCount: 5, termCount: 12, theme: "Dark", rootCount: 3, enabledRootCount: 2);
        check(report.Contains("Aredoko 診断サマリー"), "DiagnosticsReport header generated");
        check(report.Contains("UIテーマ: Dark"), "DiagnosticsReport contains UI theme");
        check(report.Contains("登録フォルダ数: 3 件"), "DiagnosticsReport contains folder count");
        check(report.Contains("棚（タグ分類）数: 5 件"), "DiagnosticsReport contains shelf count");
        check(report.Contains("AI利用可否: 利用可能"), "DiagnosticsReport contains AI available");
        check(report.Contains("EmbeddingGemma 2"), "DiagnosticsReport contains model label");
        check(report.Contains("2 フォルダに制限"), "DiagnosticsReport contains scope information");
        check(!report.Contains("Alice"), "DiagnosticsReport redacts username in error message");
        check(!report.Contains("abc12345"), "DiagnosticsReport redacts token in error message");
        check(report.Contains("自動送信されません"), "DiagnosticsReport contains non-transmission privacy statement");

        // 6. DiagnosticsReport handles nulls gracefully
        var nullReport = DiagnosticsReport.Generate(null, null, roots: null);
        check(nullReport.Contains("Aredoko 診断サマリー"), "DiagnosticsReport handles null status/scope safely");
        check(nullReport.Contains("未設定または全フォルダ"), "DiagnosticsReport describes null scope safely");
    }
}
