using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class VideoContentTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var status=new JsonObject{["supported"]=true,["available"]=true,["state"]="idle",["resident"]=false,
            ["candidate_total"]=3,["target"]=2,["processed"]=0,["indexed"]=0,["reused"]=1,["unavailable"]=0,["remaining_candidates"]=0};
        using var handler=new Stub(async request=>
        {
            check(request.Headers.Contains("X-Aredoko-Token"),"video requests retain session authentication");
            check(request.RequestUri!.AbsolutePath.StartsWith("/api/library/video-ai/"),"video requests use their own API");
            if(request.Method==HttpMethod.Post)
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
                if(request.RequestUri.AbsolutePath.EndsWith("start"))
                {
                    check(body["consent"]!.GetValue<bool>()&&body["limit"]!.GetValue<int>()==128,"video start is explicit and bounded");
                    check(body["conditions"]!["root_ids"]![0]!.GetValue<int>()==7,"video start retains selected roots");
                    status["state"]="running";
                }
                else{check(body.Count==0,"video cancel uses empty command");status["state"]="cancelling";}
            }
            return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(status.ToJsonString(),Encoding.UTF8,"application/json")};
        });
        using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        http.DefaultRequestHeaders.Add("X-Aredoko-Token","generated");
        var client=new VideoContentClient(http);
        check(!(await client.StatusAsync()).Busy,"video idle status is not active");
        check((await client.StartAsync(new(){["root_ids"]=new JsonArray(7)})).Busy,"video index status starts polling");
        check((await client.CancelAsync()).State=="cancelling","video cancellation is visible");
        foreach(var change in new Action<JsonObject>[] {value=>value["target"]=-1,value=>value["processed"]=1001,
            value=>value["available"]="true",value=>value["indexed"]=true,value=>value["state"]="future"})
        {
            var bad=status.DeepClone().AsObject();change(bad);var rejected=false;
            try{VideoContentStatus.Parse(bad.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"video malformed status rejected");
        }
        var method=SearchMethod.FromIndex(8);
        check(method.IsAI&&method.IsVideoContent,"video search appends its index without replacing audio");
        var conditions=ResultSearchConditions.Create("海の場面","video","favorites",method,null,[7],shelfIds:[9]);
        check(conditions!["mode"]!.GetValue<string>()=="video-direct"&&!conditions.ContainsKey("scope"),"video content uses its own namespace");
        check(conditions["root_ids"]![0]!.GetValue<int>()==7&&conditions["shelf_ids"]![0]!.GetValue<long>()==9,"video search retains root and shelf filters");
        check(ResultSearchConditions.Create("","video","all",method,null,null) is null,"empty video query does not start inference");
        var badKind=false;try{ResultSearchConditions.Create("海","audio","all",method,null,null);}catch(ArgumentException){badKind=true;}
        check(badKind,"video search rejects other media kinds");
        var similar=ResultSearchConditions.Create("ignored","video","favorites",SearchMethod.FromIndex(0),null,[7],originId:9,shelfIds:[11],directVideoSimilarity:true)!;
        check(similar["mode"]!.GetValue<string>()=="video-similar"&&similar["item_id"]!.GetValue<int>()==9,"direct similarity uses video namespace");
        check(similar["root_ids"]![0]!.GetValue<int>()==7&&similar["shelf_ids"]![0]!.GetValue<long>()==11&&!similar.ContainsKey("scope"),"video similarity retains filters without image scope");
        var both=false;try{ResultSearchConditions.Create("","video","all",method,null,null,originId:9,directAudioSimilarity:true,directVideoSimilarity:true);}catch(ArgumentException){both=true;}
        check(both,"ambiguous direct similarity rejected");

        var item=JsonNode.Parse("""{"id":2,"title":"clip.mp4","kind":"video","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.8,"video_match_ms":16000,"video_match_end_ms":17500,"video_match_source":"direct-video","video_match_contract":"direct-video-window:v1"}""")!.AsObject();
        var row=Protocol.ParseItem(item.ToJsonString());
        check(row.VideoMatchMs==16000&&row.VideoMatchEndMs==17500&&row.AIEvidence.Contains("動画の内容一致（0:16–0:17.5）"),"direct video shows exact interval, including fractional endpoint");
        var legacy=Protocol.ParseItem("""{"id":3,"title":"clip.mp4","kind":"video","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.8,"video_match_ms":1500}""");
        check(legacy.VideoMatchEndMs is null&&legacy.AIEvidence.Contains("動画フレーム一致（0:01）"),"legacy video frame evidence remains a point");
        item["similarity_origin_id"]=9;item["origin_match_ms"]=0;item["origin_match_end_ms"]=3300;
        row=Protocol.ParseItem(item.ToJsonString());
        check(row.OriginMatchEndMs==3300&&row.AIEvidence.Contains("起点 0:00–0:03.3 → 候補 0:16–0:17.5"),"direct similarity shows both intervals");
        foreach(var change in new Action<JsonObject>[] {
            value=>value["video_match_source"]="cover",value=>value["video_match_contract"]="other",
            value=>value.Remove("video_match_source"),value=>value.Remove("video_match_contract"),
            value=>value.Remove("video_match_end_ms"),value=>value["video_match_end_ms"]=16000,
            value=>value["video_match_end_ms"]=32001,value=>value["video_match_ms"]=-1,
            value=>value["video_match_end_ms"]=86400001,value=>value["origin_match_end_ms"]=0,
            value=>value.Remove("origin_match_end_ms"),value=>value["kind"]="audio"})
        {
            var bad=item.DeepClone().AsObject();change(bad);var rejected=false;
            try{Protocol.ParseItem(bad.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid direct video source, contract, kind or interval rejected");
        }
        var response=new JsonObject{["mode"]="video-similar",["origin_id"]=9,["origin_kind"]="video",
            ["origin_revision"]=new string('a',64),["profile"]="profile",["source"]="video-direct",["score_kind"]="cosine",
            ["similarity_status"]="ready",["page"]=0,["limit"]=60,["total"]=1,["items"]=new JsonArray(item.DeepClone())};
        check(SimilaritySearch.Parse(response.ToJsonString(),9,0,directVideo:true).Items[0].VideoMatchEndMs==17500,"strict similarity accepts direct video intervals");
        var wrongMode=false;try{SimilaritySearch.Parse(response.ToJsonString(),9,0);}catch(InvalidDataException){wrongMode=true;}
        check(wrongMode,"legacy similarity rejects direct video namespace");
        response["origin_kind"]="audio";var wrongOrigin=false;
        try{SimilaritySearch.Parse(response.ToJsonString(),9,0,directVideo:true);}catch(InvalidDataException){wrongOrigin=true;}
        check(wrongOrigin,"direct video similarity rejects non-video origin");
        check(SimilaritySearch.Guidance("unindexed","video",directVideo:true).Contains("動画の内容検索"),"missing video index points to preparation");

        // Frozen ranges must take the strict video-similar dispatcher, not the
        // generic row parser which has no expected origin or namespace.
        response["origin_kind"]="video";bool alterOrigin=false;
        using var sessionHandler=new Stub(async request=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
            var id=body["session_id"]!.GetValue<string>();
            JsonObject result;
            if(request.RequestUri!.AbsolutePath.EndsWith("create"))
                result=new(){["session_id"]=id,["state"]="ready",["conditions"]=similar.DeepClone(),["total"]=1,["range_limit"]=120,["idle_seconds"]=900};
            else if(request.RequestUri.AbsolutePath.EndsWith("range"))
            {
                result=response.DeepClone().AsObject();result["session_id"]=id;result["state"]="ready";
                result["conditions"]=similar.DeepClone();result["offset"]=0;result["limit"]=1;
                if(alterOrigin)result["origin_id"]=8;
            }
            else result=new(){["session_id"]=id};
            return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(result.ToJsonString(),Encoding.UTF8,"application/json")};
        });
        using var sessionHttp=new HttpClient(sessionHandler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        await using var session=await new ResultSessionClient(sessionHttp).CreateAsync(similar,CancellationToken.None);
        check((await session.RangeAsync(0,1,CancellationToken.None)).Items[0].VideoMatchEndMs==17500,"frozen direct video similarity range is accepted");
        alterOrigin=true;var badSession=false;
        try{await session.RangeAsync(0,1,CancellationToken.None);}catch(InvalidDataException){badSession=true;}
        check(badSession,"frozen direct video similarity range validates origin");
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>send(request);}
}
