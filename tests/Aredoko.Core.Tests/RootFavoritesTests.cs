using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;
internal static class RootFavoritesTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var old=RegisteredRootRow.ParseList(JsonNode.Parse("""{"items":[{"id":1,"path":"fixture","enabled":1,"online":true,"default_shelf":"","excludes":[]}]}""")!)[0];
        check(!old.Favorite&&old.ShelfIds is null,"old root metadata defaults to not favorite without losing compatibility");
        var current=RegisteredRootRow.ParseList(JsonNode.Parse("""{"items":[{"id":1,"path":"fixture","enabled":1,"online":true,"default_shelf":"A","excludes":[],"favorite":true,"shelf_ids":[1,4294967297]}]}""")!)[0];
        check(current.Favorite&&current.ShelfIds!.Count==2&&current.ShelfLabel.Contains("ほか1棚"),"registered root carries independent favorite and all initial shelves");
        using var handler=new Stub(async request=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
            check(request.RequestUri!.AbsolutePath=="/api/library/roots/favorite"&&body["root_id"]!.GetValue<int>()==1&&body["favorite"]!.GetValue<bool>(),"root favorite targets the root endpoint rather than media metadata");
            return new(HttpStatusCode.OK){Content=new StringContent("{}",Encoding.UTF8,"application/json")};
        });
        using var api=new LibraryApi(handler);await api.SetRootFavoriteAsync(1,true);
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>send(request);}
}
