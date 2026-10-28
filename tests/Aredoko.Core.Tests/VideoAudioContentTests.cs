using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class VideoAudioContentTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var status=new JsonObject{["supported"]=true,["available"]=true,["state"]="idle",["resident"]=false,
            ["candidate_total"]=0,["target"]=0,["processed"]=0,["indexed"]=0,["reused"]=0,["unavailable"]=0,["remaining_candidates"]=0,["source_kind"]="audio"};
        var operations=new List<string>();
        using var handler=new Stub(async request=>
        {
            check(request.Headers.Contains("X-Aredoko-Token"),"video audio keeps authentication");
            var path=request.RequestUri!.AbsolutePath;
            check(path.StartsWith("/api/library/video-audio-ai/"),"video audio uses its explicit API");
            operations.Add(path.Split('/')[^1]);
            if(request.Method==HttpMethod.Post)
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
                if(path.EndsWith("/start"))
                {
                    check(body["consent"]!.GetValue<bool>()&&body["limit"]!.GetValue<int>()==128,"video audio start is explicit and bounded");
                    check(body["conditions"]!["root_ids"]![0]!.GetValue<int>()==7&&body["conditions"]!["shelf_ids"]![0]!.GetValue<long>()==11,"video audio preparation preserves folder and shelf scope");
                    status["source_kind"]="video";status["state"]="planning";
                }
                else{check(body.Count==0,"video audio cancel has empty body");status["state"]="cancelling";}
            }
            return Reply(status);
        });
        using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        http.DefaultRequestHeaders.Add("X-Aredoko-Token","generated");
        var client=new AudioContentClient(http,videoAudio:true);
        check(client.SourceKind=="video"&&(await client.StatusAsync()).SourceKind=="audio","video audio status exposes shared owner rather than inventing own job");
        var conditions=new JsonObject{["root_ids"]=new JsonArray(7),["shelf_ids"]=new JsonArray(JsonValue.Create(11L)),["view"]="favorites"};
        check((await client.StartAsync(conditions)).SourceKind=="video","video audio starts the selected source");
        check((await client.CancelAsync()).State=="cancelling","video audio cancellation is visible");
        check(operations.SequenceEqual(new[]{"status","start","cancel"}),"video audio client performs only requested operations");

        var method=SearchMethod.FromIndex(9);
        check(method.IsAI&&method.IsVideoAudioContent&&method.IsDirectContent&&!method.IsAudioContent&&!method.IsVideoContent,"video audio appends a separate search method");
        var search=ResultSearchConditions.Create("雨と話し声","video","favorites",method,null,[7],shelfIds:[11])!;
        check(search["mode"]!.GetValue<string>()=="video-audio-direct"&&!search.ContainsKey("scope")&&!search.ContainsKey("kind"),"video audio bypasses visual namespace and fixes media kind");
        check(search["root_ids"]![0]!.GetValue<int>()==7&&search["shelf_ids"]![0]!.GetValue<long>()==11&&search["view"]!.GetValue<string>()=="favorites","video audio query preserves all library filters");
        check(ResultSearchConditions.Create(" ","video","all",method,null,null) is null,"empty video audio query does not infer");
        var badKind=false;try{ResultSearchConditions.Create("雨","audio","all",method,null,null);}catch(ArgumentException){badKind=true;}
        check(badKind,"video audio cannot search audio files by mistake");

        var item=JsonNode.Parse("""{"id":2,"title":"generated.mp4","kind":"video","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.8,"audio_match_ms":30000,"audio_match_end_ms":31250,"audio_match_source":"video-audio","audio_match_contract":"direct-audio-window:v1"}""")!.AsObject();
        var row=Protocol.ParseItem(item.ToJsonString());
        check(row.AudioMatchEndMs==31250&&row.AudioMatchContract=="direct-audio-window:v1"&&row.AIEvidence.Contains("動画内の音声一致（0:30–0:31.25）")&&!row.AIEvidence.Contains("発話"),"video audio shows exact PCM evidence without invented transcript");
        check(VideoPlayerPolicy.MatchStartMs(row)==30000,"video player starts at the audio match");
        var legacy=Protocol.ParseItem("""{"id":3,"title":"legacy.mp4","kind":"video","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.8,"video_match_ms":1500}""");
        check(VideoPlayerPolicy.MatchStartMs(legacy)==1500&&legacy.AIEvidence.Contains("動画フレーム一致"),"legacy representative frame seek remains unchanged");
        foreach(var change in new Action<JsonObject>[] {
            value=>value["kind"]="audio",value=>value["audio_match_source"]="direct-audio",value=>value["audio_match_source"]="unknown",
            value=>value.Remove("audio_match_source"),value=>value.Remove("audio_match_contract"),value=>value["audio_match_contract"]="other",
            value=>value.Remove("audio_match_ms"),value=>value["audio_match_ms"]=-1,value=>value["audio_match_ms"]="30000",
            value=>value.Remove("audio_match_end_ms"),value=>value["audio_match_end_ms"]=30000,value=>value["audio_match_end_ms"]=60001,
            value=>value["audio_match_end_ms"]=86400001,value=>value["audio_match_end_ms"]=true,value=>value.Remove("semantic_score"),
            value=>value["similarity_origin_id"]=7,value=>value["origin_match_ms"]=0,value=>value["video_match_ms"]=0})
        {
            var bad=item.DeepClone().AsObject();change(bad);var rejected=false;
            try{Protocol.ParseItem(bad.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid video audio kind, source, interval, score or conflicting evidence is rejected");
        }
        var reply=new JsonObject{["total"]=1,["source"]="video-audio-direct",["score_kind"]="cosine",["items"]=new JsonArray(item.DeepClone())};
        check(Protocol.ParseSearch(reply.ToJsonString()).Items[0].AudioMatchSource=="video-audio","video audio response retains its evidence source");
        reply["items"]![0]!.AsObject().Remove("audio_match_source");reply["items"]![0]!.AsObject().Remove("audio_match_contract");reply["items"]![0]!.AsObject().Remove("audio_match_end_ms");
        var missing=false;try{Protocol.ParseSearch(reply.ToJsonString());}catch(InvalidDataException){missing=true;}
        check(missing,"video audio envelope cannot downgrade to legacy audio evidence");

        var similarSearch=ResultSearchConditions.Create("ignored","video","favorites",SearchMethod.FromIndex(0),null,[7],originId:9,shelfIds:[11],directVideoAudioSimilarity:true)!;
        check(similarSearch["mode"]!.GetValue<string>()=="video-audio-similar"&&similarSearch["item_id"]!.GetValue<int>()==9&&!similarSearch.ContainsKey("scope"),"video audio similarity uses cached PCM mode without visual scope");
        check(similarSearch["root_ids"]![0]!.GetValue<int>()==7&&similarSearch["shelf_ids"]![0]!.GetValue<long>()==11,"video audio similarity keeps folder and shelf scope");
        var ambiguous=false;
        try{ResultSearchConditions.Create("","video","all",method,null,null,originId:9,directVideoSimilarity:true,directVideoAudioSimilarity:true);}catch(ArgumentException){ambiguous=true;}
        check(ambiguous,"ambiguous visual and audio video similarity is rejected");
        var candidate=item.DeepClone().AsObject();candidate["similarity_origin_id"]=9;candidate["origin_match_ms"]=0;candidate["origin_match_end_ms"]=2200;
        var similarReply=new JsonObject{["mode"]="video-audio-similar",["origin_id"]=9,["origin_kind"]="video",["origin_revision"]=new string('a',64),
            ["profile"]="generated-audio-profile",["source"]="video-audio-direct",["score_kind"]="cosine",["similarity_status"]="ready",["page"]=0,["limit"]=60,
            ["total"]=1,["search_complete"]=true,["search_candidate_total"]=1,["indexed_total"]=1,["items"]=new JsonArray(candidate.DeepClone())};
        var compared=SimilaritySearch.Parse(similarReply.ToJsonString(),9,0,directVideoAudio:true);
        check(compared.Items[0].AIEvidence.Contains("起点 0:00–0:02.2 → 候補 0:30–0:31.25")&&VideoPlayerPolicy.MatchStartMs(compared.Items[0])==30000,"video audio similarity preserves both intervals and seeks candidate audio");
        check(SimilaritySearch.Guidance("unindexed","video",directVideoAudio:true).Contains("動画内の音声"),"unindexed video audio gives its own preparation guidance");
        foreach(var change in new Action<JsonObject>[] {
            value=>value["source"]="audio-direct",value=>value["mode"]="video-similar",value=>value["origin_kind"]="audio",
            value=>value["origin_revision"]="invalid",value=>value["items"]![0]!["origin_match_end_ms"]=30001,
            value=>value["items"]![0]!.AsObject().Remove("origin_match_end_ms"),value=>value["items"]![0]!["similarity_origin_id"]=8,
            value=>value["items"]![0]!["id"]=9,value=>value["items"]![0]!["semantic_score"]=2})
        {
            var bad=similarReply.DeepClone().AsObject();change(bad);var rejected=false;
            try{SimilaritySearch.Parse(bad.ToJsonString(),9,0,directVideoAudio:true);}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid video audio similarity namespace, interval, identity or score is rejected");
        }
        var accidentalLegacy=false;
        try{SimilaritySearch.Parse(similarReply.ToJsonString(),9,0);}catch(InvalidDataException){accidentalLegacy=true;}
        check(accidentalLegacy,"video audio results cannot be read as legacy visual similarity");

        // Even an empty range must validate its namespace. The condition identity
        // alone does not prove that the server returned video audio results.
        string responseSource="video-audio-direct";
        using var resultsHandler=new Stub(async request=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
            if(request.RequestUri!.AbsolutePath.EndsWith("/close"))return Reply(new(){["closed"]=true});
            var response=new JsonObject{["session_id"]=body["session_id"]!.DeepClone(),["conditions"]=search.DeepClone(),["state"]="ready",["total"]=0};
            if(request.RequestUri.AbsolutePath.EndsWith("/create")){response["range_limit"]=120;response["idle_seconds"]=900;}
            else{response["offset"]=0;response["limit"]=60;response["items"]=new JsonArray();response["source"]=responseSource;}
            return Reply(response);
        });
        using var resultsHttp=new HttpClient(resultsHandler){BaseAddress=http.BaseAddress};
        await using var session=await new ResultSessionClient(resultsHttp).CreateAsync(search,CancellationToken.None);
        check((await session.RangeAsync(0,60,CancellationToken.None)).Total==0,"empty video audio range accepts correct namespace");
        responseSource="audio-direct";var wrong=false;
        try{await session.RangeAsync(0,60,CancellationToken.None);}catch(InvalidDataException){wrong=true;}
        check(wrong,"empty video audio range rejects the audio-file namespace");

        using var comparedHandler=new Stub(async request=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
            if(request.RequestUri!.AbsolutePath.EndsWith("/close"))return Reply(new(){["closed"]=true});
            var response=similarReply.DeepClone().AsObject();response["session_id"]=body["session_id"]!.DeepClone();response["conditions"]=similarSearch.DeepClone();response["state"]="ready";
            if(request.RequestUri.AbsolutePath.EndsWith("/create")){response["range_limit"]=120;response["idle_seconds"]=900;}
            else{response["offset"]=0;response["limit"]=60;}
            return Reply(response);
        });
        using var comparedHttp=new HttpClient(comparedHandler){BaseAddress=http.BaseAddress};
        await using var comparedSession=await new ResultSessionClient(comparedHttp).CreateAsync(similarSearch,CancellationToken.None);
        check((await comparedSession.RangeAsync(0,60,CancellationToken.None)).Items[0].OriginMatchEndMs==2200,"frozen video audio similarity routes through strict origin validation");
    }
    private static HttpResponseMessage Reply(JsonObject body)=>new(HttpStatusCode.OK)
    {Content=new ByteArrayContent(Encoding.UTF8.GetBytes(body.ToJsonString()))};
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>send(request);}
}
