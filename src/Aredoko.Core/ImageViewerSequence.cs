namespace Aredoko.Core;

public sealed record ViewerImageItem(int Id, string Title, string Location = "");

// Local-page compatibility plus a bounded session-backed current item. Remote
// navigation never expands all result metadata or walks the filesystem.
public sealed class ImageViewerSequence
{
    private readonly ViewerImageItem[] items;
    private readonly Func<int, int, CancellationToken, Task<ResultNeighbor?>>? neighbor;
    private ViewerImageItem? remoteCurrent;
    private readonly int count;
    private long navigationVersion;
    private bool previousExhausted, nextExhausted;
    public int Position { get; private set; }
    // Session positions count all media; local compatibility positions count images.
    public int Count => count;
    public bool IsSession => neighbor is not null;
    public ViewerImageItem Current => remoteCurrent ?? items[Position];
    public bool HasPrevious => !previousExhausted && Position > 0;
    public bool HasNext => !nextExhausted && Position + 1 < Count;

    public ImageViewerSequence(IEnumerable<MediaRow> results, int selectedId)
    {
        items = results.Where(ImageViewerPolicy.CanOpen).DistinctBy(row => row.Id)
            .Select(row => new ViewerImageItem(row.Id, row.Title, row.Location)).ToArray();
        count = items.Length;
        Position = Array.FindIndex(items, item => item.Id == selectedId);
        if (Position < 0) throw new ArgumentException("Selected image is not in this result page", nameof(selectedId));
    }

    public ImageViewerSequence(MediaRow selected, int ordinal, int total,
        Func<int, int, CancellationToken, Task<ResultNeighbor?>> neighbor,
        bool previousExhausted = false, bool nextExhausted = false)
    {
        if (!ImageViewerPolicy.CanOpen(selected) || total < 1 || ordinal < 0 || ordinal >= total)
            throw new ArgumentException("Selected image is outside the result session", nameof(selected));
        this.neighbor = neighbor ?? throw new ArgumentNullException(nameof(neighbor));
        items = []; count = total; Position = ordinal;
        this.previousExhausted = previousExhausted;
        this.nextExhausted = nextExhausted;
        remoteCurrent = new(selected.Id, selected.Title, selected.Location);
    }

    public void MoveTo(ResultNeighbor target)
    {
        ArgumentNullException.ThrowIfNull(target);
        if (!ImageViewerPolicy.CanOpen(target.Item) || target.Item.Id == Current.Id ||
            target.Ordinal < 0 || target.Ordinal >= Count)
            throw new InvalidDataException("Invalid result image order");
        Interlocked.Increment(ref navigationVersion);
        remoteCurrent = new(target.Item.Id, target.Item.Title, target.Item.Location);
        Position = target.Ordinal;
        previousExhausted = nextExhausted = false;
    }

    public bool TryJumpTo(int index)
    {
        if (IsSession) throw new InvalidOperationException("Use asynchronous session navigation");
        if (index < 0 || index >= Count) return false;
        Interlocked.Increment(ref navigationVersion);
        Position = index;
        return true;
    }

    public bool TryMove(int direction)
    {
        ValidateDirection(direction);
        if (IsSession) throw new InvalidOperationException("Use asynchronous session navigation");
        Interlocked.Increment(ref navigationVersion);
        var destination = Position + direction;
        if (destination < 0 || destination >= Count) return false;
        Position = destination; return true;
    }

    public async Task<bool> TryMoveAsync(int direction, CancellationToken cancellation)
    {
        ValidateDirection(direction); cancellation.ThrowIfCancellationRequested();
        if (neighbor is null) return TryMove(direction);
        var version = Interlocked.Increment(ref navigationVersion);
        var current = Current.Id; var position = Position;
        if (direction < 0 ? !HasPrevious : !HasNext) return false;
        var target = await neighbor(current, direction, cancellation);
        cancellation.ThrowIfCancellationRequested();
        if (version != Volatile.Read(ref navigationVersion) || Current.Id != current) return false;
        if (target is null)
        {
            if (direction < 0) previousExhausted = true; else nextExhausted = true;
            return false;
        }
        if (!ImageViewerPolicy.CanOpen(target.Item) || target.Item.Id == current ||
            target.Ordinal < 0 || target.Ordinal >= Count ||
            (direction < 0 ? target.Ordinal >= position : target.Ordinal <= position))
            throw new InvalidDataException("Invalid result image order");
        remoteCurrent = new(target.Item.Id, target.Item.Title, target.Item.Location);
        Position = target.Ordinal; previousExhausted = nextExhausted = false;
        return true;
    }

    private static void ValidateDirection(int direction)
    {
        if (direction is not (-1 or 1)) throw new ArgumentOutOfRangeException(nameof(direction));
    }
}
