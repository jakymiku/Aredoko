using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

internal static class ResultSessionTests
{
    public static async Task Run(Action<bool, string> check)
    {
        var conditions = new JsonObject { ["mode"] = "literal", ["query"] = "generated" };
        string? id = null; var closes = 0; var touches = 0; var expired = false;
        JsonObject Item(int number) => new()
        {
            ["id"] = number, ["title"] = $"{number}.png", ["kind"] = "image", ["tags"] = new JsonArray(),
            ["shelf"] = "", ["favorite"] = false, ["reviewed"] = false,
            ["relative_path"] = $"{number}.png", ["availability"] = "present"
        };
        using var handler = new Stub(async request =>
        {
            check(request.Headers.Contains("X-Aredoko-Token"), "result requests retain session authentication");
            var body = JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
            var sid = body["session_id"]!.GetValue<string>();
            if (request.RequestUri!.AbsolutePath.EndsWith("/create"))
            {
                id = sid;
                return Reply(new JsonObject { ["session_id"] = id, ["state"] = "ready", ["total"] = 125,
                    ["conditions"] = conditions.DeepClone(), ["range_limit"] = 120, ["idle_seconds"] = 900 });
            }
            check(id == sid, "range and neighbor use one frozen result ID");
            if (request.RequestUri.AbsolutePath.EndsWith("/close")) { closes++; return Reply(new JsonObject { ["closed"] = true }); }
            if (expired) return Reply(new JsonObject { ["conditions"] = conditions.DeepClone(), ["current_id"] = 60 }, HttpStatusCode.Gone);
            if (request.RequestUri.AbsolutePath.EndsWith("/status"))
            {
                touches++;
                return Reply(new JsonObject { ["session_id"] = id, ["state"] = "ready", ["total"] = 125, ["processed"] = 125, ["conditions"] = conditions.DeepClone() });
            }
            if (request.RequestUri.AbsolutePath.EndsWith("/neighbor"))
            {
                check(body["item_id"]!.GetValue<int>() == 60, "neighbor is relative to selected ID");
                return Reply(new JsonObject { ["session_id"] = id, ["current_id"] = 60, ["conditions"] = conditions.DeepClone(),
                    ["neighbor"] = new JsonObject { ["ordinal"] = 60, ["item"] = Item(61) } });
            }
            var offset = body["offset"]!.GetValue<int>(); var limit = body["limit"]!.GetValue<int>(); var items = new JsonArray();
            for (var number = offset + 1; number <= Math.Min(125, offset + limit); number++) items.Add(Item(number));
            return Reply(new JsonObject { ["session_id"] = id, ["state"] = "ready", ["total"] = 125,
                ["offset"] = offset, ["limit"] = limit, ["conditions"] = conditions.DeepClone(), ["items"] = items });
        });
        using var http = new HttpClient(handler) { BaseAddress = new Uri("http://127.0.0.1:8769/") };
        http.DefaultRequestHeaders.Add("X-Aredoko-Token", "fixture");
        var session = await new ResultSessionClient(http).CreateAsync(conditions, CancellationToken.None);
        session.Conditions["query"] = "mutated copy";
        check(session.Conditions["query"]!.GetValue<string>() == "generated", "result conditions are immutable to callers");
        var range = await session.RangeAsync(60, 60, CancellationToken.None);
        check(range.Items[0].Id == 61 && range.Items.Count == 60, "client range traverses 60/61 without a new search");
        await session.TouchAsync(CancellationToken.None);
        check(touches == 1, "client touch sends a status keep-alive for the frozen result ID");
        var neighbor = await session.NeighborAsync(60, 1, CancellationToken.None);
        check(neighbor?.Item.Id == 61 && neighbor.Ordinal == 60, "client neighbor keeps global ordinal");
        expired = true; var preserved = false;
        try { await session.NeighborAsync(60, 1, CancellationToken.None); }
        catch (ResultSessionException error) { preserved = error.Status == HttpStatusCode.Gone && error.CurrentId == 60 && error.Conditions!.Contains("generated"); }
        check(preserved, "expiry is an explicit refresh with current ID and conditions");
        await session.DisposeAsync(); await session.DisposeAsync(); check(closes == 1, "result session owns one idempotent close");
        using var missingHandler = new Stub(request => Task.FromResult(request.RequestUri!.AbsolutePath.EndsWith("/close")
            ? Reply(new JsonObject { ["closed"] = true })
            : Reply(new JsonObject { ["error"] = "AI環境が未導入です。", ["error_code"] = "ai_unavailable" }, HttpStatusCode.ServiceUnavailable)));
        using var missing = new HttpClient(missingHandler) { BaseAddress = http.BaseAddress };
        var explained = false;
        try { await new ResultSessionClient(missing).CreateAsync(conditions, CancellationToken.None); }
        catch (InvalidOperationException error) { explained = error.Message.Contains("未導入"); }
        check(explained, "result creation preserves AI missing guidance rather than reporting image decoder busy");

        using var aiIndexingHandler = new Stub(request => Task.FromResult(request.RequestUri!.AbsolutePath.EndsWith("/close")
            ? Reply(new JsonObject { ["closed"] = true })
            : Reply(new JsonObject
            {
                ["error"] = "Results expired or changed; refresh search",
                ["error_code"] = "result_session_changed",
                ["ai_indexing"] = true,
                ["conditions"] = new JsonObject { ["mode"] = "semantic", ["query"] = "sunset" },
                ["current_id"] = 42
            }, HttpStatusCode.Conflict)));
        using var aiIndexingHttp = new HttpClient(aiIndexingHandler) { BaseAddress = http.BaseAddress };
        var aiIndexingFlagged = false;
        try { await new ResultSessionClient(aiIndexingHttp).CreateAsync(new JsonObject { ["mode"] = "semantic", ["query"] = "sunset" }, CancellationToken.None); }
        catch (ResultSessionException error)
        {
            aiIndexingFlagged = error.Status == HttpStatusCode.Conflict && error.AIIndexing && error.CurrentId == 42 && error.Message.Contains("AI検索データの作成中");
        }
        check(aiIndexingFlagged, "result_session_changed with ai_indexing=true surfaces AI indexing guidance");

        using var ordinaryConflictHandler = new Stub(request => Task.FromResult(request.RequestUri!.AbsolutePath.EndsWith("/close")
            ? Reply(new JsonObject { ["closed"] = true })
            : Reply(new JsonObject
            {
                ["error"] = "Results expired or changed; refresh search",
                ["error_code"] = "result_session_changed",
                ["conditions"] = conditions.DeepClone()
            }, HttpStatusCode.Conflict)));
        using var ordinaryConflictHttp = new HttpClient(ordinaryConflictHandler) { BaseAddress = http.BaseAddress };
        var ordinaryConflictNotFlagged = false;
        try { await new ResultSessionClient(ordinaryConflictHttp).CreateAsync(conditions, CancellationToken.None); }
        catch (ResultSessionException error)
        {
            ordinaryConflictNotFlagged = error.Status == HttpStatusCode.Conflict && !error.AIIndexing;
        }
        check(ordinaryConflictNotFlagged, "result_session_changed without ai_indexing keeps AIIndexing false");
    }
    private static HttpResponseMessage Reply(JsonObject body, HttpStatusCode status = HttpStatusCode.OK) => new(status)
    { Content = new ByteArrayContent(Encoding.UTF8.GetBytes(body.ToJsonString())) };
    private sealed class Stub(Func<HttpRequestMessage, Task<HttpResponseMessage>> handle) : HttpMessageHandler
    { protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) => handle(request); }
}
