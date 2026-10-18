namespace Aredoko.Core;

public static class AudioPlayerPolicy
{
    public const int MaxSourceBytes = 64 * 1024 * 1024;
    private static readonly string[] Extensions = [".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".wma"];

    public static bool CanOpen(MediaRow row) => row.Kind == "audio" && row.Availability == "present" &&
        Extensions.Any(extension => row.Location.EndsWith(extension, StringComparison.OrdinalIgnoreCase));
}
