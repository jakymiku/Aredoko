using System.Net;
using System.Text.Json.Nodes;
using Aredoko.Core;
internal static class AIDownloadTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var id=new string('a',32);var digest=new string('b',64);var count=0;var rates=new List<long?>();
        var catalog=new JsonObject{["catalog_id"]=digest,["name"]="generated-runtime",["kind"]="runtime",["revision"]=new string('c',40),["bytes"]=128,["license"]="MIT",["license_url"]="https://example.org/LICENSE",["source_hosts"]=new JsonArray("example.org")};
        var catalogs=new JsonObject{["download_supported"]=true,["catalogs"]=new JsonArray(catalog)};
        var job=new JsonObject{["job_id"]=id,["catalog_id"]=digest,["state"]="downloading",["bytes_received"]=64,["bytes_verified"]=32,["bytes_total"]=128,["published"]=false,["result"]=null,["message"]="取得中"};
        using var handler=new Stub(async request=>
        {
            count++;var route=request.RequestUri!.AbsolutePath;check(route.StartsWith("/api/library/ai/setup/download/"),"acquisition uses owned setup API");
            if(request.Method==HttpMethod.Post)
            {
                var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
                if(route.EndsWith("start"))
                {
                    check(body.Count==3&&body["consent"]!.GetValue<bool>()&&body["catalog_id"]!.GetValue<string>()==digest&&!body.ContainsKey("url")&&!body.ContainsKey("root"),"download start supplies only consent/catalog/rate");
                    rates.Add(body["bytes_per_second"]?.GetValue<long>());
                }
                else check(body.Count==1&&body["job_id"]!.GetValue<string>()==id,"download cancellation targets exact job");
            }
            return new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(route.EndsWith("catalog")?catalogs.ToJsonString():job.ToJsonString())};
        });
        using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};var client=new AIDownloadClient(http);
        var available=await client.CatalogsAsync();check(available.Count==1&&available[0].Bytes==128&&available[0].License=="MIT"&&available[0].SourceHosts.SequenceEqual(new[]{"example.org"}),"catalog retains capacity and license before consent");
        var progress=await client.JobAsync();check(progress.Active&&!progress.Published&&progress.BytesReceived==64&&progress.BytesVerified==32,"received and verified bytes are distinct before publication");
        await client.StartAsync(digest);await client.StartAsync(digest,6000000);await client.CancelAsync(id);
        check(rates.Count==2&&rates[0] is null&&rates[1]==6000000,"download defaults unlimited; optional rate is explicit");
        var before=count;var rejected=false;
        try{await client.StartAsync(digest,0);}catch(ArgumentOutOfRangeException){rejected=true;}check(rejected&&count==before,"zero byte limit rejected before HTTP");
        rejected=false;try{await client.StartAsync("https://example.org/model");}catch(InvalidDataException){rejected=true;}check(rejected&&count==before,"URL cannot be sent as trusted catalog ID");
        rejected=false;try{await client.CancelAsync("stale");}catch(ArgumentException){rejected=true;}check(rejected&&count==before,"invalid download job ID never reaches HTTP");
        void Invalid(Action action,string name){var failed=false;try{action();}catch(InvalidDataException){failed=true;}check(failed,name);}
        job["bytes_verified"]=65;Invalid(()=>AIDownloadJob.Parse(job.ToJsonString()),"verification cannot exceed received bytes");job["bytes_verified"]=32;
        job["state"]="complete";Invalid(()=>AIDownloadJob.Parse(job.ToJsonString()),"complete acquisition requires publication");job["published"]=true;
        check(AIDownloadJob.Parse(job.ToJsonString()).Published,"post-publication diagnostic failure still preserves saved state without invented path");
        job["result"]=new JsonObject{["root"]=Path.GetTempPath(),["catalog_sha256"]=digest};check(AIDownloadJob.Parse(job.ToJsonString()).Root==Path.GetTempPath(),"published root remains explicit selection, not inference activation");
        job["result"]!["root"]="relative";Invalid(()=>AIDownloadJob.Parse(job.ToJsonString()),"published relative path rejected");job["result"]=null;
        job["state"]="cancelled";Invalid(()=>AIDownloadJob.Parse(job.ToJsonString()),"published acquisition cannot claim cancelled");
        job["state"]="downloading";job["published"]=false;job["cancel_accepted"]=false;check(AIDownloadJob.Parse(job.ToJsonString()).CancelAccepted==false,"cancel refusal preserved as explicit acknowledgement");
        job["state"]="extracting";check(AIDownloadJob.Parse(job.ToJsonString()).Active,"archive expansion stays cancellable and active");job["state"]="downloading";
        catalog["unpacked_bytes"]=4096;catalog["unpacked_files"]=12;
        var archiveCatalog=AIDownloadCatalog.ParseList(catalogs.ToJsonString())[0];
        check(archiveCatalog.Bytes==128&&archiveCatalog.UnpackedBytes==4096&&archiveCatalog.UnpackedFiles==12,"compressed and installed runtime capacity remain distinct");
        catalog.Remove("unpacked_files");Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"partial runtime expansion metadata rejected");catalog["unpacked_files"]=12;
        catalog["unpacked_bytes"]=true;Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"boolean runtime capacity rejected");catalog["unpacked_bytes"]=4096;
        catalog["kind"]="model";Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"model cannot claim runtime archive capacity");catalog["kind"]="runtime";
        catalog["unpacked_files"]=100001;Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"unbounded expanded file count rejected");
        catalog.Remove("unpacked_bytes");catalog.Remove("unpacked_files");
        catalog["license_url"]="file:///local/license";Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"catalog cannot expose local license link");catalog["license_url"]="https://example.org/LICENSE";
        catalogs["catalogs"]!.AsArray().Add(catalog.DeepClone());Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"duplicate trusted catalog rejected");catalogs["catalogs"]!.AsArray().RemoveAt(1);
        catalog["source_hosts"]=new JsonArray("example.org","example.org");Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"duplicate acquisition source host rejected");
        catalog["source_hosts"]=new JsonArray("https://example.org/private");Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"source display accepts hosts only, never secret URLs");
        catalog["source_hosts"]=new JsonArray("example.org");
        var runtimeCatalog=new AIDownloadCatalog(digest,"runtime","runtime",new string('c',40),128,"MIT",new Uri("https://example.org/LICENSE"),new[]{"example.org"});
        var modelCatalog=runtimeCatalog with{Id=new string('d',64),Kind="model",Name="model"};
        var target=new AIModelTarget("tagger","example/wd",new string('c',40),"wd");
        var boundModel=modelCatalog with{ModelTarget=target,DefinitionSha256=new string('e',64)};
        var completed=new AIDownloadJob(id,"complete",digest,128,128,128,true,Path.GetTempPath(),"保存済み",null);
        var selection=AIDownloadSelection.FromPublished(completed,new[]{modelCatalog,runtimeCatalog});
        check(selection is {Kind:"runtime"}&&selection.Root==Path.GetTempPath(),"selection uses the completed job catalog, not the current picker choice");
        check(AIDownloadSelection.FromPublished(completed with{CatalogId=modelCatalog.Id},new[]{runtimeCatalog,modelCatalog}) is null,"unbound model never guesses its role or offers use shortcut");
        check(AIDownloadSelection.FromPublished(completed with{CatalogId=boundModel.Id},new[]{runtimeCatalog,boundModel})?.ModelTarget==target,"model selection retains exact pinned role and physical identity");
        var identity=new JsonObject{["role"]="tagger",["model_id"]="example/wd",["revision"]=new string('c',40),["directory"]="wd"};
        catalog["model_target"]=identity;catalog["definition_sha256"]=new string('e',64);
        Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"runtime cannot claim model binding");
        catalog["kind"]="model";
        check(AIDownloadCatalog.ParseList(catalogs.ToJsonString())[0].ModelTarget==target,"source model binding survives manual Core parsing");
        identity["revision"]=new string('f',40);Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"model revision must match bound catalog");identity["revision"]=new string('c',40);
        foreach(var path in new[]{"../escape","CON","nested/LPT1.dat","/absolute","a\\b"})
        {identity["directory"]=path;Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"unsafe bound model directory rejected");}
        identity["directory"]="wd";catalog.Remove("model_target");Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"definition digest alone cannot imply a model role");catalog.Remove("definition_sha256");
        foreach(var invalid in new[]{completed with{State="failed"},completed with{Published=false},completed with{Root=null},completed with{Root="relative"},completed with{BytesVerified=127},completed with{BytesReceived=127},completed with{BytesTotal=null}})
            check(AIDownloadSelection.FromPublished(invalid,new[]{runtimeCatalog}) is null,"incomplete or unverified job offers no selection shortcut");
        check(AIDownloadSelection.FromPublished(completed,Array.Empty<AIDownloadCatalog>()) is null,"removed catalog cannot provide a selection shortcut");
        check(AIDownloadSelection.FromPublished(completed,new[]{runtimeCatalog with{Bytes=129}}) is null,"selection capacity must match the completed catalog");
        catalog["bytes"]=-1;Invalid(()=>AIDownloadCatalog.ParseList(catalogs.ToJsonString()),"negative catalog size rejected");catalog["bytes"]=128;
        catalogs["catalogs"]=new JsonArray();catalogs["download_supported"]=false;check(AIDownloadCatalog.ParseList(catalogs.ToJsonString()).Count==0,"empty production registry offers no invented download");
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)=>send(request);}
}
