namespace Aredoko.Core;

public static class AISearchStatus
{
    public const string Ready = "ready";
    public const string Unindexed = "unindexed";
    public const string PartiallyIndexed = "partially_indexed";
    public const string OutOfScope = "out_of_scope";
    public const string ModelMissing = "model_missing";
    public const string WorkerFailed = "worker_failed";
    public const string CorruptProfile = "corrupt_profile";
    public const string InsufficientSpace = "insufficient_space";
    public const string PortConflict = "port_conflict";
    public const string StaleIndex = "stale_index";
    public const string LimitReached = "limit_reached";

    public static string Guidance(string statusCode, int candidateTotal = 0, int indexedTotal = 0, string query = "") => statusCode switch
    {
        ModelMissing => AppText.L("AI環境（モデル・Python）が未導入です。名前・タグの文字検索、棚・整理、閲覧はそのまま利用できます。", "AI runtime and model are not installed. Name/tag search, shelves, organization, and viewing still work."),
        Unindexed => candidateTotal > 0
            ? AppText.L($"選択範囲の作品はAI索引がまだ作成されていません（対象 {candidateTotal:N0}件・未索引）。「設定」→「AI検索の準備」から索引を作成してください。名前・タグ検索は利用できます。", $"Selected scope has no AI index yet ({candidateTotal:N0} candidate(s) unindexed). Build the index from Settings → AI Search. Name/tag search remains available.")
            : AppText.L("選択範囲の作品はAI索引がまだ作成されていません。「設定」→「AI検索の準備」から索引を作成してください。名前・タグ検索は利用できます。", "Selected scope has no AI index yet. Build the index from Settings → AI Search. Name/tag search remains available."),
        PartiallyIndexed => AppText.L($"選択範囲の一部のみ索引済みです（{candidateTotal:N0}件中 {indexedTotal:N0}件完了）。残りの作品は「設定」→「AI検索の準備」から索引を追加できます。", $"Selected scope is partially indexed ({indexedTotal:N0} of {candidateTotal:N0} done). Index remaining items from Settings → AI Search."),
        OutOfScope => AppText.L("選択されたフォルダ・絞り込みに対象作品がありません。検索フォルダや種類の条件を確認してください。", "No matching items in the selected folder or filter. Check your folder and type filters."),
        WorkerFailed => AppText.L("AI推論プロセスが停止または失敗しました。文字検索は利用できます。「設定」からAI状態を確認・再開してください。", "The AI worker stopped or failed. Text search remains available. Check or restart AI status in Settings."),
        CorruptProfile => AppText.L("AIプロファイル設定が無効または破損しています。「設定」からプロファイルを選び直してください。", "AI profile settings are invalid or corrupt. Reselect a profile in Settings."),
        InsufficientSpace => AppText.L("検索用の一時作業領域の空き容量が不足しています。ドライブの空き容量を確認してください。", "Not enough temporary disk space for search. Check free space on your drive."),
        PortConflict => AppText.L("ポートの競合が発生しました。他のインスタンスが起動していないか確認してください。", "Port conflict occurred. Make sure another instance is not already running."),
        StaleIndex => AppText.L("索引が古くなっています。「設定」→「AI検索の準備」で索引を更新してください。", "AI index is out of date. Update the index from Settings → AI Search."),
        LimitReached => AppText.L("検索上限または索引上限に達しました。絞り込み条件を指定してください。", "Search or index limit reached. Narrow your filters."),
        Ready => string.IsNullOrWhiteSpace(query)
            ? AppText.L("探したい内容を文章で入力してください。", "Enter text describing what you are looking for.")
            : AppText.L($"「{query}」に一致するAI候補はありませんでした。別の言葉で検索するか、名前・タグ検索をお試しください。", $"No AI results matched \"{query}\". Try another query or switch to Name & Tag search."),
        _ => AppText.L("AI検索の状態を確認してください。名前・タグ検索は引き続き利用できます。", "Check AI search status. Name & tag search remains available.")
    };

