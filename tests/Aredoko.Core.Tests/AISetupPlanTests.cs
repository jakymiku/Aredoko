using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Nodes;
using Aredoko.Core;

static class AISetupPlanTests
{
    private static JsonObject Reply(IReadOnlyList<string> features)
    {
        var choices=new JsonArray();foreach(var id in features)choices.Add(new JsonObject{["id"]=id});
        var dependencies=new JsonArray();
        if(features.Count>0)
        {
            dependencies.Add(new JsonObject{["id"]="embedding-runtime",["files_present"]=false,["action"]="select_existing_environment",["download_candidates"]=new JsonArray()});
            dependencies.Add(new JsonObject{["id"]="embedding-model",["files_present"]=false,["action"]="review_download",["download_candidates"]=new JsonArray(new JsonObject{["catalog_id"]=new string('a',64)})});
        }
        return new(){["version"]=1,["basic_available"]=true,["ai_optional"]=true,["skip_ai"]=features.Count==0,["acquisition_started"]=false,["settings_saved"]=false,
            ["hardware_checked_by_plan"]=false,["inference_checked_by_plan"]=false,["features"]=choices,["requirements"]=dependencies,
            ["known_download_bytes"]=features.Count==0?0:100,["total_download_bytes"]=features.Count==0?(JsonNode?)JsonValue.Create(0):null,
            ["unresolved_features"]=new JsonArray(),["restart_required"]=false};
    }
    private sealed class Handler:HttpMessageHandler
    {
        public int Calls;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken token)
        {
            if(request.Method!=HttpMethod.Post||request.RequestUri!.AbsolutePath!="/api/library/ai/setup/plan")throw new Exception("Unexpected setup request");
            var body=JsonNode.Parse(await request.Content!.ReadAsStringAsync(token))!.AsObject();
            if(body.Count!=1||body["features"] is not JsonArray values)throw new Exception("Setup planning must not send consent/URL/command");
            Calls++;var features=values.Select(v=>v!.GetValue<string>()).ToArray();
            return new(HttpStatusCode.OK){Content=new StringContent(Reply(features).ToJsonString(),Encoding.UTF8,"application/json")};
        }
    }
    public static async Task Run(Action<bool,string> check)
    {
        using var handler=new Handler();using var http=new HttpClient(handler){BaseAddress=new Uri("http://127.0.0.1:8769/")};
        var client=new AISetupPlanClient(http);var plan=await client.CreateAsync(15);
        check(handler.Calls==1&&plan.Requirements.Count==2,"four uses request one shared runtime and model plan");
        check(plan.KnownBytes==100&&plan.TotalBytes is null&&plan.Summary.Contains("別途必要"),"unknown runtime bytes are not presented as a complete download size");
        check(plan.Summary.Contains("自動取得は準備中")&&plan.Summary.Contains("取得やAI処理を開始しません"),"unpublished runtime and read-only planning are explicit");
        var skip=await client.CreateAsync(0);check(skip.SkipAI&&skip.Requirements.Count==0&&skip.Summary.Contains("AIは使わず"),"AI opt-out keeps basic use available");
        check(AISetupSelection.FromMask(12).SequenceEqual(new[]{"video","audio"}),"feature flags retain audio/video without implicit extra models");
        check(AISetupSelection.Normalize(16)==3&&AISetupSelection.Normalize(-1)==3,"invalid stored feature selection uses backward-compatible defaults");
        var idleDownload=new AIDownloadJob(null,"idle",null,0,0,null,false,null,"",null);
        var idleEnvironment=new AIEnvironmentJob(null,"idle",false,"",0,null,0,null);
        var guidance=AISetupGuidance.Describe(plan,12,idleDownload,idleEnvironment);
        check(guidance.Contains("不足する実行環境")&&guidance.Contains("動画の準備欄")&&guidance.Contains("音声の準備欄")&&!guidance.Contains("意味検索・類似画像："),"next steps use selected media and do not claim missing dependencies are ready");
        var active=AISetupGuidance.Describe(plan,12,idleDownload with{State="downloading"},idleEnvironment with{State="validating"});
        check(active.Contains("バックグラウンドで続いて")&&active.Contains("完了してから再起動"),"returning to setup does not stop acquisition or claim placement is complete");
        var cancelled=AISetupGuidance.Describe(plan,12,idleDownload with{State="cancelled"},idleEnvironment with{State="cancelled"});
        check(cancelled.Contains("取得は中止")&&cancelled.Contains("再開できます")&&cancelled.Contains("前の設定を保持"),"cancelled acquisition and placement have explicit recovery steps");
        var published=AISetupGuidance.Describe(plan,15,idleDownload with{State="complete",Published=true},idleEnvironment);
        check(published.Contains("取得だけでは設定は変わりません")&&!published.Contains("配置を確認しました"),"published download is not an applied environment or inference result");
        var ready=plan with{Requirements=plan.Requirements.Select(r=>r with{FilesPresent=true}).ToArray()};
        var pending=AISetupGuidance.Describe(ready with{RestartRequired=true},15,idleDownload,idleEnvironment with{State="complete",Saved=true});
        check(pending.Contains("いつものAredoko.exe")&&pending.Contains("再起動後")&&!pending.Contains("次は「索引・詳細設定へ」"),"saved environment must restart before current-session indexing instructions");
        var prepared=AISetupGuidance.Describe(ready,3,idleDownload,idleEnvironment);
        check(prepared.Contains("動作確認とは別")&&prepared.Contains("索引・詳細設定へ")&&!prepared.Contains("音声の準備欄"),"present files lead to selected indexing without declaring hardware success");
        check(!AISetupGuidance.Describe(plan with{Requirements=Array.Empty<AISetupRequirement>()},3,null,null).Contains("配置を確認しました"),"an empty dependency response cannot be declared ready");
        check(!AISetupGuidance.Describe(skip,0,idleDownload with{State="downloading"},idleEnvironment).Contains("バックグラウンド"),"AI opt-out keeps next steps focused on basic use");
        foreach(var mutate in new Action<JsonObject>[]
        {
            row=>row["acquisition_started"]=true,row=>row["hardware_checked_by_plan"]=true,
            row=>row["known_download_bytes"]=-1,row=>row["skip_ai"]=true,
            row=>row["features"]=new JsonArray(new JsonObject{["id"]="future"}),
            row=>row["requirements"]!.AsArray()[0]!["action"]="run-pip",
            row=>row["requirements"]!.AsArray()[1]!["download_candidates"]!.AsArray()[0]!["catalog_id"]="https://example.invalid",
        })
        {
            var bad=Reply(AISetupSelection.FromMask(15));mutate(bad);var rejected=false;
            try{AISetupPlan.Parse(bad.ToJsonString(),AISetupSelection.FromMask(15));}catch(InvalidDataException){rejected=true;}
            check(rejected,"setup plan rejects unexpected execution, selection or catalog data");
        }
    }
}
