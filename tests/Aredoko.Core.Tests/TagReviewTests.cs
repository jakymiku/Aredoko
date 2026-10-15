using Aredoko.Core;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;

static class TagReviewTests
{
    static readonly string Revision=new('a',64);
    static string History()=>$$"""
    {"item_id":7,"source_revision":"{{Revision}}","available":true,"reason":"","next_before":null,"batches":[
      {"id":4000000000,"item_id":7,"source_revision":"{{Revision}}","stale":false,
       "evidence":{"item_id":7,"revision":"{{Revision}}","kind":"cover","page":0},
       "producer":{"model":"test-only","model_revision":"fixed","adapter":"fixture","version":"1","preprocessing":"cover"},
       "proposals":[{"id":5000000000,"tag":"候補","explanation":"先頭ページだけの根拠","page":0,"state":"pending","accepted_tag":null,"version":0}]}]}
    """;
    static HttpResponseMessage Json(string text)=>new(HttpStatusCode.OK){Content=new StringContent(text,Encoding.UTF8,"application/json")};
    sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> handle):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>handle(request,cancellation);}
    public static async Task Run(Action<bool,string> check)
    {
        var parsed=TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(History()),7);
        check(parsed.Batches[0].Candidates[0].Id==5000000000&&parsed.Batches[0].Id==4000000000,"tag IDs preserve Int64");
        check(parsed.Batches[0].Candidates[0].StateLabel=="未承認"&&parsed.Batches[0].EvidenceKind=="cover","pending and cover provenance remain explicit");
        foreach(var field in new[]{"item_id","source_revision","producer","evidence","proposals"})
        {
            var broken=JsonNode.Parse(History())!;broken["batches"]![0]!.AsObject().Remove(field);
            try{TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(broken.ToJsonString()),7);check(false,"missing tag field "+field);}
            catch(InvalidDataException){check(true,"missing tag field rejected "+field);}
        }
        var stale=JsonNode.Parse(History())!;stale["source_revision"]=new string('b',64);stale["batches"]![0]!["stale"]=true;
        check(TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(stale.ToJsonString()),7).Batches[0].Stale,"changed physical source marks candidate stale");
        var duplicate=JsonNode.Parse(History())!;duplicate["batches"]![0]!["proposals"]!.AsArray().Add(duplicate["batches"]![0]!["proposals"]![0]!.DeepClone());
        try{TagReviewProtocol.Parse(Encoding.UTF8.GetBytes(duplicate.ToJsonString()),7);check(false,"duplicate proposal");}catch(InvalidDataException){check(true,"duplicate proposal rejected");}
        var fault="";var calls=0;
        using var api=new LibraryApi(new Handler(async(request,cancellation)=>
        {
            calls++;if(request.RequestUri!.AbsolutePath=="/api/session")return Json("""{"mode":"production","token":"fixture"}""");
            check(request.Headers.GetValues("X-Aredoko-Token").Single()=="fixture"&&request.Headers.GetValues("Origin").Single()=="http://127.0.0.1:8769","tag client retains authenticated local session");
            if(fault=="cancel")await Task.Delay(Timeout.Infinite,cancellation);
            if(fault=="size")return new(HttpStatusCode.OK){Content=new ByteArrayContent(new byte[TagReviewProtocol.MaxJsonBytes+1])};
            if(fault=="mime")return new(HttpStatusCode.OK){Content=new StringContent(History(),Encoding.UTF8,"text/html")};
            if(request.RequestUri.AbsolutePath.EndsWith("/review"))
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync(cancellation))!;
                check(body["proposal_id"]!.GetValue<long>()==5000000000&&body["tag"]!.GetValue<string>()=="修正タグ","review serializes exact candidate and edited tag");
                return Json("""{"proposal_id":5000000000,"version":1,"state":"accepted","accepted_tag":"修正タグ"}""");
            }
            check(request.RequestUri.PathAndQuery=="/api/library/tag-suggestions/7?limit=10","bounded item history route");return Json(History());
        }));
        await api.ConnectAsync();await api.TagReviews.HistoryAsync(7,null,CancellationToken.None);
        await api.TagReviews.ReviewAsync(7,parsed.Batches[0].Candidates[0],true," 修正タグ ",CancellationToken.None);
        foreach(var mode in new[]{"size","mime"})
        {fault=mode;try{await api.TagReviews.HistoryAsync(7,null,CancellationToken.None);check(false,"tag response "+mode);}catch(InvalidDataException){check(true,"tag response rejects "+mode);}}
        fault="cancel";using var cancel=new CancellationTokenSource();var pending=api.TagReviews.HistoryAsync(7,null,cancel.Token);cancel.Cancel();
        try{await pending;check(false,"tag cancellation");}catch(OperationCanceledException){check(true,"tag read cancellation is distinct from timeout");}
        var before=calls;try{await api.TagReviews.EvidenceAsync(7,"bad",CancellationToken.None);check(false,"invalid evidence revision");}catch(ArgumentException){check(calls==before,"invalid evidence revision sends no request");}
        check(!TagReviewProtocol.CanOpen(new(){Location="video.mp4",Availability="present"})&&TagReviewProtocol.CanOpen(new(){Location="book.CBZ",Availability="present"}),"review entry only for supported present image and archive");
    }
}
