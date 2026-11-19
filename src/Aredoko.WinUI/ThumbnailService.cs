using Aredoko.Core;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

internal sealed class ThumbnailService(LibraryApi api)
{
    private const int MaxMemoryEntries = 256;
    private readonly SemaphoreSlim workers = new(4, 4);
    private readonly object cacheLock = new();
    private readonly Dictionary<(long Generation, int ItemId, int Edge), LinkedListNode<CacheEntry>> cacheMap = new();
    private readonly LinkedList<CacheEntry> cacheOrder = new();
    private long generation = 1;

    private readonly record struct CacheEntry((long Generation, int ItemId, int Edge) Key, BitmapImage Image);

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
        lock (cacheLock)
        {
            generation++;
            cacheMap.Clear();
            cacheOrder.Clear();
        }
    }

    public void InvalidateItem(int itemId)
    {
        lock (cacheLock)
        {
            var keys = cacheMap.Keys.Where(k => k.ItemId == itemId).ToArray();
            foreach (var key in keys)
            {
                if (cacheMap.Remove(key, out var node))
                    cacheOrder.Remove(node);
            }
        }
    }

    private void Put(long expectedGeneration, int itemId, int edge, BitmapImage image)
    {
        lock (cacheLock)
        {
            if (expectedGeneration != generation) return;
            var key = (expectedGeneration, itemId, edge);
            if (cacheMap.TryGetValue(key, out var existing))
            {
                cacheOrder.Remove(existing);
                cacheMap.Remove(key);
            }
            var node = new LinkedListNode<CacheEntry>(new CacheEntry(key, image));
            cacheOrder.AddFirst(node);
            cacheMap[key] = node;
            while (cacheOrder.Count > MaxMemoryEntries && cacheOrder.Last is { } oldest)
            {
                cacheOrder.RemoveLast();
                cacheMap.Remove(oldest.Value.Key);
            }
        }
    }

    public async Task<BitmapImage?> GetAsync(MediaRow row, CancellationToken cancellation, int edge = PreviewPolicy.Edge)
    {
        if (row.Availability != "present" || (row.Kind != "image" && row.Kind != "book" && row.Kind != "archive" && row.Kind != "video")) return null;
        if (TryGetCached(row, edge) is { } cached) return cached;
        long requestGeneration;
        lock (cacheLock) requestGeneration = generation;
        await workers.WaitAsync(cancellation);
        try
        {
            cancellation.ThrowIfCancellationRequested();
            if (TryGetCached(row, edge) is { } racedHit) return racedHit;
            // All supported media thumbnails (including videos) flow through the
            // guarded persistent thumbnail endpoint with live source validation.
            var png = await api.ThumbnailAsync(row.Id, edge, cancellation);
            if (png is null) return null;
            using var stream = new InMemoryRandomAccessStream();
            using (var writer = new DataWriter(stream))
            {
                writer.WriteBytes(png); await writer.StoreAsync(); writer.DetachStream();
            }
            stream.Seek(0);
            var image = new BitmapImage(); await image.SetSourceAsync(stream);
            cancellation.ThrowIfCancellationRequested();
            Put(requestGeneration, row.Id, edge, image);
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
        finally { workers.Release(); }
    }
}
