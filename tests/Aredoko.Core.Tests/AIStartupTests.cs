using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

static class AIStartupTests
{
    static HttpResponseMessage Reply(JsonObject value)=>new(HttpStatusCode.OK)
        {Content=new StringContent(value.ToJsonString(),Encoding.UTF8,"application/json")};

    public static async Task Run(Action<bool,string> check)
    {
        var entered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using(var api=new LibraryApi(new Handler(async(request,cancellation)=>
        {
            entered.TrySetResult();
            await Task.Delay(Timeout.Infinite,cancellation);
            return Reply(new());
        })))
        {
            using var stop=new CancellationTokenSource();
            var pending=api.GetAsync("api/library/ai/status",stop.Token);
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(2));stop.Cancel();
            try{await pending;check(false,"runtime status cancellation");}
            catch(OperationCanceledException){check(true,"runtime wait cancels in-flight status request");}
        }
        var normal=0;var ai=0;JsonNode? latestConditions=null;
        async Task<HttpResponseMessage> Response(HttpRequestMessage request)
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
            if(request.RequestUri!.AbsolutePath.EndsWith("/range"))return Reply(new()
                {["session_id"]=body["session_id"]!.DeepClone(),["conditions"]=latestConditions!.DeepClone(),
                 ["state"]="ready",["total"]=0,["offset"]=0,["limit"]=120,["items"]=new JsonArray()});
            if(body["conditions"] is JsonNode conditions)latestConditions=conditions.DeepClone();
            return Reply(request.RequestUri!.AbsolutePath.EndsWith("/close")
                ?new(){["closed"]=true}
                :new(){["session_id"]=body["session_id"]!.DeepClone(),["conditions"]=body["conditions"]!.DeepClone(),
                    ["state"]="ready",["range_limit"]=120,["idle_seconds"]=900,["total"]=0});
        }
        using var ordinary=new HttpClient(new Handler((r,_)=>{normal++;return Response(r);})) {BaseAddress=new("http://127.0.0.1:8769/")};
        using var inference=new HttpClient(new Handler((r,_)=>{ai++;return Response(r);})) {BaseAddress=ordinary.BaseAddress};
        var results=new ResultSessionClient(ordinary,inference);
        foreach(var mode in new[]{"semantic","similar","pending-proposals-semantic"})
        {await using var session=await results.CreateAsync(new(){["mode"]=mode},CancellationToken.None);}
        check(ai==3&&normal==3,"AI result creation uses the build transport; close remains responsive");
        await using(var literal=await results.CreateAsync(new(){["mode"]="literal"},CancellationToken.None))
        {
            await literal.RangeAsync(0,120,CancellationToken.None);
            check(ai==4&&normal==4,"literal snapshot creation uses build transport but range reads stay ordinary");
        }
        check(ai==4&&normal==5,"literal session close stays on ordinary transport");
        var snapshotEntered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var snapshotCloses=0;string? snapshotId=null;
        using var snapshotControl=new HttpClient(new Handler(async(request,_)=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
            check(request.RequestUri!.AbsolutePath.EndsWith("/close")&&body["session_id"]!.GetValue<string>()==snapshotId,"cancelled literal build closes its preallocated ID on ordinary transport");
            snapshotCloses++;return Reply(new(){["closed"]=true});
        })){BaseAddress=ordinary.BaseAddress};
        using var snapshotBuild=new HttpClient(new Handler(async(request,ct)=>
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;snapshotId=body["session_id"]!.GetValue<string>();
            snapshotEntered.TrySetResult();await Task.Delay(Timeout.Infinite,ct);return Reply(new());
        })){BaseAddress=ordinary.BaseAddress};
        using(var snapshotStop=new CancellationTokenSource())
        {
            var pending=new ResultSessionClient(snapshotControl,snapshotBuild).CreateAsync(new(){["mode"]="literal"},snapshotStop.Token);
            await snapshotEntered.Task.WaitAsync(TimeSpan.FromSeconds(2));snapshotStop.Cancel();
            try{await pending;check(false,"literal snapshot build cancellation");}
            catch(OperationCanceledException){check(snapshotCloses==1,"literal build remains cancellable and owns cleanup");}
        }
        var generation=0;var controls=0;
        var generationEntered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var control=new HttpClient(new Handler((_,_)=>{controls++;return Task.FromResult(Reply(new(){["cancel_requested"]=true}));})){BaseAddress=ordinary.BaseAddress};
        using var loader=new HttpClient(new Handler(async(_,ct)=>{generation++;generationEntered.TrySetResult();await Task.Delay(Timeout.Infinite,ct);return Reply(new());})){BaseAddress=ordinary.BaseAddress};
        var tags=new TagReviewClient(control,loader);using var cancel=new CancellationTokenSource();var requestId=Guid.NewGuid().ToString("N");
        var generating=tags.GenerateAsync(7,requestId,cancel.Token);await generationEntered.Task.WaitAsync(TimeSpan.FromSeconds(2));cancel.Cancel();
        try{await generating;check(false,"generation cancellation");}
        catch(OperationCanceledException){check(generation==1&&controls==0,"cold WD generation uses inference transport and caller cancellation");}
        check(await tags.CancelAsync(requestId,CancellationToken.None)&&controls==1,"generation cancellation control uses ordinary transport");
    }
    sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request,cancellationToken);}
}