    public static string StatusLabel(string state) => state switch
    {
        "idle" => AppText.L("未作成", "Not built"),
        "running" => AppText.L("作成中", "Building"),
        "cancelling" => AppText.L("中断待ち", "Cancelling"),
        "complete" => AppText.L("準備完了", "Ready"),
        "cancelled" => AppText.L("中断済み", "Cancelled"),
        "interrupted" => AppText.L("前回中断", "Interrupted"),
        "failed" => AppText.L("失敗", "Failed"),
        "partial" => AppText.L("一部完了", "Partial"),
        _ => state
    };

    public static (string Step3Status, string NextHint) SettingsDataStatus(
        string jobState,
        int jobProcessed,
        int jobTotal,
        int? coverageTargetTotal = null,
        int? coverageFreshTotal = null,
        int unscopedPresentTotal = 0)
    {
        if (jobState == "running")
            return (AppText.L($"作成中（{jobProcessed:N0}/{jobTotal:N0}）", $"Building ({jobProcessed:N0}/{jobTotal:N0})"),
                AppText.L("AI検索データを作成しています。完了前でも作成済み分から検索できます。", "Building AI search index. Already indexed items can be searched right away."));
        if (jobState == "cancelling")
            return (AppText.L("中断中", "Cancelling"),
                AppText.L("AI検索データの作成を中断しています。", "Cancelling AI index build."));

        if (coverageTargetTotal is int target && coverageFreshTotal is int fresh)
        {
            var clampedFresh = Math.Clamp(fresh, 0, Math.Max(0, target));
            var remaining = Math.Max(0, target - clampedFresh);
            if (target == 0)
            {
                if (unscopedPresentTotal > 0)
                    return (AppText.L($"対象外（全 {unscopedPresentTotal:N0} 件がAI対象外）", $"Out of scope ({unscopedPresentTotal:N0} excluded)"),
                        AppText.L("登録フォルダがAI検索の対象範囲に含まれていません。［AI検索を設定］の「対象範囲」を確認してください。", "Registered folders are excluded from AI search scope. Check Scope in Configure AI."));
                return (AppText.L("対象なし（0 件）", "No items (0)"),
                    AppText.L("作品を追加すると［AI検索を設定］からAI検索データを作成できます。", "Add items to build AI search data from Configure AI."));
            }
            if (clampedFresh == 0)
                return (AppText.L($"未作成（0 / {target:N0} 件）", $"Not built (0 / {target:N0})"),
                    AppText.L($"対象 {target:N0} 件のAI検索データが未作成です。［AI検索を設定］から作成できます。", $"{target:N0} target item(s) have no AI index yet. Build it in Configure AI."));
            if (remaining > 0)
                return (AppText.L($"一部作成（{clampedFresh:N0} / {target:N0} 件・未作成 {remaining:N0} 件）", $"Partial ({clampedFresh:N0} / {target:N0}, {remaining:N0} remaining)"),
                    AppText.L($"未作成の作品が {remaining:N0} 件あります。［AI検索を設定］からAI検索データを追加作成できます。", $"{remaining:N0} unindexed item(s) remaining. Add them from Configure AI."));
            if (unscopedPresentTotal > 0)
                return (AppText.L($"対象分は作成済み（{clampedFresh:N0}/{target:N0} · 対象外 {unscopedPresentTotal:N0} 件）", $"Scoped ready ({clampedFresh:N0}/{target:N0} · {unscopedPresentTotal:N0} excluded)"),
                    AppText.L($"AI対象外のフォルダに {unscopedPresentTotal:N0} 件あります。含める場合は［AI検索を設定］の「対象範囲」を確認してください。", $"{unscopedPresentTotal:N0} item(s) are in excluded folders. Update Scope in Configure AI to include them."));
            return (AppText.L($"✓ 作成済み（{clampedFresh:N0}/{target:N0}）", $"✓ Ready ({clampedFresh:N0}/{target:N0})"),
                AppText.L("AI検索の準備が整っています。検索欄の［AI］から使えます。", "AI search is ready. Switch to [AI] in the search bar to try it."));
        }

        return jobState switch
        {
            "complete" => (AppText.L($"✓ 作成済み（{jobProcessed:N0}/{jobTotal:N0}）", $"✓ Ready ({jobProcessed:N0}/{jobTotal:N0})"), AppText.L("AI検索の準備が整っています。検索欄の［AI］から使えます。", "AI search is ready. Switch to [AI] in the search bar to try it.")),
            "partial" or "cancelled" or "interrupted" => (AppText.L($"一部作成（{jobProcessed:N0}/{jobTotal:N0}）", $"Partial ({jobProcessed:N0}/{jobTotal:N0})"), AppText.L("［AI検索を設定］から残りのAI検索データを作成できます。", "Build the remaining AI search index from Configure AI.")),
            _ => (AppText.L("未作成", "Not built"), AppText.L("［AI検索を設定］から対象フォルダのAI検索データを作成できます。", "Build the AI search index for target folders from Configure AI."))
        };
    }

