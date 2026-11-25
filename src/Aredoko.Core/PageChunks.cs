using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public static class PageChunkRequests
{
    public const int MaxPages=128,ChunkSize=16,LargeBookWarningThreshold=100;
    public static bool NeedsLargeBookWarning(int pageCount)=>pageCount>LargeBookWarningThreshold;
    public static string LargeBookWarningMessage(string title,int pageCount,int remainingPages)=>AppText.L(
        $"「{title}」は {pageCount:N0} ページ（未登録 {remainingPages:N0} ページ）あるため、全ページの登録に時間がかかる可能性があります。\n\n途中で中止しても、処理済みのページは保持されます。このまま全ページを登録しますか？",
        $"\"{title}\" has {pageCount:N0} pages ({remainingPages:N0} unindexed), so indexing all pages may take a while.\n\nPages already processed are kept if you cancel midway. Index all pages now?");
    internal static string Profile(string profile)=>profile.Length is >0 and <=256?profile:throw new ArgumentException(AppText.L("モデル設定を確認してください。", "Check the AI model setting."));
    internal static JsonObject Scope(JsonObject scope)
    {
        if(scope.Any(p=>p.Key is not ("root_ids" or "kind" or "shelf" or "book_pages")))throw new ArgumentException(AppText.L("対象範囲が無効です。", "Invalid target scope."));
        JsonArray? roots=null;
        if(scope["root_ids"] is JsonNode node)
        {
            long Root(JsonNode? n)
            {
                if(n is JsonValue value)
                {
                    if(value.TryGetValue<long>(out var wide))return wide;
                    if(value.TryGetValue<int>(out var narrow))return narrow;
                }
                throw new ArgumentException(AppText.L("対象フォルダが無効です。", "Invalid target folder."));
            }
            var ids=node.AsArray().Select(Root).ToArray();
            if(ids.Length>256||ids.Any(n=>n<1)||ids.Distinct().Count()!=ids.Length)throw new ArgumentException(AppText.L("対象フォルダが無効です。", "Invalid target folder."));
            roots=new JsonArray(ids.Order().Select(n=>(JsonNode?)JsonValue.Create(n)).ToArray());
        }
        if(scope.ContainsKey("kind")&&scope["kind"] is null)throw new ArgumentException(AppText.L("対象の種類が無効です。", "Invalid target kind."));
        var kind=scope["kind"]?.GetValue<string>()??"";var shelf=scope["shelf"]?.GetValue<string>();
        if(kind is not ("" or "book" or "archive" or "compressed" or "image" or "video" or "audio" or "material")||shelf?.Length>80)throw new ArgumentException(AppText.L("対象条件が無効です。", "Invalid target filter."));
        string? bookPages=null;
        if(scope.ContainsKey("book_pages"))
        {
            if(scope["book_pages"] is null)throw new ArgumentException(AppText.L("対象範囲が無効です。", "Invalid target scope."));
            bookPages=scope["book_pages"]!.GetValue<string>();
            if(bookPages is not ("cover_only" or "all_pages"))throw new ArgumentException(AppText.L("対象範囲が無効です。", "Invalid target scope."));
        }
        var result=new JsonObject{{"root_ids",roots},{"kind",kind},{"shelf",shelf}};
        if(bookPages is not null)result["book_pages"]=bookPages;
        return result;
    }
    public static JsonObject Plan(int item,string revision,JsonObject scope,int maximum,string profile)
    {
        PageEvidenceProtocol.ValidateId(item);PageEvidenceProtocol.ValidateToken(revision,nameof(revision));
        if(maximum is <1 or >MaxPages)throw new ArgumentOutOfRangeException(nameof(maximum));
        return new(){{"item_id",item},{"revision",revision},{"scope",Scope(scope)},{"max_pages",maximum},{"profile",Profile(profile)}};
    }
    public static JsonObject AllPages(int item,string revision,JsonObject scope,string profile)
    {
        PageEvidenceProtocol.ValidateId(item);PageEvidenceProtocol.ValidateToken(revision,nameof(revision));
        return new(){{"item_id",item},{"revision",revision},{"scope",Scope(scope)},{"profile",Profile(profile)}};
    }
    public static JsonObject Start(PageChunkPlan plan)
    {
        if(!plan.CanStart)throw new ArgumentException(AppText.L("追加する範囲を確認してください。", "Check the scope to add."));
        if(plan.PageIds.Count is <1 or >128||plan.PageIds.Count>plan.Maximum||plan.PageIds.Distinct().Count()!=plan.PageIds.Count||plan.PageIds.Any(p=>!TagReviewProtocol.IsRevision(p)))throw new ArgumentException(AppText.L("ページの選択が無効です。", "Invalid page selection."));
        var request=Plan(plan.ItemId,plan.Revision,plan.Scope,plan.Maximum,plan.Profile);request.Remove("max_pages");
        request["page_ids"]=new JsonArray(plan.PageIds.Select(p=>(JsonNode?)JsonValue.Create(p)).ToArray());return request;
    }
    public static JsonObject Resume(PageChunkStatus status,JsonObject scope)
    {
        if(!status.CanResume||!status.MatchesScope(scope))throw new ArgumentException(AppText.L("前回と同じ対象範囲を保存してから再開してください。", "Save the same target scope before resuming."));
        PageEvidenceProtocol.ValidateRequestId(status.JobId);
        var request=AIScopeRequests.Scoped(Scope(scope));request["job_id"]=status.JobId;request["profile"]=Profile(status.Profile);return request;
    }
    internal static IReadOnlyList<string> Ids(JsonElement root,bool empty=false)
    {
        var array=root.GetProperty("page_ids");
        if(array.ValueKind!=JsonValueKind.Array||array.GetArrayLength()>(int)MaxPages||(!empty&&array.GetArrayLength()==0))throw new InvalidDataException(AppText.L("ページ数が無効です。", "Invalid page count."));
        var ids=array.EnumerateArray().Select(n=>n.GetString()??"").ToArray();
        if(ids.Any(p=>!TagReviewProtocol.IsRevision(p))||ids.Distinct().Count()!=ids.Length)throw new InvalidDataException(AppText.L("ページの選択が無効です。", "Invalid page selection."));
        return Array.AsReadOnly(ids);
    }
    internal static JsonObject ReadScope(JsonElement root)=>Scope(JsonNode.Parse(root.GetProperty("scope").GetRawText())!.AsObject());
}

