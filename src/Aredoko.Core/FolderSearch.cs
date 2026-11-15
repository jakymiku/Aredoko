using System.Globalization;
using System.Text.Json.Nodes;
namespace Aredoko.Core;

public static class FolderSearch
{
    public const int MaxRoots = 256;

    public static string LiteralRoute(string query,string kind,string view,int page,int? rootId=null)
    {
        Validate(rootId);
        return BaseRoute(query,kind,view,page)
            +(rootId is int id ? "&root_id="+id.ToString(CultureInfo.InvariantCulture) : "");
    }

    public static string LiteralRouteMulti(string query,string kind,string view,int page,IReadOnlyList<int>? rootIds,string? tag=null)
    {
        var route=BaseRoute(query,kind,view,page);
        var normalized=NormalizeNonEmpty(rootIds);
        if(normalized is not null)
            route+=normalized.Length==1
                ?"&root_id="+normalized[0].ToString(CultureInfo.InvariantCulture)
                :"&root_ids="+string.Join(",",normalized.Select(id=>id.ToString(CultureInfo.InvariantCulture)));
        if(ResultSearchConditions.NormalizeTag(tag) is {} exactTag)
            route+="&tag="+Uri.EscapeDataString(exactTag);
        return route;
    }

    // The result is owned by this request. Selected roots intersect saved
    // AI scope; they must never silently broaden an empty/disjoint selection.
    public static JsonObject? RestrictAI(JsonObject? scope,int? rootId)
    {
        Validate(rootId);
        return rootId is int id ? RestrictAIMulti(scope,new[]{id}) : scope?.DeepClone().AsObject();
    }

    public static JsonObject? RestrictAIMulti(JsonObject? scope,IReadOnlyList<int>? rootIds)
    {
        var result=scope?.DeepClone().AsObject();
        if(rootIds is null)return result;
        result ??= new JsonObject();
        if(rootIds.Count==0)
        {
            result["root_ids"]=new JsonArray();
            return result;
        }
        var normalized=NormalizeNonEmpty(rootIds)!;
        HashSet<int>? allowedSet=result["root_ids"] is JsonArray roots
            ? roots.Select(n=>n!.GetValue<int>()).ToHashSet()
            : null;
        var intersected=new JsonArray();
        foreach(var id in normalized)
            if(allowedSet is null || allowedSet.Contains(id))
                intersected.Add((JsonNode?)JsonValue.Create(id));
        result["root_ids"]=intersected;
        return result;
    }

    public static int[]? NormalizeNonEmpty(IReadOnlyList<int>? rootIds)
    {
        if(rootIds is null)return null;
        if(rootIds.Count==0 || rootIds.Count>MaxRoots)throw new ArgumentOutOfRangeException(nameof(rootIds));
        foreach(var id in rootIds)if(id<=0)throw new ArgumentOutOfRangeException(nameof(rootIds));
        var sorted=rootIds.Order().ToArray();
        for(var i=1;i<sorted.Length;i++)
            if(sorted[i]==sorted[i-1])throw new ArgumentException("Duplicate root IDs are not allowed",nameof(rootIds));
        return sorted;
    }

    private static string BaseRoute(string query,string kind,string view,int page)
    {
        if(page<0)throw new ArgumentOutOfRangeException(nameof(page));
        return $"api/items?q={Uri.EscapeDataString(query)}&kind={Uri.EscapeDataString(kind)}&view={Uri.EscapeDataString(view)}&page={page.ToString(CultureInfo.InvariantCulture)}";
    }

    private static void Validate(int? rootId)
    {
        if(rootId is int id && id<=0)throw new ArgumentOutOfRangeException(nameof(rootId));
    }
}
