using Aredoko.Core;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

internal sealed class ThumbnailService(LibraryApi api)
{
    private readonly SemaphoreSlim workers = new(2, 2);

    public async Task<BitmapImage?> GetAsync(MediaRow row, CancellationToken cancellation, int edge = PreviewPolicy.Edge)
    {
        if (row.Availability != "present" || (row.Kind != "image" && row.Kind != "book" && row.Kind != "archive" && row.Kind != "video")) return null;
        await workers.WaitAsync(cancellation);
        try
        {
            cancellation.ThrowIfCancellationRequested();
            // Each realization reaches a guarded backend cache. A row-key-only
            // local hit cannot authorize current scope or physical source.
            // Video's existing preview endpoint also emits a bounded 256px PNG.
            var png = row.Kind == "video"
                ? await api.PreviewAsync(row.Id, cancellation)
                : await api.ThumbnailAsync(row.Id, edge, cancellation);
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
            cancellation.ThrowIfCancellationRequested(); return null;
        }
        finally { workers.Release(); }
    }
}