public sealed record PageChunkPlan(int ItemId,string Revision,string Profile,JsonObject Scope,bool Supported,bool Available,string SourceState,
    int PageCount,int IndexedPages,int RemainingPages,int Maximum,IReadOnlyList<PageImageRange> Ranges,IReadOnlyList<string> PageIds,int ChunksTotal)
{
    public bool CanStart=>Supported&&Available&&SourceState=="current"&&PageIds.Count>0;
    public string Summary=>PageIds.Count==0?AppText.L("追加する未準備ページはありません。", "No unready pages to add."):AppText.L($"今回: {PageIds.Count}ページ · {ChunksTotal}回に分けて保存", $"This batch: {PageIds.Count} pages · Save in {ChunksTotal} chunks");
    public string RangeSummary=>AppText.L(string.Join("、",Ranges.Select(r=>r.Label))+"ページ", "Pages " + string.Join(", ",Ranges.Select(r=>r.Label)));
    public static PageChunkPlan Parse(byte[] bytes,int item,string revision,JsonObject scope,int maximum,string profile)
    {
        try
        {
            using var doc=JsonDocument.Parse(bytes);var r=doc.RootElement;
            var source=r.GetProperty("source_state").GetString()??"";var supported=r.GetProperty("supported").GetBoolean();var available=r.GetProperty("available").GetBoolean();
            var total=r.GetProperty("page_count").GetInt32();var ready=r.GetProperty("indexed_pages").GetInt32();var remaining=r.GetProperty("remaining_pages").GetInt32();
            var ids=PageChunkRequests.Ids(r,true);var chunks=r.GetProperty("chunks_total").GetInt32();var actualScope=PageChunkRequests.ReadScope(r);
            if(r.GetProperty("item_id").GetInt32()!=item||r.GetProperty("source_revision").GetString()!=revision||!TagReviewProtocol.IsRevision(revision)
                ||r.GetProperty("profile").GetString()!=profile||r.GetProperty("max_pages").GetInt32()!=maximum||maximum is <1 or >128
                ||!JsonNode.DeepEquals(actualScope,PageChunkRequests.Scope(scope))||r.GetProperty("chunk_size").GetInt32()!=16
                ||source is not ("current" or "stale" or "unverified" or "unavailable")||total is <1 or >10000||ready<0||ready>total||remaining!=total-ready
                ||ids.Count!=(supported&&source=="current"?Math.Min(maximum,remaining):0)||chunks!=(ids.Count+15)/16||r.GetProperty("total_gap_pages").GetInt32()!=ids.Count)
                throw new InvalidDataException(AppText.L("追加範囲が変わりました。もう一度確認してください。", "The range to add has changed. Please check again."));
            var array=r.GetProperty("chunks");if(array.ValueKind!=JsonValueKind.Array||array.GetArrayLength()>128)throw new InvalidDataException(AppText.L("範囲数が無効です。", "Invalid chunk count."));
            var ranges=new List<PageImageRange>();var sum=0;
            foreach(var entry in array.EnumerateArray())
            {
                var range=new PageImageRange(entry.GetProperty("start").GetInt32(),entry.GetProperty("count").GetInt32());
                if(range.Start<0||range.Start>=total||range.Count is <1 or >16||range.Count>total-range.Start||ranges.Count>0&&range.Start<ranges[^1].End)throw new InvalidDataException(AppText.L("ページ範囲が無効です。", "Invalid page range."));
                ranges.Add(range);sum+=range.Count;
            }
            if(sum!=ids.Count||(!supported||source!="current")&&(ids.Count!=0||ready!=0))throw new InvalidDataException(AppText.L("ページ件数が一致しません。", "Page counts do not match."));
            return new(item,revision,profile,actualScope,supported,available,source,total,ready,remaining,maximum,ranges.AsReadOnly(),ids,chunks);
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {throw new InvalidDataException(AppText.L("ページの追加範囲を読み取れません。", "Unable to read the page range to add."),ex);}
    }
}

public sealed record PageChunkStatus(string JobId,int ItemId,string Revision,string Profile,JsonObject Scope,string State,
    int Total,int Processed,int Indexed,int Reused,int ChunkSize,int ChunksTotal,int ChunksCompleted,IReadOnlyList<string> PageIds,string Error)
{
    public bool Running=>State is "running" or "cancelling";
    public bool CanResume=>State is "cancelled" or "interrupted" or "failed";
    public string Summary=>AppText.L($"保存済み {Indexed}/{Total}ページ · {ChunksCompleted}/{ChunksTotal}回", $"Saved {Indexed}/{Total} pages · {ChunksCompleted}/{ChunksTotal} chunks");
    public bool MatchesScope(JsonObject scope)
    {try{return JsonNode.DeepEquals(Scope,PageChunkRequests.Scope(scope));}catch(Exception ex) when(ex is ArgumentException or InvalidOperationException or FormatException){return false;}}
    public static PageChunkStatus Parse(byte[] bytes,string profile,string? expectedJob=null,int? item=null,string? revision=null,JsonObject? scope=null)
    {
        try
        {
            using var doc=JsonDocument.Parse(bytes);var r=doc.RootElement;
            var job=TagReviewProtocol.Text(r,"job_id",32);var source=TagReviewProtocol.Text(r,"source_revision",64);var state=TagReviewProtocol.Text(r,"state",16);
            var actualItem=r.GetProperty("item_id").GetInt32();var total=r.GetProperty("total").GetInt32();var processed=r.GetProperty("processed").GetInt32();
            var saved=r.GetProperty("indexed").GetInt32();var reused=r.GetProperty("reused").GetInt32();var size=r.GetProperty("chunk_size").GetInt32();
            var chunks=r.GetProperty("chunks_total").GetInt32();var complete=r.GetProperty("chunks_completed").GetInt32();var ids=PageChunkRequests.Ids(r);
            var actualScope=PageChunkRequests.ReadScope(r);var error=r.GetProperty("error").GetString();
            if(r.GetProperty("job").GetString()!="book-pages-chunked"||job.Length!=32||job.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))
                ||expectedJob is not null&&job!=expectedJob||actualItem<1||item is int expectedItem&&actualItem!=expectedItem||revision is not null&&source!=revision
                ||!TagReviewProtocol.IsRevision(source)||r.GetProperty("profile").GetString()!=profile||profile.Length is <1 or >256
                ||scope is not null&&!JsonNode.DeepEquals(actualScope,PageChunkRequests.Scope(scope))
                ||state is not ("running" or "cancelling" or "complete" or "cancelled" or "interrupted" or "failed")
                ||total!=ids.Count||processed<0||processed>total||saved<0||saved>processed||reused<0||reused>processed||size is <1 or >16
                ||chunks!=(total+size-1)/size||complete<0||complete>chunks||saved!=Math.Min(complete*size,total)
                ||state=="complete"&&(saved!=total||processed!=total)||error is null||error.Length>1024)
                throw new InvalidDataException(AppText.L("ページの処理状況が変わりました。設定で確認してください。", "Page processing status has changed. Check it in Settings."));
            return new(job,actualItem,source,profile,actualScope,state,total,processed,saved,reused,size,chunks,complete,ids,AppText.TranslateBackend(error));
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {throw new InvalidDataException(AppText.L("ページの処理状況を読み取れません。", "Unable to read page processing status."),ex);}
    }
}

