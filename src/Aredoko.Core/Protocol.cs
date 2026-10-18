// Reflection-free JSON protocol shared by the production client and tests.
// Uses the System.Text.Json DOM and Utf8JsonWriter: no runtime reflection or
// JsonSerializerContext needed, including for packaged trimmed Release builds.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Aredoko.Core;

public sealed class MediaRow
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Kind { get; set; } = "";
    public string[] Tags { get; set; } = [];
    public string Shelf { get; set; } = "";
    public bool Favorite { get; set; }
    public bool Reviewed { get; set; }
    public int RootId { get; set; }
    public long Modified { get; set; }
    public long Size { get; set; }
    public string PreviewKey => $"{RootId}:{Id}:{Modified}:{Size}";
    public string Location { get; set; } = "";
    // An image folder registered as one book: the server marks it with a
    // trailing "/" ("./" for the registered folder itself); file paths never end so.
    public bool IsFolderBook => Location.EndsWith('/');
    public string LocationLabel => Location == "./" ? "登録フォルダ直下の画像（一冊）" : IsFolderBook ? Location + "（画像フォルダを一冊として表示）" : Location;
    public string Availability { get; set; } = "";
    // "related" when the row matched only through the user's related-term dictionary;
    // "partial" when nothing had every word and this row lacks one of them.
    public string Match { get; set; } = "";
    public string SimilarityGroup { get; set; } = "";
    public double? SemanticScore { get; set; }
    public string ScoreKind { get; set; } = "";
    public int? SimilarityOriginId { get; set; }
    public int? VideoMatchMs { get; set; }
    public int? OriginMatchMs { get; set; }
    public int? AudioMatchMs { get; set; }
    public string? AudioMatchSnippet { get; set; }
    public int LiteralHits { get; set; }
    public int LiteralWords { get; set; }
    private static string FormatVideoTimestamp(int ms)
    {
        var sec = Math.Max(0, ms / 1000);
        return $"{sec / 60}:{sec % 60:D2}";
    }
    public string AIEvidence => AIPage is not null || Proposal?.SemanticScore is not null ? "" : SemanticScore is double score
        ? (SimilarityOriginId is int ? (VideoMatchMs is int matchMs ? (OriginMatchMs is int v2vOms ? $"動画一致（起点 {FormatVideoTimestamp(v2vOms)} → 候補 {FormatVideoTimestamp(matchMs)}）" : $"動画フレーム一致（{FormatVideoTimestamp(matchMs)}）")
                                       : OriginMatchMs is int v2iOms ? $"起点の動画（{FormatVideoTimestamp(v2iOms)}）に似た候補"
                                       : "起点の画像・表紙に似た候補")
           : VideoMatchMs is int vms ? $"動画フレーム一致（{FormatVideoTimestamp(vms)}）" + (LiteralWords>0 ? $" · 文字一致{LiteralHits}/{LiteralWords}語" : "")
           : AudioMatchMs is int ams ? $"音声発話一致（{FormatVideoTimestamp(ams)}{(string.IsNullOrEmpty(AudioMatchSnippet) ? "" : $" · 「{AudioMatchSnippet}」")}）" + (LiteralWords>0 ? $" · 文字一致{LiteralHits}/{LiteralWords}語" : "")
           : LiteralWords>0 ? (LiteralHits==LiteralWords ? "名前・タグで全語一致" : $"文字一致{LiteralHits}/{LiteralWords}語 · AI候補") : "AI類似候補")
          + (ScoreKind=="cosine" ? $"\n類似度 {score:F3}" : ScoreKind=="reciprocal-rank" ? $"\n順位統合値 {score:F4}" : "")
        : "";
    public string MatchLabel => Match switch { "related" => "関連語の候補 · ", "partial" => "一部の語のみ一致 · ", _ => "" };
    public string KindAndTags => MatchLabel + $"{Kind} · {string.Join("、", Tags)}";
    // Per-word reason for a literal search row; null for list/AI/old servers.
    public SearchEvidence? Evidence { get; set; }
    // Latest-batch pending tag proposal match when searching in ModeTagCandidates.
    public ProposalMatch? Proposal { get; set; }
    // Explicit page-text search match when searching page texts.
    public PageTextMatch? PageText { get; set; }
    public AIPageMatch? AIPage { get; set; }
}

