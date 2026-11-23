using Aredoko.Core;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;
internal static class LibrarySelectionTests
{
    public static async Task Run(Action<bool,string> check)
    {
        check(MediaKindFilter.FromIndex(5)=="compressed"&&MediaKindFilter.FromIndex(1)=="book","compressed filter keeps existing UI indices and book contract");
        foreach(var (kind,path,expected) in new[]{("book","comic.CBZ",true),("archive","comic.zip",true),("book","comic.pdf",false),("book","comic/",false),("image","comic.cbz.png",false)})
        {
            var row=new MediaRow{Id=1,Kind=kind,Location=path,Availability="present"};
            check(MediaKindFilter.IsCompressed(row)==expected&&(expected?MediaKindFilter.DisplayName(row)=="圧縮ファイル":true),"derived compressed category: "+path);
            if(expected)check(ArchiveManifest.CanOpen(row),"compressed label preserves the book viewer route: "+path);
        }
        var selection=new LibrarySelection();selection.Bind("first",1000);selection.Single(new(1,0));
        selection.Visible([new(601,600),new(602,601)],[601],601);
        check(selection.Ids.SequenceEqual(new[]{1,601}),"selected IDs survive eviction from the 600-row window");
        selection.Single(new(60,59));var calls=new List<(int,int)>();
        await selection.RangeAsync(new(181,180),false,(offset,count,token)=>{calls.Add((offset,count));return Task.FromResult<IReadOnlyList<int>>(Enumerable.Range(offset+1,count).ToArray());},CancellationToken.None);
        check(selection.Count==122&&selection.Contains(60)&&selection.Contains(61)&&selection.Contains(121)&&selection.Contains(181)&&calls.SequenceEqual(new[]{(59,120),(179,2)}),"Shift range crosses 60/120 in bounded server-order reads");
        var previous=selection.Ids.ToArray();bool overflow=false;
        try{await selection.RangeAsync(new(400,399),false,(_,_,_)=>throw new Exception("must not fetch"),CancellationToken.None);}catch(InvalidOperationException){overflow=true;}
        check(overflow&&selection.Ids.SequenceEqual(previous),"oversized ranges are rejected without truncating or changing the selection");
        using var cancelled=new CancellationTokenSource();cancelled.Cancel();bool cancellation=false;
        try{await selection.RangeAsync(new(61,60),false,(_,_,_)=>throw new Exception("must not fetch"),cancelled.Token);}catch(OperationCanceledException){cancellation=true;}
        check(cancellation&&selection.Ids.SequenceEqual(previous),"cancelled range preparation is atomic");
        bool obsolete=false;
        try{await selection.RangeAsync(new(61,60),false,(offset,count,token)=>{selection.Bind("new",1000);return Task.FromResult<IReadOnlyList<int>>(Enumerable.Range(offset+1,count).ToArray());},CancellationToken.None);}catch(OperationCanceledException){obsolete=true;}
        check(obsolete&&selection.Count==0&&selection.SessionId=="new","a stale range cannot enter another search session");
        selection.Single(new(5,4));bool invalid=false;
        try{await selection.RangeAsync(new(6,5),false,(_,_,_)=>Task.FromResult<IReadOnlyList<int>>(new[]{5,5}),CancellationToken.None);}catch(InvalidDataException){invalid=true;}
        check(invalid&&selection.Ids.SequenceEqual(new[]{5}),"invalid server range leaves the previous selection intact");
        selection.Clear();
        check(selection.PreviousAnchor is null,"clear resets PreviousAnchor");
        selection.Single(new(12,1));
        check(selection.Anchor==new ResultPosition(12,1)&&selection.PreviousAnchor is null,"first single selection after clear has no PreviousAnchor");
        selection.Single(new(14,3));
        check(selection.Anchor==new ResultPosition(14,3)&&selection.PreviousAnchor==new ResultPosition(12,1),"second distinct single selection retains the previous anchor");
        selection.Single(new(14,3));
        check(selection.PreviousAnchor==new ResultPosition(12,1),"re-selecting the same row keeps the previous anchor intact");
        await selection.RangeAsync(new(16,5),false,(offset,count,token)=>Task.FromResult<IReadOnlyList<int>>(Enumerable.Range(12+offset-1,count).ToArray()),CancellationToken.None);
        check(selection.PreviousAnchor is null,"range selection resets PreviousAnchor");
        selection.Single(new(5,4));selection.Single(new(6,5));
        check(selection.PreviousAnchor==new ResultPosition(5,4),"Distinct Single establishes PreviousAnchor before Visible");
        selection.Visible([new(6,5)],[6],6);
        check(selection.PreviousAnchor is null,"visible selection resets PreviousAnchor");
        selection.Bind("filtered",1,[new(6,0)]);
        check(selection.Count==1&&selection.Contains(6)&&!selection.Contains(5)&&selection.Anchor==new ResultPosition(6,0)&&selection.PreviousAnchor is null,"rebasing preserves remaining IDs, drops filtered-out items, and resets PreviousAnchor");

        var requests=new List<string>();
        using var handler=new Stub(async request=>
        {
            var payload=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;var id=payload["session_id"]!.GetValue<string>();
            var route=request.RequestUri!.AbsolutePath.Split('/').Last();requests.Add(route);
            JsonObject response=route switch
            {
                "create"=>new(){["session_id"]=id,["state"]="ready",["total"]=1000,["conditions"]=payload["conditions"]!.DeepClone(),["range_limit"]=120,["idle_seconds"]=900},
                "locate"=>new(){["session_id"]=id,["conditions"]=new JsonObject{["query"]="fixture"},["positions"]=new JsonArray(new JsonObject{["id"]=1,["ordinal"]=0})},
                "edit"=>new(){["session_id"]=id,["operation"]=payload["operation"]!.DeepClone(),["item_ids"]=payload["item_ids"]!.DeepClone(),["updated"]=payload["item_ids"]!.AsArray().Count},
                _=>new(){["closed"]=true}
            };
            if(route=="edit")check(payload["operation"]!.GetValue<string>()=="shelves_add"&&payload["shelf_ids"]![0]!.GetValue<long>()==4294967297,"bulk shelf request preserves 64-bit shelf IDs and explicit additive semantics");
            return new(HttpStatusCode.OK){Content=new StringContent(response.ToJsonString(),Encoding.UTF8,"application/json")};
        });
        using var api=new LibraryApi(handler);await using var session=await api.Results.CreateAsync(new JsonObject{["query"]="fixture"},CancellationToken.None);
        check((await session.LocateAsync([1,9],CancellationToken.None)).SequenceEqual(new[]{new ResultPosition(1,0)}),"selection locate accepts only IDs remaining in the current scope");
        await session.EditSelectionAsync([1,2],SelectionOperation.ShelvesAdd,[4294967297],CancellationToken.None);
        bool wrong=false;try{await session.EditSelectionAsync([1,1],SelectionOperation.FavoriteAdd,[],CancellationToken.None);}catch(ArgumentException){wrong=true;}
        check(wrong&&requests.Count(route=>route=="edit")==1,"invalid bulk IDs are rejected before sending a request");
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)=>send(request);}
}
