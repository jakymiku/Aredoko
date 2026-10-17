using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record PageEntry(string PageId, int Page, string Mime, long SizeBytes);
public sealed record PageIndexList(int ItemId, string? SourceRevision, string? SourceKind, string SourceState, int PageCount, int Offset, int Limit, IReadOnlyList<PageEntry> Pages);
public sealed record PageIndexRefresh(int ItemId, string SourceRevision, string SourceKind, int PageCount, bool Reused);
public sealed record PageTextProducer(string Adapter, string Version, string Model, string ModelRevision, string Preprocessing);
public sealed record PageTextEntry(int Page, string PageId, string Text, PageTextProducer Producer);
public sealed record PageTextList(int ItemId, string? SourceRevision, string SourceState, int Total, int Offset, int Limit, IReadOnlyList<PageTextEntry> Pages);
public sealed record PageTextStatus(bool Available, string Reason);
public sealed record PageTextGenerationResult(int ItemId, string SourceRevision, int Processed, int Reused);
public sealed record PageTextEvidencePage(string PageId, int Page, string Excerpt, PageTextProducer Producer);
public sealed record PageTextMatch(string SourceRevision, string SourceState, int MatchingPages, IReadOnlyList<PageTextEvidencePage> Pages)
{
    // A stored page number is meaningful only in its exact source revision.
    public int? InitialReaderPage(ArchiveManifest manifest)
    {
        if(SourceState!="current"||SourceRevision!=manifest.Revision||Pages.Count==0)return null;
        var page=Pages[0].Page;
        return page>=0&&page<manifest.PageCount?page:null;
    }
    public string SourceStateLabel => SourceState switch
    {
        "current" => "元ファイル一致",
        "stale" => "元ファイル変更あり",
        "unverified" => "元ファイル確認待ち",
        _ => "元ファイル利用不可"
    };
    public string Summary
    {
        get
        {
            var first = Pages.Count > 0 ? Pages[0] : null;
            var snippet = first is null ? "" : (first.Excerpt.Length > 80 ? first.Excerpt[..80] + "…" : first.Excerpt).Replace('\r', ' ').Replace('\n', ' ');
            var model = first?.Producer.Model ?? "";
            var pageNumbers = string.Join("、", Pages.Select(p => $"{p.Page + 1}ページ"));
            return $"ページ本文一致（{MatchingPages}ページ: {pageNumbers}）{(snippet.Length > 0 ? $" · 「{snippet}」" : "")}\nモデル: {model} · {SourceStateLabel}";
        }
    }
}

public static class PageEvidenceProtocol
{
    public const int MaxJsonBytes = 1024 * 1024;
    private static readonly HashSet<string> States = ["unindexed", "current", "stale", "unverified", "unavailable"];
    private static readonly HashSet<string> Kinds = ["image", "archive", "folder"];

    public static void ValidateId(int id)
    {
        if (id < 1) throw new ArgumentOutOfRangeException(nameof(id));
    }

    public static void ValidateToken(string value, string name)
    {
        if (!TagReviewProtocol.IsRevision(value))
            throw new ArgumentException($"Invalid {name}", name);
    }

    public static void ValidateRequestId(string id)
    {
        if (id is null || id.Length != 32 || id.Any(c => !(c is >= '0' and <= '9' or >= 'a' and <= 'f')))
            throw new ArgumentException("Invalid page text request ID", nameof(id));
    }

    public static PageTextProducer ParseProducer(JsonElement root) => new(
        TagReviewProtocol.Text(root, "adapter", 256),
        TagReviewProtocol.Text(root, "version", 256),
        TagReviewProtocol.Text(root, "model", 256),
        TagReviewProtocol.Text(root, "model_revision", 256),
        TagReviewProtocol.Text(root, "preprocessing", 256));

