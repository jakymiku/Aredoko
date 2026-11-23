namespace Aredoko.Core;

public static class ImageViewerPolicy
{
    public const int MaxAnimationFrames = 64;
    private static readonly string[] Extensions = [".png", ".apng", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];
    private static readonly string[] AnimatedCandidateExtensions = [".gif", ".webp", ".png", ".apng"];
    public static bool CanOpen(MediaRow row) => row.Kind == "image" && row.Availability == "present" &&
        Extensions.Any(extension => row.Location.EndsWith(extension, StringComparison.OrdinalIgnoreCase));
    public static bool MayAnimate(string location) =>
        AnimatedCandidateExtensions.Any(extension => location.EndsWith(extension, StringComparison.OrdinalIgnoreCase));
}

public sealed record ImageAnimationManifest(
    int ItemId,
    string Revision,
    int Width,
    int Height,
    bool Animated,
    int FrameCount,
    int LoopCount,
    int[] DurationsMs,
    int RepresentativeFrame)
{
    public void Validate()
    {
        if (ItemId < 1 || Width is < 1 or > 16384 || Height is < 1 or > 16384 ||
            (long)Width * Height > PreviewPolicy.MaxPixels ||
            Revision is null || Revision.Length != 64 ||
            Revision.Any(c => !(c is >= '0' and <= '9' or >= 'a' and <= 'f')) ||
            FrameCount is < 1 or > ImageViewerPolicy.MaxAnimationFrames ||
            LoopCount is < 0 or > 10000 ||
            DurationsMs is null || DurationsMs.Length != FrameCount ||
            DurationsMs.Any(d => d is < 20 or > 60000) ||
            RepresentativeFrame < 0 || RepresentativeFrame >= FrameCount)
            throw new InvalidDataException("アニメーション画像の情報が無効です。");
    }

    public static ImageAnimationManifest Parse(byte[] json, int expectedItemId)
    {
        try
        {
            using var document = System.Text.Json.JsonDocument.Parse(json);
            var root = document.RootElement;
            var durationsElement = root.GetProperty("durations_ms");
            if (durationsElement.ValueKind != System.Text.Json.JsonValueKind.Array)
                throw new InvalidDataException("アニメーション時間の形式が無効です。");
            var durations = new int[durationsElement.GetArrayLength()];
            var idx = 0;
            foreach (var entry in durationsElement.EnumerateArray())
                durations[idx++] = entry.GetInt32();
            var result = new ImageAnimationManifest(
                root.GetProperty("item_id").GetInt32(),
                root.GetProperty("revision").GetString()!,
                root.GetProperty("width").GetInt32(),
                root.GetProperty("height").GetInt32(),
                root.GetProperty("animated").GetBoolean(),
                root.GetProperty("frame_count").GetInt32(),
                root.GetProperty("loop_count").GetInt32(),
                durations,
                root.GetProperty("representative_frame").GetInt32());
            result.Validate();
            if (result.ItemId != expectedItemId)
                throw new InvalidDataException("別の画像の情報を受信しました。");
            return result;
        }
        catch (Exception ex) when (ex is System.Text.Json.JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            throw new InvalidDataException("アニメーション画像の情報を読み取れません。", ex);
        }
    }
}
