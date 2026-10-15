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
    public TagReviewClient TagReviews {get;}
    public LibraryApi(HttpMessageHandler handler)
    {
        client=new(handler){BaseAddress=new Uri("http://127.0.0.1:8769/"),Timeout=TimeSpan.FromSeconds(40)};
        tagClient=new(handler,disposeHandler:false){BaseAddress=client.BaseAddress,Timeout=TimeSpan.FromSeconds(100)};
        TagReviews=new(tagClient);
    }
    public Task<ArchiveManifest> ReaderManifestAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ManifestAsync(id, cancellation);
    public Task<ReaderProgress?> ReaderProgressAsync(int id,CancellationToken cancellation)=>new ArchiveReaderClient(client).ProgressAsync(id,cancellation);
    public Task SaveReaderProgressAsync(ArchiveManifest manifest,int page,ReaderDisplayMode mode,CancellationToken cancellation)=>new ArchiveReaderClient(client).SaveProgressAsync(manifest,page,mode,cancellation);
    public Task<byte[]> ReaderPageAsync(ArchiveManifest manifest, int page, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).PageAsync(manifest, page, cancellation);
    public Task<byte[]> ImageAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ImageAsync(id, cancellation);
    public Task<VideoRangeSource> OpenVideoRangeAsync(int id,CancellationToken cancellation)=>new ArchiveReaderClient(client).OpenVideoRangeAsync(id,cancellation);
    public Task<byte[]> VideoFrameAsync(VideoManifest manifest,int atMs,CancellationToken cancellation)=>new ArchiveReaderClient(client).VideoFrameAsync(manifest,atMs,cancellation);
    public Task<(byte[] Data, string Mime)> VideoAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).VideoAsync(id, cancellation);
    public async Task ConnectAsync() {
        using var doc = JsonDocument.Parse(await client.GetStringAsync("api/session"));
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
    public Task<SearchResponse> SearchAsync(string q,string kind,string view,int page,bool semantic=false,string source="all",JsonObject? scope=null,int? rootId=null,bool literalOnly=false,double? groupThreshold=null,string resultGroup="all") =>
        SearchMultiAsync(q,kind,view,page,semantic,source,scope,rootId is int id ? new[]{id} : null,literalOnly,groupThreshold,resultGroup);
    public async Task<SearchResponse> SearchMultiAsync(string q,string kind,string view,int page,bool semantic,string source,JsonObject? scope,IReadOnlyList<int>? rootIds,bool literalOnly=false,double? groupThreshold=null,string resultGroup="all")
    {
        if(source=="pending-proposals")
            return await TagReviews.SearchCandidatesAsync(q,kind,view,page,rootIds);
        if(semantic && !string.IsNullOrWhiteSpace(q))
        {
            var result=await PostAsync("api/library/ai/search",AIScopeRequests.Search(q,kind,view,page,source,FolderSearch.RestrictAIMulti(scope,rootIds),literalOnly,groupThreshold,resultGroup));
            return Protocol.ParseSearch(result.ToJsonString());
        }
        return Protocol.ParseSearch(await GetTextAsync(FolderSearch.LiteralRouteMulti(q,kind,view,page,rootIds)));
    }
    public async Task SaveAsync(int id,EditorState state) => await PostAsync("api/items/update",Protocol.CreateUpdate(id,state.ParsedTags,state.Shelf,state.Favorite,state.Reviewed));
    public Task<SearchResponse> SimilarAsync(int itemId,string kind,string view,int page,JsonObject scope,int? rootId,CancellationToken cancellation) =>
        SimilarMultiAsync(itemId,kind,view,page,scope,rootId is int id ? new[]{id} : null,cancellation);
    public async Task<SearchResponse> SimilarMultiAsync(int itemId,string kind,string view,int page,JsonObject scope,IReadOnlyList<int>? rootIds,CancellationToken cancellation)
    {
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(10));
        try
        {
            using var request=new HttpRequestMessage(HttpMethod.Post,"api/library/ai/similar") {
                Content=new StringContent(SimilaritySearch.RequestMulti(itemId,kind,view,page,scope,rootIds).ToJsonString(),Encoding.UTF8,"application/json")
            };
            using var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,deadline.Token);
            if(response.Content.Headers.ContentType?.MediaType!="application/json"||response.Content.Headers.ContentLength is long size&&size>SimilaritySearch.MaxResponseBytes)
                throw new InvalidDataException("類似検索の応答形式またはサイズが無効です。");
            await using var input=await response.Content.ReadAsStreamAsync(deadline.Token);
            using var output=new MemoryStream();var buffer=new byte[16384];int read;
            while((read=await input.ReadAsync(buffer,deadline.Token))!=0)
            {
                if(output.Length+read>SimilaritySearch.MaxResponseBytes)throw new InvalidDataException("類似検索の応答が大きすぎます。");
                output.Write(buffer,0,read);
            }
            if(response.Content.Headers.ContentLength is long expected&&expected!=output.Length)throw new InvalidDataException("類似検索の応答が途中で切れました。");
            var text=Encoding.UTF8.GetString(output.ToArray());
            if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
            return SimilaritySearch.Parse(text,itemId,page);
        }
        catch(OperationCanceledException ex) when(!cancellation.IsCancellationRequested)
        {throw new TimeoutException("類似検索が時間内に完了しませんでした。少し待ってやり直してください。",ex);}
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
    {
        using var response = await client.GetAsync($"api/library/preview/{id}", HttpCompletionOption.ResponseHeadersRead, cancellation);
        if ((int)response.StatusCode >= 500) response.EnsureSuccessStatusCode();
        if (!response.IsSuccessStatusCode) return null;
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
        return output.ToArray();
    }
    public void Dispose(){tagClient.Dispose();client.Dispose();}
}

