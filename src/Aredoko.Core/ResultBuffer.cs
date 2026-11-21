namespace Aredoko.Core;

// Bidirectional incremental metadata. Search order remains the server's order;
// this buffer never derives a new rank or retains the whole catalog.
public sealed class ResultBuffer
{
    public const int Capacity=600;
    public int MaxCapacity { get; }
    public int Start { get; private set; }
    public int Total { get; }
    public IReadOnlyList<MediaRow> Items { get; private set; }
    public int End => Start+Items.Count;
    public ResultBuffer(int start, SearchResponse response, int capacity = Capacity)
    {
        MaxCapacity=capacity>0?capacity:throw new ArgumentOutOfRangeException(nameof(capacity));
        Total=response.Total;Start=start;Items=response.Items.ToArray();
        Validate(start,response);
    }
    private void Validate(int offset,SearchResponse response)
    {
        if(offset<0||response.Total!=Total||response.Items.Count>MaxCapacity||
            (long)offset+response.Items.Count>Total||response.Items.Any(row=>row.Id<1)||
            response.Items.Select(row=>row.Id).Distinct().Count()!=response.Items.Count)
            throw new InvalidDataException("Invalid incremental result range");
    }
    public void Extend(int offset,SearchResponse response)
    {
        Validate(offset,response);
        if(response.Items.Count==0)throw new InvalidDataException("Empty incremental range");
        var append=offset==End;
        if(!append&&offset+response.Items.Count!=Start)throw new InvalidDataException("Non-adjacent result range");
        var merged=append?Items.Concat(response.Items).ToArray():response.Items.Concat(Items).ToArray();
        if(merged.Select(row=>row.Id).Distinct().Count()!=merged.Length)throw new InvalidDataException("Duplicate incremental result");
        var excess=Math.Max(0,merged.Length-MaxCapacity);
        var nextStart=append?Start+excess:offset;
        var retained=append?merged.Skip(excess).ToArray():merged.Take(MaxCapacity).ToArray();
        Start=nextStart;Items=retained;
    }
}
