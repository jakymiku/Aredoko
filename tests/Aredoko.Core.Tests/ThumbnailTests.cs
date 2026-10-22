using System.Net;
using System.Net.Http.Headers;
using Aredoko.Core;

internal static class ThumbnailTests
{
    public static async Task Run(Action<bool, string> check)
    {
        check(ThumbnailPolicy.EdgeFor(80, 64, 1) == 128, "small list thumbnail requests 128px");
        check(ThumbnailPolicy.EdgeFor(144, 100, 2) == 512, "DPI uses device pixels and rounds up");
        check(ThumbnailPolicy.EdgeFor(256, 200, 1) == 256, "exact size does not overfetch");
        check(ThumbnailPolicy.EdgeFor(600, 600, 4) == 1024, "large tiles use bounded maximum");
        check(ThumbnailPolicy.EdgeFor(0, 0, 1) == 128, "not-yet-measured control stays bounded");
        foreach (var bad in new[] {double.NaN, double.PositiveInfinity, -1})
        {
            var invalid = false;
            try { ThumbnailPolicy.EdgeFor(bad, 100, 1); } catch (ArgumentOutOfRangeException) { invalid = true; }
            check(invalid, "invalid layout cannot request a derivative");
        }
        byte[] png = [137, 80, 78, 71, 13, 10, 26, 10, 1];
        var requests = 0;
        var expectedRoute = "/api/library/thumbnail/7?edge=256";
        HttpResponseMessage Reply(byte[] data, string mime = "image/png", long? size = null)
        {
            var content = new ByteArrayContent(data);
            content.Headers.ContentType = new MediaTypeHeaderValue(mime);
            if (size is long length) content.Headers.ContentLength = length;
            return new(HttpStatusCode.OK) { Content = content };
        }
        Func<HttpResponseMessage> response = () => Reply(png);
        using var api = new LibraryApi(new Stub(request =>
        {
            requests++;
            check(request.RequestUri!.PathAndQuery == expectedRoute, "derived thumbnail uses fixed size route");
            return response();
        }));
        check((await api.ThumbnailAsync(7, 256, CancellationToken.None))!.SequenceEqual(png), "derived PNG consumed without re-encoding");
        response = () => Reply(png, "text/html");
        check(await api.ThumbnailAsync(7, 256, CancellationToken.None) is null, "wrong derived MIME rejected");
        response = () => Reply([1, 2, 3]);
        check(await api.ThumbnailAsync(7, 256, CancellationToken.None) is null, "wrong derived container rejected");
        response = () => Reply(png, size: png.Length + 1);
        check(await api.ThumbnailAsync(7, 256, CancellationToken.None) is null, "truncated derived response rejected");
        response = () => Reply(png, size: PreviewPolicy.MaxSourceBytes + 1);
        check(await api.ThumbnailAsync(7, 256, CancellationToken.None) is null, "oversized derived response rejected before reading");
        response = () => new(HttpStatusCode.NotFound);
        check(await api.ThumbnailAsync(7, 256, CancellationToken.None) is null, "offline thumbnail preserves normal listing");
        response = () => Reply(png);
        expectedRoute += "&priority=nearby";
        check(await api.ThumbnailAsync(7, 256, CancellationToken.None, nearby: true) is not null, "nearby request is explicitly lower priority");
        var previous = requests; var rejected = false;
        try { await api.ThumbnailAsync(7, 257, CancellationToken.None); }
        catch (ArgumentOutOfRangeException) { rejected = true; }
        check(rejected && requests == previous, "invalid size cannot issue a request");
    }
    private sealed class Stub(Func<HttpRequestMessage, HttpResponseMessage> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) => Task.FromResult(send(request));
    }
}
