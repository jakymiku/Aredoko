namespace Aredoko.Core;

public sealed record ViewerImageItem(int Id, string Title, string Location = "");

// Freeze the displayed result page's image order; never traverse the filesystem.
public sealed class ImageViewerSequence
{
    private readonly ViewerImageItem[] items;
    public int Position { get; private set; }
    public int Count => items.Length;
    public ViewerImageItem Current => items[Position];
    public bool HasPrevious => Position > 0;
    public bool HasNext => Position + 1 < Count;
    public ImageViewerSequence(IEnumerable<MediaRow> results, int selectedId)
    {
        items = results.Where(ImageViewerPolicy.CanOpen).DistinctBy(row => row.Id)
            .Select(row => new ViewerImageItem(row.Id, row.Title, row.Location)).ToArray();
        Position = Array.FindIndex(items, item => item.Id == selectedId);
        if (Position < 0) throw new ArgumentException("Selected image is not in this result page", nameof(selectedId));
    }
    public bool TryMove(int direction)
    {
        if (direction is not (-1 or 1)) throw new ArgumentOutOfRangeException(nameof(direction));
        var destination = Position + direction;
        if (destination < 0 || destination >= Count) return false;
        Position = destination; return true;
    }
}