    public static PageIndexRefresh ParseRefresh(byte[] bytes, int expectedItemId)
    {
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var root = doc.RootElement;
            var itemId = root.GetProperty("item_id").GetInt32();
            var revision = TagReviewProtocol.Text(root, "source_revision", 64);
            var kind = TagReviewProtocol.Text(root, "source_kind", 16);
            var count = root.GetProperty("page_count").GetInt32();
            var reused = root.GetProperty("reused").GetBoolean();
            if (itemId != expectedItemId || !TagReviewProtocol.IsRevision(revision) || !Kinds.Contains(kind) || count is < 1 or > 10000)
                throw new InvalidDataException("ページ索引の更新結果が無効です。");
            return new(itemId, revision, kind, count, reused);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            throw new InvalidDataException("ページ索引の応答を読み取れません。", ex);
        }
    }

    public static PageIndexList ParseIndexList(byte[] bytes, int expectedItemId, int expectedOffset, int expectedLimit)
    {
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var root = doc.RootElement;
            var itemId = root.GetProperty("item_id").GetInt32();
            var state = TagReviewProtocol.Text(root, "source_state", 16);
            var count = root.GetProperty("page_count").GetInt32();
            var offset = root.GetProperty("offset").GetInt32();
            var limit = root.GetProperty("limit").GetInt32();
            var revEl = root.GetProperty("source_revision");
            var kindEl = root.GetProperty("source_kind");
            string? rev = revEl.ValueKind == JsonValueKind.Null ? null : revEl.GetString();
            string? kind = kindEl.ValueKind == JsonValueKind.Null ? null : kindEl.GetString();
            if (itemId != expectedItemId || !States.Contains(state) || offset != expectedOffset || limit != expectedLimit)
                throw new InvalidDataException("ページ一覧のヘッダが無効です。");
            var arr = root.GetProperty("pages");
            if (arr.ValueKind != JsonValueKind.Array || arr.GetArrayLength() > limit)
                throw new InvalidDataException("ページ一覧の件数が無効です。");
            if (state == "unindexed")
            {
                if (rev is not null || kind is not null || count != 0 || arr.GetArrayLength() != 0)
                    throw new InvalidDataException("未索引のページ一覧が無効です。");
                return new(itemId, null, null, state, 0, offset, limit, []);
            }
            if (rev is null || !TagReviewProtocol.IsRevision(rev) || kind is null || !Kinds.Contains(kind) || count is < 1 or > 10000)
                throw new InvalidDataException("ページ一覧の版情報が無効です。");
            var pages = new List<PageEntry>(arr.GetArrayLength());
            foreach (var p in arr.EnumerateArray())
            {
                var pageId = TagReviewProtocol.Text(p, "page_id", 64);
                var num = p.GetProperty("page").GetInt32();
                var mime = TagReviewProtocol.Text(p, "mime", 64);
                var size = p.GetProperty("size_bytes").GetInt64();
                if (!TagReviewProtocol.IsRevision(pageId) || num < 0 || num >= count || size < 0)
                    throw new InvalidDataException("ページ項目が無効です。");
                pages.Add(new(pageId, num, mime, size));
            }
            return new(itemId, rev, kind, state, count, offset, limit, pages);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            throw new InvalidDataException("ページ一覧を読み取れません。", ex);
        }
    }

    public static PageTextStatus ParseStatus(byte[] bytes)
    {
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var root = doc.RootElement;
            return new(root.GetProperty("available").GetBoolean(), root.GetProperty("reason").GetString() ?? "");
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException)
        {
            throw new InvalidDataException("文字抽出の状態を読み取れません。", ex);
        }
    }

    public static PageTextGenerationResult ParseGenerate(byte[] bytes, int expectedItemId, string expectedRevision)
    {
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var root = doc.RootElement;
            var itemId = root.GetProperty("item_id").GetInt32();
            var rev = TagReviewProtocol.Text(root, "source_revision", 64);
            var processed = root.GetProperty("processed").GetInt32();
            var reused = root.GetProperty("reused").GetInt32();
            if (itemId != expectedItemId || rev != expectedRevision || processed < 0 || reused < 0 || processed + reused is < 1 or > 16)
                throw new InvalidDataException("文字抽出の応答が要求と一致しません。");
            return new(itemId, rev, processed, reused);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            throw new InvalidDataException("文字抽出の結果を読み取れません。", ex);
        }
    }

    public static PageTextList ParseTextList(byte[] bytes, int expectedItemId, int expectedOffset, int expectedLimit)
    {
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var root = doc.RootElement;
            var itemId = root.GetProperty("item_id").GetInt32();
            var state = TagReviewProtocol.Text(root, "source_state", 16);
            var total = root.GetProperty("total").GetInt32();
            var offset = root.GetProperty("offset").GetInt32();
            var limit = root.GetProperty("limit").GetInt32();
            var revEl = root.GetProperty("source_revision");
            string? rev = revEl.ValueKind == JsonValueKind.Null ? null : revEl.GetString();
            if (itemId != expectedItemId || !States.Contains(state) || offset != expectedOffset || limit != expectedLimit || total < 0)
                throw new InvalidDataException("ページ本文一覧のヘッダが無効です。");
            var arr = root.GetProperty("pages");
            if (arr.ValueKind != JsonValueKind.Array || arr.GetArrayLength() > limit)
                throw new InvalidDataException("ページ本文一覧の件数が無効です。");
            if (state == "unindexed")
            {
                if (rev is not null || total != 0 || arr.GetArrayLength() != 0)
                    throw new InvalidDataException("未索引のページ本文一覧が無効です。");
                return new(itemId, null, state, 0, offset, limit, []);
            }
            if (rev is null || !TagReviewProtocol.IsRevision(rev))
                throw new InvalidDataException("ページ本文一覧の版が無効です。");
            var pages = new List<PageTextEntry>(arr.GetArrayLength());
            foreach (var p in arr.EnumerateArray())
            {
                var num = p.GetProperty("page").GetInt32();
                var pageId = TagReviewProtocol.Text(p, "page_id", 64);
                var text = p.GetProperty("text").GetString() ?? throw new InvalidDataException("ページ本文が無効です。");
                if (!TagReviewProtocol.IsRevision(pageId) || num is < 0 or > 9999 || text.Length > 20000)
                    throw new InvalidDataException("ページ本文の項目が無効です。");
                pages.Add(new(num, pageId, text, ParseProducer(p.GetProperty("producer"))));
            }
            return new(itemId, rev, state, total, offset, limit, pages);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            throw new InvalidDataException("ページ本文一覧を読み取れません。", ex);
        }
    }

    public static JsonObject SearchRequest(string query, string kind, string view, int page, IReadOnlyList<int>? rootIds = null, string? shelf = null, string? model = null)
    {
        if (string.IsNullOrWhiteSpace(query) || query.Length > 300)
            throw new ArgumentOutOfRangeException(nameof(query));
        return TagReviewProtocol.CandidateSearchRequest(query, kind, view, page, rootIds, shelf, model);
    }

    public static SearchResponse ParseSearch(byte[] bytes, int expectedPage)
    {
        try
        {
            if (expectedPage < 0) throw new ArgumentOutOfRangeException(nameof(expectedPage));
            var text = Encoding.UTF8.GetString(bytes);
            using var doc = JsonDocument.Parse(text);
            var root = doc.RootElement;
            if (root.GetProperty("search_mode").GetString() != "page-text" ||
                root.GetProperty("page").GetInt32() != expectedPage ||
                root.GetProperty("limit").GetInt32() != 20)
                throw new InvalidDataException("ページ本文検索の応答が要求と一致しません。");
            var parsed = Protocol.ParseSearch(text);
            var rawItems = root.GetProperty("items");
            if (parsed.Total < 0 || parsed.Items.Count > 20 || parsed.Items.Count > parsed.Total ||
                rawItems.GetArrayLength() != parsed.Items.Count ||
                parsed.Items.Select(x => x.Id).Distinct().Count() != parsed.Items.Count)
                throw new InvalidDataException("ページ本文検索の件数が無効です。");
            var index = 0;
            foreach (var element in rawItems.EnumerateArray())
            {
                var row = parsed.Items[index++];
                if (row.Id < 1 || !element.TryGetProperty("page_text_match", out var match) || match.ValueKind != JsonValueKind.Object)
                    throw new InvalidDataException("ページ本文検索の根拠情報がありません。");
                var revision = TagReviewProtocol.Text(match, "source_revision", 64);
                var state = TagReviewProtocol.Text(match, "source_state", 16);
                var matchingPages = match.GetProperty("matching_pages").GetInt32();
                var pagesArr = match.GetProperty("pages");
                if (!TagReviewProtocol.IsRevision(revision) || !States.Contains(state) || state == "unindexed" ||
                    matchingPages < 1 || pagesArr.ValueKind != JsonValueKind.Array || pagesArr.GetArrayLength() is < 1 or > 3)
                    throw new InvalidDataException("ページ本文検索の一致情報が無効です。");
                var evPages = new List<PageTextEvidencePage>(pagesArr.GetArrayLength());
                foreach (var p in pagesArr.EnumerateArray())
                {
                    var pageId = TagReviewProtocol.Text(p, "page_id", 64);
                    var pageNum = p.GetProperty("page").GetInt32();
                    var excerpt = p.GetProperty("excerpt").GetString() ?? "";
                    if (!TagReviewProtocol.IsRevision(pageId) || pageNum is < 0 or > 9999 || excerpt.Length > 240)
                        throw new InvalidDataException("ページ本文検索の抜粋情報が無効です。");
                    evPages.Add(new(pageId, pageNum, excerpt, ParseProducer(p.GetProperty("producer"))));
                }
                row.PageText = new PageTextMatch(revision, state, matchingPages, evPages);
            }
            return parsed;
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {
            throw new InvalidDataException("ページ本文の検索結果を読み取れません。", ex);
        }
    }
}

