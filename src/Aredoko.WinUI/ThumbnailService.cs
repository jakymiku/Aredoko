using Aredoko.Core;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

internal sealed class ThumbnailService(LibraryApi api)
{
    private const int MaxMemoryEntries = 1200;
    private const long MaxMemoryBytes = 512L * 1024 * 1024;
    private readonly SemaphoreSlim workers = new(6, 6);
    private readonly SemaphoreSlim prefetchWorkers = new(2, 2);
    private readonly object cacheLock = new();
    private readonly Dictionary<(long Generation, int ItemId, int Edge), LinkedListNode<CacheEntry>> cacheMap = new();
    private readonly LinkedList<CacheEntry> cacheOrder = new();
    private readonly Dictionary<(long Generation, int ItemId, int Edge), Task<byte[]?>> inflight = new();
    private CancellationTokenSource generationCts = new();
    private long currentMemoryBytes;
    private long generation = 1;

    private readonly record struct CacheEntry((long Generation, int ItemId, int Edge) Key, BitmapImage Image, long Bytes);

    public BitmapImage? TryGetCached(MediaRow row, int edge)
    {
        if (row.Availability != "present" || (row.Kind != "image" && row.Kind != "book" && row.Kind != "archive" && row.Kind != "video")) return null;
        lock (cacheLock)
        {
            var key = (generation, row.Id, edge);
            if (!cacheMap.TryGetValue(key, out var node)) return null;
            cacheOrder.Remove(node);
            cacheOrder.AddFirst(node);
            return node.Value.Image;
        }
    }

    public void ResetSession()
    {
        CancellationTokenSource previous;
        lock (cacheLock)
        {
            generation++;
            previous = generationCts;
            generationCts = new CancellationTokenSource();
            inflight.Clear();
            cacheMap.Clear();
            cacheOrder.Clear();
            currentMemoryBytes = 0;
        }
        previous.Cancel();
    }

    public void InvalidateItem(int itemId)
    {
        lock (cacheLock)
        {
            foreach (var key in inflight.Keys.Where(k => k.ItemId == itemId).ToArray())
                inflight.Remove(key);
            foreach (var key in cacheMap.Keys.Where(k => k.ItemId == itemId).ToArray())
            {
                if (cacheMap.Remove(key, out var node))
                {
                    cacheOrder.Remove(node);
                    currentMemoryBytes = Math.Max(0, currentMemoryBytes - node.Value.Bytes);
                }
            }
        }
    }

    private void Put(long expectedGeneration, int itemId, int edge, BitmapImage image, long estimatedBytes)
    {
        lock (cacheLock)
        {
            if (expectedGeneration != generation) return;
            var key = (expectedGeneration, itemId, edge);
            if (cacheMap.TryGetValue(key, out var existing))
            {
                cacheOrder.Remove(existing);
                cacheMap.Remove(key);
                currentMemoryBytes = Math.Max(0, currentMemoryBytes - existing.Value.Bytes);
            }
            var node = new LinkedListNode<CacheEntry>(new CacheEntry(key, image, estimatedBytes));
            cacheOrder.AddFirst(node);
            cacheMap[key] = node;
            currentMemoryBytes += estimatedBytes;
            while ((cacheOrder.Count > MaxMemoryEntries || (currentMemoryBytes > MaxMemoryBytes && cacheOrder.Count > 1)) && cacheOrder.Last is { } oldest)
            {
                cacheOrder.RemoveLast();
                cacheMap.Remove(oldest.Value.Key);
                currentMemoryBytes = Math.Max(0, currentMemoryBytes - oldest.Value.Bytes);
            }
        }
    }

    private async Task<byte[]?> FetchBytesAsync(int itemId, int edge, CancellationToken genToken)
    {
        await workers.WaitAsync(genToken);
        try
        {
            genToken.ThrowIfCancellationRequested();
            return await api.ThumbnailAsync(itemId, edge, genToken);
        }
        finally { workers.Release(); }
    }

