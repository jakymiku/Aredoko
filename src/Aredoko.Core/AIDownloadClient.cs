using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record AIDownloadCatalog(string Id,string Name,string Kind,string Revision,long Bytes,string License,Uri LicenseUri,IReadOnlyList<string> SourceHosts)
{
    internal static string Digest(string? value,int length=64)
    {
        if(value is null||value.Length!=length||value.Any(c=>c is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))throw new InvalidDataException("Invalid acquisition identity");
        return value;
    }
    internal static string Text(JsonElement root,string field,int limit)
    {
        var value=root.GetProperty(field).GetString();
        if(string.IsNullOrWhiteSpace(value)||value.Length>limit||value.Any(char.IsControl))throw new InvalidDataException("Invalid acquisition metadata");
        return value;
    }
    public static IReadOnlyList<AIDownloadCatalog> ParseList(string json)
    {
        using var document=JsonDocument.Parse(json);var root=document.RootElement;var result=new List<AIDownloadCatalog>();var seen=new HashSet<string>();
        foreach(var row in root.GetProperty("catalogs").EnumerateArray())
        {
            if(result.Count>=256)throw new InvalidDataException("Too many acquisition catalogs");
            var id=Digest(row.GetProperty("catalog_id").GetString());if(!seen.Add(id))throw new InvalidDataException("Duplicate acquisition catalog");
            var name=Text(row,"name",64);var kind=Text(row,"kind",16);if(kind is not ("runtime" or "model"))throw new InvalidDataException("Unknown acquisition kind");
            var revision=Text(row,"revision",64);Digest(revision,revision.Length==40?40:64);
            var size=row.GetProperty("bytes").GetInt64();if(size<0||size>64L*1024*1024*1024)throw new InvalidDataException("Invalid acquisition size");
            var link=Text(row,"license_url",8192);
            if(!Uri.TryCreate(link,UriKind.Absolute,out var uri)||uri.Scheme!="https"||string.IsNullOrEmpty(uri.Host)||!string.IsNullOrEmpty(uri.UserInfo)||!string.IsNullOrEmpty(uri.Fragment))throw new InvalidDataException("Invalid acquisition license link");
            var hosts=new List<string>();
            foreach(var value in row.GetProperty("source_hosts").EnumerateArray())
            {
                var host=value.GetString();
                if(host is null||host.Length is <1 or >253||host.Any(c=>c is not (>= 'a' and <= 'z') and not (>= '0' and <= '9') and not '.' and not '-')||hosts.Contains(host)||hosts.Count>=16)throw new InvalidDataException("Invalid acquisition source hosts");
                hosts.Add(host);
            }
            if(hosts.Count==0)throw new InvalidDataException("Missing acquisition source hosts");
            result.Add(new(id,name,kind,revision,size,Text(row,"license",128),uri,hosts.AsReadOnly()));
        }
        if(root.GetProperty("download_supported").GetBoolean()!=(result.Count>0))throw new InvalidDataException("Inconsistent acquisition availability");
        return result.AsReadOnly();
    }
}
public sealed record AIDownloadSelection(string CatalogId,string Kind,string Root)
{
    public static AIDownloadSelection? FromPublished(AIDownloadJob? job,IReadOnlyList<AIDownloadCatalog> catalogs)
    {
        if(job is not {State:"complete",Published:true,Root:not null,BytesTotal:not null}||
           job.BytesVerified!=job.BytesTotal||job.BytesReceived!=job.BytesTotal||
           !Path.IsPathFullyQualified(job.Root)||job.Root.Any(char.IsControl))return null;
        var source=catalogs.SingleOrDefault(item=>item.Id==job.CatalogId);
        return source is {Kind:"runtime" or "model"}&&source.Bytes==job.BytesTotal
            ?new(source.Id,source.Kind,job.Root):null;
    }
}
public sealed record AIDownloadJob(string? Id,string State,string? CatalogId,long BytesReceived,long BytesVerified,long? BytesTotal,bool Published,string? Root,string Message,bool? CancelAccepted)
{
    public bool Active=>State is "waiting" or "downloading" or "verifying" or "publishing" or "cancelling";
    public static AIDownloadJob Parse(string json)
    {
        using var document=JsonDocument.Parse(json);var root=document.RootElement;
        var state=root.GetProperty("state").GetString()??"";if(state is not ("idle" or "waiting" or "downloading" or "verifying" or "publishing" or "cancelling" or "complete" or "cancelled" or "failed"))throw new InvalidDataException("Unknown acquisition job state");
        var id=root.GetProperty("job_id").GetString();var catalog=root.GetProperty("catalog_id").GetString();
        if(state!="idle"){BackupClient.ValidateId(id);AIDownloadCatalog.Digest(catalog);}
        var received=root.GetProperty("bytes_received").GetInt64();var verified=root.GetProperty("bytes_verified").GetInt64();var totalValue=root.GetProperty("bytes_total");long? total=totalValue.ValueKind==JsonValueKind.Null?null:totalValue.GetInt64();
        var published=root.GetProperty("published").GetBoolean();
        if(received<0||verified<0||verified>received||total<0||total>64L*1024*1024*1024||received>total||state=="complete"&&!published||state=="cancelled"&&published)throw new InvalidDataException("Invalid acquisition progress/publication");
        string? path=null;
        if(root.TryGetProperty("result",out var result)&&result.ValueKind!=JsonValueKind.Null)
        {
            path=result.GetProperty("root").GetString();
            if(string.IsNullOrWhiteSpace(path)||path.Length>4096||!Path.IsPathFullyQualified(path)||path.Any(char.IsControl)||!published||result.GetProperty("catalog_sha256").GetString()!=catalog)throw new InvalidDataException("Invalid published acquisition location");
        }
        bool? accepted=root.TryGetProperty("cancel_accepted",out var acknowledgement)?acknowledgement.GetBoolean():null;
        return new(id,state,catalog,received,verified,total,published,path,root.GetProperty("message").GetString()??"",accepted);
    }
}
public sealed class AIDownloadClient(HttpClient client)
{
    private const string Prefix="api/library/ai/setup/download/";
    public async Task<IReadOnlyList<AIDownloadCatalog>> CatalogsAsync(CancellationToken token=default)
    {using var response=await client.GetAsync(Prefix+"catalog",token);return AIDownloadCatalog.ParseList(await ReadAsync(response,token));}
    public async Task<AIDownloadJob> JobAsync(CancellationToken token=default)
    {using var response=await client.GetAsync(Prefix+"job",token);return AIDownloadJob.Parse(await ReadAsync(response,token));}
    public Task<AIDownloadJob> StartAsync(string catalogId,long? bytesPerSecond=null,CancellationToken token=default)
    {
        AIDownloadCatalog.Digest(catalogId);
        if(bytesPerSecond is <=0 or >1099511627776)throw new ArgumentOutOfRangeException(nameof(bytesPerSecond));
        return PostAsync("start",new(){["consent"]=true,["catalog_id"]=catalogId,["bytes_per_second"]=bytesPerSecond},token);
    }
    public Task<AIDownloadJob> CancelAsync(string id,CancellationToken token=default)
    {BackupClient.ValidateId(id);return PostAsync("cancel",new(){["job_id"]=id},token);}
    private async Task<AIDownloadJob> PostAsync(string action,JsonObject body,CancellationToken token)
    {
        using var content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");using var response=await client.PostAsync(Prefix+action,content,token);
        return AIDownloadJob.Parse(await ReadAsync(response,token));
    }
    private static async Task<string> ReadAsync(HttpResponseMessage response,CancellationToken token)
    {
        var text=await response.Content.ReadAsStringAsync(token);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return text;
    }
}
