namespace Aredoko.Core;
public readonly record struct EditorState(string Tags, string Shelf, bool Favorite, bool Reviewed)
{
    public IReadOnlyList<long>? ShelfIds { get; init; }
    public static bool IsDirty(EditorState saved, EditorState current) =>
        saved.Tags != current.Tags || saved.Favorite != current.Favorite || saved.Reviewed != current.Reviewed ||
        (saved.ShelfIds is null || current.ShelfIds is null
            ? saved.ShelfIds is not null || current.ShelfIds is not null || saved.Shelf != current.Shelf
            : !saved.ShelfIds.Order().SequenceEqual(current.ShelfIds.Order()));
    public string[] ParsedTags => Tags.Split([',','、'],StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Distinct().ToArray();
    public string? Validate() => ParsedTags.Length > 30 || ParsedTags.Any(t=>t.Length > 60) ? AppText.L("タグは30個まで、各60文字以内です。","Up to 30 tags allowed (max 60 characters each).") : Shelf.Length > 80 ? AppText.L("棚は80文字以内です。","Shelf name must be 80 characters or fewer.") : null;
}
public sealed class RequestVersion { private long current; public long Next()=>Interlocked.Increment(ref current); public bool IsCurrent(long value)=>Interlocked.Read(ref current)==value; }
