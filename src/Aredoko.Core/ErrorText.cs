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
        ["Choose an absolute folder path"] = "フォルダを絶対パスで選んでください。",
        ["The library must not contain the application database"] = "アプリのデータベースを含むフォルダはライブラリにできません。",
        ["A scan is already running"] = "スキャン中です。完了後にやり直してください。",
        ["Scan in progress; retry after it completes"] = "スキャン中です。完了後にやり直してください。",
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
            if (JsonNode.Parse(body)?["error"] is JsonValue value && value.TryGetValue<string>(out var error) && error.Length > 0)
                return Localize(error);
        }
        catch (JsonException) { }
        return status >= 500 ? $"バックエンドでエラーが起きました（{status}）。" : $"要求を処理できませんでした（{status}）。";
    }
}