    public async Task<BitmapImage?> GetAsync(MediaRow row, CancellationToken cancellation, int edge = PreviewPolicy.Edge)
    {
        if (row.Availability != "present" || (row.Kind != "image" && row.Kind != "book" && row.Kind != "archive" && row.Kind != "video")) return null;
        if (TryGetCached(row, edge) is { } cached) return cached;
        (long Generation, int ItemId, int Edge) key;
        Task<byte[]?> sharedFetch;
        lock (cacheLock)
        {
            key = (generation, row.Id, edge);
            if (!inflight.TryGetValue(key, out sharedFetch!))
            {
                var created = FetchBytesAsync(row.Id, edge, generationCts.Token);
                inflight[key] = created;
                sharedFetch = created;
                _ = created.ContinueWith(_ =>
                {
                    lock (cacheLock)
                    {
                        if (inflight.TryGetValue(key, out var current) && ReferenceEquals(current, created))
                            inflight.Remove(key);
                    }
                }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
            }
        }
        try
        {
            cancellation.ThrowIfCancellationRequested();
            // All supported media thumbnails (including videos) flow through the
            // guarded persistent thumbnail endpoint with live source validation.
            var png = await sharedFetch.WaitAsync(cancellation);
            if (png is null) return null;
            cancellation.ThrowIfCancellationRequested();
            if (TryGetCached(row, edge) is { } racedHit) return racedHit;
            using var stream = new InMemoryRandomAccessStream();
            using (var writer = new DataWriter(stream))
            {
                writer.WriteBytes(png); await writer.StoreAsync(); writer.DetachStream();
            }
            stream.Seek(0);
            var image = new BitmapImage { DecodePixelWidth = edge, DecodePixelType = DecodePixelType.Logical };
            await image.SetSourceAsync(stream);
            cancellation.ThrowIfCancellationRequested();
            var estimatedBytes = Math.Max((long)edge * edge * 4L, png.LongLength * 4L);
            Put(key.Generation, row.Id, edge, image, estimatedBytes);
            return image;
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex) when (ex is HttpRequestException or ObjectDisposedException or IOException)
        {
            // Transient transport/offline failures are retried on next realization.
            cancellation.ThrowIfCancellationRequested(); return null;
        }
        catch (Exception ex) when (ex is System.Runtime.InteropServices.COMException or ArgumentException or InvalidDataException)
        {
            // Unsupported codecs, corrupt sources, and offline media use a label.
            cancellation.ThrowIfCancellationRequested(); return null;
        }
    }

    public async Task PrefetchRowsAsync(IReadOnlyList<MediaRow> rows, int edge, CancellationToken cancellation)
    {
        if (rows.Count == 0) return;
        long expectedGen;
        CancellationToken genToken;
        lock (cacheLock)
        {
            expectedGen = generation;
            genToken = generationCts.Token;
        }
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellation, genToken);
        var token = linked.Token;
        try
        {
            // Let newly realized viewport items issue their visible-priority requests first.
            await Task.Delay(120, token);
            var tasks = new List<Task>(rows.Count);
            foreach (var row in rows)
            {
                if (token.IsCancellationRequested) break;
                if (row.Availability != "present" || (row.Kind != "image" && row.Kind != "book" && row.Kind != "archive" && row.Kind != "video")) continue;
                if (TryGetCached(row, edge) is not null) continue;
                tasks.Add(PrefetchOneAsync(row, edge, expectedGen, token));
            }
            if (tasks.Count > 0) await Task.WhenAll(tasks);
        }
        catch (OperationCanceledException) { }
    }

    private async Task PrefetchOneAsync(MediaRow row, int edge, long expectedGen, CancellationToken token)
    {
        if (token.IsCancellationRequested || TryGetCached(row, edge) is not null) return;
        await prefetchWorkers.WaitAsync(token);
        try
        {
            if (token.IsCancellationRequested || TryGetCached(row, edge) is not null) return;
            lock (cacheLock)
            {
                if (expectedGen != generation || inflight.ContainsKey((expectedGen, row.Id, edge))) return;
            }
            var png = await api.ThumbnailAsync(row.Id, edge, token, nearby: true);
            if (png is null || token.IsCancellationRequested || TryGetCached(row, edge) is not null) return;
            using var stream = new InMemoryRandomAccessStream();
            using (var writer = new DataWriter(stream))
            {
                writer.WriteBytes(png); await writer.StoreAsync(); writer.DetachStream();
            }
            stream.Seek(0);
            var image = new BitmapImage { DecodePixelWidth = edge, DecodePixelType = DecodePixelType.Logical };
            await image.SetSourceAsync(stream);
            if (token.IsCancellationRequested) return;
            var estimatedBytes = Math.Max((long)edge * edge * 4L, png.LongLength * 4L);
            Put(expectedGen, row.Id, edge, image, estimatedBytes);
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) when (ex is HttpRequestException or ObjectDisposedException or IOException or System.Runtime.InteropServices.COMException or ArgumentException or InvalidDataException)
        {
            // Best-effort speculative warm; visible realization retries cleanly.
        }
        finally
        {
            prefetchWorkers.Release();
        }
    }
}
