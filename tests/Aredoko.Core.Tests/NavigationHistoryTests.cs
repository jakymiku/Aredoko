using Aredoko.Core;
internal static class NavigationHistoryTests
{
    public static void Run(Action<bool,string> check)
    {
        var history=new NavigationHistory<string>(3);
        history.Track("all");history.Track("shelf-A");history.Track("query");
        var back=history.Peek(false)!;
        check(back=="shelf-A"&&history.Current=="query","peeking keeps cursor until restore succeeds");
        check(history.Commit(false,back)&&history.Current=="shelf-A"&&history.CanForward,"successful back exposes forward history");
        var forward=history.Peek(true)!;
        check(!history.Commit(true,new string("query".ToCharArray()))&&history.Current=="shelf-A","stale/other restore cannot move cursor");
        check(history.Commit(true,forward)&&history.Current=="query","forward restores original route");
        history.ReplaceCurrent("query-selected");check(history.Count==3&&history.Current=="query-selected","selection/scroll update does not add a route");
        history.Commit(false,history.Peek(false)!);history.Track("folders");
        check(!history.CanForward&&history.Count==3,"new route after back discards obsolete forward branch");
        history.Track("shelves");check(history.Count==3,"history evicts oldest location at capacity");
        history.Track("shelves");check(history.Count==3,"same location refresh coalesces rather than grows history");
    }
}
