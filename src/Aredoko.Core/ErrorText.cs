using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Aredoko.Core;

// Server errors are stable English strings (tests and logs rely on them);
// the GUI shows Japanese. Unknown messages pass through unchanged, and
// messages the server already writes in Japanese are kept as they are.
public static class ErrorText
{
    private static readonly Dictionary<string, string> Exact = new()
    {
        ["AI runtime dependencies unavailable"] = "AI実行環境の部品が不足しているか、読み込めません。「設定」→「AI環境の配置」で環境を確認してください。基本検索と閲覧は利用できます。",
        ["AI runtime architecture incompatible"] = "AI実行環境の種類がこのアプリと一致しません。「設定」→「AI環境の配置」で対応するx64環境を選び直してください。基本検索と閲覧は利用できます。",
        ["AI runtime initialization failed"] = "AIを起動できませんでした。ほかのAI処理を終了し、空きメモリとAI環境の設定を確認してから再試行してください。基本検索と閲覧は利用できます。",
        ["AI inference failed"] = "AIの処理を完了できませんでした。AI環境と対象ファイルを確認してから再試行してください。",
        ["Invalid AI worker response"] = "AIの応答を確認できませんでした。アプリを再起動し、AI環境を確認してください。",
        ["AI worker timed out"] = "AIの応答が時間内に返りませんでした。ほかのAI処理と空きメモリを確認して、再試行してください。",
        ["AI worker disconnected"] = "AIとの接続が切れました。AI環境を確認して、再試行してください。",
        ["AI runtime validation failed"] = "AI実行環境の照合を完了できません。「設定」→「AI環境の配置」で環境を確認してください。",
        ["Incompatible AI worker"] = "AI実行環境が選択中のモデルに対応していません。AI環境とモデルの設定を確認してください。",
        ["Invalid scan mode"] = "スキャン方法が無効です。アイテム一覧の更新、またはAI索引の作成を選び直してください。",
        ["Animation decoder busy"] = "アニメーションの処理が混んでいます。別のビューワーを閉じてから、開き直してください。",
        ["Animation source changed or session closed"] = "アニメーションの元ファイルが変わったか、表示が終了しました。開き直してください。",
        ["Animation unavailable"] = "このアニメーションを読み取れません。ファイルの状態と対応形式を確認してください。",
        ["Invalid animation request"] = "アニメーション表示の指定が無効です。開き直してください。",
        ["Invalid acquisition query"] = "取得状況の指定が無効です。取得画面を開き直してください。",
        ["Invalid audio status query"] = "音声の準備状況の指定が無効です。設定を開き直してください。",
        ["Invalid video audio status query"] = "動画内の音声の準備状況の指定が無効です。設定を開き直してください。",
        ["Invalid video status query"] = "動画の準備状況の指定が無効です。設定を開き直してください。",
        ["Invalid backup query"] = "バックアップ状況の指定が無効です。バックアップ画面を開き直してください。",
        ["Invalid restore query"] = "復元状況の指定が無効です。復元画面を開き直してください。",
        ["Invalid history query"] = "閲覧履歴の指定が無効です。履歴を開き直してください。",
        ["Invalid shelf query"] = "棚の指定が無効です。棚一覧を開き直してください。",
        ["Invalid thumbnail request"] = "サムネイルの指定が無効です。一覧を取得し直してください。",
        ["Result source unavailable; refresh search"] = "検索対象を読み取れません。フォルダの接続と登録状態を確認し、検索し直してください。",
        ["Results expired or changed; refresh search"] = "検索結果の有効期限が切れたか、対象が変わりました。検索し直してください。",
        ["Thumbnail cancelled"] = "サムネイルの読み込みを中断しました。必要なときに再度読み込みます。",
        ["Thumbnail source changed; rescan"] = "元ファイルが変わりました。アイテム一覧を更新してください。",
        ["Thumbnail unavailable"] = "サムネイルを読み取れません。ファイルの状態を確認してください。",
        ["History generation changed"] = "閲覧履歴が更新されました。もう一度操作してください。",
        ["Result workspace busy or full; close another search"] = "検索用の領域が使用中か、空き容量が不足しています。別の検索を閉じて再試行してください。",
        ["AI index cleanup failed; library records were kept"] = "AI索引を削除できません。登録・タグ等の記録は残しています。AI処理の終了後に再試行してください。",
        ["Invalid page text request"] = "ページ本文の指定が無効です。対象を選び直してください。",
        ["Invalid page text extractor configuration"] = "文字抽出モデルの設定が無効です。本文は保存していません。",
        ["Page text extraction in progress"] = "ページ本文を抽出中です。完了か取消後にやり直してください。",
        ["Page text extraction cancelled; no text saved"] = "ページ本文の抽出を取り消しました。本文は保存していません。",
        ["Page text extraction failed; no text saved"] = "ページ本文の抽出に失敗しました。本文は保存していません。",
        ["Invalid page text output; no text saved"] = "文字抽出モデルの応答が無効です。本文は保存していません。",
        ["Page text batch exceeds limit; no text saved"] = "抽出した本文が上限を超えました。ページ数を減らしてください。本文は保存していません。",
        ["Page text extractor changed; retry"] = "抽出中に文字抽出モデルが変わりました。やり直してください。",
        ["Invalid proposal history request"] = "タグ候補の履歴指定が無効です。開き直してください。",
        ["Tag source unavailable"] = "タグ候補の対象を読み取れません。フォルダ登録・除外・接続状態を確認してください。",
        ["Tag source unavailable; records preserved"] = "対象にアクセスできません。タグ候補の履歴は保持しています。",
        ["Preview workers busy; retry later"] = "プレビュー処理が混んでいます。少し待ってからやり直してください。",
        ["Source changed; rescan before reviewing"] = "元ファイルが変わりました。再スキャンしてからタグ候補を確認してください。",
        ["Source changed; regenerate proposals"] = "元ファイルが変わりました。タグ候補を再生成してください。",
        ["Invalid tagger configuration; no proposals saved"] = "タグ生成モデルの設定が無効です。候補は保存していません。",
        ["Tag generation in progress"] = "タグ候補を生成中です。完了か取消後にやり直してください。",
        ["Source changed before analysis"] = "解析前に元ファイルが変わりました。再スキャンしてからやり直してください。",
        ["Tagger failed; no proposals saved"] = "タグ候補の生成に失敗しました。候補は保存していません。",
        ["Tag generation cancelled; no proposals saved"] = "タグ候補の生成を取り消しました。候補は保存していません。",
        ["Tagger changed during analysis; retry"] = "解析中にタグ生成モデルが変わりました。やり直してください。",
        ["Invalid tagger output; no proposals saved"] = "タグ生成モデルの応答が無効です。候補は保存していません。",
        ["Proposal already reviewed; refresh before saving"] = "この候補は承認または却下済みです。最新の状態を読み直してください。",
        ["Proposal source is stale; regenerate before reviewing"] = "元ファイルが変わったため古い候補は承認できません。候補を再生成してください。",
        ["Similarity source unavailable"] = "起点の作品がAI対象の範囲外か、登録解除・除外されています。AI索引の対象と検索フォルダを確認してください。",
        ["Invalid similarity source"] = "類似検索は画像・本・ZIPの表紙から利用できます。",
        ["Video range outside source"] = "動画の範囲が変わりました。開き直してください。",
        ["Invalid video range request"] = "動画の読み取り範囲が無効です。開き直してください。",
        ["Audio range outside source"] = "音声の範囲が変わりました。開き直してください。",
        ["Invalid audio range request"] = "音声の読み取り範囲が無効です。開き直してください。",
        ["Archive changed; reopen before saving progress"] = "本が更新されました。開き直してから読書位置を保存してください。",
        ["Book unavailable"] = "本を読み取れません。フォルダ登録・除外・接続状態を確認してください。",
        ["Invalid reading progress request"] = "読書位置の指定が無効です。本を開き直してください。",
        ["Invalid request"] = "要求が無効です。",
        ["Invalid literal evidence filter"] = "AI候補の文字一致条件が無効です。",
        ["Invalid similarity boundary"] = "類似度の区切りは-1から1の数値で指定してください。",
        ["Similarity boundary requires cosine scores"] = "順位統合の検索では類似度の区切りを指定できません。画像の見た目か名前・タグの意味を選んでください。",
        ["Invalid result group"] = "AI候補の表示範囲が無効です。",
        ["Invalid root filter"] = "検索フォルダの指定が無効です。",
        ["Unknown registered root"] = "選択中の登録フォルダが見つからないか解除されています。検索フォルダを見直してください。",
        ["Invalid filter"] = "絞り込み条件が無効です。",
        ["Invalid paging"] = "検索条件が無効です（検索語は300文字まで）。",
        ["Expected term with optional aliases and related words"] = "関連語の形式が正しくありません。",
        ["Not an Aredoko related-term export (format/version)"] = "Aredokoの関連語ファイル（format/version）ではありません。",
        ["Related-term entry not found"] = "その見出し語は登録されていません。",
        ["Only term is accepted"] = "削除する見出し語だけを指定してください。",
        ["Invalid body size"] = "送信内容が大きすぎます。",
        ["Invalid session"] = "アプリとバックエンドの接続が切れました。再起動してください。",
        ["Invalid host"] = "アプリとバックエンドの接続が切れました。再起動してください。",
        ["Item not found"] = "作品が見つかりません。削除・移動された可能性があります。再スキャンしてください。",
        ["Invalid item"] = "作品の指定が無効です。",
        ["Invalid update"] = "保存内容が無効です。",
        ["Not found"] = "見つかりません。",
        ["Root not found"] = "登録フォルダが見つかりません。",
        ["Archive changed; rescan and reopen the reader"] = "アーカイブが変更されました。再スキャンしてから開き直してください。",
        ["Folder unavailable; records preserved"] = "フォルダにアクセスできません。登録内容は保持しています。",
        ["Preview unavailable"] = "プレビューを表示できません。",
        ["Preview workers busy"] = "プレビュー処理が混んでいます。少し待ってからやり直してください。",
        ["Reader page unavailable"] = "このページを表示できません。",
        ["Invalid reader request"] = "読書画面の要求が無効です。開き直してください。",
        ["Invalid request: check folder, exclusions or scan state"] = "フォルダ・除外設定・スキャン状態を確認してください。",
        ["Explicit folder consent required"] = "登録するフォルダを選択して、登録操作をやり直してください。",
        ["Shelf name already exists"] = "同じ名前の棚があります。別の名前を入力してください。",
        ["Shelf or item not found"] = "棚または作品が見つかりません。最新の一覧を取得してください。",
        ["Invalid shelf request"] = "棚の名前や選択内容を確認してください。",
        ["Legacy scalar update would lose multiple shelves"] = "この操作では複数の棚所属を保持できません。棚の選択から変更してください。",
        ["Shelf must be 80 characters or less"] = "棚の名前は80文字までです。",
        ["Include subfolders must be true or false"] = "サブフォルダの設定が無効です。",
        ["Symlink roots are not supported"] = "シンボリックリンクのフォルダは登録できません。",
        ["Root must exist and be accessible"] = "フォルダが見つからないか、アクセスできません。",
        ["Reparse-point roots are not supported"] = "ジャンクションなどのリンクフォルダは登録できません。",
        ["Root must be an existing ordinary directory"] = "通常のフォルダを選んでください。",
        ["Overlapping roots are not supported"] = "登録済みフォルダの中や外側にあたるフォルダは登録できません。",
        ["This root is already registered"] = "このフォルダはすでに登録されています。",
        ["Exclusion patterns must be a list (max 64)"] = "除外ルールは64個までです。",
        ["Invalid exclusion pattern"] = "除外ルールが無効です（1〜200文字）。",
        ["Use relative POSIX-style exclusion patterns"] = "除外ルールはフォルダ内の相対パスを「/」区切りで書いてください。",
        ["folder_books must be true or false"] = "「一冊として扱う」の指定が無効です。",
        ["Page source changed; rescan and refresh page index"] = "ページ構成が変わりました。再スキャンしてページ索引を更新してください。",
        ["Page source changed; review a new range"] = "元ファイルが変わりました。範囲を確認し直してください。",
        ["Page source or saved batch unavailable"] = "対象の本または前回の処理を利用できません。登録状態と範囲を確認してください。",
        ["AI profile changed"] = "AIモデルが変わりました。範囲を確認し直してください。",
        ["AI scope changed; review a new range"] = "AI対象範囲が変わりました。範囲を確認し直してください。",
        ["Batch is no longer resumable"] = "この処理は再開できません。最新の状況を確認してください。",
        ["Select 1..8 books"] = "1〜8冊を選択してください。",
        ["Invalid total page limit"] = "合計ページ数は1〜128を指定してください。",
        ["Total page limit exceeded"] = "合計ページ数の上限を超えています。",
        ["Invalid batch fields"] = "複数本の指定が無効です。",
        ["Invalid chunked page request"] = "分割追加の指定が無効です。対象フォルダ・モデル・ページ範囲を確認し直してください。",
        ["Page source or saved chunked job unavailable"] = "対象の本または前回の分割追加を利用できません。登録状態と範囲を確認してください。",
        ["Invalid book range"] = "本の範囲指定が無効です。",
        ["Invalid page IDs"] = "ページの選択が無効です。",
        ["Duplicate book"] = "同じ本が重複しています。",
        ["Page source unavailable"] = "このページの元データを読み取れません。登録状態・形式・容量を確認してください。",
        ["Invalid page index request"] = "ページ索引の指定が無効です。開き直して再試行してください。",
        ["Folder book mode cannot change after scanning"] = "「画像フォルダを一冊として扱う」はスキャン後に変更できません。登録時の設定のまま再登録してください。",
        ["Explicit folder purge consent required"] = "記録の完全削除を続行するには、確認ダイアログで実行を選んでください。",
        ["Unregister the root before purging database records"] = "登録中のフォルダは削除できません。先に登録を解除してください。",
        ["Choose an absolute folder path"] = "フォルダを絶対パスで選んでください。",
        ["The library must not contain the application database"] = "アプリのデータベースを含むフォルダはライブラリにできません。",
        ["A scan is already running"] = "スキャン中です。完了後にやり直してください。",
        ["Scan in progress; retry after it completes"] = "スキャン中です。完了後にやり直してください。",
    };