    public static string FolderSummary(
        bool available,
        string jobState,
        int jobProcessed,
        int jobTotal,
        bool scopeInvalid,
        int? coverageTargetTotal = null,
        int? coverageFreshTotal = null,
        int unscopedPresentTotal = 0)
    {
        if (!available)
            return AppText.L("AI検索データ: 未設定（設定 → AI から準備できます）", "AI Index: Not set up (configure in Settings → AI)");
        if (jobState == "running")
            return AppText.L($"AI検索データ: 作成中（{jobProcessed:N0} / {jobTotal:N0} 件）", $"AI Index: Building ({jobProcessed:N0} / {jobTotal:N0})");
        if (jobState == "cancelling")
            return AppText.L($"AI検索データ: 中断中（{jobProcessed:N0} / {jobTotal:N0} 件）", $"AI Index: Canceling ({jobProcessed:N0} / {jobTotal:N0})");
        if (scopeInvalid)
            return AppText.L("AI検索データ: 対象範囲の確認が必要です", "AI Index: Search scope needs attention");
        if (coverageTargetTotal is int target && coverageFreshTotal is int fresh)
        {
            var clampedFresh = Math.Clamp(fresh, 0, Math.Max(0, target));
            var remaining = Math.Max(0, target - clampedFresh);
            if (target == 0)
            {
                return unscopedPresentTotal > 0
                    ? AppText.L($"AI検索データ: 対象外（全 {unscopedPresentTotal:N0} 件がAI対象外）", $"AI Index: Out of scope ({unscopedPresentTotal:N0} excluded)")
                    : AppText.L("AI検索データ: 対象なし（0 件）", "AI Index: No items in scope (0)");
            }
            if (clampedFresh == 0)
                return AppText.L($"AI検索データ: 未作成（対象 {target:N0} 件）", $"AI Index: Not built ({target:N0} in scope)");
            if (remaining > 0)
                return AppText.L($"AI検索データ: {clampedFresh:N0} / {target:N0} 件作成済み（未作成 {remaining:N0} 件）", $"AI Index: {clampedFresh:N0} / {target:N0} built ({remaining:N0} remaining)");
            return unscopedPresentTotal > 0
                ? AppText.L($"AI検索データ: ✓ 対象分作成済み（{clampedFresh:N0} / {target:N0} 件 · 対象外 {unscopedPresentTotal:N0} 件）", $"AI Index: ✓ Scoped ready ({clampedFresh:N0} / {target:N0} · {unscopedPresentTotal:N0} excluded)")
                : AppText.L($"AI検索データ: ✓ 作成済み（{clampedFresh:N0} / {target:N0} 件）", $"AI Index: ✓ Ready ({clampedFresh:N0} / {target:N0})");
        }
        return jobState switch
        {
            "complete" => AppText.L($"AI検索データ: ✓ 作成済み（{jobProcessed:N0} / {jobTotal:N0} 件）", $"AI Index: ✓ Ready ({jobProcessed:N0} / {jobTotal:N0})"),
            "partial" or "cancelled" or "interrupted" => AppText.L($"AI検索データ: 一部作成（{jobProcessed:N0} / {jobTotal:N0} 件）", $"AI Index: Partial ({jobProcessed:N0} / {jobTotal:N0})"),
            _ => AppText.L("AI検索データ: 未作成", "AI Index: Not built")
        };
    }
}
