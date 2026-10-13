using Aredoko.Core;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;

internal static class ArchiveReaderTests
{
    public static async Task Run(Action<bool, string> check)
    {
        var revision = new string('a', 64);
        var json = "{\"item_id\":7,\"page_count\":3,\"revision\":\"" + revision + "\"}";
        var manifest = ArchiveManifest.Parse(Encoding.UTF8.GetBytes(json), 7);
        check(manifest.ItemId == 7 && manifest.PageCount == 3 && manifest.Revision == revision, "reader reflection-free manifest");
        foreach (var invalid in new[] { "{}", "[]", "null", "not json",
            json.Replace("\"item_id\":7", "\"item_id\":true"),
            json.Replace("\"item_id\":7", "\"item_id\":8"),
            json.Replace("\"page_count\":3", "\"page_count\":0"),
            json.Replace("\"page_count\":3", "\"page_count\":10001"),
            json.Replace("\"page_count\":3", "\"page_count\":999999999999999"),
            json.Replace(revision, new string('A', 64)), json.Replace(revision, "short") })
        {
            var rejected = false;
            try { ArchiveManifest.Parse(Encoding.UTF8.GetBytes(invalid), 7); }
            catch (InvalidDataException) { rejected = true; }
            check(rejected, "invalid reader manifest rejected " + invalid[..Math.Min(45, invalid.Length)]);
        }
        var row = Protocol.ParseItem("""{"id":7,"title":"本","kind":"book","tags":[],"shelf":"","favorite":false,"reviewed":false,"relative_path":"folder/book.CBZ","availability":"present"}""");
        check(ArchiveManifest.CanOpen(row), "present uppercase CBZ can open");
        var unsupported = Protocol.ParseItem("""{"id":8,"title":"本","kind":"book","tags":[],"shelf":"","favorite":false,"reviewed":false,"relative_path":"book.pdf","availability":"present"}""");
        check(!ArchiveManifest.CanOpen(unsupported), "unsupported book does not advertise reader");
        var missing = Protocol.ParseItem("""{"id":8,"title":"本","kind":"book","tags":[],"shelf":"","favorite":false,"reviewed":false,"relative_path":"book.cbz","availability":"missing"}""");
        check(!ArchiveManifest.CanOpen(missing), "missing archive does not advertise reader");

        async Task Reject<T>(Func<Task> action, string label) where T : Exception
        {
            var rejected = false;
            try { await action(); } catch (T) { rejected = true; }
            check(rejected, label);
        }
        var calls = new List<string>();
        using var transport = new StubHandler((request, token) =>
        {
            calls.Add(request.RequestUri!.PathAndQuery);
            check(request.Headers.Contains("X-Aredoko-Token"), "reader keeps authenticated session");
            return Task.FromResult(Response(request.RequestUri.AbsolutePath.EndsWith("/7")
                ? Encoding.UTF8.GetBytes(json) : new byte[] { 1, 2, 3 },
                request.RequestUri.AbsolutePath.EndsWith("/7") ? "application/json" : "image/png"));
        });
        using var client = new HttpClient(transport) { BaseAddress = new Uri("http://127.0.0.1:8769/") };
        client.DefaultRequestHeaders.Add("X-Aredoko-Token", "fixture-token");
        var reader = new ArchiveReaderClient(client);
        check(await reader.ManifestAsync(7, CancellationToken.None) == manifest, "reader fetches manifest from fixed route");
        check((await reader.PageAsync(manifest, 2, CancellationToken.None)).SequenceEqual(new byte[] { 1, 2, 3 }), "reader returns bounded page bytes");
        check(calls.SequenceEqual(new[] { "/api/library/reader/7", "/api/library/reader/7/pages/2?revision=" + revision }), "page route freezes revision and zero-based index");
        await Reject<ArgumentOutOfRangeException>(() => reader.PageAsync(manifest, -1, CancellationToken.None), "negative page rejected before HTTP");
        await Reject<ArgumentOutOfRangeException>(() => reader.PageAsync(manifest, 3, CancellationToken.None), "past-last page rejected before HTTP");
        await Reject<InvalidDataException>(() => reader.PageAsync(manifest with { Revision = "../private" }, 0, CancellationToken.None), "revision cannot inject path");
        check(calls.Count == 2, "invalid page requests never reach transport");

        foreach (var code in new[] { HttpStatusCode.Conflict, HttpStatusCode.Forbidden, HttpStatusCode.NotFound, HttpStatusCode.ServiceUnavailable })
        {
            using var stub = new StubHandler((_, _) => Task.FromResult(new HttpResponseMessage(code)));
            using var http = new HttpClient(stub) { BaseAddress = client.BaseAddress };
            ArchiveReadException? observed = null;
            try { await new ArchiveReaderClient(http).PageAsync(manifest, 0, CancellationToken.None); }
            catch (ArchiveReadException ex) { observed = ex; }
            check(observed?.Status == code && observed.RequiresReopen == (code is HttpStatusCode.Conflict or HttpStatusCode.Forbidden), "reader status recovery " + code);
        }
        foreach (var (bytes, length, mime) in new[] {
            (new byte[] { 1 }, (long)PreviewPolicy.MaxSourceBytes + 1, "image/png"),
            (new byte[] { 1 }, 0L, "image/png"),
            (new byte[] { 1 }, 2L, "image/png"),
            (new byte[] { 1, 2 }, 1L, "image/png"),
            (new byte[] { 1 }, 1L, "text/html") })
        {
            using var stub = new StubHandler((_, _) =>
            {
                var response = Response(bytes, mime); response.Content.Headers.ContentLength = length;
                return Task.FromResult(response);
            });
            using var http = new HttpClient(stub) { BaseAddress = client.BaseAddress };
            await Reject<InvalidDataException>(() => new ArchiveReaderClient(http).PageAsync(manifest, 0, CancellationToken.None), "reader rejects size/MIME " + length + "/" + mime);
        }
        using var cancellation = new CancellationTokenSource();
        using var slow = new StubHandler(async (_, token) =>
        {
            cancellation.Cancel(); await Task.Delay(Timeout.Infinite, token);
            return Response([], "image/png");
        });
        using var slowClient = new HttpClient(slow) { BaseAddress = client.BaseAddress };
        await Reject<OperationCanceledException>(() => new ArchiveReaderClient(slowClient).PageAsync(manifest, 0, cancellation.Token), "closing reader cancels transport");
    }

    private static HttpResponseMessage Response(byte[] data, string mime)
    {
        var response = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(data) };
        response.Content.Headers.ContentType = new MediaTypeHeaderValue(mime);
        return response;
    }

    private sealed class StubHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> handle) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => handle(request, cancellationToken);
    }
}
