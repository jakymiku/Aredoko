using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record ShelfDescriptor(long Id, string Name, int ItemCount, MediaRow? Representative = null);

public static class ShelfProtocol
{
    public static void ValidateIds(IReadOnlyList<long> ids)
    {
        if(ids.Count>64 || ids.Any(id=>id<1) || ids.Distinct().Count()!=ids.Count)
            throw new ArgumentException("棚は重複のない64件以内で選択してください。");
    }
    public static long[] ReadIds(JsonElement value)
    {
        if(value.ValueKind!=JsonValueKind.Array)throw new InvalidDataException("Invalid shelf membership");
        var ids=value.EnumerateArray().Select(x=>x.GetInt64()).ToArray();ValidateIds(ids);return ids.Order().ToArray();
    }
    public static JsonArray Ids(IReadOnlyList<long> ids)
    {
        ValidateIds(ids);var result=new JsonArray();
        foreach(var id in ids.Order())result.Add((JsonNode?)JsonValue.Create(id));
        return result;
    }
    public static JsonObject Restrict(JsonObject conditions, IReadOnlyList<long>? ids)
    {
        if(ids is null)return conditions;
        var semantic=conditions["mode"]?.GetValue<string>() is "semantic" or "similar";
        var target=semantic?conditions["scope"]?.AsObject() ?? throw new InvalidDataException("Missing search scope"):conditions;
        // Items may belong to both A and B: intersecting the ID sets would
        // incorrectly return no items. Backend combines two membership predicates.
        target[semantic?"shelf_filter_ids":"shelf_ids"]=Ids(ids);return conditions;
    }
    public static IReadOnlyList<ShelfDescriptor> ReadList(string json)
    {
        using var doc=JsonDocument.Parse(json);
        var rows=doc.RootElement.GetProperty("shelves");
        if(rows.ValueKind!=JsonValueKind.Array)throw new InvalidDataException("Invalid shelf list");
        var result=new List<ShelfDescriptor>();var seen=new HashSet<long>();
        foreach(var row in rows.EnumerateArray())
        {
            var id=row.GetProperty("id").GetInt64();var name=row.GetProperty("name").GetString();var count=row.GetProperty("item_count").GetInt32();
            if(id<1 || !seen.Add(id) || name is null || name.Length is <1 or >80 || count<0)
                throw new InvalidDataException("Invalid shelf descriptor");
            var representative=row.TryGetProperty("representative",out var sample)&&sample.ValueKind==JsonValueKind.Object ? Protocol.ParseItem(sample.GetRawText()) : null;
            result.Add(new(id,name,count,representative));
        }
        return result;
    }
    public static string SummarizeNames(IEnumerable<string> names, string emptyText = "", int maxVisible = 3)
    {
        var list = names.Where(name => !string.IsNullOrWhiteSpace(name)).ToArray();
        if (list.Length == 0) return emptyText;
        return maxVisible > 0 && list.Length > maxVisible
            ? string.Join("、", list.Take(maxVisible)) + $" ほか{list.Length - maxVisible:N0}棚"
            : string.Join("、", list);
    }
}

// IDs and JSON data only: no WinUI types, native handles or OS-specific paths.
public sealed class ShelfClient(HttpClient client)
{
    public async Task<IReadOnlyList<ShelfDescriptor>> ListAsync(CancellationToken cancellation=default)
    {
        using var response=await client.GetAsync("api/library/shelves",cancellation);
        return ShelfProtocol.ReadList(await ReadAsync(response,cancellation));
    }
    public async Task<long> CreateAsync(string name,CancellationToken cancellation=default) =>
        (await PostAsync("create",new(){["name"]=ValidateName(name)},cancellation))["id"]!.GetValue<long>();
    public Task RenameAsync(long id,string name,CancellationToken cancellation=default) =>
        PostAsync("rename",new(){["shelf_id"]=ValidId(id),["name"]=ValidateName(name)},cancellation);
    public Task DeleteAsync(long id,CancellationToken cancellation=default) =>
        PostAsync("delete",new(){["shelf_id"]=ValidId(id),["consent"]=true},cancellation);
    public Task AssignAsync(string entity,IReadOnlyList<int> objectIds,IReadOnlyList<long> shelfIds,CancellationToken cancellation=default)
    {
        if(entity is not ("item" or "root") || objectIds.Count is <1 or >256 || objectIds.Any(id=>id<1) || objectIds.Distinct().Count()!=objectIds.Count)
            throw new ArgumentException("Invalid shelf objects");
        var objects=new JsonArray();foreach(var id in objectIds)objects.Add((JsonNode?)JsonValue.Create(id));
        return PostAsync("assign",new(){["entity"]=entity,["object_ids"]=objects,["shelf_ids"]=ShelfProtocol.Ids(shelfIds)},cancellation);
    }
    private static long ValidId(long id)=>id>0?id:throw new ArgumentOutOfRangeException(nameof(id));
    private static string ValidateName(string name)=>string.IsNullOrWhiteSpace(name)||name.Trim().Length>80
        ?throw new ArgumentException("棚の名前は1～80文字で入力してください。") :name.Trim();
    private async Task<JsonObject> PostAsync(string operation,JsonObject body,CancellationToken cancellation)
    {
        using var content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");
        using var response=await client.PostAsync("api/library/shelves/"+operation,content,cancellation);
        return JsonNode.Parse(await ReadAsync(response,cancellation))!.AsObject();
    }
    private static async Task<string> ReadAsync(HttpResponseMessage response,CancellationToken cancellation)
    {
        var text=await response.Content.ReadAsStringAsync(cancellation);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return text;
    }
}
