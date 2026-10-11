using Aredoko.Core;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

// Uses built-in Windows codecs; all output is a derived, bounded PNG in memory.
internal static class ThumbnailCodec
{
    public static async Task<byte[]> ResizeAsync(byte[] source, CancellationToken cancellation)
    {
        if (source.Length > PreviewPolicy.MaxSourceBytes) throw new InvalidDataException("Preview source too large");
        using var input = new InMemoryRandomAccessStream();
        using (var writer = new DataWriter(input))
        {
            writer.WriteBytes(source); await writer.StoreAsync(); writer.DetachStream();
        }
        input.Seek(0);
        cancellation.ThrowIfCancellationRequested();
        var decoder = await BitmapDecoder.CreateAsync(input);
        PreviewPolicy.ValidateDimensions(decoder.PixelWidth, decoder.PixelHeight);
        var scale = Math.Min(1, (double)PreviewPolicy.Edge / Math.Max(decoder.PixelWidth, decoder.PixelHeight));
        var transform = new BitmapTransform
        {
            ScaledWidth = Math.Max(1, (uint)Math.Round(decoder.PixelWidth * scale)),
            ScaledHeight = Math.Max(1, (uint)Math.Round(decoder.PixelHeight * scale)),
            InterpolationMode = BitmapInterpolationMode.Fant
        };
        cancellation.ThrowIfCancellationRequested();
        var pixels = await decoder.GetPixelDataAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied,
            transform, ExifOrientationMode.RespectExifOrientation, ColorManagementMode.ColorManageToSRgb);
        cancellation.ThrowIfCancellationRequested();
        uint width = Math.Max(1, (uint)Math.Round(decoder.OrientedPixelWidth * scale));
        uint height = Math.Max(1, (uint)Math.Round(decoder.OrientedPixelHeight * scale));
        using var output = new InMemoryRandomAccessStream();
        var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, output);
        encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied, width, height, 96, 96, pixels.DetachPixelData());
        await encoder.FlushAsync();
        cancellation.ThrowIfCancellationRequested();
        output.Seek(0);
        using var reader = new DataReader(output);
        await reader.LoadAsync((uint)output.Size);
        var result = new byte[(int)output.Size]; reader.ReadBytes(result);
        return result;
    }
}
