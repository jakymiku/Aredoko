using System.Net;
using Aredoko.Core;

internal static class ResultWindowTests
{
    private static SearchResponse Page(int total, int offset, int count) => new()
    {
        Total = total, SearchComplete = true, SearchCandidateTotal = total, IndexedTotal = total,
        ScoreKind = "cosine", GroupBoundary = .5, LeadingTotal = 10, OtherTotal = Math.Max(0,total-10),
        SearchStatus = "ready", PartialWords = 2,
        Items = Enumerable.Range(offset, Math.Min(count, Math.Max(0,total-offset)))
            .Select(index => new MediaRow { Id=index+1, Title=$"generated {index}", Kind="image", Availability="present" }).ToList(),
        Expansions = [new SearchExpansion("test", ["related"], false)]
    };

    public static async Task Run(Action<bool,string> check)
    {
        var calls = new List<(int Offset,int Count)>();
        using var window = new ResultWindow(50000, (offset,count,token) =>
        {
            calls.Add((offset,count)); return Task.FromResult(Page(50000,offset,count));
        });
        var result = await window.ReadAsync(119,2,CancellationToken.None);
        check(result.Items.Select(row=>row.Id).SequenceEqual(new[]{120,121}), "window joins exact 119/120 block boundary");
        check(result.PartialWords==2 && result.Expansions.Count==1 && result.ScoreKind=="cosine" && result.SearchComplete,
            "window slicing preserves search evidence and coverage metadata");
        await window.PrefetchAsync(CancellationToken.None);
        check(window.RetainedBlockCount==5 && window.RetainedItemCount==600, "50k result session retains at most five 120-item blocks");
        var previous = calls.Count;
        await window.ReadAsync(120,60,CancellationToken.None);
        check(calls.Count==previous+1 && calls[^1]==(120,120), "prefetched visible block still revalidates with backend");
        foreach (var offset in new[]{6000,24000,49980,0})
        {
            result = await window.ReadAsync(offset,60,CancellationToken.None);
            await window.PrefetchAsync(CancellationToken.None);
            check(result.Items[0].Id==offset+1 && window.RetainedBlockCount<=5 && window.RetainedItemCount<=600,
                "distant scroll evicts metadata without expanding 50k rows");
        }
        check(calls.Count<40 && calls.All(call=>call.Count==120), "large library issues only bounded range requests");
        using var empty = new ResultWindow(0,(offset,count,_)=>Task.FromResult(Page(0,offset,count)));
        check((await empty.ReadAsync(60,60,CancellationToken.None)).Items.Count==0, "out-of-range page preserves empty state for page correction");

        var release = new TaskCompletionSource<SearchResponse>(TaskCreationOptions.RunContinuationsAsynchronously);
        var began = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var stale = new ResultWindow(1000,(offset,count,_)=>
        {
            if(offset==0){began.TrySetResult();return release.Task;} // deliberately ignores cancellation
            return Task.FromResult(Page(1000,offset,count));
        });
        var old = stale.ReadAsync(0,60,CancellationToken.None); await began.Task;
        var current = await stale.ReadAsync(720,60,CancellationToken.None);
        release.SetResult(Page(1000,0,120)); var cancelled=false;
        try { await old; } catch(OperationCanceledException) { cancelled=true; }
        check(cancelled && current.Items[0].Id==721 && stale.RetainedItemCount==120,
            "late cancelled transport cannot overwrite or clear newer viewport");

        using var invalid = new ResultWindow(240,(offset,count,_)=>
        {
            var value=Page(240,offset,count); if(offset==120)value.Items[0]=Page(240,0,1).Items[0];
            return Task.FromResult(value);
        });
        var rejected=false;
        try { await invalid.ReadAsync(119,2,CancellationToken.None); } catch(InvalidDataException){rejected=true;}
        check(rejected && invalid.RetainedItemCount==0, "duplicate item in distinct blocks cannot silently corrupt order");

        using var expired = new ResultWindow(120,(_,_,_)=>throw new ResultSessionException(HttpStatusCode.Gone,"kept conditions",7));
        var explained=false;
        try { await expired.ReadAsync(0,60,CancellationToken.None); }
        catch(ResultSessionException ex){explained=ex.Conditions=="kept conditions" && ex.CurrentId==7;}
        check(explained, "expiry propagates with selection context instead of returning EOF");
        var closingReply=new TaskCompletionSource<SearchResponse>(TaskCreationOptions.RunContinuationsAsynchronously);
        var closing=new ResultWindow(120,(_,_,_)=>closingReply.Task);
        var pending=closing.ReadAsync(0,60,CancellationToken.None); closing.Dispose(); closingReply.SetResult(Page(120,0,120));
        cancelled=false;try{await pending;}catch(OperationCanceledException){cancelled=true;}
        check(cancelled && closing.RetainedItemCount==0,"close rejects delayed response and releases cached metadata");
    }
}