public sealed class PageEvidenceClient(HttpClient client)
{
    private async Task<byte[]> ReadAsync(string route, JsonObject? body, int limit, CancellationToken cancellation, int seconds = 15, bool image = false)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        var token = deadline.Token;
        try
        {
            using var request = new HttpRequestMessage(body is null ? HttpMethod.Get : HttpMethod.Post, route);
            if (body is not null) request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
            if (response.Content.Headers.ContentLength is long contentLength && (contentLength < 1 || contentLength > limit))
                throw new InvalidDataException("ページ根拠応答のデータ量が無効です。");
            await using var stream = await response.Content.ReadAsStreamAsync(token);
            using var output = new MemoryStream();
            var buffer = new byte[16384];
            int count;
            while ((count = await stream.ReadAsync(buffer, token)) != 0)
            {
                if (output.Length + count > limit) throw new InvalidDataException("ページ根拠応答が大きすぎます。");
                output.Write(buffer, 0, count);
            }
            if (output.Length == 0) throw new InvalidDataException("ページ根拠応答が空です。");
            if (response.Content.Headers.ContentLength is long expected && expected != output.Length)
                throw new InvalidDataException("ページ根拠応答が途中で切れました。");
            var bytes = output.ToArray();
            if (!response.IsSuccessStatusCode)
                throw new InvalidOperationException(ErrorText.FromResponse(Encoding.UTF8.GetString(bytes), (int)response.StatusCode));
            var mime = response.Content.Headers.ContentType?.MediaType;
            if (image ? mime is not ("image/png" or "image/jpeg" or "image/webp" or "image/gif" or "image/bmp") : mime != "application/json")
                throw new InvalidDataException("ページ根拠応答の形式が無効です。");
            return bytes;
        }
        catch (OperationCanceledException ex) when (!cancellation.IsCancellationRequested)
        {
            throw new TimeoutException("ページ根拠の処理が時間内に完了しませんでした。", ex);
        }
    }

    public async Task<PageBatchStatus> StartBatchAsync(IReadOnlyList<BookPageSelection> books,JsonObject scope,int pageLimit,string profile,CancellationToken cancellation=default)
    {
        var bytes=await ReadAsync("api/library/ai/pages/batch",PageBatchRequests.Create(books,scope,pageLimit,profile),PageEvidenceProtocol.MaxJsonBytes,cancellation);
        return PageBatchStatus.Parse(bytes,profile);
    }
    public async Task<PageBatchStatus> ResumeBatchAsync(string jobId,JsonObject scope,string profile,CancellationToken cancellation=default)
    {
        var bytes=await ReadAsync("api/library/ai/pages/batch/resume",PageBatchRequests.Resume(jobId,scope,profile),PageEvidenceProtocol.MaxJsonBytes,cancellation);
        return PageBatchStatus.Parse(bytes,profile);
    }
    public async Task<PageBatchStatus> BatchStatusAsync(string jobId,string profile,CancellationToken cancellation=default)=>
        PageBatchStatus.Parse(await ReadAsync("api/library/ai/status",null,PageEvidenceProtocol.MaxJsonBytes,cancellation),profile,jobId);

    public async Task<PageChunkPlan> PlanChunksAsync(int item,string revision,JsonObject scope,int maximum,string profile,CancellationToken cancellation=default)
    {
        var bytes=await ReadAsync("api/library/ai/pages/chunked/plan",PageChunkRequests.Plan(item,revision,scope,maximum,profile),PageEvidenceProtocol.MaxJsonBytes,cancellation);
        return PageChunkPlan.Parse(bytes,item,revision,scope,maximum,profile);
    }
    public async Task<PageChunkStatus> StartChunksAsync(PageChunkPlan plan,CancellationToken cancellation=default)
    {
        var bytes=await ReadAsync("api/library/ai/pages/chunked",PageChunkRequests.Start(plan),PageEvidenceProtocol.MaxJsonBytes,cancellation);
        var status=PageChunkStatus.Parse(bytes,plan.Profile,item:plan.ItemId,revision:plan.Revision,scope:plan.Scope);
        if(!status.PageIds.SequenceEqual(plan.PageIds)||status.ChunkSize!=16)throw new InvalidDataException("追加範囲が変わりました。");
        return status;
    }
    public async Task<PageChunkStatus> ResumeChunksAsync(PageChunkStatus saved,JsonObject scope,CancellationToken cancellation=default)
    {
        var bytes=await ReadAsync("api/library/ai/pages/chunked/resume",PageChunkRequests.Resume(saved,scope),PageEvidenceProtocol.MaxJsonBytes,cancellation);
        var status=PageChunkStatus.Parse(bytes,saved.Profile,item:saved.ItemId,revision:saved.Revision,scope:scope);
        if(!status.PageIds.SequenceEqual(saved.PageIds)||status.ChunkSize!=saved.ChunkSize)throw new InvalidDataException("前回の選択が変わりました。");
        return status;
    }
    public async Task<PageChunkStatus> ChunkStatusAsync(PageChunkStatus owned,CancellationToken cancellation=default)
    {
        var bytes=await ReadAsync("api/library/ai/status",null,PageEvidenceProtocol.MaxJsonBytes,cancellation);
        var status=PageChunkStatus.Parse(bytes,owned.Profile,owned.JobId,owned.ItemId,owned.Revision,owned.Scope);
        if(!status.PageIds.SequenceEqual(owned.PageIds)||status.ChunkSize!=owned.ChunkSize)throw new InvalidDataException("処理中のページ選択が変わりました。");
        return status;
    }

    public async Task<PageImageCoverage> ImageCoverageAsync(int itemId,string revision,JsonObject scope,string? expectedProfile=null,CancellationToken cancellation=default)
    {
        PageEvidenceProtocol.ValidateId(itemId);PageEvidenceProtocol.ValidateToken(revision,nameof(revision));
        var request=AIScopeRequests.Scoped(scope);request["item_id"]=itemId;request["revision"]=revision;
        var bytes=await ReadAsync("api/library/ai/pages/coverage",request,PageEvidenceProtocol.MaxJsonBytes,cancellation);
        return PageImageCoverage.Parse(bytes,itemId,revision,expectedProfile);
    }

    public async Task<PageIndexRefresh> RefreshIndexAsync(int itemId, CancellationToken cancellation = default)
    {
        PageEvidenceProtocol.ValidateId(itemId);
        var bytes = await ReadAsync("api/library/page-index", new() { ["item_id"] = itemId }, 32768, cancellation);
        return PageEvidenceProtocol.ParseRefresh(bytes, itemId);
    }

    public async Task<PageIndexList> ListPagesAsync(int itemId, int offset = 0, int limit = 60, string? revision = null, CancellationToken cancellation = default)
    {
        PageEvidenceProtocol.ValidateId(itemId);
        if (offset is < 0 or > 10000) throw new ArgumentOutOfRangeException(nameof(offset));
        if (limit is < 1 or > 100) throw new ArgumentOutOfRangeException(nameof(limit));
        if (offset > 0 && revision is null) throw new ArgumentException("Revision is required when offset > 0", nameof(revision));
        if (revision is not null) PageEvidenceProtocol.ValidateToken(revision, nameof(revision));
        var route = $"api/library/page-index/{itemId}?offset={offset}&limit={limit}" + (revision is null ? "" : $"&revision={revision}");
        var bytes = await ReadAsync(route, null, PageEvidenceProtocol.MaxJsonBytes, cancellation);
        return PageEvidenceProtocol.ParseIndexList(bytes, itemId, offset, limit);
    }

    public Task<byte[]> PageImageAsync(int itemId, string pageId, string revision, CancellationToken cancellation = default)
    {
        PageEvidenceProtocol.ValidateId(itemId);
        PageEvidenceProtocol.ValidateToken(pageId, nameof(pageId));
        PageEvidenceProtocol.ValidateToken(revision, nameof(revision));
        return ReadAsync($"api/library/page-index/{itemId}/pages/{pageId}?revision={revision}", null, PreviewPolicy.MaxSourceBytes, cancellation, image: true);
    }

    public async Task<PageTextStatus> TextStatusAsync(CancellationToken cancellation = default) =>
        PageEvidenceProtocol.ParseStatus(await ReadAsync("api/library/page-text/status", null, 32768, cancellation));

    public async Task<PageTextGenerationResult> GenerateTextAsync(int itemId, IReadOnlyList<string> pageIds, string revision, string requestId, CancellationToken cancellation = default)
    {
        PageEvidenceProtocol.ValidateId(itemId);
        PageEvidenceProtocol.ValidateToken(revision, nameof(revision));
        PageEvidenceProtocol.ValidateRequestId(requestId);
        if (pageIds is null || pageIds.Count is < 1 or > 16 || pageIds.Distinct().Count() != pageIds.Count)
            throw new ArgumentException("Select 1..16 distinct page IDs", nameof(pageIds));
        var arr = new JsonArray();
        foreach (var pid in pageIds)
        {
            PageEvidenceProtocol.ValidateToken(pid, nameof(pageIds));
            arr.Add((JsonNode?)JsonValue.Create(pid));
        }
        var body = new JsonObject { ["item_id"] = itemId, ["page_ids"] = arr, ["revision"] = revision, ["request_id"] = requestId };
        var bytes = await ReadAsync("api/library/page-text/generate", body, PageEvidenceProtocol.MaxJsonBytes, cancellation, 95);
        return PageEvidenceProtocol.ParseGenerate(bytes, itemId, revision);
    }

    public async Task<bool> CancelTextAsync(string requestId, CancellationToken cancellation = default)
    {
        PageEvidenceProtocol.ValidateRequestId(requestId);
        using var doc = JsonDocument.Parse(await ReadAsync("api/library/page-text/cancel", new() { ["request_id"] = requestId }, 32768, cancellation, 5));
        return doc.RootElement.GetProperty("cancel_requested").GetBoolean();
    }

    public async Task<PageTextList> ListTextAsync(int itemId, int offset = 0, int limit = 10, string? revision = null, CancellationToken cancellation = default)
    {
        PageEvidenceProtocol.ValidateId(itemId);
        if (offset is < 0 or > 10000) throw new ArgumentOutOfRangeException(nameof(offset));
        if (limit is < 1 or > 10) throw new ArgumentOutOfRangeException(nameof(limit));
        if (offset > 0 && revision is null) throw new ArgumentException("Revision is required when offset > 0", nameof(revision));
        if (revision is not null) PageEvidenceProtocol.ValidateToken(revision, nameof(revision));
        var route = $"api/library/page-text/{itemId}?offset={offset}&limit={limit}" + (revision is null ? "" : $"&revision={revision}");
        var bytes = await ReadAsync(route, null, PageEvidenceProtocol.MaxJsonBytes, cancellation);
        return PageEvidenceProtocol.ParseTextList(bytes, itemId, offset, limit);
    }

    public async Task<SearchResponse> SearchTextAsync(string query, string kind, string view, int page, IReadOnlyList<int>? rootIds = null, string? shelf = null, string? model = null, CancellationToken cancellation = default)
    {
        var body = PageEvidenceProtocol.SearchRequest(query, kind, view, page, rootIds, shelf, model);
        var bytes = await ReadAsync("api/library/page-text/search", body, PageEvidenceProtocol.MaxJsonBytes, cancellation, 15);
        return PageEvidenceProtocol.ParseSearch(bytes, page);
    }
}
