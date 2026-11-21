using Aredoko.Core;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

internal sealed class ThumbnailService(LibraryApi api)
{
    private const int MaxMemoryEntries = 256;
    private const long MaxMemoryBytes = 128L * 1024 * 1024;
    private readonly SemaphoreSlim workers = new(4, 4);
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
            var image = new BitmapImage(); await image.SetSourceAsync(stream);
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
}
