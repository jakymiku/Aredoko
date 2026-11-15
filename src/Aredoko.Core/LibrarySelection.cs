namespace Aredoko.Core;

public sealed record ResultPosition(int Id,int Ordinal);
public enum SelectionOperation { FavoriteAdd,FavoriteRemove,ShelvesAdd,ShelvesRemove }

// Stable logical IDs survive eviction from the 600-row presentation window.
// A selection belongs to one frozen result order, never to recycled native cells.
public sealed class LibrarySelection
{
    public const int Maximum=256;
    private Dictionary<int,ResultPosition> entries=[];
    private long version;
    public string? SessionId {get;private set;}
    public int Total {get;private set;}
    public ResultPosition? Anchor {get;private set;}
    public ResultPosition? PreviousAnchor {get;private set;}
    public int Count=>entries.Count;
    public IReadOnlyList<int> Ids=>entries.Values.OrderBy(row=>row.Ordinal).Select(row=>row.Id).ToArray();
    public bool Contains(int id)=>entries.ContainsKey(id);

    private void Validate(ResultPosition row)
    {
        if(row.Id<1||row.Ordinal<0||row.Ordinal>=Total)throw new InvalidDataException("Invalid selection position");
    }
    private void Commit(IEnumerable<ResultPosition> values,ResultPosition? anchor)
    {
        var next=values.ToArray();
        if(next.Length>Maximum)throw new InvalidOperationException($"一度に選択できるのは{Maximum}件までです。");
        foreach(var row in next)Validate(row);
        if(next.Select(row=>row.Id).Distinct().Count()!=next.Length||next.Select(row=>row.Ordinal).Distinct().Count()!=next.Length)
            throw new InvalidDataException("Duplicate selection position");
        entries=next.ToDictionary(row=>row.Id);Anchor=anchor;PreviousAnchor=null;version++;
    }
    public void Bind(string? sessionId,int total,IReadOnlyList<ResultPosition>? retained=null)
    {
        if(total<0||sessionId is null&&total!=0)throw new ArgumentOutOfRangeException(nameof(total));
        var oldSession=SessionId;var oldTotal=Total;
        SessionId=sessionId;Total=total;
        try
        {
            var positions=retained??[];
            var anchor=positions.FirstOrDefault(row=>row.Id==Anchor?.Id);
            Commit(positions,anchor);
        }
        catch{SessionId=oldSession;Total=oldTotal;throw;}
    }
    public void Single(ResultPosition row)
    {
        Validate(row);
        var previous=Anchor is {} current&&current.Id!=row.Id?current:PreviousAnchor;
        Commit([row],row);
        PreviousAnchor=previous;
    }
    public void Clear()=>Commit([],null);
    public void Visible(IReadOnlyList<ResultPosition> visible,IReadOnlyList<int> selected,int? anchorId=null)
    {
        var map=visible.ToDictionary(row=>row.Id);foreach(var row in visible)Validate(row);
        if(selected.Distinct().Count()!=selected.Count||selected.Any(id=>!map.ContainsKey(id)))throw new InvalidDataException("Invalid visible selection");
        var next=entries.Values.Where(row=>!map.ContainsKey(row.Id)).Concat(selected.Select(id=>map[id]));
        var anchor=anchorId is int id&&map.TryGetValue(id,out var position)?position:Anchor;
        Commit(next,anchor);
    }
    public async Task RangeAsync(ResultPosition target,bool additive,
        Func<int,int,CancellationToken,Task<IReadOnlyList<int>>> fetch,CancellationToken cancellation)
    {
        Validate(target);
        var anchor=Anchor??target;var start=Math.Min(anchor.Ordinal,target.Ordinal);var end=Math.Max(anchor.Ordinal,target.Ordinal);
        if((long)end-start+1>Maximum)throw new InvalidOperationException($"範囲選択は{Maximum}件以内にしてください。");
        var expected=version;var range=new List<ResultPosition>();
        for(var offset=start;offset<=end;)
        {
            cancellation.ThrowIfCancellationRequested();var count=Math.Min(120,end-offset+1);
            var ids=await fetch(offset,count,cancellation);
            if(ids.Count!=count)throw new InvalidDataException("Incomplete selection range");
            for(var i=0;i<ids.Count;i++)range.Add(new(ids[i],offset+i));
            offset+=count;
        }
        cancellation.ThrowIfCancellationRequested();
        if(expected!=version)throw new OperationCanceledException("Selection changed while preparing the range");
        if(range.Single(row=>row.Ordinal==target.Ordinal).Id!=target.Id||range.Single(row=>row.Ordinal==anchor.Ordinal).Id!=anchor.Id)
            throw new InvalidDataException("Selection result order changed");
        var replaced=range.Select(row=>row.Id).ToHashSet();
        Commit((additive?entries.Values.Where(row=>!replaced.Contains(row.Id)):[]).Concat(range),anchor);
    }
}
