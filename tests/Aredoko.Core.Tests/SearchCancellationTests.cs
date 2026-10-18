using Aredoko.Core;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;
internal static class SearchCancellationTests
{
    const string Id="0123456789abcdef0123456789abcdef";
    static HttpResponseMessage Json(string text)=>new(HttpStatusCode.OK){Content=new StringContent(text,Encoding.UTF8,"application/json")};
    public static async Task Run(Action<bool,string> check)
    {
        check(SearchRequestClient.IsRequestId(Id)&&!SearchRequestClient.IsRequestId(null)&&!SearchRequestClient.IsRequestId(new string('A',32)),"search capability strict lowercase ID");
        var calls=new List<string>();var blocked=false;var badEcho=false;var cancelMalformed=false;var entered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var http=new HttpClient(new Handler(async(request,token)=>
        {
            var path=request.RequestUri!.AbsolutePath;calls.Add(path);
            check(request.Headers.GetValues("X-Aredoko-Token").Single()=="session"&&request.Headers.GetValues("Origin").Single()=="http://127.0.0.1:8769","search lifecycle preserves authenticated loopback session");
            if(path.EndsWith("/prepare"))return Json("""{"request_id":"0123456789abcdef0123456789abcdef","expires_in_seconds":60}""");
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync(token))!;
            check(body["request_id"]!.GetValue<string>()==Id,"cancel/query carries same owned capability");
            if(path.EndsWith("/cancel"))return Json(cancelMalformed?"""{"request_id":"00000000000000000000000000000000","cancel_requested":true}""":"""{"request_id":"0123456789abcdef0123456789abcdef","cancel_requested":false}""");
            if(blocked){entered.TrySetResult();await Task.Delay(Timeout.Infinite,token);}
            return Json(badEcho?"""{"request_id":"00000000000000000000000000000000","total":0,"items":[]}""":"""{"request_id":"0123456789abcdef0123456789abcdef","total":0,"items":[]}""");
        })){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        http.DefaultRequestHeaders.Add("X-Aredoko-Token","session");http.DefaultRequestHeaders.Add("Origin","http://127.0.0.1:8769");
        var client=new SearchRequestClient(http);var original=new JsonObject{["query"]="青髪"};
        var bytes=await client.RunAsync("api/library/ai/search",original);
        check(Protocol.ParseSearch(Encoding.UTF8.GetString(bytes)).Total==0&&!original.ContainsKey("request_id")&&calls.Count==2,"normal search prepares then queries, preserves caller body, no completed cancel");
        check(!await client.CancelAsync(Id),"finished cancellation false is preserved");
        blocked=true;using var cancellation=new CancellationTokenSource();
        var task=client.RunAsync("api/library/ai/search",original,cancellation.Token);await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));cancellation.Cancel();
        try{await task;check(false,"search cancellation");}catch(OperationCanceledException){check(calls.Last().EndsWith("/cancel"),"caller cancellation sends independently uncancelled owned cancel before returning");}
        blocked=false;badEcho=true;var before=calls.Count;
        try{await client.RunAsync("api/library/ai/search",original);check(false,"wrong search echo");}catch(InvalidDataException){check(calls.Count==before+3&&calls.Last().EndsWith("/cancel"),"wrong response ID rejected and exact request cleaned up");}
        cancelMalformed=true;
        try{await client.CancelAsync(Id);check(false,"wrong cancel echo");}catch(InvalidDataException){check(true,"wrong cancellation response ID rejected");}
        before=calls.Count;
        try{await client.RunAsync("api/library/ai/cancel",original);check(false,"index cancel route");}catch(ArgumentException){check(calls.Count==before,"search helper cannot call index-job cancellation");}
        using var timed=new HttpClient(new Handler((request,token)=>request.RequestUri!.AbsolutePath.EndsWith("/prepare")
            ?Task.FromResult(Json("""{"request_id":"0123456789abcdef0123456789abcdef","expires_in_seconds":60}"""))
            :request.RequestUri.AbsolutePath.EndsWith("/cancel")?throw new HttpRequestException("cancel connection lost"):throw new TaskCanceledException("query timeout"))){BaseAddress=http.BaseAddress};
        try{await new SearchRequestClient(timed).RunAsync("api/library/ai/search",original);check(false,"query timeout");}catch(TimeoutException){check(true,"transport deadline becomes timeout; failed cancel never hides original failure");}
        using var preCancelled=new CancellationTokenSource();preCancelled.Cancel();
        using var enforcing=new HttpClient(new Handler((request,token)=>{token.ThrowIfCancellationRequested();return Task.FromResult(Json("{}"));})){BaseAddress=http.BaseAddress};
        try{await new SearchRequestClient(enforcing).RunAsync("api/library/ai/search",original,preCancelled.Token);check(false,"pre-cancelled query");}catch(OperationCanceledException){check(true,"pre-cancelled search never reaches query operation");}
        using var large=new HttpClient(new Handler((_,_)=>Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){Content=new ByteArrayContent(new byte[32769]){Headers={ContentType=new("application/json")}}}))){BaseAddress=http.BaseAddress};
        try{await new SearchRequestClient(large).RunAsync("api/library/ai/search",original);check(false,"large prepare");}catch(InvalidDataException){check(true,"preparation JSON bounded before parsing");}
    }
    sealed class Handler(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request,cancellationToken);}
}
