using System.Text.Json.Nodes;

namespace Aredoko.Core;

// Translate existing search controls into one immutable backend condition set.
// A null result is the established empty-input state of explicit text/tag AI.
public static class ResultSearchConditions
{
    public const int MaxTagLength = 60;

    public static string? NormalizeTag(string? tag)
    {
        if (tag is null) return null;
        var trimmed = tag.Trim();
        if (trimmed.Length is < 1 or > MaxTagLength)
            throw new ArgumentException($"タグは1～{MaxTagLength}文字で指定してください。", nameof(tag));
        return trimmed;
    }

    public static JsonObject? RestrictTag(JsonObject? conditions, string? tag)
    {
        var normalized = NormalizeTag(tag);
        if (conditions is null || normalized is null) return conditions;
        var semantic = conditions["mode"]?.GetValue<string>() is "semantic" or "similar";
        var target = semantic ? conditions["scope"]?.AsObject() ?? throw new InvalidDataException("Missing search scope") : conditions;
        target["tag"] = normalized;
        return conditions;
    }

    public static JsonObject? Create(string query, string kind, string view, SearchMethod method,
        JsonObject? scope, IReadOnlyList<int>? rootIds, int? originId = null,
        bool literalOnly = false, double? groupThreshold = null, string resultGroup = "all", IReadOnlyList<long>? shelfIds = null,
        bool directAudioSimilarity = false, bool directVideoSimilarity = false, bool directVideoAudioSimilarity = false,
        string? tag = null, int? originPage = null, int? originMs = null)
    {
        if((directAudioSimilarity?1:0)+(directVideoSimilarity?1:0)+(directVideoAudioSimilarity?1:0)>1)throw new ArgumentException("Select one direct similarity mode");
        JsonObject Finish(JsonObject conditions) => RestrictTag(ShelfProtocol.Restrict(conditions, shelfIds), tag)!;
        JsonObject result;
        if (originId is int origin)
        {
            if(directAudioSimilarity || directVideoSimilarity || directVideoAudioSimilarity)
            {
                if(origin<=0)throw new ArgumentOutOfRangeException(nameof(originId));
                result=new JsonObject{["mode"]=directVideoAudioSimilarity?"video-audio-similar":directVideoSimilarity?"video-similar":"audio-similar",["item_id"]=origin,["view"]=view};
                if(FolderSearch.NormalizeNonEmpty(rootIds) is {} audioRoots)
                {
                    var values=new JsonArray();foreach(var id in audioRoots)values.Add((JsonNode?)JsonValue.Create(id));
                    result["root_ids"]=values;
                }
                return Finish(result);
            }
            if (scope is null) throw new ArgumentException("AI scope is required", nameof(scope));
            result = SimilaritySearch.RequestMulti(origin, kind, view, 0, scope, rootIds, originPage, originMs);
            result.Remove("page"); result["mode"] = "similar";
            return Finish(result);
        }
        if (view == "history")
        {
            if (method.IsAI || method.Source != "all") throw new ArgumentException("History uses literal search");
            result = new JsonObject { ["mode"] = "history", ["query"] = query, ["kind"] = kind };
        }
        else if (method.IsDirectContent)
        {
            if (string.IsNullOrWhiteSpace(query))return null;
            if(method.IsAudioContent && kind is not ("" or "audio"))throw new ArgumentException("音声の内容検索では種類を音声・音楽にしてください。");
            if(method.IsVideoContent && kind is not ("" or "video"))throw new ArgumentException("動画の内容検索では種類を動画にしてください。");
            if(method.IsVideoAudioContent && kind is not ("" or "video"))throw new ArgumentException("動画内の音声検索では種類を動画にしてください。");
            result=new JsonObject{["mode"]=method.Source,["query"]=query,["view"]=view};
        }
        else if (method.IsPageText || method.IsTagCandidates)
        {
            if ((method.IsPageText || method.IsTagSemantic) && string.IsNullOrWhiteSpace(query)) return null;
            result = new JsonObject { ["mode"] = method.Source, ["query"] = query, ["kind"] = kind, ["view"] = view };
        }
        else if (method.IsAI && !string.IsNullOrWhiteSpace(query))
        {
            if (scope is null) throw new ArgumentException("AI scope is required", nameof(scope));
            result = AIScopeRequests.Search(query, kind, view, 0, method.Source,
                FolderSearch.RestrictAIMulti(scope, rootIds), literalOnly, groupThreshold, resultGroup);
            result.Remove("page"); result["mode"] = "semantic";
            return Finish(result);
        }
        else result = new JsonObject { ["mode"] = "literal", ["query"] = query, ["kind"] = kind, ["view"] = view };
        var roots = FolderSearch.NormalizeNonEmpty(rootIds);
        if (roots is not null)
        {
            var values = new JsonArray(); foreach (var id in roots) values.Add((JsonNode?)JsonValue.Create(id));
            result["root_ids"] = values;
        }
        return Finish(result);
    }
}