public sealed record ProposalMatch(
    long BatchId,
    string SourceRevision,
    string SourceState,
    string[] Tags,
    string Model,
    string ModelRevision,
    string Adapter,
    string AdapterVersion,
    string Preprocessing,
    string EvidenceKind,
    int EvidencePage,
    double? SemanticScore = null,
    string? EmbeddingModel = null)
{
    public string SourceStateLabel => SourceState switch
    {
        "current" => "元ファイル一致",
        "stale" => "元ファイル変更あり（要再生成）",
        "unverified" => "元ファイル確認待ち",
        _ => "元ファイル利用不可"
    };
    public string EvidenceLabel => EvidenceKind == "cover" ? "本の先頭ページのみ" : "画像";
    public string Summary
    {
        get
        {
            var shown = string.Join("、", Tags.Take(5));
            var extra = Tags.Length > 5 ? $" ほか{Tags.Length - 5}件" : "";
            var meaning=SemanticScore is double score?$"タグ候補の意味一致 · 類似度 {score:F3}\n":"";
            return meaning+$"未承認タグ候補: {shown}{extra}\nモデル: {Model} ({Adapter} {AdapterVersion}) · 根拠: {EvidenceLabel} · {SourceStateLabel}";
        }
    }
}

public sealed record SearchEvidence(string[] Direct, string[] Related, string[] Missing)
{
    // Same cap as the server's query word limit; words are display-only.
    public const int MaxWords = 16;
    public const int MaxWordLength = 64;
    public bool AllDirect => Direct.Length > 0 && Related.Length == 0 && Missing.Length == 0;
}

public sealed record SearchExpansion(string Term, string[] Added, bool Truncated);

public sealed class SearchResponse
{
    public string SimilarityStatus { get; set; } = "";
    public string OriginKind { get; set; } = "";
    public int Total { get; set; }
    public int? PendingIndexRemaining { get; set; }
    public string ScoreKind { get; set; } = "";
    public double? GroupBoundary { get; set; }
    public int LeadingTotal { get; set; }
    public int OtherTotal { get; set; }
    public int? CoverageLimit { get; set; }
    public bool SearchComplete { get; set; }
    public int? SearchCandidateTotal { get; set; }
    public int? IndexedTotal { get; set; }
    public List<MediaRow> Items { get; set; } = [];
    public List<SearchExpansion> Expansions { get; set; } = [];
    // Set when no item had every word and the server fell back to items with all but one.
    public int? PartialWords { get; set; }
}

public sealed class SessionResponse
{
    public string Token { get; set; } = "";
}

public static class Protocol
{
    public static SessionResponse ParseSession(string text)
    {
        using var doc = JsonDocument.Parse(text);
        return new SessionResponse {
            Token = doc.RootElement.GetProperty("token").GetString() ?? ""
        };
    }

