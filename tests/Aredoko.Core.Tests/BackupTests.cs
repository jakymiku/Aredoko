using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class BackupTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var folder=Path.Combine(Path.GetTempPath(),"aredoko-backup-contract-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
        try
        {
            var path=Path.Combine(folder,"choices.json");var choices=new BackupSelection(false,false,true,true);choices.Save(path);
            check(BackupSelection.Load(path)==choices,"backup previous choices persist independently of viewer format");
            File.WriteAllText(path,"{\"settings\":true}");check(BackupSelection.Load(path)==new BackupSelection(),"broken backup choices use safe defaults with vectors omitted");
            var calls=new List<string>();var starts=0;var id=new string('a',32);
            var snapshot=new JsonObject{["job_id"]=id,["state"]="capturing",["published"]=false,["message"]="作成中",["bytes_done"]=128,["bytes_total"]=256,["output"]=folder,["selection"]=choices.ToJson()};
            using var handler=new Stub(async request=>
            {
                calls.Add(request.RequestUri!.AbsolutePath);
                if(request.Method==HttpMethod.Post)
                {
                    var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
                    if(request.RequestUri.AbsolutePath.EndsWith("start"))
                    {
                        check(body["consent"]!.GetValue<bool>(),"backup start explicitly consents");
                        if(++starts==1)
                        {
                            check(body["selection"]!["vectors"]!.GetValue<bool>(),"backup transport preserves chosen vector inclusion");
                            check(!body.AsObject().ContainsKey("viewer_settings"),"omitted settings do not leak viewer snapshot");
                        }
                        else check(body["viewer_settings"]!["theme"]!.GetValue<string>()=="dark"&&!body.AsObject().ContainsKey("settings_path"),"backup sends immutable viewer data instead of a local settings path");
                    }
                    else check(body["job_id"]!.GetValue<string>()==id,"backup cancel targets exact owned job");
                }
                return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(snapshot.ToJsonString(),Encoding.UTF8,"application/json")};
            });
            using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};var client=new BackupClient(http);
            var state=await client.StatusAsync();check(state.Active&&state.BytesDone==128&&state.BytesTotal==256&&!state.Published,"typed backup progress remains active without claiming completion");
            await client.StartAsync(folder,choices,new ViewerInputSettings());await client.CancelAsync(id);
            check(calls.SequenceEqual(new[]{"/api/library/backup","/api/library/backup/start","/api/library/backup/cancel"}),"backup client uses authenticated LibraryApi transport endpoints");
            snapshot["state"]="complete";var rejected=false;try{BackupJob.Parse(snapshot.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"backup rejects completion without manifest publication");
            snapshot["state"]="capturing";snapshot["bytes_done"]=300;rejected=false;try{BackupJob.Parse(snapshot.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"backup rejects impossible progress");
            rejected=false;try{await client.CancelAsync("0");}catch(ArgumentException){rejected=true;}check(rejected&&calls.Count==3,"invalid backup cancellation never reaches server");
            var restoreJson=new JsonObject{["job_id"]=id,["state"]="completed",["progress_ratio"]=1,["message"]="準備完了",["staging_supported"]=true,["switch_supported"]=false};
            var restored=RestoreJob.Parse(restoreJson.ToJsonString());check(!restored.Active&&!restored.SwitchSupported,"restore preparation completion does not authorize a database switch");
            restoreJson["progress_ratio"]=0.5;rejected=false;try{RestoreJob.Parse(restoreJson.ToJsonString());}catch(InvalidDataException){rejected=true;}check(rejected,"restore rejects premature completion");
            restoreJson["progress_ratio"]=1;
            using var restoreHandler=new Stub(async request=>
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
                check(request.RequestUri!.AbsolutePath=="/api/library/restore/start"&&body["consent"]!.GetValue<bool>()&&body["without_vectors"]!.GetValue<bool>(),"restore start carries explicit consent and cache omission");
                check(body.AsObject().Count==3&&!body.AsObject().ContainsKey("staging_path"),"restore caller cannot choose the owned staging path");
                return new HttpResponseMessage(HttpStatusCode.Accepted){Content=new StringContent(restoreJson.ToJsonString())};
            });
            using var restoreHttp=new HttpClient(restoreHandler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
            await new RestoreClient(restoreHttp).StartAsync(folder);
            restoreJson["source"]=folder;restoreJson["without_vectors"]=true;
            check(RestoreJob.Parse(restoreJson.ToJsonString()).Source==folder&&RestoreJob.Parse(restoreJson.ToJsonString()).WithoutVectors==true,"restore reattach identifies the selected backup and vector policy");
            restoreJson["switch_supported"]=true;restoreJson["restart_requested"]=true;
            check(RestoreJob.Parse(restoreJson.ToJsonString()).RestartRequested,"restore accepts a completed owned restart acknowledgment");
            restoreJson["switch_supported"]=false;rejected=false;try{RestoreJob.Parse(restoreJson.ToJsonString());}catch(InvalidDataException){rejected=true;}check(rejected,"restore rejects restart without owned launcher capability");
            restoreJson["switch_supported"]=true;
            using var restartHandler=new Stub(async request=>
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
                check(request.RequestUri!.AbsolutePath=="/api/library/restore/restart"&&body["consent"]!.GetValue<bool>()&&body["job_id"]!.GetValue<string>()==id&&body.AsObject().Count==2,"restore restart targets exact job with explicit consent");
                return new HttpResponseMessage(HttpStatusCode.Accepted){Content=new StringContent(restoreJson.ToJsonString())};
            });
            using var restartHttp=new HttpClient(restartHandler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
            check((await new RestoreClient(restartHttp).RestartAsync(id)).RestartRequested,"restart response is parsed before the frontend closes");
            restoreJson["staging_supported"]=false;restoreJson["message"]="復旧ガイドを確認してください。";
            rejected=false;try{RestoreJob.Parse(restoreJson.ToJsonString());}catch(InvalidOperationException error){rejected=error.Message.Contains("復旧ガイド");}check(rejected,"blocked durable restore gives actionable native guidance");
            snapshot["bytes_done"]=128;var viewer=new ViewerInputSettings(true,80,"dark",true);await client.StartAsync(folder,new BackupSelection(),viewer);check(viewer.ToJson()["wheel_up_advances"]!.GetValue<bool>()&&viewer.ToJson()["theme"]!.GetValue<string>()=="dark","backup and normal viewer persistence share the exact JSON contract");
        }
        finally{Directory.Delete(folder,true);}
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request);}
}
