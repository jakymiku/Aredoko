using Aredoko.Core;
using System.Net;
using System.Net.Http.Headers;

internal static class ViewerPerformanceTests
{
    private static readonly string Tag="W/\""+new string('a',64)+"\"";
    private static readonly string OtherTag="W/\""+new string('b',64)+"\"";
    public static async Task Run(Action<bool,string> check)
    {
        ViewerSource.ValidateETag(Tag);
        foreach(var bad in new[]{"*","\""+new string('a',64)+"\"","W/\"short\"","W/\""+new string('A',64)+"\""})
        {try{ViewerSource.ValidateETag(bad);check(false,"bad ETag");}catch(InvalidDataException){check(true,"malformed viewer validator rejected");}}

        int decoded=0,reads=0;
        Task<DecodedViewerPage<string>> Decode(byte[] data,bool preload,CancellationToken token)
        {token.ThrowIfCancellationRequested();decoded++;return Task.FromResult(new DecodedViewerPage<string>("decoded-"+data[0],16));}
        using(var cache=new ViewerPageCache<int,string>(2,32))
        {
            async Task<ViewerSource> Source(string? etag,CancellationToken token)
            {await Task.CompletedTask;reads++;return etag==Tag?new(null,Tag,"",true):new([1],Tag,"image/png",false);}
            check(await cache.ReadAsync(1,Source,Decode,default)=="decoded-1","cold viewer source decoded");
            check(await cache.ReadAsync(1,Source,Decode,default)=="decoded-1"&&reads==2&&decoded==1,"cache hit revalidates without decoding again");
            await cache.ReadAsync(2,(_,_)=>Task.FromResult(new ViewerSource([2],Tag,"image/png",false)),Decode,default);
            await cache.ReadAsync(3,(_,_)=>Task.FromResult(new ViewerSource([3],Tag,"image/png",false)),Decode,default);
            check(cache.Count==2&&cache.Bytes==32,"decoded cache obeys count and byte budgets");
            await cache.ReadAsync(1,Source,Decode,default);
            check(decoded==4,"evicted page is fetched and decoded again");
            try{await cache.ReadAsync(1,(_,_)=>throw new ArchiveReadException(HttpStatusCode.NotFound),Decode,default);check(false,"missing source");}
            catch(ArchiveReadException){check(cache.Count==1,"access/source failure evicts stale decoded entry");}
            cache.Clear();check(cache.Count==0&&cache.Bytes==0,"viewer cache clears across reopen");
            try{await cache.ReadAsync(1,(_,_)=>Task.FromResult(new ViewerSource(null,Tag,"",true)),Decode,default);check(false,"unsolicited304");}
            catch(InvalidDataException){check(true,"304 cannot authorize a page without a matching local entry");}
        }
        using(var cache=new ViewerPageCache<int,string>(2,8))
        {
            await cache.ReadAsync(1,(_,_)=>Task.FromResult(new ViewerSource([1],Tag,"image/png",false)),Decode,default);
            check(cache.Count==0,"large foreground page displays without retaining it over budget");
            await cache.PreloadAsync(2,(_,_)=>Task.FromResult(new ViewerSource([2],Tag,"image/png",false)),
                (_,_,_)=>throw new ViewerPreloadSkippedException(),default);
            check(cache.Count==0,"oversized speculative decode is skipped without a visible error");
        }
        using(var cache=new ViewerPageCache<int,string>())
        {
            var entered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var release=new TaskCompletionSource<ViewerSource>(TaskCreationOptions.RunContinuationsAsynchronously);
            var reading=cache.ReadAsync(1,(_,_)=>{entered.TrySetResult();return release.Task;},Decode,default);
            await entered.Task;cache.Clear();release.SetResult(new([1],Tag,"image/png",false));
            try{await reading;check(false,"late cleared session");}
            catch(OperationCanceledException){check(cache.Count==0,"late load cannot publish or repopulate a cleared session cache");}
            using var cancel=new CancellationTokenSource();cancel.Cancel();
            try{await cache.ReadAsync(2,(_,_)=>throw new Exception("must not fetch"),Decode,cancel.Token);check(false,"cancelledread");}
            catch(OperationCanceledException){check(true,"cancelled source is not started");}
        }

        int routeCalls=0;
        using(var handler=new Stub((request,_)=>
        {
            routeCalls++;
            check(request.RequestUri!.AbsolutePath=="/api/library/reader/7/original/0","conditional original uses fixed page route");
            check(request.Headers.GetValues("X-Aredoko-Token").Single()=="fixture-token","conditional request preserves session authentication");
            if(routeCalls==1)return Task.FromResult(Reply(HttpStatusCode.OK,[1,2,3],Tag));
            check(request.Headers.IfNoneMatch.Single().ToString()==Tag,"known metadata validator sent for revalidation");
            return Task.FromResult(Reply(HttpStatusCode.NotModified,[],Tag));
        }))
        using(var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769")})
        {
            http.DefaultRequestHeaders.Add("X-Aredoko-Token","fixture-token");var client=new ArchiveReaderClient(http);
            var book=new ArchiveManifest(7,2,new string('a',64));
            var first=await client.OriginalPageSourceAsync(book,0,null,default);
            var same=await client.OriginalPageSourceAsync(book,0,first.ETag,default);
            check(first.Data!.SequenceEqual(new byte[]{1,2,3})&&!first.NotModified&&same.NotModified&&same.Data is null,"original response and bodyless304 parsed");
        }
        foreach(var response in new[]{Reply(HttpStatusCode.NotModified,[],OtherTag),Reply(HttpStatusCode.NotModified,[1],Tag)})
        {
            using var http=new HttpClient(new Stub((_,_)=>Task.FromResult(response))){BaseAddress=new Uri("http://127.0.0.1:8769")};
            try{await new ArchiveReaderClient(http).OriginalImageSourceAsync(1,Tag,default);check(false,"bad304");}
            catch(InvalidDataException){check(true,"mismatched or body-bearing304 rejected");}
        }

        var saved=new List<int>();var firstSave=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseSave=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        int inFlight=0,peak=0;
        var writer=new ReaderProgressWriter(async(_,progress)=>
        {
            inFlight++;peak=Math.Max(peak,inFlight);saved.Add(progress.Page);
            if(saved.Count==1){firstSave.SetResult();await releaseSave.Task;}
            inFlight--;
        });
        var manifest=new ArchiveManifest(1,10,new string('c',64));
        writer.Queue(manifest,1,ReaderDisplayMode.Single);await firstSave.Task;
        writer.Queue(manifest,2,ReaderDisplayMode.Single);writer.Queue(manifest,3,ReaderDisplayMode.Single);
        var flush=writer.FlushAsync();check(!flush.IsCompleted,"close waits for pending position writes");
        releaseSave.SetResult();await flush;
        check(saved.SequenceEqual(new[]{1,3})&&peak==1,"position saves are serialized and intermediate pending pages coalesced");
        bool fail=true;int attempts=0;
        var retry=new ReaderProgressWriter((_,_)=>{attempts++;return fail?Task.FromException(new IOException("generated save failure")):Task.CompletedTask;});
        retry.Queue(manifest,4,ReaderDisplayMode.Single);await retry.FlushAsync();
        check(retry.LastError is IOException&&attempts==1,"save failure is exposed without automatic retries");
        fail=false;retry.Queue(manifest,4,ReaderDisplayMode.Single);await retry.FlushAsync();
        check(retry.LastError is null&&attempts==2,"explicit save retries the current visible position");
    }
    private static HttpResponseMessage Reply(HttpStatusCode status,byte[] body,string tag)
    {
        var response=new HttpResponseMessage(status){Content=new ByteArrayContent(body)};
        response.Content.Headers.ContentType=new MediaTypeHeaderValue("image/png");
        response.Headers.ETag=EntityTagHeaderValue.Parse(tag);return response;
    }
    private sealed class Stub(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>send(request,cancellation);}
}
