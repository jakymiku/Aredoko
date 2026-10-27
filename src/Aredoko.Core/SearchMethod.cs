namespace Aredoko.Core;

// Keep the established GUI indices: literal, combined, cover, text, pending tag candidates; append page text.
public readonly record struct SearchMethod(bool IsAI, string Source)
{
    public bool IsTagSemantic => Source == "pending-proposals-semantic";
    public bool IsTagCandidates => Source is "pending-proposals" or "pending-proposals-semantic";
    public bool IsPageText => Source == "page-text";
    public bool IsAudioContent => Source == "audio-direct";
    public bool IsVideoContent => Source == "video-direct";

    public static SearchMethod FromIndex(int index) => index switch
    {
        0 => new(false, "all"),
        1 => new(true, "all"),
        2 => new(true, "cover"),
        3 => new(true, "text"),
        4 => new(false, "pending-proposals"),
        5 => new(false, "page-text"),
        6 => new(false, "pending-proposals-semantic"),
        7 => new(true, "audio-direct"),
        8 => new(true, "video-direct"),
        _ => throw new ArgumentOutOfRangeException(nameof(index))
    };
}
