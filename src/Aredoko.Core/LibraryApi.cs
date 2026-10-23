using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Aredoko.Core;
public sealed class LibraryApi : IDisposable
{
    private readonly HttpClient client;
    public LibraryApi() : this(new HttpClientHandler { AllowAutoRedirect = false }) { }
    private readonly HttpClient tagClient;
    public ShelfClient Shelves {get;}
    public ResultSessionClient Results {get;}
    public AnimationStreamClient Animations {get;}
    public TagReviewClient TagReviews {get;}
    public PageEvidenceClient PageEvidences {get;}
    public IndexContinuationClient Continuation {get;}
    public LibraryApi(HttpMessageHandler handler)
    {
        client=new(handler){BaseAddress=new Uri("http://127.0.0.1:8769/"),Timeout=TimeSpan.FromSeconds(40)};
        tagClient=new(handler,disposeHandler:false){BaseAddress=client.BaseAddress,Timeout=TimeSpan.FromSeconds(100)};
        Shelves=new(client);
        Results=new(client);
        Animations=new(client);
        TagReviews=new(tagClient);
        PageEvidences=new(tagClient);
        Continuation=new(tagClient);
    }
    public Task<ArchiveManifest> ReaderManifestAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ManifestAsync(id, cancellation);
    public Task<ReaderProgress?> ReaderProgressAsync(int id,CancellationToken cancellation)=>new ArchiveReaderClient(client).ProgressAsync(id,cancellation);
    public Task SaveReaderProgressAsync(ArchiveManifest manifest,int page,ReaderDisplayMode mode,CancellationToken cancellation)=>new ArchiveReaderClient(client).SaveProgressAsync(manifest,page,mode,cancellation);
    public Task<byte[]> ReaderPageAsync(ArchiveManifest manifest, int page, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).PageAsync(manifest, page, cancellation);
    public Task<byte[]> ReaderOriginalPageAsync(ArchiveManifest manifest,int page,CancellationToken cancellation)=>new ArchiveReaderClient(client).OriginalPageAsync(manifest,page,cancellation);
    public Task<byte[]> OriginalImageAsync(int id,CancellationToken cancellation)=>new ArchiveReaderClient(client).OriginalImageAsync(id,cancellation);
    public Task<ViewerSource> ReaderOriginalSourceAsync(ArchiveManifest manifest,int page,string? etag,CancellationToken cancellation)=>new ArchiveReaderClient(client).OriginalPageSourceAsync(manifest,page,etag,cancellation);
    public Task<ViewerSource> OriginalImageSourceAsync(int id,string? etag,CancellationToken cancellation)=>new ArchiveReaderClient(client).OriginalImageSourceAsync(id,etag,cancellation);
    public Task<byte[]> ImageAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ImageAsync(id, cancellation);
    public Task<ImageSourceInfo> ImageInfoAsync(int id,CancellationToken cancellation)=>new ArchiveReaderClient(client).ImageInfoAsync(id,cancellation);
    public Task<ImageAnimationManifest> ImageManifestAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ImageManifestAsync(id, cancellation);
    public Task<byte[]> ImageFrameAsync(ImageAnimationManifest manifest, int frame, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ImageFrameAsync(manifest, frame, cancellation);
    public Task<VideoRangeSource> OpenVideoRangeAsync(int id,CancellationToken cancellation)=>new ArchiveReaderClient(client).OpenVideoRangeAsync(id,cancellation);
    public Task<VideoRangeSource> OpenAudioRangeAsync(int id,CancellationToken cancellation)=>new ArchiveReaderClient(client).OpenAudioRangeAsync(id,cancellation);
    public Task<byte[]> VideoFrameAsync(VideoManifest manifest,int atMs,CancellationToken cancellation)=>new ArchiveReaderClient(client).VideoFrameAsync(manifest,atMs,cancellation);
    public Task<(byte[] Data, string Mime)> VideoAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).VideoAsync(id, cancellation);
    public async Task ConnectAsync() {
        using var doc = JsonDocument.Parse(await client.GetStringAsync("api/session"));
        var startupInstance=Environment.GetEnvironmentVariable("AREDOKO_STARTUP_INSTANCE");
        if(startupInstance is not null&&(!doc.RootElement.TryGetProperty("instance_id",out var instance)||instance.GetString()!=startupInstance))
            throw new InvalidOperationException("今回起動したバックエンドを確認できません。");
        if (doc.RootElement.GetProperty("mode").GetString() != "production") throw new InvalidOperationException("製品用APIではありません。start-winui.ps1から起動してください。");
        client.DefaultRequestHeaders.Remove("X-Aredoko-Token");
        client.DefaultRequestHeaders.Add("X-Aredoko-Token",doc.RootElement.GetProperty("token").GetString());
        client.DefaultRequestHeaders.Remove("Origin");
        client.DefaultRequestHeaders.Add("Origin", "http://127.0.0.1:8769");
        tagClient.DefaultRequestHeaders.Remove("X-Aredoko-Token");
        tagClient.DefaultRequestHeaders.Add("X-Aredoko-Token",doc.RootElement.GetProperty("token").GetString());
        tagClient.DefaultRequestHeaders.Remove("Origin");
        tagClient.DefaultRequestHeaders.Add("Origin","http://127.0.0.1:8769");
    }
    public Task<SearchResponse> SearchAsync(string q,string kind,string view,int page,bool semantic=false,string source="all",JsonObject? scope=null,int? rootId=null,bool literalOnly=false,double? groupThreshold=null,string resultGroup="all",CancellationToken cancellation=default) =>
        SearchMultiAsync(q,kind,view,page,semantic,source,scope,rootId is int id ? new[]{id} : null,literalOnly,groupThreshold,resultGroup,cancellation);
    public async Task<SearchResponse> SearchMultiAsync(string q,string kind,string view,int page,bool semantic,string source,JsonObject? scope,IReadOnlyList<int>? rootIds,bool literalOnly=false,double? groupThreshold=null,string resultGroup="all",CancellationToken cancellation=default)
    {
        if(view=="history")
        {
            if(semantic||source!="all")throw new ArgumentException("閲覧履歴は名前・タグ検索を使ってください。");
            return Protocol.ParseSearch(await client.GetStringAsync(FolderSearch.LiteralRouteMulti(q,kind,view,page,rootIds)));
        }
        if(source is "pending-proposals" or "pending-proposals-semantic")
        {
            if(source=="pending-proposals-semantic"&&string.IsNullOrWhiteSpace(q))return new SearchResponse{Total=0,Items=[]};
            return await TagReviews.SearchCandidatesAsync(q,kind,view,page,rootIds,cancellation:cancellation,semantic:source=="pending-proposals-semantic");
        }
        if(source=="page-text")
        {
            if(string.IsNullOrWhiteSpace(q))return new SearchResponse{Total=0,Items=[]};
            return await PageEvidences.SearchTextAsync(q,kind,view,page,rootIds);
        }
        if(semantic && !string.IsNullOrWhiteSpace(q))
        {
            var result=await new SearchRequestClient(client).RunAsync("api/library/ai/search",AIScopeRequests.Search(q,kind,view,page,source,FolderSearch.RestrictAIMulti(scope,rootIds),literalOnly,groupThreshold,resultGroup),cancellation);
            return Protocol.ParseSearch(Encoding.UTF8.GetString(result));
        }
        return Protocol.ParseSearch(await GetTextAsync(FolderSearch.LiteralRouteMulti(q,kind,view,page,rootIds)));
    }
    public Task<JsonNode> SetRootFavoriteAsync(int rootId,bool favorite)
    {
        if(rootId<1)throw new ArgumentOutOfRangeException(nameof(rootId));
        return PostAsync("api/library/roots/favorite",new JsonObject{["root_id"]=rootId,["favorite"]=favorite});
    }
    public async Task SaveAsync(int id,EditorState state) => await PostAsync("api/items/update",Protocol.CreateUpdate(id,state.ParsedTags,state.Shelf,state.Favorite,state.Reviewed,state.ShelfIds));
    public Task<SearchResponse> SimilarAsync(int itemId,string kind,string view,int page,JsonObject scope,int? rootId,CancellationToken cancellation) =>
        SimilarMultiAsync(itemId,kind,view,page,scope,rootId is int id ? new[]{id} : null,cancellation);
    public async Task<SearchResponse> SimilarMultiAsync(int itemId,string kind,string view,int page,JsonObject scope,IReadOnlyList<int>? rootIds,CancellationToken cancellation)
    {
        var bytes=await new SearchRequestClient(client).RunAsync("api/library/ai/similar",
            SimilaritySearch.RequestMulti(itemId,kind,view,page,scope,rootIds),cancellation,10,SimilaritySearch.MaxResponseBytes);
        return SimilaritySearch.Parse(Encoding.UTF8.GetString(bytes),itemId,page);
    }
    public Task<string> ExportRelatedTermsAsync() => GetTextAsync("api/library/terms/export");
    public Task<JsonNode> ImportRelatedTermsAsync(string document) => PostAsync("api/library/terms/import", document);
    public async Task<JsonNode> GetAsync(string route) => JsonNode.Parse(await GetTextAsync(route))!;
    private async Task<string> GetTextAsync(string route) {
        using var response=await client.GetAsync(route);
        var text=await response.Content.ReadAsStringAsync();
        if(!response.IsSuccessStatusCode) throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return text;
    }
    public Task<JsonNode> PostAsync(string route,JsonObject data) => PostAsync(route,data.ToJsonString());
    private async Task<JsonNode> PostAsync(string route,string data,CancellationToken cancellation=default) {
        using var content=new StringContent(data,Encoding.UTF8,"application/json");
        using var response=await client.PostAsync(route,content,cancellation);
        var text=await response.Content.ReadAsStringAsync(cancellation);
        if(!response.IsSuccessStatusCode) throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return JsonNode.Parse(text)!;
    }
    public async Task<byte[]?> PreviewAsync(int id, CancellationToken cancellation)
        => await ReadPreviewAsync($"api/library/preview/{id}", cancellation);

