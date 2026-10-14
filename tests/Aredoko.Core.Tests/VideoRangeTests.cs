using Aredoko.Core;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;

internal static class VideoRangeTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var m=new VideoManifest(8,70*1024*1024,"video/mp4",new string('a',64));m.Validate();check(m.SizeBytes>VideoPlayerPolicy.MaxSourceBytes,"range manifest accepts larger than legacy limit");
        var seen=0;using var stub=new Stub((req,ct)=>
        {
            seen++;check(req.RequestUri!.AbsolutePath=="/api/library/video/8/range"&&req.RequestUri.Query=="?revision="+m.Revision,"range fixed route and revision");
            check(req.Headers.GetValues("X-Aredoko-Token").Single()=="fiction","range retains auth header");
            var span=req.Headers.Range!.Ranges.Single();var length=(int)(span.To!-span.From!+1);var response=new HttpResponseMessage(HttpStatusCode.PartialContent){Content=new ByteArrayContent(new byte[length])};
            response.Content.Headers.ContentType=new MediaTypeHeaderValue(m.Mime);response.Content.Headers.ContentRange=new ContentRangeHeaderValue(span.From!.Value,span.To!.Value,m.SizeBytes);response.Headers.ETag=new EntityTagHeaderValue("\""+m.Revision+"\"");return Task.FromResult(response);
        });using var http=new HttpClient(stub){BaseAddress=new Uri("http://127.0.0.1:8769/")};http.DefaultRequestHeaders.Add("X-Aredoko-Token","fiction");using var source=new VideoRangeSource(http,m,CancellationToken.None);
        check((await source.ReadAsync(m.SizeBytes-3,8,CancellationToken.None)).Length==3,"tail read is bounded to EOF");check((await source.ReadAsync(m.SizeBytes,1,CancellationToken.None)).Length==0&&seen==1,"EOF avoids network");
        try{await source.ReadAsync(0,VideoManifest.ChunkBytes+1,CancellationToken.None);check(false,"huge read");}catch(ArgumentOutOfRangeException){check(seen==1,"oversize range rejected before network");}
        foreach(var status in new[]{HttpStatusCode.OK,HttpStatusCode.Conflict,HttpStatusCode.ServiceUnavailable})
        {
            using var badHttp=new HttpClient(new Stub((_,_)=>Task.FromResult(new HttpResponseMessage(status){Content=new ByteArrayContent(new byte[1])}))){BaseAddress=http.BaseAddress};using var bad=new VideoRangeSource(badHttp,m,CancellationToken.None);
            try{await bad.ReadAsync(0,1,CancellationToken.None);check(false,"bad status");}catch(Exception ex) when(ex is ArchiveReadException or InvalidDataException){check(bad.Failure is not null,"full/stale/busy response rejected "+status);}
        }
        foreach(var invalid in new[]{"range","etag","weak","mime","length","short","extra"})
        {
            using var badHttp=new HttpClient(new Stub((_,_)=>
            {
                var response=new HttpResponseMessage(HttpStatusCode.PartialContent){Content=new ByteArrayContent(new byte[invalid=="short"?0:invalid=="extra"?2:1])};
                response.Content.Headers.ContentLength=invalid=="length"?2:1;
                response.Content.Headers.ContentType=new MediaTypeHeaderValue(invalid=="mime"?"image/png":m.Mime);
                response.Content.Headers.ContentRange=new ContentRangeHeaderValue(invalid=="range"?1:0,invalid=="range"?1:0,m.SizeBytes);
                response.Headers.ETag=new EntityTagHeaderValue("\""+(invalid=="etag"?new string('b',64):m.Revision)+"\"",invalid=="weak");return Task.FromResult(response);
            })){BaseAddress=http.BaseAddress};using var bad=new VideoRangeSource(badHttp,m,CancellationToken.None);
            try{await bad.ReadAsync(0,1,CancellationToken.None);check(false,"invalid "+invalid);}catch(InvalidDataException){check(bad.Failure is InvalidDataException,"invalid range contract rejected "+invalid);}
        }
        foreach(var json in new[]{"{}","[]","{\"item_id\":8,\"size_bytes\":0,\"mime\":\"video/mp4\",\"revision\":\""+m.Revision+"\"}"})
        {try{VideoManifest.Parse(Encoding.UTF8.GetBytes(json),8);check(false,"invalid manifest");}catch(InvalidDataException){check(true,"malformed/empty manifest rejected");}}
        using var cancel=new CancellationTokenSource();using var slowHttp=new HttpClient(new Stub(async(_,ct)=>{cancel.Cancel();await Task.Delay(Timeout.Infinite,ct);return new HttpResponseMessage();})){BaseAddress=http.BaseAddress};using var slow=new VideoRangeSource(slowHttp,m,cancel.Token);
        try{await slow.ReadAsync(0,1,CancellationToken.None);check(false,"cancel range");}catch(OperationCanceledException){check(slow.Failure is null,"closing cancels range without persistent failure");}
    }
    private sealed class Stub(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>send(request,cancellation);}
}
