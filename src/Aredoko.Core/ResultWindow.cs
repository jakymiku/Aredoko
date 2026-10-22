namespace Aredoko.Core;

// UI-independent bounded metadata window. The session/conditions are owned by
// the caller; disposing this object cancels reads, never closes another owner.
public sealed class ResultWindow : IDisposable
{
    public const int BlockSize = 120;
    public const int MaxBlocks = 5;
    private readonly int total;
    private readonly Func<int, int, CancellationToken, Task<SearchResponse>> read;
    private readonly object gate = new();
    private readonly SemaphoreSlim requests = new(2, 2);
    private readonly Dictionary<int, SearchResponse> blocks = new();
    private CancellationTokenSource? movement;
    private int[] wanted = [];
    private long generation, prefetchGeneration = -1;
    private bool disposed;
    public int RetainedBlockCount { get { lock (gate) return blocks.Count; } }
    public int RetainedItemCount { get { lock (gate) return blocks.Values.Sum(block => block.Items.Count); } }

    public ResultWindow(int total, Func<int, int, CancellationToken, Task<SearchResponse>> read)
    {
        if (total < 0) throw new ArgumentOutOfRangeException(nameof(total));
        this.total = total;
        this.read = read ?? throw new ArgumentNullException(nameof(read));
    }

    public async Task<SearchResponse> ReadAsync(int offset, int count, CancellationToken cancellation)
    {
        if (offset < 0 || count is < 1 or > BlockSize) throw new ArgumentOutOfRangeException(nameof(offset));
        cancellation.ThrowIfCancellationRequested();
        var first = offset / BlockSize;
        var length = Math.Min(count, Math.Max(0, total - offset));
        var last = length == 0 ? first : (offset + length - 1) / BlockSize;
        long version;
        CancellationToken token;
        CancellationTokenSource? previous;
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            version = ++generation;
            previous = movement;
            movement = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            token = movement.Token;
            var desired = Enumerable.Range(first, last - first + 1).ToList();
            var blockCount = ((long)total + BlockSize - 1) / BlockSize;
            for (var distance = 1; desired.Count < MaxBlocks && distance <= MaxBlocks; distance++)
            {
                if ((long)last + distance < blockCount) desired.Add(last + distance);
                if (desired.Count < MaxBlocks && first - distance >= 0 && first - distance < blockCount) desired.Add(first - distance);
            }
            wanted = desired.ToArray();
            foreach (var stale in blocks.Keys.Except(wanted).ToArray()) blocks.Remove(stale);
        }
        previous?.Cancel(); previous?.Dispose();
        try
        {
            // Visible blocks are always re-read on a viewport movement. A local
            // cache hit cannot bypass expiry/scope/physical-source validation.
            SearchResponse? metadata = null;
            for (var block = first; block <= last; block++)
            {
                var loaded = await FetchAsync(block, version, token).ConfigureAwait(false);
                metadata ??= loaded;
            }
            lock (gate)
            {
                Check(version, token);
                var items = new List<MediaRow>(length);
                for (var ordinal = offset; ordinal < (long)offset + length; ordinal++)
                    items.Add(blocks[ordinal / BlockSize].Items[ordinal % BlockSize]);
                return Slice(metadata!, items);
            }
        }
        catch
        {
            lock (gate) if (generation == version) blocks.Clear();
            throw;
        }
    }

    public async Task PrefetchAsync(CancellationToken cancellation)
    {
        long version; int[] targets; CancellationToken token;
        lock (gate)
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            if (movement is null || prefetchGeneration == generation) return;
            version = generation; prefetchGeneration = version;
            targets = wanted.Where(block => !blocks.ContainsKey(block)).ToArray();
            token = movement.Token;
        }
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(token, cancellation);
        foreach (var block in targets)
            await FetchAsync(block, version, linked.Token).ConfigureAwait(false);
    }

    private async Task<SearchResponse> FetchAsync(int block, long version, CancellationToken token)
    {
        await requests.WaitAsync(token).ConfigureAwait(false);
        try
        {
            lock (gate) Check(version, token);
            var offset = checked(block * BlockSize);
            var result = await read(offset, BlockSize, token).ConfigureAwait(false);
            lock (gate)
            {
                Check(version, token);
                if (result.Total != total || result.Items.Count != Math.Min(BlockSize, Math.Max(0, total - offset)) ||
                    result.Items.Any(row => row.Id < 1) || result.Items.Select(row => row.Id).Distinct().Count() != result.Items.Count)
                    throw new InvalidDataException("Invalid result block");
                var otherIds = blocks.Where(pair => pair.Key != block).SelectMany(pair => pair.Value.Items).Select(row => row.Id).ToHashSet();
                if (result.Items.Any(row => otherIds.Contains(row.Id))) throw new InvalidDataException("Duplicate result across blocks");
                blocks[block] = result;
                return result;
            }
        }
        finally { requests.Release(); }
    }

    private void Check(long version, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        ObjectDisposedException.ThrowIf(disposed, this);
        if (generation != version) throw new OperationCanceledException("Result viewport changed", token);
    }

    private static SearchResponse Slice(SearchResponse value, List<MediaRow> items) => new()
    {
        Total = value.Total, Items = items, SimilarityStatus = value.SimilarityStatus, SearchStatus = value.SearchStatus,
        OriginKind = value.OriginKind, PendingIndexRemaining = value.PendingIndexRemaining, ScoreKind = value.ScoreKind,
        GroupBoundary = value.GroupBoundary, LeadingTotal = value.LeadingTotal, OtherTotal = value.OtherTotal,
        CoverageLimit = value.CoverageLimit, SearchComplete = value.SearchComplete, SearchCandidateTotal = value.SearchCandidateTotal,
        IndexedTotal = value.IndexedTotal, Expansions = value.Expansions.ToList(), PartialWords = value.PartialWords
    };

    public void Dispose()
    {
        CancellationTokenSource? previous;
        lock (gate)
        {
            if (disposed) return;
            disposed = true; generation++; previous = movement; movement = null; blocks.Clear(); wanted = [];
        }
        previous?.Cancel(); previous?.Dispose();
        // In-flight transports may ignore cancellation; they still release their
        // semaphore slot and cannot publish after this generation has changed.
    }
}
