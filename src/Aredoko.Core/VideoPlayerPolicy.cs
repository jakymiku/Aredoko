namespace Aredoko.Core;

public static class VideoPlayerPolicy
{
    public const int MaxSourceBytes = 64 * 1024 * 1024;
    private static readonly string[] Extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".wmv", ".m4v", ".ts"];

    public static bool CanOpen(MediaRow row) => row.Kind == "video" && row.Availability == "present" &&
        Extensions.Any(extension => row.Location.EndsWith(extension, StringComparison.OrdinalIgnoreCase));

    public static int? MatchStartMs(MediaRow row)=>row.Kind=="video"
        ?(row.AudioMatchSource=="video-audio"?row.AudioMatchMs:row.VideoMatchMs):null;

    public static TimeSpan ClampSeek(TimeSpan target, TimeSpan duration)
    {
        if (duration <= TimeSpan.Zero || target <= TimeSpan.Zero) return TimeSpan.Zero;
        return target >= duration ? duration : target;
    }

    public static int ClampVolume(double percent) =>
        double.IsFinite(percent) ? (int)Math.Clamp(Math.Round(percent), 0, 100) : 80;

    public static string FormatTime(TimeSpan value)
    {
        if (value < TimeSpan.Zero || value == TimeSpan.MaxValue) value = TimeSpan.Zero;
        var totalSeconds = (int)Math.Floor(value.TotalSeconds);
        return $"{totalSeconds / 60}:{totalSeconds % 60:D2}";
    }

    public static string FormatPosition(TimeSpan position, TimeSpan duration) =>
        duration > TimeSpan.Zero
            ? $"{FormatTime(ClampSeek(position, duration))} / {FormatTime(duration)}"
            : "—";
}
