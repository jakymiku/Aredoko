using Aredoko.Core;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json.Nodes;

internal static class PageCoverageTests
{
    public static async Task Run(Action<bool,string> check)
    {
        var rev=new string('a',64);
        JsonObject Data()=>new(){{"item_id",7},{"source_revision",rev},{"source_state","current"},{"profile","page-profile"},{"model","test-model"},
            {"supported",true},{"available",true},{"page_count",40},{"indexed_pages",20},{"remaining_pages",20},
            {"indexed_ranges",JsonNode.Parse("[{\"start\":4,\"count\":4},{\"start\":16,\"count\":16}]")},
            {"next_range",new JsonObject{{"start",0},{"count",4}}}};
        PageImageCoverage Parse(JsonObject value,string? expectedProfile=null)=>PageImageCoverage.Parse(Encoding.UTF8.GetBytes(value.ToJsonString()),7,rev,expectedProfile);
        var value=Parse(Data());
        check(value.CanPrepare&&value.IndexedPages==20&&value.RemainingPages==20&&value.NextRange==new PageImageRange(0,4),"page coverage exact counts and first uncovered gap");
        check(value.Summary.Contains("20 / 40")&&value.RangeSummary=="5–8、17–32ページ","page coverage displays one-based merged ranges");
        var complete=Data();complete["indexed_ranges"]=JsonNode.Parse("[{\"start\":0,\"count\":40}]");complete["indexed_pages"]=40;complete["remaining_pages"]=0;complete["next_range"]=null;
        check(Parse(complete).NextRange is null&&Parse(complete).IndexedPages==40,"complete page coverage has no next range");
        var offline=Data();offline["available"]=false;check(!Parse(offline).CanPrepare&&Parse(offline).IndexedPages==20,"offline model preserves read-only indexed page counts");
        foreach(var state in new[]{"stale","unavailable","unverified"})
        {
            var stale=Data();stale["source_state"]=state;stale["indexed_pages"]=0;stale["remaining_pages"]=40;stale["indexed_ranges"]=new JsonArray();stale["next_range"]=null;
            check(!Parse(stale).CanPrepare&&Parse(stale).NextRange is null,"noncurrent source never offers a next range: "+state);
        }
        var badCases=new List<(string,Action<JsonObject>)>
        {
            ("wrong item",o=>o["item_id"]=8),("wrong revision",o=>o["source_revision"]=new string('b',64)),
            ("invalid state",o=>o["source_state"]="fresh"),("bad total",o=>o["page_count"]=10001),
            ("negative ready",o=>o["indexed_pages"]=-1),("wrong remaining",o=>o["remaining_pages"]=21),
            ("wrong range sum",o=>o["indexed_ranges"]=JsonNode.Parse("[{\"start\":16,\"count\":16}]")),
            ("overlap",o=>o["indexed_ranges"]=JsonNode.Parse("[{\"start\":4,\"count\":10},{\"start\":8,\"count\":10}]")),
            ("unmerged adjacent",o=>o["indexed_ranges"]=JsonNode.Parse("[{\"start\":4,\"count\":4},{\"start\":8,\"count\":16}]")),
            ("overflow range",o=>o["indexed_ranges"]=JsonNode.Parse("[{\"start\":4,\"count\":2147483647}]")),
            ("missing next",o=>o["next_range"]=null),("wrong next",o=>o["next_range"]=new JsonObject{{"start",8},{"count",8}}),
            ("next crosses ready pages",o=>o["next_range"]=new JsonObject{{"start",0},{"count",16}}),
            ("stale has ready pages",o=>o["source_state"]="stale"),("text-only has ready pages",o=>o["supported"]=false),
            ("non-bool available",o=>o["available"]="true")
        };
        foreach(var (name,change) in badCases)
        {
            var data=Data();change(data);var rejected=false;
            try{Parse(data);}catch(InvalidDataException){rejected=true;}
            check(rejected,"page coverage rejects "+name);
        }
        var profileRejected=false;try{Parse(Data(),"other-profile");}catch(InvalidDataException){profileRejected=true;}
        check(profileRejected,"page coverage cannot change profile inside a dialog");
        string? route=null;JsonObject? captured=null;
        using var api=new LibraryApi(new Stub(async request=>
        {
            route=request.RequestUri!.AbsolutePath;captured=JsonNode.Parse(await request.Content!.ReadAsStringAsync())!.AsObject();
            return new(HttpStatusCode.OK){Content=new StringContent(Data().ToJsonString(),Encoding.UTF8,"application/json")};
        }));
        var scope=new JsonObject{{"root_ids",new JsonArray(2)}};
        var actual=await api.PageEvidences.ImageCoverageAsync(7,rev,scope,"page-profile");
        check(route=="/api/library/ai/pages/coverage"&&captured!["item_id"]!.GetValue<int>()==7&&captured["revision"]!.GetValue<string>()==rev,"page coverage client uses explicit scoped POST");
        check(captured!["scope"]!["root_ids"]![0]!.GetValue<int>()==2&&scope.Count==1&&actual.IndexedPages==20,"page coverage client owns scope JSON and validates response");
        using var largeApi=new LibraryApi(new Stub(_=>Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent(new string('x',PageEvidenceProtocol.MaxJsonBytes+1),Encoding.UTF8,"application/json")})));
        var largeRejected=false;try{await largeApi.PageEvidences.ImageCoverageAsync(7,rev,scope);}catch(InvalidDataException){largeRejected=true;}
        check(largeRejected,"page coverage client bounds response bytes");
    }
    private sealed class Stub(Func<HttpRequestMessage,Task<HttpResponseMessage>> response):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellation)=>response(request);}
}
