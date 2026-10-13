namespace Aredoko.Core;

public static class ImageViewerPolicy
{
    private static readonly string[] Extensions = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];
    public static bool CanOpen(MediaRow row) => row.Kind == "image" && row.Availability == "present" &&
        Extensions.Any(extension => row.Location.EndsWith(extension, StringComparison.OrdinalIgnoreCase));
}
