using Aredoko.Core;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

internal sealed class ThumbnailService(LibraryApi api)
{
    private readonly SemaphoreSlim workers = new(2, 2);
    private readonly BoundedLru<string, byte[]?> cache = new(PreviewPolicy.CacheEntries);
    public void Clear() => cache.Clear();

    public async Task<BitmapImage?> GetAsync(MediaRow row, CancellationToken cancellation)
    {
        if (row.Availability != "present" || (row.Kind != "image" && row.Kind != "book" && row.Kind != "archive")) return null;
        await workers.WaitAsync(cancellation);
        try
        {
            cancellation.ThrowIfCancellationRequested();
            if (!cache.TryGet(row.PreviewKey, out var png))
            {
                var source = await api.PreviewAsync(row.Id, cancellation);
                png = source is null ? null : await ThumbnailCodec.ResizeAsync(source, cancellation);
                cancellation.ThrowIfCancellationRequested();
                cache.Set(row.PreviewKey, png);
            }
            if (png is null) return null;
            using var stream = new InMemoryRandomAccessStream();
            using (var writer = new DataWriter(stream))
            {
                writer.WriteBytes(png); await writer.StoreAsync(); writer.DetachStream();
            }
            stream.Seek(0);
            var image = new BitmapImage(); await image.SetSourceAsync(stream);
            cancellation.ThrowIfCancellationRequested();
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
            // Cache failures for this source revision so scrolling cannot retry forever.
            cancellation.ThrowIfCancellationRequested(); cache.Set(row.PreviewKey, null); return null;
        }
        finally { workers.Release(); }
    }
}
