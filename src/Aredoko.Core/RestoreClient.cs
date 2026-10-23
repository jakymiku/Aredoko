using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record RestoreJob(string? Id,string State,double Progress,string Message,bool SwitchSupported)
{
    public bool Active=>State is "queued" or "running";
    public static RestoreJob Parse(string json)
    {
        using var doc=JsonDocument.Parse(json);var root=doc.RootElement;
        var state=root.GetProperty("state").GetString()??"";
        if(state is not ("idle" or "queued" or "running" or "completed" or "cancelled" or "failed"))throw new InvalidDataException("Unknown restore state");
        var id=root.GetProperty("job_id").GetString();
        if(state!="idle")BackupClient.ValidateId(id);
        var progress=root.GetProperty("progress_ratio").GetDouble();
        if(!double.IsFinite(progress)||progress<0||progress>1||state=="completed"&&progress!=1)throw new InvalidDataException("Invalid restore progress");
        if(!root.GetProperty("staging_supported").GetBoolean())throw new InvalidDataException("Restore preparation unavailable");
        return new(id,state,progress,root.GetProperty("message").GetString()??"",root.GetProperty("switch_supported").GetBoolean());
    }
}

public sealed class RestoreClient(HttpClient client)
{
    public async Task<RestoreJob> StatusAsync(CancellationToken cancellation=default)
    {using var response=await client.GetAsync("api/library/restore",cancellation);return await ReadAsync(response,cancellation);}
    public Task<RestoreJob> StartAsync(string source,bool withoutVectors=true,CancellationToken cancellation=default)
    {
        if(string.IsNullOrWhiteSpace(source)||!Path.IsPathFullyQualified(source)||source.Length>4096||source.Any(char.IsControl))throw new ArgumentException("復元元のバックアップを選んでください。");
        return PostAsync("start",new(){["consent"]=true,["source"]=source,["without_vectors"]=withoutVectors},cancellation);
    }
    public Task<RestoreJob> CancelAsync(string id,CancellationToken cancellation=default)
    {BackupClient.ValidateId(id);return PostAsync("cancel",new(){["job_id"]=id},cancellation);}
    private async Task<RestoreJob> PostAsync(string operation,JsonObject body,CancellationToken cancellation)
    {
        using var content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");
        using var response=await client.PostAsync("api/library/restore/"+operation,content,cancellation);
        return await ReadAsync(response,cancellation);
    }
    private static async Task<RestoreJob> ReadAsync(HttpResponseMessage response,CancellationToken cancellation)
    {
        var text=await response.Content.ReadAsStringAsync(cancellation);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return RestoreJob.Parse(text);
    }
}
