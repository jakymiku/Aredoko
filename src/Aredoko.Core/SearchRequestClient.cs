using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace Aredoko.Core;

// One server-issued capability per query. Cancel a failed/timed-out HTTP query
// independently of its cancelled token; never call the index-job cancel route.
public sealed class SearchRequestClient(HttpClient client)
{
    private const string Route="api/library/ai/searches";
    public static bool IsRequestId(string? id)=>id is {Length:32}&&id.All(c=>c is >= '0' and <= '9' or >= 'a' and <= 'f');
    private async Task<byte[]> ReadAsync(string route,JsonObject body,int cap,CancellationToken token)
    {
        using var request=new HttpRequestMessage(HttpMethod.Post,route){Content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json")};
        using var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,token).ConfigureAwait(false);
        var limit=response.IsSuccessStatusCode?cap:32768;
        if(response.Content.Headers.ContentType?.MediaType!="application/json"||response.Content.Headers.ContentLength is long n&&(n<0||n>limit))
            throw new InvalidDataException("検索の応答形式またはサイズが無効です。");
        await using var input=await response.Content.ReadAsStreamAsync(token).ConfigureAwait(false);
        using var output=new MemoryStream();var buffer=new byte[16384];int read;
        while((read=await input.ReadAsync(buffer,token).ConfigureAwait(false))!=0)
        {if(output.Length+read>limit)throw new InvalidDataException("検索の応答が大きすぎます。");output.Write(buffer,0,read);}
        if(response.Content.Headers.ContentLength is long expected&&expected!=output.Length)throw new InvalidDataException("検索の応答が途中で切れました。");
        var bytes=output.ToArray();
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(Encoding.UTF8.GetString(bytes),(int)response.StatusCode));
        return bytes;
    }
    public async Task<bool> CancelAsync(string requestId,CancellationToken cancellation=default)
    {
        if(!IsRequestId(requestId))throw new ArgumentException("Invalid search request ID");
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellation);deadline.CancelAfter(TimeSpan.FromSeconds(3));
        using var doc=JsonDocument.Parse(await ReadAsync(Route+"/cancel",new(){["request_id"]=requestId},32768,deadline.Token).ConfigureAwait(false));
        var root=doc.RootElement;
        if(!root.TryGetProperty("request_id",out var id)||id.ValueKind!=JsonValueKind.String||id.GetString()!=requestId||
           !root.TryGetProperty("cancel_requested",out var accepted)||accepted.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException("検索中断の応答が要求と一致しません。");
        return accepted.GetBoolean();
    }
    public async Task<byte[]> RunAsync(string route,JsonObject body,CancellationToken cancellation=default,int seconds=40,int cap=2*1024*1024)
    {
        if(route is not ("api/library/ai/search" or "api/library/ai/similar" or "api/library/tag-suggestions/search"))throw new ArgumentException("Invalid search route");
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellation);deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        string? requestId=null;var completed=false;
        try
        {
            using(var prepared=JsonDocument.Parse(await ReadAsync(Route+"/prepare",new(),32768,deadline.Token).ConfigureAwait(false)))
            {
                var root=prepared.RootElement;
                if(!root.TryGetProperty("request_id",out var id)||id.ValueKind!=JsonValueKind.String||!IsRequestId(id.GetString()))throw new InvalidDataException("検索の受付IDが無効です。");
                requestId=id.GetString();
            }
            deadline.Token.ThrowIfCancellationRequested();
            var outgoing=body.DeepClone().AsObject();outgoing["request_id"]=requestId;
            var bytes=await ReadAsync(route,outgoing,cap,deadline.Token).ConfigureAwait(false);
            using var result=JsonDocument.Parse(bytes);
            if(!result.RootElement.TryGetProperty("request_id",out var echo)||echo.ValueKind!=JsonValueKind.String||echo.GetString()!=requestId)
                throw new InvalidDataException("検索の応答が別の要求のものです。");
            deadline.Token.ThrowIfCancellationRequested();completed=true;return bytes;
        }
        catch(OperationCanceledException ex) when(!cancellation.IsCancellationRequested)
        {throw new TimeoutException("検索が時間内に完了しませんでした。少し待って再検索してください。",ex);}
        finally
        {
            if(requestId is not null&&!completed)
            {
                try{await CancelAsync(requestId).ConfigureAwait(false);}
                catch(Exception ex) when(ex is HttpRequestException or OperationCanceledException or InvalidDataException or InvalidOperationException or JsonException)
                { /* Best effort: a disconnected request is also checked by the server. */ }
            }
        }
    }
}
