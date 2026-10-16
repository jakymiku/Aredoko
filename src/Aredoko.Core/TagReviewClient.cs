using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record TagCandidate(long Id,string Tag,string Explanation,int Page,string State,string? AcceptedTag,long Version)
{
    public string StateLabel => State switch {"pending"=>"未承認","accepted"=>"承認済み",_=>"却下済み"};
}
public sealed record TagBatch(long Id,string Revision,string Model,string ModelRevision,string Adapter,string AdapterVersion,
    string Preprocessing,string EvidenceKind,bool Stale,IReadOnlyList<TagCandidate> Candidates);
public sealed record TagHistory(int ItemId,string Revision,bool Available,string Reason,IReadOnlyList<TagBatch> Batches,long? NextBefore);

// Reflection-free, bounded protocol; a tag proposal ID is Int64, not a UI index.
public static class TagReviewProtocol
{
    public const int MaxJsonBytes=1024*1024;
    public static bool CanOpen(MediaRow row)=>row.Availability=="present" && row.IsFolderBook ||
        row.Availability=="present" && new[]{".png",".apng",".jpg",".jpeg",".webp",".gif",".bmp",".cbz",".zip"}.Any(x=>row.Location.EndsWith(x,StringComparison.OrdinalIgnoreCase));
    public static bool IsRevision(string? value)=>value is {Length:64} && value.All(c=>c is >= '0' and <= '9' or >= 'a' and <= 'f');
    public static void Id(long value){if(value<1)throw new ArgumentOutOfRangeException(nameof(value));}
    public static string Text(JsonElement root,string key,int max)
    {
        var value=root.GetProperty(key).GetString();
        if(string.IsNullOrWhiteSpace(value)||value.Length>max)throw new InvalidDataException("タグ候補の文字情報が無効です。");
        return value;
    }
    private static long Positive(JsonElement root,string key){var value=root.GetProperty(key).GetInt64();Id(value);return value;}
    public static TagBatch Batch(JsonElement root,int itemId,string revision)
    {
        var id=Positive(root,"id");
        if(root.GetProperty("item_id").GetInt32()!=itemId)throw new InvalidDataException("別の作品のタグ候補です。");
        var source=Text(root,"source_revision",64);
        if(!IsRevision(source))throw new InvalidDataException("タグ候補の版が無効です。");
        var evidence=root.GetProperty("evidence");
        var kind=Text(evidence,"kind",8);
        if(evidence.GetProperty("item_id").GetInt32()!=itemId||Text(evidence,"revision",64)!=source||
           evidence.GetProperty("page").GetInt32()!=0||kind is not ("image" or "cover"))
            throw new InvalidDataException("タグ候補の根拠が無効です。");
        var stale=source!=revision;
        if(root.TryGetProperty("stale",out var flag)&&flag.GetBoolean()!=stale)throw new InvalidDataException("タグ候補の更新状態が無効です。");
        var producer=root.GetProperty("producer");
        var array=root.GetProperty("proposals");
        if(array.ValueKind!=JsonValueKind.Array||array.GetArrayLength()>30)throw new InvalidDataException("タグ候補が多すぎます。");
        var candidates=new List<TagCandidate>();var ids=new HashSet<long>();
        foreach(var row in array.EnumerateArray())
        {
            var candidateId=Positive(row,"id");var tag=Text(row,"tag",60);var explanation=Text(row,"explanation",500);
            var state=Text(row,"state",16);var version=row.GetProperty("version").GetInt64();
            var accepted=row.GetProperty("accepted_tag").ValueKind==JsonValueKind.Null?null:Text(row,"accepted_tag",60);
            if(!ids.Add(candidateId)||row.GetProperty("page").GetInt32()!=0||state is not ("pending" or "accepted" or "rejected")||
               version<0||(state=="pending"&&version!=0)||(state!="pending"&&version==0)||
               (state=="accepted")!=(accepted is not null))throw new InvalidDataException("タグ候補の承認状態が無効です。");
            candidates.Add(new(candidateId,tag,explanation,0,state,accepted,version));
        }
        return new(id,source,Text(producer,"model",256),Text(producer,"model_revision",256),Text(producer,"adapter",256),
            Text(producer,"version",256),Text(producer,"preprocessing",256),kind,stale,candidates);
    }
    public static JsonObject CandidateSearchRequest(string query,string kind,string view,int page,IReadOnlyList<int>? rootIds=null,string? shelf=null,string? model=null)
    {
        if(query is null||query.Length>300)throw new ArgumentOutOfRangeException(nameof(query));
        if(page is <0 or >1000000)throw new ArgumentOutOfRangeException(nameof(page));
        if(view is not ("all" or "favorites" or "unreviewed" or "shelf"))throw new ArgumentOutOfRangeException(nameof(view));
        if(shelf is not null&&shelf.Length>80)throw new ArgumentOutOfRangeException(nameof(shelf));
        if(model is not null&&(string.IsNullOrWhiteSpace(model)||model.Trim().Length>256))throw new ArgumentOutOfRangeException(nameof(model));
        var body=new JsonObject{["query"]=query,["kind"]=kind??"",["view"]=view,["page"]=page};
        if(rootIds is not null)
        {
            var normalized=FolderSearch.NormalizeNonEmpty(rootIds)!;
            var array=new JsonArray();
            foreach(var id in normalized)array.Add((JsonNode?)JsonValue.Create(id));
            body["root_ids"]=array;
        }
        if(shelf is not null)body["shelf"]=shelf;
        if(model is not null)body["model"]=model.Trim();
        return body;
    }
    public static SearchResponse ParseCandidateSearch(byte[] bytes,int expectedPage)
    {
        try
        {
            if(expectedPage<0)throw new ArgumentOutOfRangeException(nameof(expectedPage));
            var text=Encoding.UTF8.GetString(bytes);
            using var doc=JsonDocument.Parse(text);var root=doc.RootElement;
            if(root.GetProperty("search_mode").GetString()!="pending-proposals"||
               root.GetProperty("page").GetInt32()!=expectedPage||
               root.GetProperty("limit").GetInt32()!=60)
                throw new InvalidDataException("未承認タグ候補の検索応答が要求と一致しません。");
            var parsed=Protocol.ParseSearch(text);
            var rawItems=root.GetProperty("items");
            if(parsed.Total<0||parsed.Items.Count>60||parsed.Items.Count>parsed.Total||
               rawItems.GetArrayLength()!=parsed.Items.Count||
               parsed.Items.Select(x=>x.Id).Distinct().Count()!=parsed.Items.Count)
                throw new InvalidDataException("未承認タグ候補の件数が無効です。");
            var index=0;
            foreach(var element in rawItems.EnumerateArray())
            {
                var row=parsed.Items[index++];
                if(row.Id<1||!element.TryGetProperty("proposal_match",out var match)||match.ValueKind!=JsonValueKind.Object)
                    throw new InvalidDataException("未承認タグ候補の根拠情報がありません。");
                var batchId=Positive(match,"batch_id");
                var revision=Text(match,"source_revision",64);
                var sourceState=Text(match,"source_state",16);
                var state=Text(match,"state",16);
                if(!IsRevision(revision)||state!="pending"||sourceState is not ("current" or "stale" or "unverified" or "unavailable"))
                    throw new InvalidDataException("未承認タグ候補の状態が無効です。");
                var tagArray=match.GetProperty("tags");
                if(tagArray.ValueKind!=JsonValueKind.Array||tagArray.GetArrayLength() is <1 or >30)
                    throw new InvalidDataException("未承認タグ候補の一覧が無効です。");
                var tags=new List<string>(tagArray.GetArrayLength());
                foreach(var t in tagArray.EnumerateArray())
                {
                    var val=t.GetString();
                    if(string.IsNullOrWhiteSpace(val)||val.Length>60)throw new InvalidDataException("未承認タグ候補の名前が無効です。");
                    tags.Add(val);
                }
                var producer=match.GetProperty("producer");
                var evidence=match.GetProperty("evidence");
                var evKind=Text(evidence,"kind",8);
                if(evidence.GetProperty("item_id").GetInt32()!=row.Id||Text(evidence,"revision",64)!=revision||
                   evidence.GetProperty("page").GetInt32()!=0||evKind is not ("image" or "cover"))
                    throw new InvalidDataException("未承認タグ候補の根拠が無効です。");
                row.Proposal=new ProposalMatch(
                    batchId,revision,sourceState,tags.ToArray(),
                    Text(producer,"model",256),Text(producer,"model_revision",256),
                    Text(producer,"adapter",256),Text(producer,"version",256),
                    Text(producer,"preprocessing",256),evKind,0);
            }
            return parsed;
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {throw new InvalidDataException("未承認タグ候補の検索結果を読み取れません。",ex);}
    }
    public static TagHistory Parse(byte[] bytes,int itemId)
    {
        try
        {
            Id(itemId);using var doc=JsonDocument.Parse(bytes);var root=doc.RootElement;
            if(root.GetProperty("item_id").GetInt32()!=itemId)throw new InvalidDataException("別の作品のタグ履歴です。");
            var revision=Text(root,"source_revision",64);
            if(!IsRevision(revision))throw new InvalidDataException("タグ履歴の版が無効です。");
            var available=root.GetProperty("available").GetBoolean();var reason=root.GetProperty("reason").GetString()??"";
            if(reason.Length>1000||(!available&&string.IsNullOrWhiteSpace(reason)))throw new InvalidDataException("タグモデルの状態が無効です。");
            var array=root.GetProperty("batches");
            if(array.ValueKind!=JsonValueKind.Array||array.GetArrayLength()>10)throw new InvalidDataException("タグ履歴が多すぎます。");
            var batches=array.EnumerateArray().Select(row=>Batch(row,itemId,revision)).ToArray();
            if(batches.Select(b=>b.Id).Distinct().Count()!=batches.Length||
               batches.SelectMany(b=>b.Candidates).Select(c=>c.Id).Distinct().Count()!=batches.Sum(b=>b.Candidates.Count))
                throw new InvalidDataException("タグ履歴のIDが重複しています。");
            var next=root.GetProperty("next_before").ValueKind==JsonValueKind.Null?(long?)null:Positive(root,"next_before");
            if(next is not null&&(batches.Length==0||next!=batches[^1].Id))throw new InvalidDataException("タグ履歴のページ指定が無効です。");
            return new(itemId,revision,available,reason,batches,next);
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {throw new InvalidDataException("タグ候補を読み取れません。更新してやり直してください。",ex);}
    }
}

// Shares the authenticated loopback session, but generation has a 95s deadline
// independent of the ordinary search client's 40s HttpClient timeout.
public sealed class TagReviewClient(HttpClient client)
{
    private const string Route="api/library/tag-suggestions";
    private async Task<byte[]> ReadAsync(string route,JsonObject? body,int limit,CancellationToken cancellation,int seconds=10,bool image=false)
    {
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellation);deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        try
        {
            using var request=new HttpRequestMessage(body is null?HttpMethod.Get:HttpMethod.Post,route);
            if(body is not null)request.Content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");
            using var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,deadline.Token);
            var cap=response.IsSuccessStatusCode?limit:32768;
            if(response.Content.Headers.ContentLength is long size&&(size<0||size>cap))throw new InvalidDataException("タグ候補の応答が大きすぎます。");
            await using var input=await response.Content.ReadAsStreamAsync(deadline.Token);
            using var output=new MemoryStream();var buffer=new byte[16384];int read;
            while((read=await input.ReadAsync(buffer,deadline.Token))!=0)
            {if(output.Length+read>cap)throw new InvalidDataException("タグ候補の応答が大きすぎます。");output.Write(buffer,0,read);}
            if(response.Content.Headers.ContentLength is long expected&&expected!=output.Length)throw new InvalidDataException("タグ候補の応答が途中で切れました。");
            var bytes=output.ToArray();
            if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(Encoding.UTF8.GetString(bytes),(int)response.StatusCode));
            var mime=response.Content.Headers.ContentType?.MediaType;
            if(image?mime is not ("image/png" or "image/jpeg" or "image/webp" or "image/gif" or "image/bmp"):mime!="application/json")
                throw new InvalidDataException("タグ候補の応答形式が無効です。");
            return bytes;
        }
        catch(OperationCanceledException ex) when(!cancellation.IsCancellationRequested)
        {throw new TimeoutException("タグ候補の処理が時間内に完了しませんでした。更新して状態を確認してください。",ex);}
    }
    public async Task<TagHistory> HistoryAsync(int itemId,long? before,CancellationToken cancellation)
    {
        TagReviewProtocol.Id(itemId);if(before is long id)TagReviewProtocol.Id(id);
        return TagReviewProtocol.Parse(await ReadAsync($"{Route}/{itemId}?limit=10"+(before is null?"":$"&before={before}"),null,TagReviewProtocol.MaxJsonBytes,cancellation),itemId);
    }
    public async Task GenerateAsync(int itemId,string requestId,CancellationToken cancellation)
    {
        TagReviewProtocol.Id(itemId);RequestId(requestId);
        var bytes=await ReadAsync(Route+"/generate",new(){["item_id"]=itemId,["request_id"]=requestId},TagReviewProtocol.MaxJsonBytes,cancellation,95);
        using var doc=JsonDocument.Parse(bytes);var root=doc.RootElement;_=root.GetProperty("reused").GetBoolean();
        var batch=root.GetProperty("batch");_=TagReviewProtocol.Batch(batch,itemId,TagReviewProtocol.Text(batch,"source_revision",64));
    }
    public async Task<bool> CancelAsync(string requestId,CancellationToken cancellation)
    {
        RequestId(requestId);using var doc=JsonDocument.Parse(await ReadAsync(Route+"/cancel",new(){["request_id"]=requestId},32768,cancellation,5));
        return doc.RootElement.GetProperty("cancel_requested").GetBoolean();
    }
    private static void RequestId(string id)
    {if(id.Length!=32||id.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f')))throw new ArgumentException("Invalid tag request ID");}
    public async Task ReviewAsync(int itemId,TagCandidate candidate,bool accept,string edited,CancellationToken cancellation)
    {
        TagReviewProtocol.Id(itemId);TagReviewProtocol.Id(candidate.Id);
        if(candidate.State!="pending"||candidate.Version!=0||accept&&(string.IsNullOrWhiteSpace(edited)||edited.Trim().Length>60))throw new ArgumentException("承認する候補を確認してください。");
        var body=new JsonObject{["item_id"]=itemId,["proposal_id"]=candidate.Id,["version"]=candidate.Version,["decision"]=accept?"accept":"reject"};
        if(accept)body["tag"]=edited.Trim();
        using var doc=JsonDocument.Parse(await ReadAsync(Route+"/review",body,32768,cancellation));var root=doc.RootElement;
        if(root.GetProperty("proposal_id").GetInt64()!=candidate.Id||root.GetProperty("version").GetInt64()!=candidate.Version+1||
           root.GetProperty("state").GetString()!=(accept?"accepted":"rejected")||
           (accept?root.GetProperty("accepted_tag").GetString()!=edited.Trim():root.GetProperty("accepted_tag").ValueKind!=JsonValueKind.Null))
            throw new InvalidDataException("承認結果を確認できません。更新してください。");
    }
    public Task<byte[]> EvidenceAsync(int itemId,string revision,CancellationToken cancellation)
    {
        TagReviewProtocol.Id(itemId);if(!TagReviewProtocol.IsRevision(revision))throw new ArgumentException("根拠画像の版が無効です。");
        return ReadAsync($"{Route}/{itemId}/evidence?revision={revision}",null,PreviewPolicy.MaxSourceBytes,cancellation,image:true);
    }
    public async Task<MediaRow> ItemAsync(int itemId,CancellationToken cancellation)
    {
        TagReviewProtocol.Id(itemId);var row=Protocol.ParseItem(Encoding.UTF8.GetString(await ReadAsync($"api/items/{itemId}",null,TagReviewProtocol.MaxJsonBytes,cancellation)));
        if(row.Id!=itemId)throw new InvalidDataException("別の作品の整理情報です。");return row;
    }
    public async Task<SearchResponse> SearchCandidatesAsync(string query,string kind,string view,int page,IReadOnlyList<int>? rootIds=null,string? shelf=null,string? model=null,CancellationToken cancellation=default)
    {
        var body=TagReviewProtocol.CandidateSearchRequest(query,kind,view,page,rootIds,shelf,model);
        var bytes=await ReadAsync(Route+"/search",body,TagReviewProtocol.MaxJsonBytes,cancellation,15);
        return TagReviewProtocol.ParseCandidateSearch(bytes,page);
    }
}
