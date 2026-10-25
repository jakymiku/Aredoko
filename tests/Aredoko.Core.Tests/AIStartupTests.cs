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
        var normal=0;var ai=0;
        async Task<HttpResponseMessage> Response(HttpRequestMessage request)
        {
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
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
        check(ai==3&&normal==3,"only AI result creation uses the long inference transport; close remains responsive");
        await using(var literal=await results.CreateAsync(new(){["mode"]="literal"},CancellationToken.None)){}
        check(ai==3&&normal==5,"literal creation and session lifecycle use ordinary transport");
    }
    sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request,cancellationToken);}
}
