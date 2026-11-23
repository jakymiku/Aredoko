using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

static class ResultBuildProgressTests
{
    static HttpResponseMessage Reply(JsonObject value,HttpStatusCode status=HttpStatusCode.OK)=>new(status)
        {Content=new StringContent(value.ToJsonString(),Encoding.UTF8,"application/json")};
    public static async Task Run(Action<bool,string> check)
    {
        var conditions=new JsonObject{["mode"]="literal"};var id=new string('a',32);
        JsonObject Status()=>new(){["session_id"]=id,["conditions"]=conditions.DeepClone(),["state"]="building",["processed"]=60,["total"]=125};
        check(ResultBuildProgress.Parse(Status(),id,conditions).Processed==60,"build progress exposes verified count without items");
        foreach(var bad in new[]{Status(),Status(),Status(),Status()}.Select((value,index)=>
        {
            if(index==0)value["processed"]=126;
            if(index==1)value["state"]="ready";
            if(index==2)value["items"]=new JsonArray();
            if(index==3)value["conditions"]=new JsonObject{["mode"]="similar"};
            return value;
        }))
        {
            var rejected=false;try{ResultBuildProgress.Parse(bad,id,conditions);}catch(InvalidDataException){rejected=true;}
            check(rejected,"invalid build count/state/partial items/scope rejected");
        }
        var release=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var received=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var polling=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var calls=0;var closes=0;var statusCancelled=false;
        using var control=new HttpClient(new Stub(async(request,token)=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;id=body["session_id"]!.GetValue<string>();
            if(request.RequestUri!.AbsolutePath.EndsWith("/close")){closes++;return Reply(new(){["closed"]=true});}
            if(++calls==1)return Reply(Status());
            polling.TrySetResult();
            try{await Task.Delay(Timeout.Infinite,token);throw new Exception("Unexpected progress completion");}
            catch(OperationCanceledException){statusCancelled=true;throw;}
        })){BaseAddress=new("http://127.0.0.1:8769/")};
        using var builder=new HttpClient(new Stub(async(request,token)=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;await release.Task.WaitAsync(token);
            return Reply(new(){["session_id"]=body["session_id"]!.DeepClone(),["conditions"]=body["conditions"]!.DeepClone(),
                ["state"]="ready",["range_limit"]=120,["idle_seconds"]=900,["total"]=125});
        })){BaseAddress=control.BaseAddress};
        var creating=new ResultSessionClient(control,builder).CreateAsync(conditions,CancellationToken.None,new Callback(value=>
        {check(value.Processed==60&&value.Total==125,"optional observer receives scoped progress");received.TrySetResult();}));
        await received.Task.WaitAsync(TimeSpan.FromSeconds(5));await polling.Task.WaitAsync(TimeSpan.FromSeconds(5));release.SetResult();
        await using(var session=await creating)check(session.Total==125&&statusCancelled,"creation joins and cancels an in-flight progress poll");
        check(closes==1,"progress does not change ordinary session close ownership");

        var unsupported=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var legacyControl=new HttpClient(new Stub((request,_)=>
        {
            if(request.RequestUri!.AbsolutePath.EndsWith("/close"))return Task.FromResult(Reply(new(){["closed"]=true}));
            unsupported.TrySetResult();return Task.FromResult(Reply(new(){["error"]="Optional status unsupported"},HttpStatusCode.BadRequest));
        })){BaseAddress=control.BaseAddress};
        using var legacyBuild=new HttpClient(new Stub(async(request,token)=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;await unsupported.Task.WaitAsync(token);
            return Reply(new(){["session_id"]=body["session_id"]!.DeepClone(),["conditions"]=body["conditions"]!.DeepClone(),
                ["state"]="ready",["range_limit"]=120,["idle_seconds"]=900,["total"]=0});
        })){BaseAddress=control.BaseAddress};
        using var bounded=new CancellationTokenSource(TimeSpan.FromSeconds(5));
        await using(var session=await new ResultSessionClient(legacyControl,legacyBuild).CreateAsync(conditions,bounded.Token,new Callback(_=>check(false,"legacy optional progress"))))
            check(session.Total==0,"unsupported optional progress does not break older creation servers");
    }
    sealed class Callback(Action<ResultBuildProgress> report):IProgress<ResultBuildProgress>{public void Report(ResultBuildProgress value)=>report(value);}
    sealed class Stub(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>send(request,token);}
}
