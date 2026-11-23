namespace Aredoko.Core;

public sealed record RootChoice(int Id,string Path,bool Registered=true);

// Selection belongs to the draft, never to the current filtered page.
public sealed class RootPicker
{
    public const int PageSize=32,SelectionLimit=256;
    private readonly Dictionary<int,RootChoice> choices;
    private readonly HashSet<int> selected=[];
    private RootChoice[] matches=[];
    public int Page {get;private set;}
    public int MatchCount=>matches.Length;
    public int PageCount=>Math.Max(1,(MatchCount+PageSize-1)/PageSize);
    public int SelectionCount=>selected.Count;
    public IReadOnlyList<RootChoice> Visible=>matches.Skip(Page*PageSize).Take(PageSize).ToArray();
    public int[] Selected=>selected.Order().ToArray();
    public RootPicker(IEnumerable<RootChoice> roots){choices=roots.ToDictionary(r=>r.Id);Filter("");}
    public bool IsSelected(int id)=>selected.Contains(id);
    public bool Select(int id,bool chosen)
    {
        if(!choices.ContainsKey(id))return false;
        if(!chosen){selected.Remove(id);return true;}
        if(!selected.Contains(id)&&selected.Count>=SelectionLimit)return false;
        selected.Add(id);return true;
    }
    public void Restore(IEnumerable<int> ids)
    {
        var value=ids.Distinct().Order().ToArray();
        if(value.Length>SelectionLimit)throw new ArgumentException("Too many selected roots");
        selected.Clear();
        foreach(var id in value){choices.TryAdd(id,new(id,$"登録が見つかりません（ID {id}）",false));selected.Add(id);}
        Filter("");
    }
    public void Filter(string query)
    {
        query=query.Trim();matches=choices.Values.Where(r=>r.Path.Contains(query,StringComparison.OrdinalIgnoreCase)).OrderBy(r=>r.Id).ToArray();Page=0;
    }
    public void Move(int delta){Page=Math.Clamp(Page+delta,0,PageCount-1);}
}
