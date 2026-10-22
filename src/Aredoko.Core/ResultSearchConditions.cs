using System.Text.Json.Nodes;

namespace Aredoko.Core;

// Translate existing search controls into one immutable backend condition set.
// A null result is the established empty-input state of explicit text/tag AI.
public static class ResultSearchConditions
{
    public static JsonObject? Create(string query, string kind, string view, SearchMethod method,
        JsonObject? scope, IReadOnlyList<int>? rootIds, int? originId = null,
        bool literalOnly = false, double? groupThreshold = null, string resultGroup = "all")
    {
        JsonObject result;
        if (originId is int origin)
        {
            if (scope is null) throw new ArgumentException("AI scope is required", nameof(scope));
            result = SimilaritySearch.RequestMulti(origin, kind, view, 0, scope, rootIds);
            result.Remove("page"); result["mode"] = "similar";
            return result;
        }
        if (view == "history")
        {
            if (method.IsAI || method.Source != "all") throw new ArgumentException("History uses literal search");
            result = new JsonObject { ["mode"] = "history", ["query"] = query, ["kind"] = kind };
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
            return result;
        }
        else result = new JsonObject { ["mode"] = "literal", ["query"] = query, ["kind"] = kind, ["view"] = view };
        var roots = FolderSearch.NormalizeNonEmpty(rootIds);
        if (roots is not null)
        {
            var values = new JsonArray(); foreach (var id in roots) values.Add(id);
            result["root_ids"] = values;
        }
        return result;
    }
}
