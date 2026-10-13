using Aredoko.Core;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;

internal static class ImageViewerTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var row = new MediaRow { Id=9, Kind="image", Availability="present", Location="folder/a.PNG" };
        check(ImageViewerPolicy.CanOpen(row), "present uppercase image can open");
        row.Availability="missing";check(!ImageViewerPolicy.CanOpen(row), "missing image cannot open");
        row.Availability="present";row.Location="a.svg";check(!ImageViewerPolicy.CanOpen(row), "unsupported image cannot open");
        row.Location="a.png";row.Kind="archive";check(!ImageViewerPolicy.CanOpen(row), "archive cannot use single image entry");
        var first = new MediaRow { Id=5, Title="first", Kind="image", Availability="present", Location="a.png" };
        var last = new MediaRow { Id=3, Title="last", Kind="image", Availability="present", Location="b.png" };
        var absent = new MediaRow { Id=2, Kind="image", Availability="missing", Location="c.png" };
        var results = new List<MediaRow> { last, row, absent, first };
        var sequence = new ImageViewerSequence(results, 3);
        check(sequence.Count==2 && sequence.Current.Id==3, "sequence keeps result order and skips missing/non-images");
        check(!sequence.HasPrevious && !sequence.TryMove(-1) && sequence.Position==0, "sequence stops at first image");
        results.Clear();last.Title="changed";
        check(sequence.Current.Title=="last", "sequence freezes titles and order independent of later results");
        check(sequence.TryMove(1) && sequence.Current.Id==5 && sequence.HasPrevious, "sequence moves to next result image");
        check(!sequence.HasNext && !sequence.TryMove(1) && sequence.Current.Id==5, "sequence stops at last image");
        check(sequence.TryMove(-1) && sequence.Current.Id==3, "sequence moves back in search order");
        try { sequence.TryMove(2);check(false,"bad direction"); } catch(ArgumentOutOfRangeException) { check(sequence.Position==0,"bad direction leaves sequence unchanged"); }
        try { new ImageViewerSequence([absent],2);check(false,"out of scope image"); } catch(ArgumentException) { check(true,"sequence rejects absent/out of scope selection"); }
        check(new ImageViewerSequence([first,first],5).Count==1,"sequence removes duplicate IDs");
        var calls=new List<string>();
        using var stub=new Stub((request,token)=>
        {
            calls.Add(request.RequestUri!.PathAndQuery);
            check(request.Headers.Contains("X-Aredoko-Token"), "image keeps authenticated session");
            return Task.FromResult(Response(new byte[]{1,2,3},"image/png"));
        });
        using var http=new HttpClient(stub){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        http.DefaultRequestHeaders.Add("X-Aredoko-Token","fixture-token");var reader=new ArchiveReaderClient(http);
        check((await reader.ImageAsync(9,CancellationToken.None)).SequenceEqual(new byte[]{1,2,3})&&calls.Single()=="/api/library/preview/9", "image uses bounded fixed route");
        try{await reader.ImageAsync(0,CancellationToken.None);check(false,"invalid image ID");}catch(ArgumentOutOfRangeException){check(calls.Count==1,"invalid image ID rejected before HTTP");}
        foreach(var (length,mime) in new[]{(0L,"image/png"),(2L,"image/png"),((long)PreviewPolicy.MaxSourceBytes+1,"image/png"),(1L,"text/html")})
        {
            using var bad=new Stub((_,_)=>{var r=Response(new byte[]{1},mime);r.Content.Headers.ContentLength=length;return Task.FromResult(r);});
            using var client=new HttpClient(bad){BaseAddress=http.BaseAddress};bool rejected=false;
            try{await new ArchiveReaderClient(client).ImageAsync(9,CancellationToken.None);}catch(InvalidDataException){rejected=true;}
            check(rejected,"image rejects size/MIME "+length+"/"+mime);
        }
        using var cancellation=new CancellationTokenSource();
        using var slow=new Stub(async(_,token)=>{cancellation.Cancel();await Task.Delay(Timeout.Infinite,token);return Response([],"image/png");});
        using var slowHttp=new HttpClient(slow){BaseAddress=http.BaseAddress};bool cancelled=false;
        try{await new ArchiveReaderClient(slowHttp).ImageAsync(9,cancellation.Token);}catch(OperationCanceledException){cancelled=true;}
        check(cancelled,"closing image cancels transport");
    }
    private static HttpResponseMessage Response(byte[] data,string mime)
    {var r=new HttpResponseMessage(HttpStatusCode.OK){Content=new ByteArrayContent(data)};r.Content.Headers.ContentType=new MediaTypeHeaderValue(mime);return r;}
    private sealed class Stub(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> handle):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>handle(request,cancellation);}
}
