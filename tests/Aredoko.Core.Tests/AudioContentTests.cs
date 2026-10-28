using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class AudioContentTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var status=new JsonObject{["supported"]=true,["available"]=true,["state"]="idle",["resident"]=false,
            ["candidate_total"]=3,["target"]=2,["processed"]=0,["indexed"]=0,["reused"]=1,["unavailable"]=0,["remaining_candidates"]=0};
        using var handler=new Stub(async request=>
        {
            check(request.Headers.Contains("X-Aredoko-Token"),"audio requests retain session authentication");
            if(request.Method==HttpMethod.Post)
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
                if(request.RequestUri!.AbsolutePath.EndsWith("start"))
                {
                    check(body["consent"]!.GetValue<bool>()&&body["limit"]!.GetValue<int>()==128,"audio start is explicit and bounded");
                    check(body["conditions"]!["root_ids"]![0]!.GetValue<int>()==7,"audio start retains selected roots");
                    status["state"]="running";
                }
                else{check(body.Count==0,"audio cancel uses empty command");status["state"]="cancelling";}
            }
            return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(status.ToJsonString(),Encoding.UTF8,"application/json")};
        });
        using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        http.DefaultRequestHeaders.Add("X-Aredoko-Token","generated");
        var client=new AudioContentClient(http);
        var failed=status.DeepClone().AsObject();failed["state"]="failed";failed["available"]=false;failed["error_code"]="audio_initialization_failed";
        check(AudioContentStatus.Parse(failed.ToJsonString()).Message.Contains("再起動"),"audio initialization failure explains restart even when model unavailable");
        check(!(await client.StatusAsync()).Busy,"audio idle status does not claim active job");
        check((await client.StartAsync(new(){["root_ids"]=new JsonArray(7)})).Busy,"audio index status starts polling");
        check((await client.CancelAsync()).State=="cancelling","audio cancellation is visible");
        check(AudioContentStatus.Parse(status.ToJsonString()).ItemProgress is null,"old audio server without item progress remains compatible");
        var working=status.DeepClone().AsObject();working["state"]="running";
        working["item_progress"]=new JsonObject{["item_id"]=9,["prepared_ms"]=30000,["total_ms"]=null,["prepared_windows"]=1,["phase"]="encoding"};
        var progress=AudioContentStatus.Parse(working.ToJsonString());
        check(progress.ItemProgress is {PreparedMs:30000,TotalMs:null,PreparedWindows:1}&&progress.Processed==0&&progress.Indexed==0,"audio prepared time never invents total or committed counts");
        check(progress.Message.Contains("0:30")&&progress.Message.Contains("総尺確認中")&&progress.Message.Contains("未保存"),"audio preparation explains unknown duration and pending save");
        check(progress.SourceKind=="audio","old audio status defaults to audio file source");
        var video=working.DeepClone().AsObject();video["source_kind"]="video";
        check(AudioContentStatus.Parse(video.ToJsonString()).Message.Contains("動画内の音声"),"shared audio owner identifies video audio jobs");
        check(progress.ItemProgress!.ItemTitle is null,"old audio progress without filename remains compatible");
        var named=working.DeepClone().AsObject();named["item_progress"]!["item_title"]="生成した音と動画🌟.mkv";
        check(AudioContentStatus.Parse(named.ToJsonString()).ItemProgress!.ItemTitle=="生成した音と動画🌟.mkv","audio progress retains its bounded display filename");
        foreach(var badTitle in new JsonNode?[]{JsonValue.Create("/private/file.mkv"),JsonValue.Create("bad\nname"),JsonValue.Create(new string('x',161)),JsonValue.Create(42)})
        {
            named["item_progress"]!["item_title"]=badTitle?.DeepClone();
            try{AudioContentStatus.Parse(named.ToJsonString());check(false,"invalid audio progress title rejected");}
            catch(InvalidDataException){check(true,"invalid audio progress title rejected");}
        }
        var saving=working.DeepClone().AsObject();saving["item_progress"]!["prepared_ms"]=31000;saving["item_progress"]!["prepared_windows"]=2;saving["item_progress"]!["total_ms"]=31000;saving["item_progress"]!["phase"]="saving";
        check(AudioContentStatus.Parse(saving.ToJsonString()).Message.Contains("保存しています"),"known audio EOF is still not committed before save");
        foreach(var change in new Action<JsonObject>[] {
            value=>value["item_progress"]=true,value=>value["item_progress"]!["item_id"]=0,
            value=>value["item_progress"]!["prepared_ms"]=-1,value=>value["item_progress"]!["prepared_ms"]=86400001,
            value=>value["item_progress"]!["total_ms"]=29999,value=>value["item_progress"]!["total_ms"]="31000",
            value=>value["item_progress"]!.AsObject().Remove("total_ms"),value=>value["item_progress"]!["prepared_windows"]=2,
            value=>value["item_progress"]!["phase"]="future",value=>value["item_progress"]!["phase"]="saving",
            value=>value["state"]="completed",value=>value["processed"]=2})
        {
            var bad=working.DeepClone().AsObject();change(bad);var rejected=false;
            try{AudioContentStatus.Parse(bad.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid or stale audio progress is rejected");
        }
        foreach(var change in new Action<JsonObject>[] {value=>value["target"]=-1,value=>value["processed"]=1001,
            value=>value["available"]="true",value=>value["indexed"]=true,value=>value["state"]="future",
            value=>value["source_kind"]=true,value=>value["source_kind"]=null,value=>value["source_kind"]="future"})
        {
            var bad=status.DeepClone().AsObject();change(bad);var rejected=false;
            try{AudioContentStatus.Parse(bad.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"audio malformed status is rejected");
        }
        var method=SearchMethod.FromIndex(7);
        check(method.IsAI&&method.IsAudioContent,"audio search appends without changing old mode indices");
        var similar=ResultSearchConditions.Create("ignored","audio","favorites",SearchMethod.FromIndex(0),null,[7],originId:9,shelfIds:[11],directAudioSimilarity:true)!;
        check(similar["mode"]!.GetValue<string>()=="audio-similar"&&similar["item_id"]!.GetValue<int>()==9,"direct audio similarity uses its own result mode");
        check(similar["root_ids"]![0]!.GetValue<int>()==7&&similar["shelf_ids"]![0]!.GetValue<long>()==11&&!similar.ContainsKey("scope"),"direct audio similarity retains library filters without a visual AI scope");
        var conditions=ResultSearchConditions.Create("雨の音","audio","favorites",method,null,[7],shelfIds:[9]);
        check(conditions!["mode"]!.GetValue<string>()=="audio-direct"&&!conditions.ContainsKey("scope"),"audio search uses its own namespace rather than image index scope");
        check(conditions["root_ids"]![0]!.GetValue<int>()==7&&conditions["shelf_ids"]![0]!.GetValue<long>()==9,"audio search retains root and shelf filters");
        check(ResultSearchConditions.Create("","audio","all",method,null,null) is null,"empty audio query does not start inference");
        var row=Protocol.ParseItem("""{"id":1,"title":"generated.wav","kind":"audio","tags":[],"shelf":"","favorite":false,"reviewed":false,"semantic_score":0.8,"audio_match_ms":30000,"audio_match_source":"direct-audio"}""");
        check(row.AudioMatchSource=="direct-audio"&&row.AIEvidence.Contains("音声の内容一致（0:30）")&&!row.AIEvidence.Contains("発話"),"direct audio evidence never invents speech/transcript");
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>send(request);}
}