    public static SearchResponse ParseSearch(string text)
    {
        using var doc = JsonDocument.Parse(text);
        var root = doc.RootElement;
        var result = new SearchResponse { Total = root.GetProperty("total").GetInt32(), CoverageLimit = root.TryGetProperty("coverage_limit",out var coverage) ? coverage.GetInt32() : null };
        if(root.TryGetProperty("search_complete",out var complete))
        {
            if(complete.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                throw new InvalidDataException("検索範囲の応答が無効です。");
            result.SearchComplete=complete.GetBoolean();
            if(result.SearchComplete)
            {
                var candidates=root.GetProperty("search_candidate_total").GetInt32();
                var indexed=root.GetProperty("indexed_total").GetInt32();
                if(candidates<0||indexed<0||indexed>candidates||result.Total<0||result.Total>indexed)
                    throw new InvalidDataException("検索対象の件数が無効です。");
                result.SearchCandidateTotal=candidates;result.IndexedTotal=indexed;
                result.CoverageLimit=null; // Legacy coverage_limit describes index jobs, not search truncation.
            }
        }
        result.ScoreKind=root.TryGetProperty("score_kind",out var kind) && kind.ValueKind==JsonValueKind.String ? kind.GetString()??"" : "";
        result.SimilarityStatus=root.TryGetProperty("similarity_status",out var status) && status.ValueKind==JsonValueKind.String ? status.GetString()??"" : "";
        result.OriginKind=root.TryGetProperty("origin_kind",out var originKind) && originKind.ValueKind==JsonValueKind.String ? originKind.GetString()??"" : "";
        result.GroupBoundary=root.TryGetProperty("group_boundary",out var boundary) && boundary.ValueKind==JsonValueKind.Number && boundary.TryGetDouble(out var cut) ? cut : null;
        result.LeadingTotal=root.TryGetProperty("leading_total",out var leading) && leading.TryGetInt32(out var n) ? n : result.Total;
        result.OtherTotal=root.TryGetProperty("other_total",out var other) && other.TryGetInt32(out var m) ? m : 0;
        foreach (var element in root.GetProperty("items").EnumerateArray())
        {
            var row=ReadRow(element);
            row.ScoreKind=root.TryGetProperty("score_kind",out var scoreKind) && scoreKind.ValueKind==JsonValueKind.String ? scoreKind.GetString()??"" : "";
            result.Items.Add(row);
        }
        if (root.TryGetProperty("partial", out var partial) && partial.ValueKind == JsonValueKind.Object)
            result.PartialWords = partial.GetProperty("words").GetInt32();
        if (root.TryGetProperty("expansions", out var expansions) && expansions.ValueKind == JsonValueKind.Array)
            foreach (var entry in expansions.EnumerateArray())
                result.Expansions.Add(new SearchExpansion(
                    entry.GetProperty("term").GetString() ?? "",
                    entry.GetProperty("added").EnumerateArray().Select(word => word.GetString() ?? "").Where(word => word.Length > 0).ToArray(),
                    entry.TryGetProperty("truncated", out var truncated) && truncated.ValueKind == JsonValueKind.True));
        return result;
    }

    // Short, bounded notice text: which related words the literal search added.
    public static string DescribeExpansions(IReadOnlyList<SearchExpansion> expansions, int wordsPerTerm = 3)
    {
        var parts = expansions.Where(e => e.Added.Length > 0).Take(4).Select(e =>
        {
            var shown = string.Join("、", e.Added.Take(wordsPerTerm));
            var hidden = e.Added.Length - Math.Min(wordsPerTerm, e.Added.Length);
            return $"{e.Term}→{shown}{(hidden > 0 || e.Truncated ? $" ほか{(hidden > 0 ? $"{hidden}語" : "")}" : "")}";
        }).ToList();
        if (parts.Count == 0) return "";
        return "登録した関連語も候補に含めています（" + string.Join(" / ", parts) + "）。入力した語に一致する作品を先に表示します。";
    }

    public static string DescribePartial(int? words) =>
        words is int count ? $"{count}語すべてに一致する作品はありません。{count - 1}語に一致する作品を表示しています。" : "";

    public static MediaRow ParseItem(string text)
    {
        using var doc = JsonDocument.Parse(text);
        return ReadRow(doc.RootElement);
    }

    private static MediaRow ReadRow(JsonElement row) => new() {
        Id = row.GetProperty("id").GetInt32(),
        Title = row.GetProperty("title").GetString() ?? "",
        Kind = row.GetProperty("kind").GetString() ?? "",
        Tags = row.GetProperty("tags").EnumerateArray().Select(t => t.GetString() ?? "").ToArray(),
        Shelf = row.GetProperty("shelf").GetString() ?? "",
        Favorite = row.GetProperty("favorite").GetBoolean(),
        Reviewed = row.GetProperty("reviewed").GetBoolean(),
        RootId = row.TryGetProperty("root_id", out var rootId) ? rootId.GetInt32() : 0,
        Modified = row.TryGetProperty("mtime_ns", out var modified) ? modified.GetInt64() : 0,
        Size = row.TryGetProperty("size_bytes", out var size) ? size.GetInt64() : 0,
        Location = row.TryGetProperty("relative_path", out var loc) ? loc.GetString() ?? "" : "",
        Availability = row.TryGetProperty("availability", out var av) ? av.GetString() ?? "" : "",
        SimilarityGroup = row.TryGetProperty("similarity_group",out var group) && group.ValueKind==JsonValueKind.String ? group.GetString()??"" : "",
        SimilarityOriginId = row.TryGetProperty("similarity_origin_id",out var origin) && origin.ValueKind==JsonValueKind.Number && origin.TryGetInt32(out var originId) && originId>0 ? originId : null,
        VideoMatchMs = row.TryGetProperty("video_match_ms",out var vms) && vms.ValueKind==JsonValueKind.Number && vms.TryGetInt32(out var vmsVal) && vmsVal is >=0 and <=86400000 ? vmsVal : null,
        OriginMatchMs = row.TryGetProperty("origin_match_ms",out var oms) && oms.ValueKind==JsonValueKind.Number && oms.TryGetInt32(out var omsVal) && omsVal is >=0 and <=86400000 ? omsVal : null,
        AudioMatchMs = row.TryGetProperty("audio_match_ms",out var ams) && ams.ValueKind==JsonValueKind.Number && ams.TryGetInt32(out var amsVal) && amsVal is >=0 and <=86400000 ? amsVal : null,
        AudioMatchSnippet = row.TryGetProperty("audio_match_snippet",out var snip) && snip.ValueKind==JsonValueKind.String ? (snip.GetString() is { Length: >0 } s ? (s.Length>120 ? s[..120]+"…" : s) : null) : null,
        SemanticScore = row.TryGetProperty("semantic_score",out var score) && score.ValueKind==JsonValueKind.Number && score.TryGetDouble(out var value) && double.IsFinite(value) ? value : null,
        LiteralHits = row.TryGetProperty("literal_hits",out var hits) && hits.TryGetInt32(out var count) ? count : 0,
        LiteralWords = row.TryGetProperty("literal_words",out var words) && words.TryGetInt32(out var total) ? total : 0,
        Match = row.TryGetProperty("match", out var match) && match.ValueKind == JsonValueKind.String ? match.GetString() ?? "" : "",
        AIPage = AIPageMatch.Read(row),
        Evidence = ReadEvidence(row)
    };

    private static SearchEvidence? ReadEvidence(JsonElement row)
    {
        if (!row.TryGetProperty("search_evidence", out var value) || value.ValueKind != JsonValueKind.Object) return null;
        var budget = SearchEvidence.MaxWords;
        string[] Words(string name)
        {
            if (!value.TryGetProperty(name, out var list) || list.ValueKind != JsonValueKind.Array) return [];
            var words = new List<string>();
            foreach (var word in list.EnumerateArray())
            {
                if (budget <= 0) break;
                if (word.ValueKind != JsonValueKind.String) continue;
                var text = (word.GetString() ?? "").Trim();
                if (text.Length == 0) continue;
                if (text.Length > SearchEvidence.MaxWordLength)
                {
                    var cut = char.IsHighSurrogate(text[SearchEvidence.MaxWordLength - 1]) ? SearchEvidence.MaxWordLength - 1 : SearchEvidence.MaxWordLength;
                    text = text[..cut] + "…";
                }
                words.Add(text); budget--;
            }
            return words.ToArray();
        }
        var evidence = new SearchEvidence(Words("direct_words"), Words("related_words"), Words("missing_words"));
        return evidence.Direct.Length + evidence.Related.Length + evidence.Missing.Length == 0 ? null : evidence;
    }

    // Short per-row reason. Distinguishes typed words found as-is, words found only through
    // the user's related-term dictionary, and words this row lacks. Not a confidence value.
    public static string DescribeEvidence(SearchEvidence? evidence, int wordsPerPart = 4)
    {
        if (evidence is null) return "";
        static string Part(string label, string[] words, int limit) =>
            words.Length == 0 ? "" : label + string.Join("、", words.Take(limit)) + (words.Length > limit ? $" ほか{words.Length - limit}語" : "");
        var parts = new[] {
            Part("入力語で一致：", evidence.Direct, wordsPerPart),
            Part("関連語で一致：", evidence.Related, wordsPerPart),
            Part("一致なし：", evidence.Missing, wordsPerPart)
        }.Where(part => part.Length > 0);
        return string.Join(" / ", parts);
    }

    public static string CreateUpdate(int id, IEnumerable<string> tags, string shelf, bool favorite, bool reviewed)
    {
        using var stream = new MemoryStream();
        using (var json = new Utf8JsonWriter(stream)) {
            json.WriteStartObject();
            json.WritePropertyName("ids");
            json.WriteStartArray();
            json.WriteNumberValue(id);
            json.WriteEndArray();
            json.WritePropertyName("changes");
            json.WriteStartObject();
            json.WritePropertyName("tags");
            json.WriteStartArray();
            foreach (var tag in tags) json.WriteStringValue(tag);
            json.WriteEndArray();
            json.WriteString("shelf", shelf);
            json.WriteBoolean("favorite", favorite);
            json.WriteBoolean("reviewed", reviewed);
            json.WriteEndObject();
            json.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }
}
