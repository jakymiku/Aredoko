using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Aredoko.Core;

public sealed record BackupSelection(bool Settings=true,bool History=true,bool ReaderProgress=true,bool Vectors=false)
{
    public JsonObject ToJson()=>new(){["settings"]=Settings,["history"]=History,["reader_progress"]=ReaderProgress,["vectors"]=Vectors};
    public static BackupSelection Parse(JsonElement value)
    {
        if(value.ValueKind!=JsonValueKind.Object || value.EnumerateObject().Count()!=4)throw new InvalidDataException("Invalid backup choices");
        return new(value.GetProperty("settings").GetBoolean(),value.GetProperty("history").GetBoolean(),value.GetProperty("reader_progress").GetBoolean(),value.GetProperty("vectors").GetBoolean());
    }
    public static BackupSelection Load(string path)
    {
        try{if(new FileInfo(path).Length>1024)return new();using var doc=JsonDocument.Parse(File.ReadAllBytes(path));return Parse(doc.RootElement);}
        catch(Exception error) when(error is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or KeyNotFoundException or InvalidDataException){return new();}
    }
    public void Save(string path)
    {
        var absolute=Path.GetFullPath(path);Directory.CreateDirectory(Path.GetDirectoryName(absolute)!);
        var temporary=absolute+"."+Guid.NewGuid().ToString("N")+".tmp";
        try{File.WriteAllText(temporary,ToJson().ToJsonString());File.Move(temporary,absolute,true);}
        finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
}
public sealed record BackupJob(string? Id,string State,bool Published,string Message,long BytesDone,long? BytesTotal,string? Output,BackupSelection? Selection)
{
    public bool Active=>State is "waiting" or "capturing" or "packing" or "publishing" or "cancelling";
    public static BackupJob Parse(string json)
    {
        using var doc=JsonDocument.Parse(json);var root=doc.RootElement;
        var id=root.GetProperty("job_id").GetString();var state=root.GetProperty("state").GetString()??"";
        if(state is not ("idle" or "waiting" or "capturing" or "packing" or "publishing" or "cancelling" or "complete" or "cancelled" or "failed"))throw new InvalidDataException("Unknown backup state");
        if(state!="idle")BackupClient.ValidateId(id);
        var done=root.GetProperty("bytes_done").GetInt64();var totalValue=root.GetProperty("bytes_total");long? total=totalValue.ValueKind==JsonValueKind.Null?null:totalValue.GetInt64();
        if(done<0 || total<0 || done>total)throw new InvalidDataException("Invalid backup progress");
        var published=root.GetProperty("published").GetBoolean();if(state=="complete"&&!published)throw new InvalidDataException("Backup completion without publication");
        var selected=root.GetProperty("selection");
        return new(id,state,published,root.GetProperty("message").GetString()??"",done,total,root.GetProperty("output").GetString(),selected.ValueKind==JsonValueKind.Null?null:BackupSelection.Parse(selected));
    }
}
// Shared data/JSON only. Windows picker and presentation belong to WinUI.
public sealed class BackupClient(HttpClient client)
{
    internal static void ValidateId(string? id)
    {if(id is null || !Regex.IsMatch(id,"\\A[0-9a-f]{32}\\z",RegexOptions.CultureInvariant))throw new ArgumentException("Invalid backup job ID");}
    public async Task<BackupJob> StatusAsync(CancellationToken cancellation=default)
    {using var response=await client.GetAsync("api/library/backup",cancellation);return BackupJob.Parse(await ReadAsync(response,cancellation));}
    public Task<BackupJob> StartAsync(string output,BackupSelection selection,ViewerInputSettings viewer,CancellationToken cancellation=default)
    {
        if(string.IsNullOrWhiteSpace(output)||!Path.IsPathFullyQualified(output)||output.Length>4096||output.Any(char.IsControl))throw new ArgumentException("バックアップの保存先を選んでください。");
        var body=new JsonObject{["consent"]=true,["output"]=output,["selection"]=selection.ToJson()};
        if(selection.Settings)body["viewer_settings"]=viewer.ToJson();
        return PostAsync("start",body,cancellation);
    }
    public Task<BackupJob> CancelAsync(string id,CancellationToken cancellation=default)
    {ValidateId(id);return PostAsync("cancel",new(){["job_id"]=id},cancellation);}
    private async Task<BackupJob> PostAsync(string operation,JsonObject body,CancellationToken cancellation)
    {
        using var content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");
        using var response=await client.PostAsync("api/library/backup/"+operation,content,cancellation);
        return BackupJob.Parse(await ReadAsync(response,cancellation));
    }
    private static async Task<string> ReadAsync(HttpResponseMessage response,CancellationToken cancellation)
    {
        var text=await response.Content.ReadAsStringAsync(cancellation);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return text;
    }
}
