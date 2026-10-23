using System.Net;
using System.Text.Json.Nodes;
using Aredoko.Core;
internal static class AIEnvironmentTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var id=new string('e',32);var calls=new List<string>();
        var job=new JsonObject{["job_id"]=id,["state"]="validating",["stage"]="checking_runtime",["saved"]=false,["bytes_done"]=64,["bytes_total"]=128,["files_done"]=1,["files_total"]=2,["message"]="確認中"};
        var status=new JsonObject{["runtime"]=new JsonObject{["state"]="runtime_missing",["ready"]=false},["model"]=new JsonObject{["state"]="model_files_present",["ready"]=true},["restart_required"]=true,["runtime_root"]=null,["models_root"]=Path.GetTempPath()};
        using var handler=new Stub(async request=>
        {
            var route=request.RequestUri!.AbsolutePath;calls.Add(route);
            if(request.Method==HttpMethod.Post)
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
                if(route.EndsWith("select"))
                {
                    check(body["consent"]!.GetValue<bool>()&&body.Count==2,"AI location selection has explicit consent and one changed field");
                    if(body.ContainsKey("runtime_root"))check(body["runtime_root"] is null&&!body.ContainsKey("models_root"),"runtime reset is explicit null and leaves model selection unchanged");
                    else check(body["models_root"]!.GetValue<string>()==Path.GetTempPath()&&!body.ContainsKey("runtime_root"),"models selection preserves runtime preference");
                }
                else check(body.Count==1&&body["job_id"]!.GetValue<string>()==id,"AI validation cancellation targets current owned job");
            }
            return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(route.EndsWith("/setup")?status.ToJsonString():job.ToJsonString())};
        });
        using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};var client=new AIEnvironmentClient(http);
        var diagnostic=await client.StatusAsync();check(!diagnostic.RuntimeFilesPresent&&diagnostic.ModelFilesPresent&&diagnostic.RestartRequired,"runtime/model presence and restart are distinct, without inference claims");
        var progress=await client.JobAsync();check(progress.Active&&!progress.Saved&&progress.BytesDone==64&&progress.FilesDone==1,"AI setup progress stays active before settings publication");
        await client.SelectRuntimeAsync(null);await client.SelectModelsAsync(Path.GetTempPath());await client.CancelAsync(id);
        var count=calls.Count;var invalid=false;try{await client.SelectModelsAsync("relative");}catch(ArgumentException){invalid=true;}check(invalid&&calls.Count==count,"relative AI folder never reaches backend");
        invalid=false;try{await client.CancelAsync("invalid");}catch(ArgumentException){invalid=true;}check(invalid&&calls.Count==count,"invalid setup job ID never reaches backend");
        job["state"]="complete";invalid=false;try{AIEnvironmentJob.Parse(job.ToJsonString());}catch(InvalidDataException){invalid=true;}check(invalid,"complete setup state requires saved settings");
        job["saved"]=true;check(AIEnvironmentJob.Parse(job.ToJsonString()).Saved,"published AI location is distinct from runtime inference readiness");
        job["bytes_done"]=129;invalid=false;try{AIEnvironmentJob.Parse(job.ToJsonString());}catch(InvalidDataException){invalid=true;}check(invalid,"AI setup cannot report received bytes beyond total");
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request);}
}
