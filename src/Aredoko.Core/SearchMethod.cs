namespace Aredoko.Core;

// Keep the established GUI indices: literal, combined, cover, text; append pending tag candidates.
public readonly record struct SearchMethod(bool IsAI, string Source)
{
    public bool IsTagCandidates => Source == "pending-proposals";

    public static SearchMethod FromIndex(int index) => index switch
    {
        0 => new(false, "all"),
        1 => new(true, "all"),
        2 => new(true, "cover"),
        3 => new(true, "text"),
        4 => new(false, "pending-proposals"),
        _ => throw new ArgumentOutOfRangeException(nameof(index))
    };
}
