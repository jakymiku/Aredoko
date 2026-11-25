// Reflection-free requests/parsing for the user's related-term dictionary.
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record RelatedTermEntry(string Term, string[] Aliases, string[] Related)
{
    public string Summary => Term
        + (Aliases.Length > 0 ? AppText.L($"（別名: {string.Join("、", Aliases)}）", $" (Aliases: {string.Join(", ", Aliases)})") : "")
        + (Related.Length > 0 ? $" ← {string.Join(AppText.L("、", ", "), Related)}" : "");
}

public static class RelatedTerms
{
    public const int MaxWords = 16;
    public const int MaxWordChars = 60;
    private static readonly char[] Separators = ['、', ',', '，', ' ', '\u3000', '\t', '\r', '\n'];

    public static string[] SplitWords(string? text) =>
        (text ?? "").Split(Separators, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Distinct(StringComparer.Ordinal).ToArray();

    // Returns an error message for the dialog, or null when the draft is sendable.
    public static string? Validate(string term, string[] aliases, string[] related)
    {
        if (term.Length == 0) return AppText.L("作品・キャラクター名などの見出し語を入力してください。", "Enter a headword such as a work or character name.");
        if (SplitWords(term).Length != 1) return AppText.L("見出し語は空白を含まない1語にしてください。", "The headword must be a single word without spaces.");
        if (aliases.Length > MaxWords || related.Length > MaxWords) return AppText.L($"別名・関連語はそれぞれ{MaxWords}語までです。", $"Up to {MaxWords} aliases and {MaxWords} related terms are allowed.");
        if (new[] { term }.Concat(aliases).Concat(related).Any(word => word.Length > MaxWordChars))
            return AppText.L($"1語は{MaxWordChars}文字までです。", $"Each term must be at most {MaxWordChars} characters.");
        if (aliases.Length == 0 && related.Length == 0) return AppText.L("別名か関連語を1語以上入力してください。", "Enter at least one alias or related term.");
        return null;
    }

    public static JsonObject Upsert(string term, string[] aliases, string[] related) => new()
    {
        ["term"] = term.Trim(),
        ["aliases"] = new JsonArray(aliases.Select(word => (JsonNode?)JsonValue.Create(word)).ToArray()),
        ["related"] = new JsonArray(related.Select(word => (JsonNode?)JsonValue.Create(word)).ToArray())
    };

    public const string ExportFormat = "aredoko-related-terms";
    public const int MaxImportBytes = 16 * 1024 * 1024;

    // Client-side preflight before sending an explicit user-chosen file; the
    // server validates every entry again and imports all or nothing.
    public static string? CheckImport(string text)
    {
        if (System.Text.Encoding.UTF8.GetByteCount(text) > MaxImportBytes) return AppText.L("ファイルが大きすぎます（16MiBまで）。", "File is too large (max 16 MiB).");
        JsonNode? root;
        try { root = JsonNode.Parse(text); }
        catch (System.Text.Json.JsonException) { return AppText.L("JSONとして読み込めません。", "Could not parse as JSON."); }
        if (root is not JsonObject document || document["format"]?.GetValueKind() != System.Text.Json.JsonValueKind.String
            || document["format"]!.GetValue<string>() != ExportFormat || document["version"]?.GetValueKind() != System.Text.Json.JsonValueKind.Number
            || document["version"]!.GetValue<double>() != 1 || document["entries"] is not JsonArray)
            return AppText.L("Aredokoの関連語ファイル（format/version）ではありません。", "Not an Aredoko related-terms file (format/version mismatch).");
        return null;
    }

    public static int CountExport(string document) =>
        JsonNode.Parse(document)?["entries"] is JsonArray entries ? entries.Count : 0;

    public static string DescribeImport(JsonNode result) => AppText.L(
        $"{result["imported"]?.GetValue<int>() ?? 0:N0}件を読み込みました（追加{result["added"]?.GetValue<int>() ?? 0:N0}・置換{result["replaced"]?.GetValue<int>() ?? 0:N0}）。",
        $"Imported {result["imported"]?.GetValue<int>() ?? 0:N0} entries (Added {result["added"]?.GetValue<int>() ?? 0:N0} · Replaced {result["replaced"]?.GetValue<int>() ?? 0:N0}).");

    public static JsonObject Delete(string term) => new() { ["term"] = term.Trim() };

    public static List<RelatedTermEntry> ParseList(JsonNode response)
    {
        static string[] Words(JsonNode? node) =>
            node is JsonArray array ? array.Select(word => word?.GetValue<string>() ?? "").Where(word => word.Length > 0).ToArray() : [];
        return (response["items"] as JsonArray ?? throw new FormatException("items missing"))
            .Where(node => node is JsonObject)
            .Select(node => new RelatedTermEntry(node!["term"]?.GetValue<string>() ?? "", Words(node["aliases"]), Words(node["related"])))
            .Where(entry => entry.Term.Length > 0).ToList();
    }
}
