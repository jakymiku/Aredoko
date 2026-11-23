namespace Aredoko.Core;

// Session-only bounded locations. A failed asynchronous navigation must not
// advance the cursor: callers peek, restore, then commit the move.
public sealed class NavigationHistory<T>(int capacity=64,IEqualityComparer<T>? comparer=null) where T:class
{
    private readonly List<T> entries=[];
    private readonly int limit=capacity>=2?capacity:throw new ArgumentOutOfRangeException(nameof(capacity));
    private readonly IEqualityComparer<T> equality=comparer??EqualityComparer<T>.Default;
    private int cursor=-1;
    public int Count=>entries.Count;
    public T? Current=>cursor<0?null:entries[cursor];
    public bool CanBack=>cursor>0;
    public bool CanForward=>cursor>=0&&cursor<entries.Count-1;
    public void Track(T entry)
    {
        if(Current is {} current&&equality.Equals(current,entry)){entries[cursor]=entry;return;}
        if(cursor+1<entries.Count)entries.RemoveRange(cursor+1,entries.Count-cursor-1);
        entries.Add(entry);cursor=entries.Count-1;
        if(entries.Count>limit){entries.RemoveAt(0);cursor--;}
    }
    public void ReplaceCurrent(T entry){if(cursor>=0)entries[cursor]=entry;}
    public T? Peek(bool forward)=>forward?(CanForward?entries[cursor+1]:null):(CanBack?entries[cursor-1]:null);
    public bool Commit(bool forward,T expected)
    {
        if(Peek(forward) is not {} next||!ReferenceEquals(next,expected))return false;
        cursor+=forward?1:-1;return true;
    }
}
