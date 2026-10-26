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
        check(SimilaritySearch.CanStart(new MediaRow {Id=8,Kind="video",Availability="present"}),"video similarity context entry supported");
        check(SimilaritySearch.CanStart(new MediaRow {Id=8,Kind="audio",Availability="present"}),"audio similarity context entry supported");
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
        {
            check(SimilaritySearch.Guidance(status).Length>0,"similarity fallback guidance "+status);
            check(SimilaritySearch.Guidance(status,"video").Length>0,"video similarity fallback guidance "+status);
            check(SimilaritySearch.Guidance(status,"audio").Length>0,"audio similarity fallback guidance "+status);
        }
        var parsed=Protocol.ParseSearch("""{"total":1,"items":[{"id":8,"title":"near.png","kind":"image","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.98,"similarity_origin_id":7}],"score_kind":"cosine","similarity_status":"ready"}""");
        check(parsed.SimilarityStatus=="ready"&&parsed.Items[0].SimilarityOriginId==7,"reflection-free item-origin response");
        check(parsed.Items[0].AIEvidence.Contains("起点の画像・表紙")&&parsed.Items[0].AIEvidence.Contains("0.980"),"visual origin reason and cosine shown");
        var videoParsed=Protocol.ParseSearch("""{"total":1,"origin_id":7,"origin_kind":"video","items":[{"id":9,"title":"clip.mp4","kind":"video","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.95,"similarity_origin_id":7,"video_match_ms":2500,"origin_match_ms":1000}],"score_kind":"cosine","similarity_status":"ready"}""");
        check(videoParsed.OriginKind=="video"&&videoParsed.Items[0].VideoMatchMs==2500&&videoParsed.Items[0].OriginMatchMs==1000,"video similarity origin and candidate match ms parsed");
        check(videoParsed.Items[0].AIEvidence.Contains("動画一致（起点 0:01 → 候補 0:02）")&&videoParsed.Items[0].AIEvidence.Contains("0.950"),"video-to-video similarity evidence shows both timepoints");
        check(Protocol.ParseSearch("""{"total":0,"items":[],"similarity_status":"unindexed"}""").SimilarityStatus=="unindexed","unindexed response stays empty");
        check(Protocol.ParseSearch("""{"total":0,"items":[]}""").SimilarityStatus=="","old search response remains compatible");

        var calls=0;var blocked=false;
        using var api=new LibraryApi(new Handler(async(message,token)=>
        {
            calls++;
            if(message.RequestUri!.AbsolutePath=="/api/session")return Json("""{"mode":"production","token":"test-token"}""");
            if(message.RequestUri.AbsolutePath=="/api/library/ai/searches/prepare")return Json("""{"request_id":"0123456789abcdef0123456789abcdef","expires_in_seconds":60}""");
            if(message.RequestUri.AbsolutePath=="/api/library/ai/searches/cancel")return Json("""{"request_id":"0123456789abcdef0123456789abcdef","cancel_requested":true}""");
            check(message.RequestUri.AbsoluteUri=="http://127.0.0.1:8769/api/library/ai/similar"&&message.Method==HttpMethod.Post,"fixed local similarity route");
            check(message.Headers.GetValues("Origin").Single()=="http://127.0.0.1:8769"&&message.Headers.GetValues("X-Aredoko-Token").Single()=="test-token","similarity retains session and origin");
            var body=JsonNode.Parse(await message.Content!.ReadAsStringAsync(token))!;
            check(body["item_id"]!.GetValue<int>()==7&&body["view"]!.GetValue<string>()=="favorites","LibraryApi sends clicked item and filters");
            if(blocked)await Task.Delay(Timeout.Infinite,token);
            var result=JsonNode.Parse(Response())!.AsObject();result["request_id"]=body["request_id"]!.GetValue<string>();return Json(result.ToJsonString());
        }));
        await api.ConnectAsync();
        check((await api.SimilarAsync(7,"image","favorites",0,scope,1,CancellationToken.None)).SimilarityStatus=="unindexed","LibraryApi parses fallback");
        blocked=true;using var cancel=new CancellationTokenSource();
        var pending=api.SimilarAsync(7,"image","favorites",0,scope,1,cancel.Token);cancel.Cancel();
        try{await pending;check(false,"cancel pending similarity");}
        catch(OperationCanceledException){check(true,"pending similarity can be cancelled");}
        check(calls==6,"similarity uses prepare/query/owned cancel only, never preview or indexing endpoints");
        check(SimilaritySearch.Parse(Response(),7,0).Total==0,"strict similarity fallback contract");
        var visual=JsonNode.Parse(Response())!.AsObject();visual["similarity_status"]="ready";visual["total"]=1;
        visual["items"]=JsonNode.Parse("""[{"id":8,"title":"near.png","kind":"image","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.98,"similarity_origin_id":7}]""");
        check(SimilaritySearch.Parse(visual.ToJsonString(),7,0).Items[0].Id==8,"strict visual candidate contract");
        var videoCand=visual.DeepClone().AsObject();
        videoCand["items"]=JsonNode.Parse("""[{"id":9,"title":"clip.mp4","kind":"video","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.95,"similarity_origin_id":7,"video_match_ms":1500}]""");
        var candRow=SimilaritySearch.Parse(videoCand.ToJsonString(),7,0).Items[0];
        check(candRow.Id==9&&candRow.VideoMatchMs==1500&&candRow.AIEvidence.Contains("動画フレーム一致（0:01）"),"strict video candidate contract accepts video kind and formats evidence");
        var videoToVideo=videoCand.DeepClone().AsObject();
        videoToVideo["items"]![0]!["origin_match_ms"]=3200;
        var v2vRow=SimilaritySearch.Parse(videoToVideo.ToJsonString(),7,0).Items[0];
        check(v2vRow.OriginMatchMs==3200&&v2vRow.AIEvidence.Contains("動画一致（起点 0:03 → 候補 0:01）"),"video-to-video similarity evidence shows both timepoints");
        var videoToImage=visual.DeepClone().AsObject();
        videoToImage["items"]![0]!["origin_match_ms"]=5000;
        var v2iRow=SimilaritySearch.Parse(videoToImage.ToJsonString(),7,0).Items[0];
        check(v2iRow.OriginMatchMs==5000&&v2iRow.AIEvidence.Contains("起点の動画（0:05）に似た候補"),"video-to-image similarity evidence shows origin timepoint");
        var audioCand=visual.DeepClone().AsObject();
        audioCand["origin_kind"]="audio";
        audioCand["source"]="acoustic";
        audioCand["items"]=JsonNode.Parse("""[{"id":9,"title":"track.mp3","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.93,"similarity_origin_id":7,"audio_match_ms":45000,"origin_match_ms":12000}]""");
        var audioRow=SimilaritySearch.Parse(audioCand.ToJsonString(),7,0).Items[0];
        check(SimilaritySearch.Guidance("unindexed","audio").Contains("音響特徴") && SimilaritySearch.Guidance("unindexed","audio").Contains("文章から探すための索引とは別") && SimilaritySearch.Guidance("unindexed","audio").Contains("音声の内容検索"),"audio similarity guidance distinguishes acoustic features from the direct content index");
        check(SimilaritySearch.Guidance("unsupported_profile","audio").Contains("ファイル名・タグ") && !SimilaritySearch.Guidance("unsupported_profile","audio").Contains("モデルを選ぶ"),"audio guidance does not promise an unavailable audio extraction model");
        check(audioRow.Id==9&&audioRow.AudioMatchMs==45000&&audioRow.OriginMatchMs==12000&&audioRow.AIEvidence.Contains("音声・音楽一致（起点 0:12 → 候補 0:45）"),"audio similarity parses candidate and origin match ms");
        var directAudio=audioCand.DeepClone().AsObject();directAudio["mode"]="audio-similar";directAudio["source"]="audio-direct";
        directAudio["items"]![0]!["audio_match_source"]="direct-audio";
        check(SimilaritySearch.Parse(directAudio.ToJsonString(),7,0,directAudio:true).Items[0].OriginMatchMs==12000,"direct audio similarity preserves both time anchors");
        check(SimilaritySearch.Guidance("unindexed","audio",true).Contains("音声の内容検索"),"direct audio missing-index guidance reaches preparation");
        var rejectedDirect=false;
        try{SimilaritySearch.Parse(directAudio.ToJsonString(),7,0);}catch(InvalidDataException){rejectedDirect=true;}
        check(rejectedDirect,"legacy similarity does not accept a direct-audio namespace");
        directAudio["items"]![0]!["origin_match_ms"]=null;rejectedDirect=false;
        try{SimilaritySearch.Parse(directAudio.ToJsonString(),7,0,directAudio:true);}catch(InvalidDataException){rejectedDirect=true;}
        check(rejectedDirect,"direct audio similarity requires both time anchors");
        var audioCandOnly=audioCand.DeepClone().AsObject();
        audioCandOnly["items"]![0]!["origin_match_ms"]=null;
        var aCandRow=SimilaritySearch.Parse(audioCandOnly.ToJsonString(),7,0).Items[0];
        check(aCandRow.AIEvidence.Contains("音声一致（0:45）"),"audio similarity candidate-only timestamp");
        var audioOriginOnly=audioCand.DeepClone().AsObject();
        audioOriginOnly["items"]![0]!["audio_match_ms"]=null;
        var aOrigRow=SimilaritySearch.Parse(audioOriginOnly.ToJsonString(),7,0).Items[0];
        check(aOrigRow.AIEvidence.Contains("起点の音声（0:12）に似た候補"),"audio similarity origin-only timestamp");
        var audioNoMs=audioCand.DeepClone().AsObject();
        audioNoMs["items"]![0]!["audio_match_ms"]=null;
        audioNoMs["items"]![0]!["origin_match_ms"]=null;
        var aNoMsRow=SimilaritySearch.Parse(audioNoMs.ToJsonString(),7,0).Items[0];
        check(aNoMsRow.AIEvidence.Contains("起点の音声・曲に似た候補"),"audio similarity without timestamps evidence");
        var badVisualInAudio=audioCand.DeepClone().AsObject();
        badVisualInAudio["items"]![0]!["kind"]="image";
        Reject(check,badVisualInAudio.ToJsonString(),"visual candidate in audio similarity rejected");
        var badAudioInVisual=visual.DeepClone().AsObject();
        badAudioInVisual["items"]![0]!["kind"]="audio";
        Reject(check,badAudioInVisual.ToJsonString(),"audio candidate in visual similarity rejected");
        var large=visual.DeepClone().AsObject();large["total"]=50001;large["page"]=833;
        large["search_complete"]=true;large["search_candidate_total"]=50002;large["indexed_total"]=50001;
        large["coverage_limit"]=10000;
        var tail=new JsonArray();
        for(var i=0;i<21;i++){var item=visual["items"]![0]!.DeepClone();item["id"]=1000+i;tail.Add(item);}
        large["items"]=tail;
        var largeResult=SimilaritySearch.Parse(large.ToJsonString(),7,833);
        check(largeResult.Total==50001&&largeResult.Items.Count==21&&largeResult.SearchComplete&&largeResult.CoverageLimit is null,
              "complete similarity above 10k accepts its final page with honest counts");
        var block=visual.DeepClone().AsObject();block["total"]=125;block["limit"]=120;block["page"]=0;
        var blockItems=new JsonArray();
        for(var i=0;i<120;i++){var candidate=visual["items"]![0]!.DeepClone();candidate["id"]=1000+i;blockItems.Add(candidate);}
        block["items"]=blockItems;
        check(SimilaritySearch.Parse(block.ToJsonString(),7,0,120,0).Items.Count==120,"session similarity accepts bounded 120-item range with strict origin validation");
        block["items"]![0]!["similarity_origin_id"]=9;
        var blockRejected=false;
        try{SimilaritySearch.Parse(block.ToJsonString(),7,0,120,0);}catch(InvalidDataException){blockRejected=true;}
        check(blockRejected,"session similarity keeps origin validation across range adaptation");
        foreach(var change in new (string Field,JsonNode? Value)[]{("id",7),("similarity_origin_id",9),("kind","audio"),("semantic_score",2),("semantic_score",null)})
        {
            var broken=visual.DeepClone().AsObject();broken["items"]![0]![change.Field]=change.Value;
            Reject(check,broken.ToJsonString(),"invalid visual candidate "+change.Field);
        }
        foreach(var field in new[]{"origin_id","origin_revision","profile","mode","source","score_kind","page","limit","similarity_status"})
        {
            var broken=JsonNode.Parse(Response())!.AsObject();broken.Remove(field);
            Reject(check,broken.ToJsonString(),"missing similarity field "+field);
        }
        foreach(var change in new (string Field,JsonNode? Value)[]{("origin_id",8),("page",1),("mode","semantic"),("source","text"),("origin_revision","bad"),("profile",""),("total",1),("similarity_status","unexpected"),("origin_kind","audio")})
        {
            var broken=JsonNode.Parse(Response())!.AsObject();broken[change.Field]=change.Value;
            Reject(check,broken.ToJsonString(),"invalid similarity field "+change.Field);
        }
        using var oversized=new LibraryApi(new Handler((_,_)=>Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
            Content=new ByteArrayContent(new byte[SimilaritySearch.MaxResponseBytes+1]) {Headers={ContentType=new("application/json")}}
        })));
        try{await oversized.SimilarAsync(7,"","all",0,scope,null,CancellationToken.None);check(false,"oversized response");}
        catch(InvalidDataException){check(true,"oversized response rejected before JSON parsing");}
    }
    private static string Response()=>"""{"total":0,"items":[],"similarity_status":"unindexed","origin_id":7,"origin_revision":"0000000000000000000000000000000000000000000000000000000000000000","profile":"test-profile","page":0,"limit":60,"mode":"similar","source":"cover","score_kind":"cosine"}""";
    private static void Reject(Action<bool,string> check,string text,string name)
    {
        try{SimilaritySearch.Parse(text,7,0);check(false,name);}
        catch(InvalidDataException){check(true,name);}
    }
    private static HttpResponseMessage Json(string text)=>new(HttpStatusCode.OK) {Content=new StringContent(text,Encoding.UTF8,"application/json")};
    private sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request,cancellationToken);
    }
}
