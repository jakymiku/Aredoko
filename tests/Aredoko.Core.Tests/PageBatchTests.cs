using Aredoko.Core;
using System.Text;
using System.Text.Json.Nodes;

static class PageBatchTests
{
    public static void Run(Action<bool,string> check)
    {
        var rev=new string('a',64);var pid=new string('b',64);var job=new string('c',32);var scope=new JsonObject{{"root_ids",new JsonArray(1)}};
        var books=new[]{new BookPageSelection(7,rev,new[]{pid}),new BookPageSelection(8,rev,new[]{pid})};
        var body=PageBatchRequests.Create(books,scope,2,"fixture");
        check(body["items"]!.AsArray().Count==2&&body["scope"]!["root_ids"]![0]!.GetValue<int>()==1&&scope.Count==1,"batch explicit range and cloned scope");
        foreach(var invalid in new Action[]{()=>PageBatchRequests.Create([],scope,128,"fixture"),()=>PageBatchRequests.Create([books[0],books[0]],scope,2,"fixture"),
            ()=>PageBatchRequests.Create(books,scope,1,"fixture"),()=>PageBatchRequests.Create(books,scope,129,"fixture"),
            ()=>PageBatchRequests.Create(books,scope,2,""),()=>PageBatchRequests.Resume("bad",scope,"fixture")})
        {var rejected=false;try{invalid();}catch(ArgumentException){rejected=true;}check(rejected,"invalid batch request rejected");}
        JsonObject Data()=>new(){["job"]="book-page-batch",["job_id"]=job,["profile"]="fixture",["state"]="running",
            ["total"]=2,["processed"]=0,["indexed"]=0,["reused"]=0,["books_total"]=2,["books_completed"]=0,["books_failed"]=0,["error"]="",
            ["books"]=new JsonArray(books.Select(b=>(JsonNode)new JsonObject{["item_id"]=b.ItemId,["revision"]=rev,["total"]=1,["processed"]=0,["indexed"]=0,["reused"]=0,["state"]="pending",["error"]=""}).ToArray())};
        PageBatchStatus Parse(JsonObject d,string profile="fixture",string? expected=null)=>PageBatchStatus.Parse(Encoding.UTF8.GetBytes(d.ToJsonString()),profile,expected);
        check(Parse(Data()).Running,"pending batch strict state accepts empty errors");
        foreach(var (name,mutate) in new (string,Action<JsonObject>)[]{
            ("job type",d=>d["job"]="other"),("job ID",d=>d["job_id"]="bad"),("total cap",d=>d["total"]=129),
            ("bad state",d=>d["state"]="unknown"),("processed",d=>d["processed"]=3),("unpublished indexed",d=>d["indexed"]=1),
            ("duplicate books",d=>d["books"]![1]!["item_id"]=7),("revision",d=>d["books"]![0]!["revision"]="bad"),
            ("book page cap",d=>d["books"]![0]!["total"]=17),("counts",d=>d["books_completed"]=1),
            ("false complete",d=>d["state"]="complete"),("false partial",d=>d["state"]="partial"),
            ("long error",d=>d["error"]=new string('x',1025))})
        {var d=Data();mutate(d);var rejected=false;try{Parse(d);}catch(InvalidDataException){rejected=true;}check(rejected,"batch rejects "+name);}
        foreach(var mode in new[]{"profile","job"})
        {var rejected=false;try{Parse(Data(),mode=="profile"?"other":"fixture",mode=="job"?new string('d',32):null);}catch(InvalidDataException){rejected=true;}check(rejected,"batch protects expected "+mode);}
        var cancelled=Data();cancelled["state"]="cancelled";
        check(Parse(cancelled).CanResume,"cancelled batch resumable without auto execution");
        var interrupted=Data();interrupted["state"]="interrupted";interrupted["processed"]=1;
        check(Parse(interrupted).CanResume,"interrupted in-flight range may be retried");
    }
}
