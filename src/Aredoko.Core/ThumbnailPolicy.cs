namespace Aredoko.Core;

public static class ThumbnailPolicy
{
    // Use device pixels, rounded up to the next supported derivative. Never
    // expose a page-size setting or make a huge DPI request allocate huge pixels.
    public static int EdgeFor(double width, double height, double rasterizationScale)
    {
        if (!double.IsFinite(width) || !double.IsFinite(height) || width < 0 || height < 0 ||
            !double.IsFinite(rasterizationScale) || rasterizationScale <= 0)
            throw new ArgumentOutOfRangeException(nameof(width));
        var pixels = Math.Max(width, height) * rasterizationScale;
        return pixels <= 128 ? 128 : pixels <= 256 ? 256 : pixels <= 512 ? 512 : 1024;
    }
}
