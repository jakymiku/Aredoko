namespace Aredoko.Core;

// Keep the established GUI indices: literal, combined, cover, text, pending tag candidates; append page text.
public readonly record struct SearchMethod(bool IsAI, string Source)
{
    public bool IsTagCandidates => Source == "pending-proposals";
    public bool IsPageText => Source == "page-text";

    public static SearchMethod FromIndex(int index) => index switch
    {
        0 => new(false, "all"),
        1 => new(true, "all"),
        2 => new(true, "cover"),
        3 => new(true, "text"),
        4 => new(false, "pending-proposals"),
        5 => new(false, "page-text"),
        _ => throw new ArgumentOutOfRangeException(nameof(index))
    };
}
