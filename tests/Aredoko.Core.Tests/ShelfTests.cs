using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class ShelfTests
{
    public static async Task Run(Action<bool,string> check)
    {
        const long sid=4294967297;
        var saved=new EditorState("tag","legacy",false,false){ShelfIds=new long[]{sid,2}};
        check(!EditorState.IsDirty(saved,saved with{Shelf="renamed",ShelfIds=new long[]{2,sid}}),"shelf draft compares IDs by value, independent of order/name");
        check(EditorState.IsDirty(saved,saved with{ShelfIds=new long[]{sid}}),"removing one membership marks draft dirty");
        using var updated=JsonDocument.Parse(Protocol.CreateUpdate(1,new[]{"tag"},"legacy",false,false,saved.ShelfIds));
        var changes=updated.RootElement.GetProperty("changes");
        check(!changes.TryGetProperty("shelf",out _) && changes.GetProperty("shelf_ids")[1].GetInt64()==sid,"ID save omits destructive scalar and preserves 64-bit identity");
        var scope=new JsonObject{["shelf"]="legacy"};
        foreach(var index in Enumerable.Range(0,7))
        {
            var c=ResultSearchConditions.Create("query","image","all",SearchMethod.FromIndex(index),scope,null,shelfIds:new long[]{sid})!;
            var target=c["mode"]!.GetValue<string>()=="semantic"?c["scope"]!:c;
            check(target[c["mode"]!.GetValue<string>()=="semantic"?"shelf_filter_ids":"shelf_ids"]![0]!.GetValue<long>()==sid,"shelf scope reaches search method "+index);
        }
        check(scope["shelf"]!.GetValue<string>()=="legacy"&&!scope.ContainsKey("shelf_filter_ids"),"shelf filter does not mutate configured AI scope");
        var similar=ResultSearchConditions.Create("","","all",SearchMethod.FromIndex(0),scope,null,originId:1,shelfIds:new long[]{sid})!;
        check(similar["scope"]!["shelf"]!.GetValue<string>()=="legacy"&&similar["scope"]!["shelf_filter_ids"]![0]!.GetValue<long>()==sid,"similar search preserves saved shelf and adds a separate narrowing predicate");
        var item=Protocol.ParseItem("""{"id":1,"title":"a","kind":"image","tags":[],"shelf":"素材","shelf_ids":[4294967297,2],"favorite":false,"reviewed":false}""");
        check(item.ShelfIds.SequenceEqual(new long[]{2,sid}),"row parser preserves all memberships and sorts stable IDs");
        var empty=ResultSearchConditions.Create("","","all",SearchMethod.FromIndex(0),null,null,shelfIds:Array.Empty<long>())!;
        check(empty["shelf_ids"]!.AsArray().Count==0,"explicit empty membership selection remains empty");
        var calls=new List<string>();
        using var handler=new Stub(async request=>
        {
            calls.Add(request.RequestUri!.AbsolutePath);
            if(request.Method==HttpMethod.Get)return Reply("""{"shelves":[{"id":4294967297,"name":"素材","item_count":0}]}""");
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
            if(request.RequestUri.AbsolutePath.EndsWith("delete"))check(body["consent"]!.GetValue<bool>(),"shelf delete explicitly consents");
            if(request.RequestUri.AbsolutePath.EndsWith("assign"))check(body["shelf_ids"]![0]!.GetValue<long>()==sid,"assignment transports exact shelf ID");
            return Reply("""{"id":4294967297}""");
        });
        using var client=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        var shelves=new ShelfClient(client);
        var rows=await shelves.ListAsync();check(rows[0].Id==sid&&rows[0].ItemCount==0,"empty shelf descriptor is available without media");
        check(await shelves.CreateAsync("素材")==sid,"create reads stable shelf ID");
        await shelves.RenameAsync(sid,"改名");await shelves.AssignAsync("item",new[]{1},new[]{sid});await shelves.DeleteAsync(sid);
        check(calls.Count==5,"shelf client uses existing CRUD/assignment endpoints");
        var rejected=false;try{ShelfProtocol.Ids(new long[]{1,1});}catch(ArgumentException){rejected=true;}
        check(rejected,"duplicate shelf IDs rejected before request");
        check(ShelfProtocol.SummarizeNames(Array.Empty<string>(), "棚なし")=="棚なし","empty shelf names use empty label");
        check(ShelfProtocol.SummarizeNames(new[]{"A","B","C"})=="A、B、C","up to three shelf names stay expanded");
        check(ShelfProtocol.SummarizeNames(new[]{"A","B","C","D","E"})=="A、B、C ほか2棚","more than three shelf names summarize extra count");
        check(ShelfProtocol.SummarizeNames(new[]{"A","B","C","D","E"}, maxVisible: 0)=="A、B、C、D、E","maxVisible 0 renders full shelf list");
    }
    private static HttpResponseMessage Reply(string json)=>new(HttpStatusCode.OK){Content=new StringContent(json,Encoding.UTF8,"application/json")};
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request);}
}