    public static string? AIWorkerFailure(string? code) => code switch
    {
        "ai_runtime_dependencies_unavailable" => Localize("AI runtime dependencies unavailable"),
        "ai_runtime_architecture_incompatible" => Localize("AI runtime architecture incompatible"),
        "ai_runtime_initialization_failed" => Localize("AI runtime initialization failed"),
        _ => null
    };

    private static string Field(string name) => name switch
    {
        "term" => "見出し語", "aliases" => "別名", "related" => "手がかりの語", _ => name
    };

    public static string Localize(string message)
    {
        if (string.IsNullOrWhiteSpace(message)) return "操作を完了できませんでした。";
        if (Exact.TryGetValue(message, out var known)) return known;
        Match m;
        if ((m = Regex.Match(message, @"^Entry (\d+): (.+)$")).Success) return $"{m.Groups[1].Value}件目: {Localize(m.Groups[2].Value)}";
        if ((m = Regex.Match(message, @"^duplicate term (.+)$")).Success) return $"見出し語「{m.Groups[1].Value}」が重複しています。";
        if ((m = Regex.Match(message, @"^(\w+) must contain 1 to (\d+) characters$")).Success) return $"{Field(m.Groups[1].Value)}は1〜{m.Groups[2].Value}文字にしてください。";
        if ((m = Regex.Match(message, @"^(\w+) must be a single word without spaces$")).Success) return $"{Field(m.Groups[1].Value)}に空白は入れられません（1語ずつ「、」で区切ってください）。";
        if ((m = Regex.Match(message, @"^(\w+) must be a list of at most (\d+) words$")).Success) return $"{Field(m.Groups[1].Value)}は{m.Groups[2].Value}語までです。";
        if ((m = Regex.Match(message, @"^At most (\d+) related-term entries( after import)?$")).Success) return $"関連語は{int.Parse(m.Groups[1].Value):N0}件まで登録できます{(m.Groups[2].Success ? "（読み込み後の合計）" : "")}。";
        if ((m = Regex.Match(message, @"^Use at most (\d+) search words$")).Success) return $"検索語は{m.Groups[1].Value}語までにしてください。";
        return message;
    }

    // Error body {"error": "..."} or anything else (HTML, empty) from a failed response.
    public static string FromResponse(string body, int status)
    {
        try
        {
            if (JsonNode.Parse(body) is JsonObject document && document["error"] is JsonValue value && value.TryGetValue<string>(out var error) && error.Length > 0)
                return Localize(error);
        }
        catch (JsonException) { }
        return status >= 500 ? $"バックエンドでエラーが起きました（{status}）。" : $"要求を処理できませんでした（{status}）。";
    }
}
