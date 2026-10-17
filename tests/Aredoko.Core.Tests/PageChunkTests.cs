using Aredoko.Core;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;

internal static class PageChunkTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var rev=new string('a',64);var job=new string('b',32);var profile="page-profile";
        var scope=new JsonObject{{"root_ids",new JsonArray(3,2)}};
        JsonArray Ids()=>new(Enumerable.Range(1,35).Select(n=>(JsonNode?)JsonValue.Create(n.ToString("x64"))).ToArray());
        JsonObject Plan()=>new(){{"item_id",7},{"source_revision",rev},{"source_state","current"},{"profile",profile},{"model","fixture"},
            {"scope",new JsonObject{{"root_ids",new JsonArray(2,3)},{"kind",""},{"shelf",null}}},{"supported",true},{"available",true},
            {"page_count",145},{"indexed_pages",110},{"remaining_pages",35},{"chunk_size",16},{"max_pages",64},{"total_gap_pages",35},{"chunks_total",3},
            {"page_ids",Ids()},{"chunks",JsonNode.Parse("[{\"start\":16,\"count\":16},{\"start\":32,\"count\":16},{\"start\":48,\"count\":3}]")}};
        byte[] Bytes(JsonObject value)=>Encoding.UTF8.GetBytes(value.ToJsonString());
        PageChunkPlan ParsePlan(JsonObject value)=>PageChunkPlan.Parse(Bytes(value),7,rev,scope,64,profile);
        var plan=ParsePlan(Plan());
        check(plan.CanStart&&plan.PageIds.Count==35&&plan.ChunksTotal==3&&plan.RangeSummary=="17–32、33–48、49–51ページ","chunk plan keeps fixed IDs and one-based ranges");
        var tooMany=false;try{PageChunkRequests.Start(plan with{Maximum=1});}catch(ArgumentException){tooMany=true;}
        check(tooMany,"chunk start cannot exceed the reviewed maximum");
        var request=PageChunkRequests.Start(plan);
        check(!request.ContainsKey("max_pages")&&!request.ContainsKey("chunk_size")&&request["page_ids"]!.AsArray().Count==35,"chunk start sends fixed selection, no mutable limit or chunk override");
        var planRequest=PageChunkRequests.Plan(7,rev,scope,128,profile);
        scope["root_ids"]![0]=4;
        check(planRequest["scope"]!["root_ids"]![0]!.GetValue<long>()==2,"chunk request normalizes and owns scope nodes");scope["root_ids"]![0]=3;
        foreach(var cap in new[]{0,129}){var rejected=false;try{PageChunkRequests.Plan(7,rev,scope,cap,profile);}catch(ArgumentException){rejected=true;}check(rejected,"chunk cap rejected "+cap);}
        foreach(var(name,change) in new (string,Action<JsonObject>)[]{
            ("wrong item",o=>o["item_id"]=8),("revision",o=>o["source_revision"]=new string('c',64)),("profile",o=>o["profile"]="other"),
            ("scope",o=>o["scope"]!["root_ids"]=new JsonArray()),("limit",o=>o["max_pages"]=128),("chunk override",o=>o["chunk_size"]=8),
            ("count",o=>o["total_gap_pages"]=34),("duplicate IDs",o=>o["page_ids"]![1]=o["page_ids"]![0]!.DeepClone()),
            ("invalid ID",o=>o["page_ids"]![0]="bad"),("range overflow",o=>o["chunks"]![0]!["count"]=int.MaxValue),
            ("overlap",o=>o["chunks"]![1]!["start"]=30),("stale ready",o=>o["source_state"]="stale"),("missing scope",o=>o.Remove("scope")),
            ("null root",o=>o["scope"]!["root_ids"]![0]=null),("null kind",o=>o["scope"]!["kind"]=null),("wrong source state",o=>o["source_state"]="ready")})
        {var data=Plan();change(data);var rejected=false;try{ParsePlan(data);}catch(InvalidDataException){rejected=true;}check(rejected,"chunk plan rejects "+name);}
        var offline=Plan();offline["available"]=false;check(!ParsePlan(offline).CanStart,"offline chunk plan cannot start");
        var empty=Plan();empty["indexed_pages"]=145;empty["remaining_pages"]=0;empty["total_gap_pages"]=0;empty["page_ids"]=new JsonArray();empty["chunks"]=new JsonArray();empty["chunks_total"]=0;
        check(!ParsePlan(empty).CanStart,"complete coverage needs no chunk build");
        // Fragmented missing ranges may be grouped into fewer atomic chunks.
        var fragmented=Plan();fragmented["chunks"]=new JsonArray(Enumerable.Range(0,35).Select(n=>(JsonNode?)new JsonObject{{"start",n*2},{"count",1}}).ToArray());
        check(ParsePlan(fragmented).Ranges.Count==35&&ParsePlan(fragmented).ChunksTotal==3,"fragmented ranges are distinct from atomic chunk count");
        JsonObject Status()=>new(){{"job","book-pages-chunked"},{"job_id",job},{"item_id",7},{"source_revision",rev},{"profile",profile},
            {"scope",new JsonObject{{"root_ids",new JsonArray(2,3)},{"kind",""},{"shelf",null}}},{"state","cancelled"},{"total",35},{"processed",17},{"indexed",16},{"reused",0},
            {"chunk_size",16},{"chunks_total",3},{"chunks_completed",1},{"page_ids",Ids()},{"error",""}};
        PageChunkStatus ParseStatus(JsonObject data)=>PageChunkStatus.Parse(Bytes(data),profile,job,7,rev,scope);
        var saved=ParseStatus(Status());check(saved.CanResume&&!saved.Running&&saved.Indexed==16,"cancelled chunks retain completed publication");
        check(saved.MatchesScope(scope)&&!saved.MatchesScope(new JsonObject{{"root_ids",new JsonArray()}}),"empty roots cannot broaden saved resume scope");
        foreach(var(name,change) in new (string,Action<JsonObject>)[]{("job ID",o=>o["job_id"]=new string('c',32)),("profile",o=>o["profile"]="other"),
            ("item",o=>o["item_id"]=8),("revision",o=>o["source_revision"]=new string('c',64)),("scope",o=>o["scope"]!["kind"]="image"),
            ("missing saved IDs",o=>o.Remove("page_ids")),("missing chunk size",o=>o.Remove("chunk_size")),("completed count",o=>o["chunks_completed"]=2),
            ("false completion",o=>o["state"]="complete"),("overprocessed",o=>o["processed"]=36),("zero chunk",o=>o["chunk_size"]=0)})
        {var data=Status();change(data);var rejected=false;try{ParseStatus(data);}catch(InvalidDataException){rejected=true;}check(rejected,"chunk status rejects "+name);}
        var refused=false;try{PageChunkRequests.Resume(saved,new JsonObject{{"root_ids",new JsonArray(9)}});}catch(ArgumentException){refused=true;}check(refused,"chunk resume refuses changed scope before HTTP");
        var interrupted=Status();interrupted["state"]="interrupted";check(ParseStatus(interrupted).CanResume,"interrupted chunk selection remains explicitly resumable");
        var currentResponse=Plan();string? route=null;JsonObject? body=null;
        using var api=new LibraryApi(new Stub(async r=>{route=r.RequestUri!.AbsolutePath;body=r.Content is null?null:JsonNode.Parse(await r.Content.ReadAsStringAsync())!.AsObject();return new(HttpStatusCode.OK){Content=new StringContent(currentResponse.ToJsonString(),Encoding.UTF8,"application/json")};}));
        var actual=await api.PageEvidences.PlanChunksAsync(7,rev,scope,64,profile);
        check(route=="/api/library/ai/pages/chunked/plan"&&body!["profile"]!.GetValue<string>()==profile&&body["max_pages"]!.GetValue<int>()==64,"chunk plan uses bounded profile-bound POST");
        currentResponse=Status();currentResponse["state"]="running";var started=await api.PageEvidences.StartChunksAsync(actual);
        check(route=="/api/library/ai/pages/chunked"&&body!["page_ids"]!.AsArray().Count==35&&started.JobId==job,"chunk client starts only reviewed fixed selection");
        currentResponse["job_id"]=new string('d',32);var resumed=await api.PageEvidences.ResumeChunksAsync(saved,scope);
        check(route=="/api/library/ai/pages/chunked/resume"&&body!["job_id"]!.GetValue<string>()==job&&resumed.JobId!=saved.JobId,"chunk resume uses saved job and accepts own new ID");
        currentResponse["page_ids"]![0]=new string('e',64);refused=false;try{await api.PageEvidences.ChunkStatusAsync(resumed);}catch(InvalidDataException){refused=true;}
        check(refused,"chunk polling rejects replaced page selection");
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> response):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>response(request);}
}