    public Task<byte[]?> ThumbnailAsync(int id, int edge, CancellationToken cancellation, bool nearby = false)
    {
        if (id < 1) throw new ArgumentOutOfRangeException(nameof(id));
        if (edge is not (128 or 256 or 512 or 1024)) throw new ArgumentOutOfRangeException(nameof(edge));
        var priority = nearby ? "&priority=nearby" : "";
        return ReadPreviewAsync($"api/library/thumbnail/{id}?edge={edge}{priority}", cancellation, requirePng: true);
    }

    private async Task<byte[]?> ReadPreviewAsync(string route, CancellationToken cancellation, bool requirePng = false)
    {
        using var response = await client.GetAsync(route, HttpCompletionOption.ResponseHeadersRead, cancellation);
        if ((int)response.StatusCode >= 500) response.EnsureSuccessStatusCode();
        if (!response.IsSuccessStatusCode) return null;
        if (requirePng && response.Content.Headers.ContentType?.MediaType != "image/png") return null;
        if (response.Content.Headers.ContentLength is not long size || size < 1 || size > PreviewPolicy.MaxSourceBytes)
            return null;
        await using var source = await response.Content.ReadAsStreamAsync(cancellation);
        using var output = new MemoryStream((int)size);
        var buffer = new byte[16 * 1024];
        int read;
        while ((read = await source.ReadAsync(buffer, cancellation)) != 0)
        {
            if (output.Length + read > PreviewPolicy.MaxSourceBytes) return null;
            output.Write(buffer, 0, read);
        }
        if (output.Length != size) return null;
        var data = output.ToArray();
        if (requirePng && (data.Length < 8 || !data.AsSpan(0, 8).SequenceEqual(new byte[] {137,80,78,71,13,10,26,10}))) return null;
        return data;
    }
    public void Dispose(){tagClient.Dispose();client.Dispose();}
}

