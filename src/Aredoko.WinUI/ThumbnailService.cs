using Aredoko.Core;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

internal sealed class ThumbnailService(LibraryApi api)
{
    private const int MaxMemoryEntries = 2000;
    private const long MaxMemoryBytes = 768L * 1024 * 1024;
    private const int MaxPngEntries = 6000;
    private const long MaxPngBytes = 384L * 1024 * 1024;
    private readonly SemaphoreSlim workers = new(8, 8);
    private readonly SemaphoreSlim prefetchWorkers = new(3, 3);
    private readonly object cacheLock = new();
    private readonly Dictionary<(long Generation, int ItemId, int Edge), LinkedListNode<CacheEntry>> cacheMap = new();
    private readonly LinkedList<CacheEntry> cacheOrder = new();
    private readonly Dictionary<(long Generation, int ItemId, int Edge), LinkedListNode<PngEntry>> pngMap = new();
    private readonly LinkedList<PngEntry> pngOrder = new();
    private readonly Dictionary<(long Generation, int ItemId, int Edge), Task<byte[]?>> inflight = new();
    private CancellationTokenSource generationCts = new();
    private long currentMemoryBytes;
    private long currentPngBytes;
    private long generation = 1;

    private readonly record struct CacheEntry((long Generation, int ItemId, int Edge) Key, BitmapImage Image, long Bytes);
    private readonly record struct PngEntry((long Generation, int ItemId, int Edge) Key, byte[] Data);

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

    private byte[]? TryGetPng(long expectedGeneration, int itemId, int edge)
    {
        lock (cacheLock)
        {
            if (expectedGeneration != generation) return null;
            var key = (expectedGeneration, itemId, edge);
            if (!pngMap.TryGetValue(key, out var node)) return null;
            pngOrder.Remove(node);
            pngOrder.AddFirst(node);
            return node.Value.Data;
        }
    }

    private bool HasPng(long expectedGeneration, int itemId, int edge)
    {
        lock (cacheLock)
        {
            if (expectedGeneration != generation) return false;
            var key = (expectedGeneration, itemId, edge);
            return cacheMap.ContainsKey(key) || pngMap.ContainsKey(key);
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
            pngMap.Clear();
            pngOrder.Clear();
            currentPngBytes = 0;
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
            foreach (var key in pngMap.Keys.Where(k => k.ItemId == itemId).ToArray())
            {
                if (pngMap.Remove(key, out var node))
                {
                    pngOrder.Remove(node);
                    currentPngBytes = Math.Max(0, currentPngBytes - node.Value.Data.LongLength);
                }
            }
        }
    }

    private void PutPng(long expectedGeneration, int itemId, int edge, byte[] png)
    {
        if (png.LongLength > MaxPngBytes) return;
        lock (cacheLock)
        {
            if (expectedGeneration != generation) return;
            var key = (expectedGeneration, itemId, edge);
            if (pngMap.TryGetValue(key, out var existing))
            {
                pngOrder.Remove(existing);
                pngMap.Remove(key);
                currentPngBytes = Math.Max(0, currentPngBytes - existing.Value.Data.LongLength);
            }
            var node = new LinkedListNode<PngEntry>(new PngEntry(key, png));
            pngOrder.AddFirst(node);
            pngMap[key] = node;
            currentPngBytes += png.LongLength;
            while ((pngOrder.Count > MaxPngEntries || (currentPngBytes > MaxPngBytes && pngOrder.Count > 1)) && pngOrder.Last is { } oldest)
            {
                pngOrder.RemoveLast();
                pngMap.Remove(oldest.Value.Key);
                currentPngBytes = Math.Max(0, currentPngBytes - oldest.Value.Data.LongLength);
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
        byte[]? cachedPng;
        Task<byte[]?>? sharedFetch = null;
        lock (cacheLock)
        {
            key = (generation, row.Id, edge);
            cachedPng = pngMap.TryGetValue(key, out var pngNode) ? pngNode.Value.Data : null;
            if (cachedPng is not null)
            {
                pngOrder.Remove(pngNode!);
                pngOrder.AddFirst(pngNode!);
            }
            else if (!inflight.TryGetValue(key, out sharedFetch!))
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
            var png = cachedPng ?? await sharedFetch!.WaitAsync(cancellation);
            if (png is null) return null;
            if (cachedPng is null)
                PutPng(key.Generation, row.Id, edge, png);
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
            var pixelBytes = (long)image.PixelWidth * image.PixelHeight * 4L;
            var estimatedBytes = pixelBytes > 0 ? pixelBytes : Math.Max((long)edge * edge * 4L, png.LongLength * 4L);
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
            await Task.Delay(120, token).ConfigureAwait(false);
            var tasks = new List<Task>(rows.Count);
            foreach (var row in rows)
            {
                if (token.IsCancellationRequested) break;
                if (row.Availability != "present" || (row.Kind != "image" && row.Kind != "book" && row.Kind != "archive" && row.Kind != "video")) continue;
                if (HasPng(expectedGen, row.Id, edge)) continue;
                tasks.Add(PrefetchOneAsync(row, edge, expectedGen, token));
            }
            if (tasks.Count > 0) await Task.WhenAll(tasks).ConfigureAwait(false);
        }
        catch (OperationCanceledException) { }
    }

    private async Task PrefetchOneAsync(MediaRow row, int edge, long expectedGen, CancellationToken token)
    {
        if (token.IsCancellationRequested || HasPng(expectedGen, row.Id, edge)) return;
        await prefetchWorkers.WaitAsync(token).ConfigureAwait(false);
        try
        {
            if (token.IsCancellationRequested || HasPng(expectedGen, row.Id, edge)) return;
            lock (cacheLock)
            {
                if (expectedGen != generation || inflight.ContainsKey((expectedGen, row.Id, edge))) return;
            }
            var png = await api.ThumbnailAsync(row.Id, edge, token, nearby: true).ConfigureAwait(false);
            if (png is null || token.IsCancellationRequested) return;
            PutPng(expectedGen, row.Id, edge, png);
        }
        catch (OperationCanceledException) { }
        catch (Exception ex) when (ex is HttpRequestException or ObjectDisposedException or IOException)
        {
            // Best-effort speculative warm into PNG byte cache; UI decodes only on realization.
        }
        finally
        {
            prefetchWorkers.Release();
        }
    }
}
