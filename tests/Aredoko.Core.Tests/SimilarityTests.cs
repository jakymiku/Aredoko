using Aredoko.Core;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;

static class SimilarityTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var image=new MediaRow {Id=7,Kind="image",Availability="present"};
        check(SimilaritySearch.CanStart(image),"similarity image context entry");
        check(SimilaritySearch.CanStart(new MediaRow {Id=8,Kind="book",Availability="present"}),"similarity book cover context entry");
        check(!SimilaritySearch.CanStart(new MediaRow {Id=8,Kind="video",Availability="present"}),"no unsupported video similarity entry");
        check(!SimilaritySearch.CanStart(new MediaRow {Id=8,Kind="image",Availability="missing"}),"missing image has no similarity entry");
        var scope=JsonNode.Parse("""{"root_ids":[1,2],"kind":"image","shelf":"素材"}""")!.AsObject();
        var request=SimilaritySearch.Request(7,"image","favorites",2,scope,2);
        check(request["item_id"]!.GetValue<int>()==7&&request["page"]!.GetValue<int>()==2,"context origin and page serialized");
        check(request["scope"]!["root_ids"]!.AsArray().Count==1&&request["scope"]!["root_ids"]![0]!.GetValue<int>()==2,"similarity intersects selected root");
        request["scope"]!["shelf"]="edited";
        check(scope["shelf"]!.GetValue<string>()=="素材"&&scope["root_ids"]!.AsArray().Count==2,"similarity request owns scope snapshot");
        check(SimilaritySearch.Request(7,"","all",0,scope,3)["scope"]!["root_ids"]!.AsArray().Count==0,"disjoint root remains empty");
        check(!request.ContainsKey("query")&&!request.ContainsKey("source")&&!request.ContainsKey("profile"),"similarity cannot route into text or another profile");
        try{SimilaritySearch.Request(0,"","all",0,scope);check(false,"invalid similarity origin");}
        catch(ArgumentOutOfRangeException){check(true,"invalid similarity origin rejected");}
        foreach(var status in new[]{"unindexed","unsupported_profile","unknown"})
            check(SimilaritySearch.Guidance(status).Length>0,"similarity fallback guidance "+status);
        var parsed=Protocol.ParseSearch("""{"total":1,"items":[{"id":8,"title":"near.png","kind":"image","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.98,"similarity_origin_id":7}],"score_kind":"cosine","similarity_status":"ready"}""");
        check(parsed.SimilarityStatus=="ready"&&parsed.Items[0].SimilarityOriginId==7,"reflection-free item-origin response");
        check(parsed.Items[0].AIEvidence.Contains("起点の画像・表紙")&&parsed.Items[0].AIEvidence.Contains("0.980"),"visual origin reason and cosine shown");
        check(Protocol.ParseSearch("""{"total":0,"items":[],"similarity_status":"unindexed"}""").SimilarityStatus=="unindexed","unindexed response stays empty");
        check(Protocol.ParseSearch("""{"total":0,"items":[]}""").SimilarityStatus=="","old search response remains compatible");

        var calls=0;var blocked=false;
        using var api=new LibraryApi(new Handler(async(message,token)=>
        {
            calls++;
            if(message.RequestUri!.AbsolutePath=="/api/session")return Json("""{"mode":"production","token":"test-token"}""");
            check(message.RequestUri.AbsoluteUri=="http://127.0.0.1:8769/api/library/ai/similar"&&message.Method==HttpMethod.Post,"fixed local similarity route");
            check(message.Headers.GetValues("Origin").Single()=="http://127.0.0.1:8769"&&message.Headers.GetValues("X-Aredoko-Token").Single()=="test-token","similarity retains session and origin");
            var body=JsonNode.Parse(await message.Content!.ReadAsStringAsync(token))!;
            check(body["item_id"]!.GetValue<int>()==7&&body["view"]!.GetValue<string>()=="favorites","LibraryApi sends clicked item and filters");
            if(blocked)await Task.Delay(Timeout.Infinite,token);
            return Json("""{"total":0,"items":[],"similarity_status":"unindexed"}""");
        }));
        await api.ConnectAsync();
        check((await api.SimilarAsync(7,"image","favorites",0,scope,1,CancellationToken.None)).SimilarityStatus=="unindexed","LibraryApi parses fallback");
        blocked=true;using var cancel=new CancellationTokenSource();
        var pending=api.SimilarAsync(7,"image","favorites",0,scope,1,cancel.Token);cancel.Cancel();
        try{await pending;check(false,"cancel pending similarity");}
        catch(OperationCanceledException){check(true,"pending similarity can be cancelled");}
        check(calls==3,"similarity never requests preview or inference endpoints");
    }
    private static HttpResponseMessage Json(string text)=>new(HttpStatusCode.OK) {Content=new StringContent(text,Encoding.UTF8,"application/json")};
    private sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request,cancellationToken);
    }
}
