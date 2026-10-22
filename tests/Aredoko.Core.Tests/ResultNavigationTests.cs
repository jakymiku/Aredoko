using Aredoko.Core;
using System.Net;
using System.Text.Json.Nodes;

internal static class ResultNavigationTests
{
    private static MediaRow Image(int id) => new() { Id=id, Title=$"image {id}", Kind="image", Availability="present", Location=$"{id}.png" };
    public static async Task Run(Action<bool,string> check)
    {
        var roots = new[] { 3, 1 }; var scope = new JsonObject { ["root_ids"] = new JsonArray(2, 3), ["shelf"] = "資料" };
        var literal = ResultSearchConditions.Create("雨", "image", "favorites", SearchMethod.FromIndex(0), scope, roots)!;
        check(literal["mode"]!.GetValue<string>()=="literal" && literal["root_ids"]!.ToJsonString()=="[1,3]", "literal session binds sorted selected roots");
        var semantic = ResultSearchConditions.Create("雨", "image", "favorites", SearchMethod.FromIndex(2), scope, roots,
            literalOnly:true, groupThreshold:.7, resultGroup:"leading")!;
        check(semantic["mode"]!.GetValue<string>()=="semantic" && semantic["source"]!.GetValue<string>()=="cover" &&
            semantic["scope"]!["root_ids"]!.ToJsonString()=="[3]" && semantic["scope"]!["shelf"]!.GetValue<string>()=="資料", "semantic session intersects scope without losing shelf");
        check(!semantic.ContainsKey("page") && semantic["literal_only"]!.GetValue<bool>() && semantic["result_group"]!.GetValue<string>()=="leading", "semantic conditions preserve evidence filters and exclude page");
        semantic["scope"]!["root_ids"]!.AsArray().Clear();
        check(scope["root_ids"]!.AsArray().Count==2 && roots.SequenceEqual(new[]{3,1}), "condition construction never mutates original scope or roots");
        var disjoint = ResultSearchConditions.Create("雨", "", "all", SearchMethod.FromIndex(1), scope, new[]{9})!;
        check(disjoint["scope"]!["root_ids"]!.AsArray().Count==0, "disjoint AI roots remain explicit empty scope");
        foreach(var index in new[]{4,5,6})
        {
            var value=ResultSearchConditions.Create("雨", "", "all", SearchMethod.FromIndex(index), scope, roots)!;
            check(value["mode"]!.GetValue<string>()==SearchMethod.FromIndex(index).Source && value.ContainsKey("root_ids"), "explicit text/candidate mode retained: "+index);
        }
        check(ResultSearchConditions.Create(" ","","all",SearchMethod.FromIndex(5),scope,roots) is null &&
            ResultSearchConditions.Create(" ","","all",SearchMethod.FromIndex(6),scope,roots) is null, "empty explicit text and semantic candidates stay empty without model work");
        check(ResultSearchConditions.Create("","","all",SearchMethod.FromIndex(2),null,null)!["mode"]!.GetValue<string>()=="literal", "empty AI input preserves normal browsing");
        check(ResultSearchConditions.Create("雨","","history",SearchMethod.FromIndex(0),null,null)!["mode"]!.GetValue<string>()=="history", "history uses stable result session");
        var similar=ResultSearchConditions.Create("ignored","image","all",SearchMethod.FromIndex(0),scope,roots,originId:7)!;
        check(similar["mode"]!.GetValue<string>()=="similar"&&similar["item_id"]!.GetValue<int>()==7&&!similar.ContainsKey("page"), "similarity conditions preserve origin and no page");
        var rejected=false;
        try { ResultSearchConditions.Create("雨","","all",SearchMethod.FromIndex(0),null,Array.Empty<int>()); }
        catch(ArgumentOutOfRangeException) { rejected=true; }
        check(rejected,"empty literal root selection cannot broaden to all folders");

        var calls=0;
        var sequence=new ImageViewerSequence(Image(60),59,125,(id,direction,ct)=>
        {
            calls++; var target=id+direction;
            return Task.FromResult<ResultNeighbor?>(target is <1 or >125 ? null : new(target-1,Image(target)));
        });
        check(sequence.IsSession&&await sequence.TryMoveAsync(1,CancellationToken.None)&&sequence.Current.Id==61&&sequence.Position==60,"image sequence crosses 60/61");
        check(await sequence.TryMoveAsync(-1,CancellationToken.None)&&sequence.Current.Id==60,"image sequence crosses 61/60");
        for(var i=60;i<121;i++) await sequence.TryMoveAsync(1,CancellationToken.None);
        check(sequence.Current.Id==121&&sequence.Position==120&&sequence.Count==125,"image sequence crosses 120/121 without growing result metadata");
        var mixed=new ImageViewerSequence(Image(60),59,125,(_,_,_)=>Task.FromResult<ResultNeighbor?>(new(62,Image(63))));
        check(await mixed.TryMoveAsync(1,CancellationToken.None)&&mixed.Position==62,"mixed results use backend image ordinal gaps");
        var noImage=new ImageViewerSequence(Image(60),59,125,(_,_,_)=>Task.FromResult<ResultNeighbor?>(null));
        check(!await noImage.TryMoveAsync(1,CancellationToken.None)&&!noImage.HasNext&&noImage.HasPrevious,"confirmed no-neighbor affects one direction only");

        var delayed=new TaskCompletionSource<ResultNeighbor?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var newest=new TaskCompletionSource<ResultNeighbor?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var racing=new ImageViewerSequence(Image(60),59,125,(_,direction,_)=>direction==1?delayed.Task:newest.Task);
        var old=racing.TryMoveAsync(1,CancellationToken.None);var fresh=racing.TryMoveAsync(-1,CancellationToken.None);
        newest.SetResult(new(58,Image(59)));check(await fresh,"newer image move applied");
        delayed.SetResult(new(60,Image(61)));
        check(!await old&&racing.Current.Id==59&&racing.Position==58,"late response cannot replace newer selection");

        using var cancelled=new CancellationTokenSource();
        var completion=new TaskCompletionSource<ResultNeighbor?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var closing=new ImageViewerSequence(Image(60),59,125,(_,_,_)=>completion.Task);
        var pending=closing.TryMoveAsync(1,cancelled.Token);cancelled.Cancel();completion.SetResult(new(60,Image(61)));
        rejected=false;try{await pending;}catch(OperationCanceledException){rejected=true;}
        check(rejected&&closing.Current.Id==60&&closing.Position==59,"closing rejects late neighbor even if transport ignores cancellation");
        var expired=new ImageViewerSequence(Image(60),59,125,(_,_,_)=>Task.FromException<ResultNeighbor?>(new ResultSessionException(HttpStatusCode.Gone,"{}",60)));
        rejected=false;try{await expired.TryMoveAsync(1,CancellationToken.None);}catch(ResultSessionException){rejected=true;}
        check(rejected&&expired.HasNext&&expired.Current.Id==60,"expiry is a refresh error, never end-of-sequence");
        var wrong=new ImageViewerSequence(Image(60),59,125,(_,_,_)=>Task.FromResult<ResultNeighbor?>(new(58,Image(59))));
        rejected=false;try{await wrong.TryMoveAsync(1,CancellationToken.None);}catch(InvalidDataException){rejected=true;}
        check(rejected&&wrong.Position==59,"wrong-direction response cannot move selection");
    }
}
