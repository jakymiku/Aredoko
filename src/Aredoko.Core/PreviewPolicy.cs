namespace Aredoko.Core;

public static class PreviewPolicy
{
    public const int MaxSourceBytes = 8 * 1024 * 1024;
    public const long MaxPixels = 16_000_000;
    public const int Edge = 256;
    public const int CacheEntries = 64;

    public static void ValidateDimensions(uint width, uint height)
    {
        if (width == 0 || height == 0 || (ulong)width * height > (ulong)MaxPixels)
            throw new InvalidDataException("Image dimensions exceed preview limits");
    }
}

// UI-owned bounded LRU. Values are derived PNGs, never full source images.
public sealed class BoundedLru<TKey, TValue> where TKey : notnull
{
    private readonly int capacity;
    private readonly Dictionary<TKey, LinkedListNode<(TKey Key, TValue Value)>> entries = new();
    private readonly LinkedList<(TKey Key, TValue Value)> order = new();
    public BoundedLru(int capacity)
    {
        if (capacity < 1) throw new ArgumentOutOfRangeException(nameof(capacity));
        this.capacity = capacity;
    }
    public int Count => entries.Count;
    public bool TryGet(TKey key, out TValue value)
    {
        if (!entries.TryGetValue(key, out var node)) { value = default!; return false; }
        order.Remove(node); order.AddFirst(node); value = node.Value.Value; return true;
    }
    public void Set(TKey key, TValue value)
    {
        if (entries.Remove(key, out var existing)) order.Remove(existing);
        entries[key] = order.AddFirst((key, value));
        if (entries.Count <= capacity) return;
        var oldest = order.Last!; order.RemoveLast(); entries.Remove(oldest.Value.Key);
    }
    public void Clear() { entries.Clear(); order.Clear(); }
}
