using System.Buffers.Binary;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class AnimationStreamTests
{
    public static async Task Run(Action<bool, string> check)
    {
        var source = new ImageSourceInfo(7, new string('a', 64), "image/webp", 1400, true);
        string? sessionId = null; var closes = 0; var frameRequests = 0;
        var malformed = false;
        using var handler = new Stub(async request =>
        {
            check(request.Headers.Contains("X-Aredoko-Token") && request.Headers.Contains("Origin"), "animation preserves authenticated owner headers");
            var body = JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
            var id = body["session_id"]!.GetValue<string>();
            if (request.RequestUri!.AbsolutePath.EndsWith("/open"))
            {
                sessionId = id;
                return Json(new JsonObject { ["item_id"] = 7, ["revision"] = source.Revision, ["session_id"] = id,
                    ["max_batch_frames"] = 4, ["max_batch_bytes"] = AnimationStreamClient.MaxBytes });
            }
            var first=request.RequestUri!.AbsolutePath.EndsWith("/open-first");
            if(first){sessionId=id;frameRequests=0;check(body.Count==3&&!body.ContainsKey("count"),"combined open has exact source identity and client-owned ID");}
            check(id == sessionId, "animation close/pull stays with same session");
            if (request.RequestUri.AbsolutePath.EndsWith("/close")) { closes++; return Json(new JsonObject { ["closed"] = true }); }
            frameRequests++;
            var pixels = new byte[] { 10, 20, 30, 128 };
            var header = new JsonObject
            {
                ["session_id"] = id, ["item_id"] = 7, ["revision"] = source.Revision, ["width"] = 1, ["height"] = 1,
                ["stride"] = malformed ? 8 : 4, ["pixel_format"] = "bgra8", ["alpha"] = "premultiplied", ["done"] = false,
                ["frames"] = new JsonArray(new JsonObject { ["sequence"] = frameRequests - 1, ["index"] = first?0:69,
                    ["cycle"] = 0, ["duration_ms"] = 80, ["byte_length"] = 4 })
            };
            var json = Encoding.UTF8.GetBytes(header.ToJsonString());
            var data = new byte[4 + json.Length + pixels.Length]; BinaryPrimitives.WriteInt32LittleEndian(data, json.Length);
            json.CopyTo(data, 4); pixels.CopyTo(data, 4 + json.Length);
            var response = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(data) };
            response.Content.Headers.ContentType = new MediaTypeHeaderValue("application/vnd.aredoko.animation-frame-batch");
            return response;
        });
        using var http = new HttpClient(handler) { BaseAddress = new Uri("http://127.0.0.1:8769/") };
        http.DefaultRequestHeaders.Add("X-Aredoko-Token", "fixture"); http.DefaultRequestHeaders.Add("Origin", "http://127.0.0.1:8769");
        var stream = await new AnimationStreamClient(http).OpenAsync(source, CancellationToken.None);
        check(frameRequests == 0, "animation open never fetches every frame");
        var batch = await stream.ReadAsync(1, CancellationToken.None);
        check(batch.Width == 1 && batch.Height == 1 && batch.Frames[0].Index == 69, "stream accepts frames beyond old 64 cap");
        check(batch.Frames[0].Pixels.SequenceEqual(new byte[] { 10, 20, 30, 128 }) && batch.Frames[0].DurationMs == 80, "binary pixels and duration retained");
        malformed = true; var rejected = false;
        try { await stream.ReadAsync(1, CancellationToken.None); } catch (InvalidDataException) { rejected = true; }
        check(rejected, "invalid stride rejected before allocation/display");
        await stream.DisposeAsync(); await stream.DisposeAsync(); check(closes == 1, "animation close is idempotent");
        rejected = false;
        try { await stream.ReadAsync(1, CancellationToken.None); } catch (ObjectDisposedException) { rejected = true; }
        check(rejected && frameRequests == 2, "closed stream never requests another frame");
        malformed=false;var opened=await new AnimationStreamClient(http).OpenFirstAsync(source,CancellationToken.None);
        check(frameRequests==1&&opened.First.Frames.Count==1&&opened.First.Frames[0].Sequence==0,"combined open delivers first frame in one request");
        var next=await opened.Stream.ReadAsync(2,CancellationToken.None);
        check(next.Frames[0].Sequence==1&&frameRequests==2,"combined open continues without repeating or skipping first frame");
        await opened.Stream.DisposeAsync();check(closes==2,"combined first frame retains ordinary close ownership");
        malformed=true;rejected=false;
        try{await new AnimationStreamClient(http).OpenFirstAsync(source,CancellationToken.None);}catch(InvalidDataException){rejected=true;}
        check(rejected&&closes==3,"malformed combined first response closes its preallocated session ID");
    }
    private static HttpResponseMessage Json(JsonObject body) => new(HttpStatusCode.OK) { Content = new ByteArrayContent(Encoding.UTF8.GetBytes(body.ToJsonString())) };
    private sealed class Stub(Func<HttpRequestMessage, Task<HttpResponseMessage>> handle) : HttpMessageHandler
    { protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) => handle(request); }
}
