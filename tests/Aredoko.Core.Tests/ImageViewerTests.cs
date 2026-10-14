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
        var videoRow = new MediaRow { Id=11, Kind="video", Availability="present", Location="folder/clip.MP4" };
        check(VideoPlayerPolicy.CanOpen(videoRow), "present uppercase video can open");
        videoRow.Availability="missing";check(!VideoPlayerPolicy.CanOpen(videoRow), "missing video cannot open");
        videoRow.Availability="present";videoRow.Location="clip.png";check(!VideoPlayerPolicy.CanOpen(videoRow), "non-video extension cannot open video player");
        check(VideoPlayerPolicy.FormatPosition(TimeSpan.FromSeconds(1.8),TimeSpan.FromSeconds(65))=="0:01 / 1:05" &&
            VideoPlayerPolicy.FormatPosition(TimeSpan.FromSeconds(90),TimeSpan.FromSeconds(65))=="1:05 / 1:05" &&
            VideoPlayerPolicy.FormatPosition(TimeSpan.Zero,TimeSpan.Zero)=="—", "video position formatted and clamped");
        check(VideoPlayerPolicy.ClampVolume(140)==100 && VideoPlayerPolicy.ClampVolume(-20)==0 && VideoPlayerPolicy.ClampVolume(double.NaN)==80, "video volume clamped");
        var videoCalls=new List<string>();
        using var videoStub=new Stub((request,_)=>
        {
            videoCalls.Add(request.RequestUri!.PathAndQuery);
            check(request.Headers.Contains("X-Aredoko-Token"), "video keeps authenticated session");
            return Task.FromResult(Response(new byte[]{4,5,6,7},"video/mp4"));
        });
        using var videoHttp=new HttpClient(videoStub){BaseAddress=http.BaseAddress};
        videoHttp.DefaultRequestHeaders.Add("X-Aredoko-Token","fixture-token");
        var videoClient=new ArchiveReaderClient(videoHttp);
        var fetchedVideo=await videoClient.VideoAsync(11,CancellationToken.None);
        check(fetchedVideo.Data.SequenceEqual(new byte[]{4,5,6,7})&&fetchedVideo.Mime=="video/mp4"&&videoCalls.Single()=="/api/library/video/11", "video uses bounded fixed route");
        try{await videoClient.VideoAsync(0,CancellationToken.None);check(false,"invalid video ID");}catch(ArgumentOutOfRangeException){check(videoCalls.Count==1,"invalid video ID rejected before HTTP");}
        foreach(var (length,mime) in new[]{(0L,"video/mp4"),(2L,"video/mp4"),((long)VideoPlayerPolicy.MaxSourceBytes+1,"video/mp4"),(1L,"image/png")})
        {
            using var bad=new Stub((_,_)=>{var r=Response(new byte[]{1},mime);r.Content.Headers.ContentLength=length;return Task.FromResult(r);});
            using var client=new HttpClient(bad){BaseAddress=http.BaseAddress};bool rejected=false;
            try{await new ArchiveReaderClient(client).VideoAsync(11,CancellationToken.None);}catch(InvalidDataException){rejected=true;}
            check(rejected,"video rejects size/MIME "+length+"/"+mime);
        }
        using var videoCancel=new CancellationTokenSource();
        using var slowVideo=new Stub(async(_,token)=>{videoCancel.Cancel();await Task.Delay(Timeout.Infinite,token);return Response([],"video/mp4");});
        using var slowVideoHttp=new HttpClient(slowVideo){BaseAddress=http.BaseAddress};bool videoCancelled=false;
        try{await new ArchiveReaderClient(slowVideoHttp).VideoAsync(11,videoCancel.Token);}catch(OperationCanceledException){videoCancelled=true;}
        check(videoCancelled,"closing video cancels transport");
    }
    private static HttpResponseMessage Response(byte[] data,string mime)
    {var r=new HttpResponseMessage(HttpStatusCode.OK){Content=new ByteArrayContent(data)};r.Content.Headers.ContentType=new MediaTypeHeaderValue(mime);return r;}
    private sealed class Stub(Func<HttpRequestMessage,CancellationToken,Task<HttpResponseMessage>> handle):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>handle(request,cancellation);}
}
