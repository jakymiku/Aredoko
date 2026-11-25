using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record AIEnvironmentStatus(string RuntimeState,bool RuntimeFilesPresent,string ModelState,bool ModelFilesPresent,bool RestartRequired,string? RuntimeRoot,string? ModelsRoot,string? SharedModelsRoot=null,IReadOnlyDictionary<string,string>? ModelRoots=null,IReadOnlyList<AIModelLocation>? ModelLocations=null)
{
    public string? ModelLocation(string? role=null,AIModelTarget? target=null)
    {
        if(target is not null)
        {
            target.Validate();if(role!=target.Role)throw new ArgumentException("Model role mismatch");
            var exact=ModelLocations?.SingleOrDefault(item=>item.Target==target);if(exact is not null)return exact.Root;
        }
        return role is null?SharedModelsRoot??ModelsRoot:ModelRoots?.GetValueOrDefault(role)??SharedModelsRoot;
    }
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
        var roles=new Dictionary<string,string>();
        if(root.TryGetProperty("model_roots",out var modelRoots))
            foreach(var item in modelRoots.EnumerateObject())
            {
                if(item.Name is not ("embedding" or "tagger" or "intent")||roles.ContainsKey(item.Name))throw new InvalidDataException("Invalid model roles");
                var path=Location(modelRoots,item.Name);
                if(path is null||!Path.IsPathFullyQualified(path))throw new InvalidDataException("Invalid model role location");
                roles.Add(item.Name,path);
            }
        var locations=new List<AIModelLocation>();
        if(root.TryGetProperty("model_locations",out var placements))
            foreach(var row in placements.EnumerateArray())
            {
                var target=AIModelTarget.Parse(row,true);var path=Location(row,"root");
                if(locations.Count>=32||locations.Any(item=>item.Target==target)||path is null||!Path.IsPathFullyQualified(path))throw new InvalidDataException("Invalid model placement");
                locations.Add(new(target,path));
            }
        return new(runtime.GetProperty("state").GetString()??"",runtime.GetProperty("ready").GetBoolean(),model.GetProperty("state").GetString()??"",model.GetProperty("ready").GetBoolean(),root.GetProperty("restart_required").GetBoolean(),Location(root,"runtime_root"),Location(root,"models_root"),Location(root,"shared_models_root"),new System.Collections.ObjectModel.ReadOnlyDictionary<string,string>(roles),locations.AsReadOnly());
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
        return new(id,state,saved,AppText.TranslateBackend(root.GetProperty("message").GetString()),done,total,files,filesTotal);
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
    public Task<AIEnvironmentJob> SelectModelRoleAsync(string role,string? root,CancellationToken token=default)
    {
        if(role is not ("embedding" or "tagger" or "intent"))throw new ArgumentException("Unknown model role");
        ValidateRoot(root);return PostAsync("select",new(){["consent"]=true,["models_root"]=root,["model_role"]=role},token);
    }
    public Task<AIEnvironmentJob> SelectModelAsync(AIModelTarget target,string? root,CancellationToken token=default)
    {
        ArgumentNullException.ThrowIfNull(target);ValidateRoot(root);
        return PostAsync("select",new(){["consent"]=true,["models_root"]=root,["model_target"]=target.ToJson()},token);
    }
    private static void ValidateRoot(string? root)
    {if(root is not null&&(root.Length>4096||!Path.IsPathFullyQualified(root)||root.Any(char.IsControl)))throw new ArgumentException(AppText.L("AI環境のフォルダを選んでください。","Select an AI environment folder."));}
    private Task<AIEnvironmentJob> SelectAsync(string field,string? root,CancellationToken token)
    {
        ValidateRoot(root);
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
