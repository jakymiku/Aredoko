using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
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
public sealed class ResultSessionClient(HttpClient client,HttpClient? creationClient=null)
{
    public Task<ResultSession> CreateAsync(JsonObject conditions,CancellationToken cancellation)=>CreateAsync(conditions,cancellation,null);

    public async Task<ResultSession> CreateAsync(JsonObject conditions, CancellationToken cancellation,IProgress<ResultBuildProgress>? progress)
    {
        var id = Guid.NewGuid().ToString("N"); var frozen = conditions.DeepClone().AsObject();
        var session = new ResultSession(client, id, frozen);
        using var observing=CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        var observer=progress is null?Task.CompletedTask:ObserveAsync(id,frozen,progress,observing.Token);
        try
        {
            // Even literal results freeze/check the full matched library.
            // Only creation gets the longer timeout; range and close retain
            // their ordinary control transport and caller cancellation.
            var root = await SendAsync(creationClient??client, "create", new JsonObject { ["session_id"] = id, ["conditions"] = frozen.DeepClone() }, cancellation);
            if (root["session_id"]?.GetValue<string>() != id || root["state"]?.GetValue<string>() != "ready" ||
                !JsonNode.DeepEquals(root["conditions"], frozen) || root["range_limit"]?.GetValue<int>() != 120 ||
                root["idle_seconds"]?.GetValue<int>() != 900 || root["total"]?.GetValue<int>() is not int total || total < 0)
                throw new InvalidDataException("Invalid result session");
            session.Total = total;
            session.FavoritePatchSupported=root["favorite_patch_supported"]?.GetValue<bool>()==true;
            return session;
        }
        catch { await session.DisposeAsync(); throw; }
        finally
        {
            observing.Cancel();
            await observer;
        }
    }

    private async Task ObserveAsync(string id,JsonObject conditions,IProgress<ResultBuildProgress> progress,CancellationToken stop)
    {
        while(!stop.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(TimeSpan.FromSeconds(1),stop);
                using var deadline=CancellationTokenSource.CreateLinkedTokenSource(stop);
                deadline.CancelAfter(TimeSpan.FromSeconds(2));
                var root=await SendAsync(client,"status",new(){["session_id"]=id},deadline.Token);
                var value=ResultBuildProgress.Parse(root,id,conditions);
                if(value.State=="ready")return;
                progress.Report(value);
            }
            catch(OperationCanceledException){if(stop.IsCancellationRequested)return;}
            catch(ResultSessionException ex) when(ex.Status==HttpStatusCode.Gone){ } // create admission may still be queued
            catch(Exception ex) when(ex is ResultSessionException or HttpRequestException or InvalidOperationException or IOException or JsonException or FormatException or OverflowException)
            {return;} // Optional progress must not break creation/older servers.
        }
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
        if (response.StatusCode == HttpStatusCode.Gone ||
            response.StatusCode == HttpStatusCode.Conflict && root["error_code"]?.GetValue<string>() == "result_session_changed")
            throw new ResultSessionException(response.StatusCode, root["conditions"]?.ToJsonString(), root["current_id"]?.GetValue<int>());
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException(ErrorText.FromResponse(root.ToJsonString(), (int)response.StatusCode));
        return root;
    }
}

