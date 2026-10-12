namespace Aredoko.Core;

// Keep the established GUI indices: literal, combined, cover; append text.
public readonly record struct SearchMethod(bool IsAI, string Source)
{
    public static SearchMethod FromIndex(int index) => index switch
    {
        0 => new(false, "all"),
        1 => new(true, "all"),
        2 => new(true, "cover"),
        3 => new(true, "text"),
        _ => throw new ArgumentOutOfRangeException(nameof(index))
    };
}
