using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

static class FavoritePatchTests
{
    public static async Task Run(Action<bool,string> check)
    {
        foreach(var supported in new[]{false,true})
        {
            bool retained=true;int creates=0,edits=0;JsonObject? sent=null;
            using var handler=new Handler(async request=>
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();var id=body["session_id"]!.GetValue<string>();
                JsonObject reply;
                if(request.RequestUri!.AbsolutePath.EndsWith("/create"))
                {
                    creates++;reply=new(){["session_id"]=id,["state"]="ready",["total"]=50000,["conditions"]=body["conditions"]!.DeepClone(),["range_limit"]=120,["idle_seconds"]=900};
                    if(supported)reply["favorite_patch_supported"]=true;
                }
                else if(request.RequestUri.AbsolutePath.EndsWith("/edit"))
                {
                    edits++;sent=body;reply=new(){["session_id"]=id,["item_ids"]=body["item_ids"]!.DeepClone(),["operation"]=body["operation"]!.DeepClone(),["updated"]=1};
                    if(supported)reply["kept_session"]=retained;
                }
                else reply=new(){["closed"]=true};
                return new(HttpStatusCode.OK){Content=new StringContent(reply.ToJsonString(),Encoding.UTF8,"application/json")};
            });
            using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
            await using var session=await new ResultSessionClient(http).CreateAsync(new(){["mode"]="literal",["view"]="all"},CancellationToken.None);
            var kept=await session.EditFavoriteAsync(1201,true,CancellationToken.None);
            check(kept==supported&&creates==1&&edits==1,"favorite-only edit reports retention without rebuilding fifty thousand results");
            check(sent!["operation"]!.GetValue<string>()=="favorite_add"&&sent["item_ids"]![0]!.GetValue<int>()==1201&&sent["shelf_ids"]!.AsArray().Count==0,"favorite patch never includes an unsaved tag or shelf draft");
            check(supported?sent["keep_session"]?.GetValue<bool>()==true:!sent.ContainsKey("keep_session"),"old server receives only its existing strict edit fields");
            retained=false;
            check(!await session.EditFavoriteAsync(1201,false,CancellationToken.None)&&sent["operation"]!.GetValue<string>()=="favorite_remove","saved edit requiring refresh is distinct from a failed save");
            bool invalid=false;try{await session.EditFavoriteAsync(0,true,CancellationToken.None);}catch(ArgumentException){invalid=true;}
            check(invalid&&edits==2,"invalid favorite IDs never reach the server");
        }
    }
    private sealed class Handler(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>send(request);}
}
