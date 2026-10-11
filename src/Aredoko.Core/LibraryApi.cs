using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Aredoko.Core;
public sealed class LibraryApi : IDisposable
{
    private readonly HttpClient client = new() { BaseAddress = new Uri("http://127.0.0.1:8769/"), Timeout = TimeSpan.FromSeconds(40) };
    public async Task ConnectAsync() {
        using var doc = JsonDocument.Parse(await client.GetStringAsync("api/session"));
        if (doc.RootElement.GetProperty("mode").GetString() != "production") throw new InvalidOperationException("製品用APIではありません。start-winui.ps1から起動してください。");
        client.DefaultRequestHeaders.Remove("X-Aredoko-Token");
        client.DefaultRequestHeaders.Add("X-Aredoko-Token",doc.RootElement.GetProperty("token").GetString());
        client.DefaultRequestHeaders.Remove("Origin");
        client.DefaultRequestHeaders.Add("Origin", "http://127.0.0.1:8769");
    }
    public async Task<SearchResponse> SearchAsync(string q,string kind,string view,int page) => Protocol.ParseSearch(await client.GetStringAsync($"api/items?q={Uri.EscapeDataString(q)}&kind={kind}&view={view}&page={page}"));
    public async Task SaveAsync(int id,EditorState state) => await PostAsync("api/items/update",Protocol.CreateUpdate(id,state.ParsedTags,state.Shelf,state.Favorite,state.Reviewed));
    public async Task<JsonNode> GetAsync(string route) => JsonNode.Parse(await client.GetStringAsync(route))!;
    public Task<JsonNode> PostAsync(string route,JsonObject data) => PostAsync(route,data.ToJsonString());
    private async Task<JsonNode> PostAsync(string route,string data) {
        using var content=new StringContent(data,Encoding.UTF8,"application/json");
        using var response=await client.PostAsync(route,content);
        var text=await response.Content.ReadAsStringAsync();
        if(!response.IsSuccessStatusCode) throw new InvalidOperationException(JsonNode.Parse(text)?["error"]?.GetValue<string>() ?? response.StatusCode.ToString());
        return JsonNode.Parse(text)!;
    }
    public void Dispose()=>client.Dispose();
}
