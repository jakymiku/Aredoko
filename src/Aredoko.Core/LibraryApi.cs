using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Aredoko.Core;
public sealed class LibraryApi : IDisposable
{
    private readonly HttpClient client = new() { BaseAddress = new Uri("http://127.0.0.1:8769/"), Timeout = TimeSpan.FromSeconds(40) };
    public Task<ArchiveManifest> ReaderManifestAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ManifestAsync(id, cancellation);
    public Task<byte[]> ReaderPageAsync(ArchiveManifest manifest, int page, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).PageAsync(manifest, page, cancellation);
    public Task<byte[]> ImageAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).ImageAsync(id, cancellation);
    public Task<(byte[] Data, string Mime)> VideoAsync(int id, CancellationToken cancellation) =>
        new ArchiveReaderClient(client).VideoAsync(id, cancellation);
    public async Task ConnectAsync() {
        using var doc = JsonDocument.Parse(await client.GetStringAsync("api/session"));
        if (doc.RootElement.GetProperty("mode").GetString() != "production") throw new InvalidOperationException("製品用APIではありません。start-winui.ps1から起動してください。");
        client.DefaultRequestHeaders.Remove("X-Aredoko-Token");
        client.DefaultRequestHeaders.Add("X-Aredoko-Token",doc.RootElement.GetProperty("token").GetString());
        client.DefaultRequestHeaders.Remove("Origin");
        client.DefaultRequestHeaders.Add("Origin", "http://127.0.0.1:8769");
    }
    public async Task<SearchResponse> SearchAsync(string q,string kind,string view,int page,bool semantic=false,string source="all",JsonObject? scope=null,int? rootId=null,bool literalOnly=false,double? groupThreshold=null,string resultGroup="all")
    {
        if(semantic && !string.IsNullOrWhiteSpace(q))
        {
            var result=await PostAsync("api/library/ai/search",AIScopeRequests.Search(q,kind,view,page,source,FolderSearch.RestrictAI(scope,rootId),literalOnly,groupThreshold,resultGroup));
            return Protocol.ParseSearch(result.ToJsonString());
        }
        return Protocol.ParseSearch(await GetTextAsync(FolderSearch.LiteralRoute(q,kind,view,page,rootId)));
    }
    public async Task SaveAsync(int id,EditorState state) => await PostAsync("api/items/update",Protocol.CreateUpdate(id,state.ParsedTags,state.Shelf,state.Favorite,state.Reviewed));
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
    private async Task<JsonNode> PostAsync(string route,string data) {
        using var content=new StringContent(data,Encoding.UTF8,"application/json");
        using var response=await client.PostAsync(route,content);
        var text=await response.Content.ReadAsStringAsync();
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
    public void Dispose()=>client.Dispose();
}

