using System.Globalization;
using System.Text.Json.Nodes;
namespace Aredoko.Core;

public static class FolderSearch
{
    public static string LiteralRoute(string query,string kind,string view,int page,int? rootId=null)
    {
        Validate(rootId);
        return $"api/items?q={Uri.EscapeDataString(query)}&kind={Uri.EscapeDataString(kind)}&view={Uri.EscapeDataString(view)}&page={page.ToString(CultureInfo.InvariantCulture)}"
            +(rootId is int id ? "&root_id="+id.ToString(CultureInfo.InvariantCulture) : "");
    }
    // The result is owned by this request. A selected root intersects saved
    // AI scope; it must never silently broaden an empty/disjoint selection.
    public static JsonObject? RestrictAI(JsonObject? scope,int? rootId)
    {
        Validate(rootId);
        var result=scope?.DeepClone().AsObject();
        if(rootId is not int id)return result;
        result ??= new JsonObject();
        var allowed=result["root_ids"] is not JsonArray roots || roots.Any(n=>n?.GetValue<int>()==id);
        result["root_ids"]=allowed ? new JsonArray((JsonNode?)JsonValue.Create(id)) : new JsonArray();
        return result;
    }
    private static void Validate(int? rootId)
    {
        if(rootId is int id && id<=0)throw new ArgumentOutOfRangeException(nameof(rootId));
    }
}
