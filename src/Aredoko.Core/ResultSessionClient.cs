using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed class ResultSessionException(HttpStatusCode status, string? conditions, int? currentId)
    : Exception("検索結果が更新されたか、有効期限が切れました。条件を保って再検索してください。")
{
    public HttpStatusCode Status { get; } = status;
    public string? Conditions { get; } = conditions;
    public int? CurrentId { get; } = currentId;
}

public sealed record ResultNeighbor(int Ordinal, MediaRow Item);

// Shared contracts only: rendering, selection, drafts and scrolling belong to
// the native frontend. All range/neighbor reads use the same owned search ID.
public sealed class ResultSessionClient(HttpClient client)
{
    public async Task<ResultSession> CreateAsync(JsonObject conditions, CancellationToken cancellation)
    {
        var id = Guid.NewGuid().ToString("N"); var frozen = conditions.DeepClone().AsObject();
        var session = new ResultSession(client, id, frozen);
        try
        {
            var root = await SendAsync(client, "create", new JsonObject { ["session_id"] = id, ["conditions"] = frozen.DeepClone() }, cancellation);
            if (root["session_id"]?.GetValue<string>() != id || root["state"]?.GetValue<string>() != "ready" ||
                !JsonNode.DeepEquals(root["conditions"], frozen) || root["range_limit"]?.GetValue<int>() != 120 ||
                root["idle_seconds"]?.GetValue<int>() != 900 || root["total"]?.GetValue<int>() is not int total || total < 0)
                throw new InvalidDataException("Invalid result session");
            session.Total = total;
            return session;
        }
        catch { await session.DisposeAsync(); throw; }
    }

    internal static async Task<JsonObject> SendAsync(HttpClient client, string action, JsonObject payload, CancellationToken cancellation)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "api/library/results/" + action)
        { Content = new StringContent(payload.ToJsonString(), Encoding.UTF8, "application/json") };
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        if (response.Content.Headers.ContentLength is not long length || length is < 1 or > 8 * 1024 * 1024)
            throw new InvalidDataException("Invalid result response size");
        await using var source = await response.Content.ReadAsStreamAsync(cancellation);
        var bytes = new byte[(int)length]; await source.ReadExactlyAsync(bytes, cancellation);
        var root = JsonNode.Parse(bytes)?.AsObject() ?? throw new InvalidDataException("Invalid result response");
        if (response.StatusCode is HttpStatusCode.Conflict or HttpStatusCode.Gone)
            throw new ResultSessionException(response.StatusCode, root["conditions"]?.ToJsonString(), root["current_id"]?.GetValue<int>());
        if (!response.IsSuccessStatusCode) throw new ArchiveReadException(response.StatusCode);
        return root;
    }
}

public sealed class ResultSession(HttpClient client, string id, JsonObject conditions) : IAsyncDisposable
{
    private int disposed;
    public string Id => id;
    public int Total { get; internal set; }
    public JsonObject Conditions => conditions.DeepClone().AsObject();

    private void Validate(JsonObject response)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
        if (response["session_id"]?.GetValue<string>() != id || !JsonNode.DeepEquals(response["conditions"], conditions))
            throw new InvalidDataException("Result identity or conditions changed");
    }

    public async Task<SearchResponse> RangeAsync(int offset, int limit, CancellationToken cancellation)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
        if (offset < 0 || limit is < 1 or > 120) throw new ArgumentOutOfRangeException(nameof(offset));
        var root = await ResultSessionClient.SendAsync(client, "range", new JsonObject
        { ["session_id"] = id, ["offset"] = offset, ["limit"] = limit }, cancellation);
        Validate(root);
        if (root["offset"]?.GetValue<int>() != offset || root["limit"]?.GetValue<int>() != limit ||
            root["total"]?.GetValue<int>() != Total || root["state"]?.GetValue<string>() != "ready" ||
            root["items"] is not JsonArray items || items.Count != Math.Min(limit, Math.Max(0, Total - offset)))
            throw new InvalidDataException("Invalid frozen result range");
        return Protocol.ParseSearch(root.ToJsonString());
    }

    public async Task<ResultNeighbor?> NeighborAsync(int itemId, int direction, CancellationToken cancellation)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
        if (itemId < 1 || direction is not (-1 or 1)) throw new ArgumentOutOfRangeException(nameof(itemId));
        var root = await ResultSessionClient.SendAsync(client, "neighbor", new JsonObject
        { ["session_id"] = id, ["item_id"] = itemId, ["direction"] = direction }, cancellation);
        Validate(root);
        if (root["current_id"]?.GetValue<int>() != itemId) throw new InvalidDataException("Result origin changed");
        if (root["neighbor"] is null) return null;
        var neighbor = root["neighbor"]!.AsObject(); var ordinal = neighbor["ordinal"]!.GetValue<int>();
        var row = Protocol.ParseItem(neighbor["item"]!.ToJsonString());
        if (ordinal < 0 || ordinal >= Total || row.Id == itemId || !ImageViewerPolicy.CanOpen(row))
            throw new InvalidDataException("Invalid image neighbor");
        return new(ordinal, row);
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref disposed, 1) != 0) return;
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        try { await ResultSessionClient.SendAsync(client, "close", new JsonObject { ["session_id"] = id }, timeout.Token); }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or ObjectDisposedException or ArchiveReadException or ResultSessionException or IOException or System.Text.Json.JsonException or InvalidOperationException)
        { /* Owned backend idle cleanup handles a lost connection. */ }
    }
}