public sealed class ResultSession(HttpClient client, string id, JsonObject conditions) : IAsyncDisposable
{
    private int disposed;
    public string Id => id;
    public int Total { get; internal set; }
    public bool FavoritePatchSupported { get; internal set; }
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
        if (conditions["mode"]?.GetValue<string>() is "similar" or "audio-similar" or "video-similar")
        {
            root["page"] = offset / limit;
            return SimilaritySearch.Parse(root.ToJsonString(), conditions["item_id"]!.GetValue<int>(), offset / limit, limit, offset,
                directAudio:conditions["mode"]!.GetValue<string>()=="audio-similar",
                directVideo:conditions["mode"]!.GetValue<string>()=="video-similar");
        }
        var result = Protocol.ParseSearch(root.ToJsonString());
        if(conditions["mode"]?.GetValue<string>()=="video-direct" &&
            (root["source"]?.GetValue<string>()!="video-direct" || result.Items.Any(row=>row.VideoMatchSource!="direct-video" || row.SimilarityOriginId is not null)))
            throw new InvalidDataException("Invalid direct-video result namespace");
        if (result.Items.Any(row => row.Id < 1) || result.Items.Select(row => row.Id).Distinct().Count() != result.Items.Count)
            throw new InvalidDataException("Invalid frozen result identities");
        return result;
    }

    public async Task<IReadOnlyList<ResultPosition>> LocateAsync(IReadOnlyList<int> itemIds,CancellationToken cancellation)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed)!=0,this);
        ValidateSelectionIds(itemIds);
        var response=await ResultSessionClient.SendAsync(client,"locate",new JsonObject
            {["session_id"]=id,["item_ids"]=new JsonArray(itemIds.Select(value=>JsonValue.Create(value)).ToArray())},cancellation);
        if(response["session_id"]?.GetValue<string>()!=id||!JsonNode.DeepEquals(response["conditions"],conditions))throw new InvalidDataException("Invalid selection scope");
        var positions=response["positions"]?.AsArray().Select(row=>new ResultPosition(row!["id"]!.GetValue<int>(),row["ordinal"]!.GetValue<int>())).ToArray()
            ??throw new InvalidDataException("Invalid selection positions");
        if(positions.Any(row=>!itemIds.Contains(row.Id)||row.Ordinal<0||row.Ordinal>=Total)
            ||positions.Select(row=>row.Id).Distinct().Count()!=positions.Length||positions.Select(row=>row.Ordinal).Distinct().Count()!=positions.Length
            ||!positions.Select(row=>row.Ordinal).SequenceEqual(positions.Select(row=>row.Ordinal).Order()))throw new InvalidDataException("Invalid selection order");
        return positions;
    }
    private static void ValidateSelectionIds(IReadOnlyList<int> itemIds)
    {
        if(itemIds.Count is <1 or >LibrarySelection.Maximum||itemIds.Any(id=>id<1)||itemIds.Distinct().Count()!=itemIds.Count)
            throw new ArgumentException("Select 1 to 256 distinct item IDs",nameof(itemIds));
    }
    public async Task EditSelectionAsync(IReadOnlyList<int> itemIds,SelectionOperation operation,IReadOnlyList<long> shelfIds,CancellationToken cancellation)
        =>await EditSelectionCoreAsync(itemIds,operation,shelfIds,false,cancellation);

    public Task<bool> EditFavoriteAsync(int itemId,bool value,CancellationToken cancellation)
        =>EditFavoritesAsync([itemId],value,cancellation);

    public Task<bool> EditFavoritesAsync(IReadOnlyList<int> itemIds,bool value,CancellationToken cancellation)
        =>EditSelectionCoreAsync(itemIds,value?SelectionOperation.FavoriteAdd:SelectionOperation.FavoriteRemove,[],FavoritePatchSupported,cancellation);

    private async Task<bool> EditSelectionCoreAsync(IReadOnlyList<int> itemIds,SelectionOperation operation,IReadOnlyList<long> shelfIds,bool keepSession,CancellationToken cancellation)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed)!=0,this);ValidateSelectionIds(itemIds);ShelfProtocol.ValidateIds(shelfIds);
        var wire=operation switch{SelectionOperation.FavoriteAdd=>"favorite_add",SelectionOperation.FavoriteRemove=>"favorite_remove",SelectionOperation.ShelvesAdd=>"shelves_add",SelectionOperation.ShelvesRemove=>"shelves_remove",_=>throw new ArgumentOutOfRangeException(nameof(operation))};
        if((operation is SelectionOperation.FavoriteAdd or SelectionOperation.FavoriteRemove)&&shelfIds.Count!=0
            ||(operation is SelectionOperation.ShelvesAdd or SelectionOperation.ShelvesRemove)&&shelfIds.Count==0)throw new ArgumentException("Invalid shelves for operation");
        var body=new JsonObject
            {["session_id"]=id,["item_ids"]=new JsonArray(itemIds.Select(value=>JsonValue.Create(value)).ToArray()),
             ["operation"]=wire,["shelf_ids"]=new JsonArray(shelfIds.Select(value=>JsonValue.Create(value)).ToArray())};
        if(keepSession)body["keep_session"]=true;
        var response=await ResultSessionClient.SendAsync(client,"edit",body,cancellation);
        if(response["session_id"]?.GetValue<string>()!=id||response["operation"]?.GetValue<string>()!=wire||response["updated"]?.GetValue<int>()!=itemIds.Count
            ||response["item_ids"]?.AsArray().Select(node=>node!.GetValue<int>()).SequenceEqual(itemIds)!=true)throw new InvalidDataException("Invalid selection edit acknowledgment");
        if(keepSession&&response["kept_session"] is null)throw new InvalidDataException("Missing result retention acknowledgment");
        return keepSession&&response["kept_session"]!.GetValue<bool>();
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
