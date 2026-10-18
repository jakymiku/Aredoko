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
        ModelMissing => "AI環境（モデル・Python）が未導入です。名前・タグの文字検索、棚・整理、閲覧はそのまま利用できます。",
        Unindexed => candidateTotal > 0
            ? $"選択範囲の作品はAI索引がまだ作成されていません（対象 {candidateTotal:N0}件・未索引）。「設定」→「AI検索の準備」から索引を作成してください。名前・タグ検索は利用できます。"
            : "選択範囲の作品はAI索引がまだ作成されていません。「設定」→「AI検索の準備」から索引を作成してください。名前・タグ検索は利用できます。",
        PartiallyIndexed => $"選択範囲の一部のみ索引済みです（{candidateTotal:N0}件中 {indexedTotal:N0}件完了）。残りの作品は「設定」→「AI検索の準備」から索引を追加できます。",
        OutOfScope => "選択されたフォルダ・絞り込みに対象作品がありません。検索フォルダや種類の条件を確認してください。",
        WorkerFailed => "AI推論プロセスが停止または失敗しました。文字検索は利用できます。「設定」からAI状態を確認・再開してください。",
        CorruptProfile => "AIプロファイル設定が無効または破損しています。「設定」からプロファイルを選び直してください。",
        InsufficientSpace => "検索用の一時作業領域の空き容量が不足しています。ドライブの空き容量を確認してください。",
        PortConflict => "ポートの競合が発生しました。他のインスタンスが起動していないか確認してください。",
        StaleIndex => "索引が古くなっています。「設定」→「AI検索の準備」で索引を更新してください。",
        LimitReached => "検索上限または索引上限に達しました。絞り込み条件を指定してください。",
        Ready => string.IsNullOrWhiteSpace(query)
            ? "探したい内容を文章で入力してください。"
            : $"「{query}」に一致するAI候補はありませんでした。別の言葉で検索するか、名前・タグ検索をお試しください。",
        _ => "AI検索の状態を確認してください。名前・タグ検索は引き続き利用できます。"
    };

    public static string StatusLabel(string state) => state switch
    {
        "idle" => "未作成",
        "running" => "作成中",
        "cancelling" => "中断待ち",
        "complete" => "準備完了",
        "cancelled" => "中断済み",
        "interrupted" => "前回中断",
        "failed" => "失敗",
        "partial" => "一部完了",
        _ => state
    };
}
