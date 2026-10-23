using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record AIEnvironmentStatus(string RuntimeState,bool RuntimeFilesPresent,string ModelState,bool ModelFilesPresent,bool RestartRequired,string? RuntimeRoot,string? ModelsRoot)
{
    public static AIEnvironmentStatus Parse(string json)
    {
        using var doc=JsonDocument.Parse(json);var root=doc.RootElement;
        var runtime=root.GetProperty("runtime");var model=root.GetProperty("model");
        static string? Location(JsonElement root,string key)
        {
            if(!root.TryGetProperty(key,out var value)||value.ValueKind==JsonValueKind.Null)return null;
            var path=value.GetString();
            if(path is not null&&(path.Length>4096||path.Any(char.IsControl)))throw new InvalidDataException("Invalid AI location");
            return path;
        }
        return new(runtime.GetProperty("state").GetString()??"",runtime.GetProperty("ready").GetBoolean(),model.GetProperty("state").GetString()??"",model.GetProperty("ready").GetBoolean(),root.GetProperty("restart_required").GetBoolean(),Location(root,"runtime_root"),Location(root,"models_root"));
    }
}
public sealed record AIEnvironmentJob(string? Id,string State,bool Saved,string Message,long BytesDone,long? BytesTotal,int FilesDone,int? FilesTotal)
{
    public bool Active=>State is "validating" or "saving" or "cancelling";
    public static AIEnvironmentJob Parse(string json)
    {
        using var doc=JsonDocument.Parse(json);var root=doc.RootElement;
        var state=root.GetProperty("state").GetString()??"";var id=root.GetProperty("job_id").GetString();
        if(state is not ("idle" or "validating" or "saving" or "cancelling" or "complete" or "cancelled" or "failed"))throw new InvalidDataException("Unknown AI environment job state");
        if(state!="idle")BackupClient.ValidateId(id);
        var done=root.GetProperty("bytes_done").GetInt64();var totalValue=root.GetProperty("bytes_total");long? total=totalValue.ValueKind==JsonValueKind.Null?null:totalValue.GetInt64();
        var files=root.GetProperty("files_done").GetInt32();var filesValue=root.GetProperty("files_total");int? filesTotal=filesValue.ValueKind==JsonValueKind.Null?null:filesValue.GetInt32();
        var saved=root.GetProperty("saved").GetBoolean();
        if(done<0||total<0||done>total||files<0||filesTotal<0||files>filesTotal||state=="complete"&&!saved)throw new InvalidDataException("Invalid AI environment progress/publication");
        return new(id,state,saved,root.GetProperty("message").GetString()??"",done,total,files,filesTotal);
    }
}
public sealed class AIEnvironmentClient(HttpClient client)
{
    public async Task<AIEnvironmentStatus> StatusAsync(CancellationToken token=default)
    {using var response=await client.GetAsync("api/library/ai/setup",token);return AIEnvironmentStatus.Parse(await ReadAsync(response,token));}
    public async Task<AIEnvironmentJob> JobAsync(CancellationToken token=default)
    {using var response=await client.GetAsync("api/library/ai/setup/job",token);return AIEnvironmentJob.Parse(await ReadAsync(response,token));}
    public Task<AIEnvironmentJob> SelectRuntimeAsync(string? root,CancellationToken token=default)=>SelectAsync("runtime_root",root,token);
    public Task<AIEnvironmentJob> SelectModelsAsync(string? root,CancellationToken token=default)=>SelectAsync("models_root",root,token);
    private Task<AIEnvironmentJob> SelectAsync(string field,string? root,CancellationToken token)
    {
        if(root is not null&&(root.Length>4096||!Path.IsPathFullyQualified(root)||root.Any(char.IsControl)))throw new ArgumentException("AI環境のフォルダを選んでください。");
        return PostAsync("select",new(){["consent"]=true,[field]=root},token);
    }
    public Task<AIEnvironmentJob> CancelAsync(string id,CancellationToken token=default)
    {BackupClient.ValidateId(id);return PostAsync("cancel",new(){["job_id"]=id},token);}
    private async Task<AIEnvironmentJob> PostAsync(string operation,JsonObject body,CancellationToken token)
    {
        using var content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");
        using var response=await client.PostAsync("api/library/ai/setup/"+operation,content,token);
        return AIEnvironmentJob.Parse(await ReadAsync(response,token));
    }
    private static async Task<string> ReadAsync(HttpResponseMessage response,CancellationToken token)
    {
        var text=await response.Content.ReadAsStringAsync(token);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return text;
    }
}
