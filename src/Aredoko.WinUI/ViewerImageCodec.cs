using Aredoko.Core;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

// Decode single-frame originals with Windows codecs without downsampling or
// re-encoding. Multi-frame fallback below keeps only frame zero; animation
// playback and thumbnail preprocessing stay separate.
internal static class ViewerImageCodec
{
    public static async Task<BitmapImage> DecodeAsync(byte[] source,CancellationToken cancellation)
    {
        if(source.Length==0||source.Length>PreviewPolicy.ViewerSourceBytes)throw new InvalidDataException("Viewer source too large");
        using var stream=new InMemoryRandomAccessStream();
        using(var writer=new DataWriter(stream)){writer.WriteBytes(source);await writer.StoreAsync();writer.DetachStream();}
        stream.Seek(0);cancellation.ThrowIfCancellationRequested();
        var decoder=await BitmapDecoder.CreateAsync(stream);
        PreviewPolicy.ValidateViewerDimensions(decoder.PixelWidth,decoder.PixelHeight);
        // Reader pages and fallback views show a single frame. Explicitly decode
        // frame zero for multi-frame formats; never create an unbounded frame cache.
        if(decoder.FrameCount>1)
        {
            var frame=await decoder.GetFrameAsync(0);
            var pixels=await frame.GetPixelDataAsync(BitmapPixelFormat.Bgra8,BitmapAlphaMode.Premultiplied,
                new BitmapTransform(),ExifOrientationMode.RespectExifOrientation,ColorManagementMode.ColorManageToSRgb);
            cancellation.ThrowIfCancellationRequested();
            using var output=new InMemoryRandomAccessStream();
            var encoder=await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId,output);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8,BitmapAlphaMode.Premultiplied,decoder.OrientedPixelWidth,decoder.OrientedPixelHeight,96,96,pixels.DetachPixelData());
            await encoder.FlushAsync();
            if(output.Size>PreviewPolicy.ViewerSourceBytes)throw new InvalidDataException("Decoded frame exceeds viewer limits");
            output.Seek(0);var first=new BitmapImage();await first.SetSourceAsync(output);
            cancellation.ThrowIfCancellationRequested();return first;
        }
        stream.Seek(0);var bitmap=new BitmapImage();await bitmap.SetSourceAsync(stream);
        cancellation.ThrowIfCancellationRequested();return bitmap;
    }
}