public sealed record PageAllStatus(string JobId,string State,int ItemId,string Revision,string Profile,int PageCount,int AlreadyIndexed,int Processed,int Total,int Indexed,int ChunksCompleted,int ChunksTotal,string Error)
{
    public bool Running=>State is "running" or "cancelling";
    public bool Complete=>State=="complete";
    public string Summary=>Total==0
        ?AppText.L($"全 {PageCount:N0} ページはすでに登録済みです", $"All {PageCount:N0} pages are already indexed")
        :AppText.L($"全ページ処理: {AlreadyIndexed+Indexed}/{PageCount} ページ（今回 {Indexed}/{Total} · {ChunksCompleted}/{ChunksTotal}回）", $"All pages: {AlreadyIndexed+Indexed}/{PageCount} pages (batch {Indexed}/{Total} · {ChunksCompleted}/{ChunksTotal} chunks)");
    public static PageAllStatus Parse(byte[] bytes,string expectedProfile,string? expectedJobId,int expectedItem,string expectedRevision)
    {
        try
        {
            using var doc=JsonDocument.Parse(bytes);var r=doc.RootElement;
            var job=TagReviewProtocol.Text(r,"job_id",32);
            var source=TagReviewProtocol.Text(r,"source_revision",64);
            var state=TagReviewProtocol.Text(r,"state",16);
            var actualItem=r.GetProperty("item_id").GetInt32();
            var profile=r.GetProperty("profile").GetString()??"";
            var pageCount=r.GetProperty("page_count").GetInt32();
            var alreadyIndexed=r.GetProperty("already_indexed").GetInt32();
            var processed=r.GetProperty("processed").GetInt32();
            var total=r.GetProperty("total").GetInt32();
            var indexed=r.GetProperty("indexed").GetInt32();
            var chunksCompleted=r.GetProperty("chunks_completed").GetInt32();
            var chunksTotal=r.GetProperty("chunks_total").GetInt32();
            var error=r.GetProperty("error").GetString();
            if(r.GetProperty("job").GetString()!="book-pages-all"
                ||job.Length!=32||job.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))
                ||(expectedJobId is not null&&job!=expectedJobId)
                ||actualItem!=expectedItem||source!=expectedRevision
                ||!TagReviewProtocol.IsRevision(source)||profile!=expectedProfile||profile.Length is <1 or >256
                ||state is not ("running" or "cancelling" or "complete" or "cancelled" or "interrupted" or "failed")
                ||pageCount is <1 or >10000||alreadyIndexed<0||alreadyIndexed>pageCount
                ||total!=pageCount-alreadyIndexed||processed<0||processed>total
                ||indexed<0||indexed>total||chunksTotal!=(total+15)/16
                ||chunksCompleted<0||chunksCompleted>chunksTotal
                ||(state=="complete"&&(indexed!=total||processed!=total))
                ||error is null||error.Length>1024)
                throw new InvalidDataException(AppText.L("全ページ登録の状況が変わりました。", "All-page indexing status has changed."));
            return new(job,state,actualItem,source,profile,pageCount,alreadyIndexed,processed,total,indexed,chunksCompleted,chunksTotal,AppText.TranslateBackend(error));
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {throw new InvalidDataException(AppText.L("全ページ登録の状況を読み取れません。", "Unable to read all-page indexing status."),ex);}
    }
}
