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
        check(!(await client.StatusAsync()).Busy,"audio idle status does not claim active job");
        check((await client.StartAsync(new(){["root_ids"]=new JsonArray(7)})).Busy,"audio index status starts polling");
        check((await client.CancelAsync()).State=="cancelling","audio cancellation is visible");
        foreach(var change in new Action<JsonObject>[] {value=>value["target"]=-1,value=>value["processed"]=1001,
            value=>value["available"]="true",value=>value["indexed"]=true,value=>value["state"]="future"})
        {
            var bad=status.DeepClone().AsObject();change(bad);var rejected=false;
            try{AudioContentStatus.Parse(bad.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"audio malformed status is rejected");
        }
        var method=SearchMethod.FromIndex(7);
        check(method.IsAI&&method.IsAudioContent,"audio search appends without changing old mode indices");
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
