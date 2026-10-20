namespace Aredoko.Core;

public sealed record ViewerSource(byte[]? Data,string? ETag,string Mime,bool NotModified)
{
    public static void ValidateETag(string value)
    {
        if(value.Length!=68||!value.StartsWith("W/\"",StringComparison.Ordinal)||value[^1]!='"'||
            value.Skip(3).Take(64).Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f')))
            throw new InvalidDataException("ページの再確認情報が無効です。");
    }
}

public sealed record DecodedViewerPage<T>(T Value,long Bytes);
public sealed class ViewerPreloadSkippedException : Exception { }

// Per-viewer decoded cache. Every use, including an already prefetched page,
// revalidates via the authenticated backend; no cached permission or file path.
public sealed class ViewerPageCache<TKey,TValue> : IDisposable where TKey:notnull
{
    private sealed record Entry(TValue Value,string ETag,long Bytes);
    private readonly Dictionary<TKey,LinkedListNode<(TKey Key,Entry Value)>> entries=[];
    private readonly LinkedList<(TKey Key,Entry Value)> order=[];
    private readonly object sync=new();
    private readonly SemaphoreSlim sourceGate=new(1,1);
    private readonly CancellationTokenSource lifetime=new();
    private readonly int capacity;
    private readonly long budget;
    private long bytes;
    private int epoch;
    private bool disposed;
    public ViewerPageCache(int capacity=6,long budget=96*1024*1024)
    {
        if(capacity<1||budget<1)throw new ArgumentOutOfRangeException(nameof(capacity));
        this.capacity=capacity;this.budget=budget;
    }
    public int Count {get{lock(sync)return entries.Count;}}
    public long Bytes {get{lock(sync)return bytes;}}

    public Task<TValue> ReadAsync(TKey key,Func<string?,CancellationToken,Task<ViewerSource>> source,
        Func<byte[],bool,CancellationToken,Task<DecodedViewerPage<TValue>>> decode,CancellationToken cancellation)
        =>ReadAsync(key,source,decode,cancellation,false);

    private async Task<TValue> ReadAsync(TKey key,Func<string?,CancellationToken,Task<ViewerSource>> source,
        Func<byte[],bool,CancellationToken,Task<DecodedViewerPage<TValue>>> decode,CancellationToken cancellation,bool preload)
    {
        Entry? cached;int generation;
        lock(sync)
        {
            ObjectDisposedException.ThrowIf(disposed,this);generation=epoch;
            cached=entries.TryGetValue(key,out var node)?node.Value.Value:null;
        }
        using var linked=CancellationTokenSource.CreateLinkedTokenSource(cancellation,lifetime.Token);
        var token=linked.Token;
        ViewerSource response;
        // At most one viewer source request at a time, leaving a backend slot
        // for interactive work. Decode tasks for a spread can still overlap.
        await sourceGate.WaitAsync(token);
        try{response=await source(cached?.ETag,token);}
        catch{lock(sync){if(generation==epoch)Remove(key);}throw;}
        finally{sourceGate.Release();}
        token.ThrowIfCancellationRequested();
        lock(sync){if(disposed||generation!=epoch)throw new OperationCanceledException(token);}
        if(response.NotModified)
        {
            if(cached is null||response.ETag!=cached.ETag||response.Data is not null)
                throw new InvalidDataException("キャッシュの再確認応答が無効です。");
            lock(sync){if(generation==epoch&&entries.TryGetValue(key,out var hit)){order.Remove(hit);order.AddFirst(hit);}}
            return cached.Value;
        }
        if(response.Data is null||response.Data.Length is <1 or >PreviewPolicy.ViewerSourceBytes)
            throw new InvalidDataException("ページのデータ量が無効です。");
        lock(sync){if(generation==epoch)Remove(key);}
        if(preload&&response.Data.Length>8*1024*1024)throw new ViewerPreloadSkippedException();
        var decoded=await decode(response.Data,preload,token);
        token.ThrowIfCancellationRequested();
        lock(sync){if(disposed||generation!=epoch)throw new OperationCanceledException(token);}
        if(decoded.Bytes<1)throw new InvalidDataException("ページのメモリ量が無効です。");
        if(response.ETag is not null)
        {
            ViewerSource.ValidateETag(response.ETag);
            lock(sync)
            {
                if(!disposed&&generation==epoch&&decoded.Bytes<=budget)
                {
                    Remove(key);
                    while(entries.Count>=capacity||bytes>budget-decoded.Bytes)Remove(order.Last!.Value.Key);
                    var entry=new Entry(decoded.Value,response.ETag,decoded.Bytes);
                    entries[key]=order.AddFirst((key,entry));bytes+=decoded.Bytes;
                }
            }
        }
        return decoded.Value;
    }

    public async Task PreloadAsync(TKey key,Func<string?,CancellationToken,Task<ViewerSource>> source,
        Func<byte[],bool,CancellationToken,Task<DecodedViewerPage<TValue>>> decode,CancellationToken cancellation)
    {
        try{await ReadAsync(key,source,decode,cancellation,true);}
        catch(Exception ex) when(ex is not OutOfMemoryException) { /* Speculative work never changes the visible page/error. */ }
    }
    private void Remove(TKey key)
    {
        if(entries.Remove(key,out var node)){order.Remove(node);bytes-=node.Value.Value.Bytes;}
    }
    public void Clear(){lock(sync){epoch++;entries.Clear();order.Clear();bytes=0;}}
    public void Dispose(){lock(sync){if(disposed)return;disposed=true;Clear();}lifetime.Cancel();}
}
