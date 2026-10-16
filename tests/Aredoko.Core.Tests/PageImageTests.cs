using Aredoko.Core;
using System.Text.Json.Nodes;

internal static class PageImageTests
{
    public static void Run(Action<bool,string> check)
    {
        var rev=new string('a',64);var pid=new string('b',64);var modelRev=new string('c',40);
        var row=JsonNode.Parse("""{"id":7,"title":"book","kind":"book","tags":[],"shelf":"","favorite":false,"reviewed":false}""")!.AsObject();
        JsonObject Evidence()=>new(){{"source_revision",rev},{"source_state","current"},{"page_id",pid},{"page",2},
            {"model","fixture-model"},{"model_revision",modelRev},{"profile","fixture-profile"},{"preprocessing","book-page-image:v1"},{"semantic_score",.8}};
        row["ai_page_match"]=Evidence();
        var parsed=Protocol.ParseItem(row.ToJsonString());var match=parsed.AIPage!;
        check(match.Page==2&&match.PageId==pid&&match.ModelRevision==modelRev&&match.Profile=="fixture-profile","AI page image provenance parsed without reflection");
        check(match.Summary.Contains("3ページ")&&match.Summary.Contains("fixture-model")&&parsed.AIEvidence=="","AI page evidence avoids duplicate generic label");
        check(match.InitialReaderPage(new(7,4,rev))==2,"AI page opens current matching source revision");
        check(match.InitialReaderPage(new(7,4,new string('d',64))) is null,"changed reader revision never jumps to stale AI page");
        check(match.InitialReaderPage(new(7,2,rev)) is null&&(match with {SourceState="stale"}).InitialReaderPage(new(7,4,rev)) is null,"AI page jump validates bounds and state");
        foreach(var (key,value) in new (string,JsonNode?)[]{("page",JsonValue.Create(-1)),("page",JsonValue.Create(10000)),("page_id",JsonValue.Create("bad")),
            ("source_revision",JsonValue.Create("bad")),("model_revision",JsonValue.Create(new string('z',40))),("source_state",JsonValue.Create("stale")),
            ("semantic_score",JsonValue.Create(1.1)),("preprocessing",JsonValue.Create("unknown")),("model",JsonValue.Create(new string('x',129)))})
        {
            var ev=Evidence();ev[key]=value;row["ai_page_match"]=ev;
            var rejected=false;try{Protocol.ParseItem(row.ToJsonString());}catch(InvalidDataException){rejected=true;}
            check(rejected,"AI page rejects invalid "+key+" "+value);
        }
        var scope=new JsonObject{{"root_ids",new JsonArray(1)}};
        var request=PageImageRequests.Create(7,[pid],rev,scope);request["scope"]!["kind"]="book";
        check(scope["kind"] is null&&request["page_ids"]!.AsArray().Count==1,"page image request owns scope and selected IDs");
        foreach(var ids in new IReadOnlyList<string>[] {[],[pid,pid],Enumerable.Repeat(pid,17).ToArray(),["bad"]})
        {
            var rejected=false;try{PageImageRequests.Create(7,ids,rev,scope);}catch(ArgumentException){rejected=true;}
            check(rejected,"page image range validation "+ids.Count);
        }
    }
}
