using Aredoko.Core;
using System.Net;
using System.Text;
using System.Text.Json.Nodes;

internal static class IndexContinuationTests
{
    public static async Task Run(Action<bool, string> check)
    {
        var planHex = new string('a', 32);
        var jobHex = new string('b', 32);
        var profile = "test-profile";
        var scope = new JsonObject { ["root_ids"] = new JsonArray(2, 1) };

        // 1. Requests formatting and parameter boundary validation
        var planReq = IndexContinuationRequests.Plan(scope, profile, 500, 10);
        check(planReq["limit"]!.GetValue<int>() == 500 && planReq["after_id"]!.GetValue<long>() == 10, "continuation plan request sets limit and after_id");
        check(planReq["profile"]!.GetValue<string>() == profile, "continuation plan request sets profile");
        check(planReq["scope"]!["root_ids"]![0]!.GetValue<long>() == 1, "continuation plan request normalizes scope root_ids order");

        // Mutating original scope does not alter request
        scope["root_ids"]![0] = 99;
        check(planReq["scope"]!["root_ids"]![0]!.GetValue<long>() == 1, "continuation plan request clones and owns scope");
        scope["root_ids"]![0] = 2;

        foreach (var badLimit in new[] { 0, -1, 10001 })
        {
            var rejected = false;
            try { IndexContinuationRequests.Plan(scope, profile, badLimit); }
            catch (ArgumentOutOfRangeException) { rejected = true; }
            check(rejected, $"continuation plan rejects invalid limit: {badLimit}");
        }

        var badAfterRejected = false;
        try { IndexContinuationRequests.Plan(scope, profile, 100, -1); }
        catch (ArgumentOutOfRangeException) { badAfterRejected = true; }
        check(badAfterRejected, "continuation plan rejects negative after_id");

        var badProfileRejected = false;
        try { IndexContinuationRequests.Plan(scope, ""); }
        catch (ArgumentException) { badProfileRejected = true; }
        check(badProfileRejected, "continuation plan rejects empty profile");

        // Start request
        var startReq = IndexContinuationRequests.Start(planHex, scope, profile);
        check(startReq["plan_id"]!.GetValue<string>() == planHex && startReq["profile"]!.GetValue<string>() == profile, "continuation start request sets plan_id and profile");

        var badStartPlanId = false;
        try { IndexContinuationRequests.Start("short", scope, profile); }
        catch (ArgumentException) { badStartPlanId = true; }
        check(badStartPlanId, "continuation start rejects invalid plan_id");

        // Resume request
        var resumeReq = IndexContinuationRequests.Resume(jobHex, scope, profile);
        check(resumeReq["job_id"]!.GetValue<string>() == jobHex, "continuation resume request sets job_id");

        var badResumeJobId = false;
        try { IndexContinuationRequests.Resume("bad_hex_job_id_that_is_32_chars!", scope, profile); }
        catch (ArgumentException) { badResumeJobId = true; }
        check(badResumeJobId, "continuation resume rejects invalid job_id");

        // Cancel request
        var cancelReq = IndexContinuationRequests.Cancel(jobHex);
        check(cancelReq["job_id"]!.GetValue<string>() == jobHex, "continuation cancel request sets job_id");

        var badCancelJobId = false;
        try { IndexContinuationRequests.Cancel("invalid"); }
        catch (ArgumentException) { badCancelJobId = true; }
        check(badCancelJobId, "continuation cancel rejects invalid job_id");

        // 2. Plan Parsing
        JsonObject ValidPlanJson() => new()
        {
            ["plan_id"] = planHex,
            ["profile"] = profile,
            ["scope"] = new JsonObject { ["root_ids"] = new JsonArray(1, 2), ["kind"] = "", ["shelf"] = null },
            ["candidate_total"] = 10,
            ["fresh_total"] = 4,
            ["remaining_total"] = 6,
            ["remaining_after_id"] = 6,
            ["selected_total"] = 2,
            ["index_limit"] = 1000,
            ["after_id"] = 0,
            ["upper_id"] = 10,
            ["next_after_id"] = 2,
            ["expires_in_seconds"] = 300
        };

        byte[] ToBytes(JsonObject obj) => Encoding.UTF8.GetBytes(obj.ToJsonString());

        var parsedPlan = IndexContinuationPlan.Parse(ToBytes(ValidPlanJson()), profile, scope);
        check(parsedPlan.CanStart && parsedPlan.SelectedTotal == 2 && parsedPlan.RemainingTotal == 6, "plan parse keeps valid counts");
        check(parsedPlan.PlanId == planHex && parsedPlan.NextAfterId == 2, "plan parse keeps IDs and cursors");
        check(parsedPlan.Summary.Contains("今回追加: 2件") && parsedPlan.DetailSummary.Contains("対象 10件中"), "plan summary strings formatted");

        var emptyPlanJson = ValidPlanJson();
        emptyPlanJson["selected_total"] = 0;
        emptyPlanJson["remaining_after_id"] = 0;
        var emptyPlan = IndexContinuationPlan.Parse(ToBytes(emptyPlanJson), profile, scope);
        check(!emptyPlan.CanStart && emptyPlan.Summary == "追加する未準備アイテムはありません。", "empty plan cannot start");

        var startFromEmptyRejected = false;
        try { IndexContinuationRequests.Start(emptyPlan); }
        catch (ArgumentException) { startFromEmptyRejected = true; }
        check(startFromEmptyRejected, "cannot start continuation from empty plan");

        // Plan parse corruption rejections
        foreach (var (name, change) in new (string, Action<JsonObject>)[]
        {
            ("wrong profile", o => o["profile"] = "other"),
            ("wrong scope", o => o["scope"]!["kind"] = "image"),
            ("short plan_id", o => o["plan_id"] = "1234"),
            ("uppercase plan_id", o => o["plan_id"] = new string('A', 32)),
            ("negative candidate", o => o["candidate_total"] = -1),
            ("fresh greater than candidate", o => o["fresh_total"] = 11),
            ("remaining mismatch", o => o["remaining_total"] = 5),
            ("remaining_after mismatch", o => o["remaining_after_id"] = 7),
            ("selected greater than remaining_after", o => o["selected_total"] = 7),
            ("selected greater than limit", o => { o["index_limit"] = 1; o["selected_total"] = 2; }),
            ("zero limit", o => o["index_limit"] = 0),
            ("limit above max", o => o["index_limit"] = 10001),
            ("negative after_id", o => o["after_id"] = -1),
            ("zero expires", o => o["expires_in_seconds"] = 0)
        })
        {
            var data = ValidPlanJson();
            change(data);
            var rejected = false;
            try { IndexContinuationPlan.Parse(ToBytes(data), profile, scope); }
            catch (InvalidDataException) { rejected = true; }
            check(rejected, $"plan parsing rejects {name}");
        }

        // 3. Status Parsing
        JsonObject ValidStatusJson() => new()
        {
            ["job"] = "library-continuation-v1",
            ["job_id"] = jobHex,
            ["profile"] = profile,
            ["scope"] = new JsonObject { ["root_ids"] = new JsonArray(1, 2), ["kind"] = "", ["shelf"] = null },
            ["state"] = "running",
            ["total"] = 100,
            ["processed"] = 20,
            ["indexed"] = 15,
            ["skipped"] = 5,
            ["reused"] = 10,
            ["selected_total"] = 100,
            ["unready_total"] = 5,
            ["after_id"] = 0,
            ["upper_id"] = 100,
            ["next_after_id"] = 20,
            ["error"] = "",
            ["resumed_from"] = null
        };

        var parsedStatus = IndexContinuationStatus.Parse(ToBytes(ValidStatusJson()), profile, jobHex, scope);
        check(parsedStatus.Running && !parsedStatus.CanResume && parsedStatus.Total == 100 && parsedStatus.Processed == 20, "status parse keeps running properties");
        check(parsedStatus.MatchesScope(scope), "status matches active scope");
        check(!parsedStatus.MatchesScope(new JsonObject { ["root_ids"] = new JsonArray(9) }), "status rejects different scope");
        check(parsedStatus.Summary.Contains("継続索引: 20/100件 · 保存 15 · 再利用 10 · 未準備 5"), "status summary string formatted");

        // Resumable states
        foreach (var resumableState in new[] { "cancelled", "interrupted", "failed" })
        {
            var rData = ValidStatusJson();
            rData["state"] = resumableState;
            var rStatus = IndexContinuationStatus.Parse(ToBytes(rData), profile);
            check(!rStatus.Running && rStatus.CanResume, $"state {resumableState} is resumable and not running");
        }

        // Complete state validation
        var completeData = ValidStatusJson();
        completeData["state"] = "complete";
        completeData["processed"] = 100;
        completeData["indexed"] = 90;
        completeData["skipped"] = 10;
        completeData["unready_total"] = 10;
        var completeStatus = IndexContinuationStatus.Parse(ToBytes(completeData), profile);
        check(!completeStatus.Running && !completeStatus.CanResume, "complete state is neither running nor resumable");

        // Resumed_from field
        var resumedData = ValidStatusJson();
        resumedData["resumed_from"] = planHex;
        var resumedStatus = IndexContinuationStatus.Parse(ToBytes(resumedData), profile);
        check(resumedStatus.ResumedFrom == planHex, "status parses resumed_from hex");

        // Status corruption rejections
        foreach (var (name, change) in new (string, Action<JsonObject>)[]
        {
            ("wrong job name", o => o["job"] = "book-pages-chunked"),
            ("wrong job_id", o => o["job_id"] = planHex),
            ("invalid job_id hex", o => o["job_id"] = new string('Z', 32)),
            ("wrong profile", o => o["profile"] = "other"),
            ("wrong scope", o => o["scope"]!["kind"] = "book"),
            ("invalid state", o => o["state"] = "unknown"),
            ("processed above total", o => o["processed"] = 101),
            ("indexed above processed", o => o["indexed"] = 21),
            ("skipped above processed", o => o["skipped"] = 21),
            ("reused above processed", o => o["reused"] = 21),
            ("selected_total mismatch", o => o["selected_total"] = 99),
            ("unready_total mismatch", o => o["unready_total"] = 99),
            ("total above limit", o => o["total"] = 10001),
            ("incomplete numbers marked complete", o => o["state"] = "complete"),
            ("bad resumed_from", o => o["resumed_from"] = "not_hex")
        })
        {
            var data = ValidStatusJson();
            change(data);
            var rejected = false;
            try { IndexContinuationStatus.Parse(ToBytes(data), profile, jobHex, scope); }
            catch (InvalidDataException) { rejected = true; }
            check(rejected, $"status parsing rejects {name}");
        }

        // Resume request helper validation
        var resumeRequestSuccess = IndexContinuationRequests.Resume(parsedStatus with { State = "cancelled" }, scope);
        check(resumeRequestSuccess["job_id"]!.GetValue<string>() == jobHex, "resume request creates from resumable status");

        var resumeRequestScopeMismatch = false;
        try { IndexContinuationRequests.Resume(parsedStatus with { State = "cancelled" }, new JsonObject { ["root_ids"] = new JsonArray(9) }); }
        catch (ArgumentException) { resumeRequestScopeMismatch = true; }
        check(resumeRequestScopeMismatch, "resume request rejects scope mismatch");

        var resumeRequestNotResumable = false;
        try { IndexContinuationRequests.Resume(parsedStatus, scope); } // parsedStatus is running
        catch (ArgumentException) { resumeRequestNotResumable = true; }
        check(resumeRequestNotResumable, "resume request rejects non-resumable status");

        // 4. HTTP Client Integration via LibraryApi
        string? requestedRoute = null;
        JsonObject? requestedBody = null;
        JsonObject currentResponse = ValidPlanJson();

        using var api = new LibraryApi(new Stub(async req =>
        {
            requestedRoute = req.RequestUri!.AbsolutePath;
            requestedBody = req.Content is null ? null : JsonNode.Parse(await req.Content.ReadAsStringAsync())!.AsObject();
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(currentResponse.ToJsonString(), Encoding.UTF8, "application/json")
            };
        }));

        // PlanAsync
        var apiPlan = await api.Continuation.PlanAsync(scope, profile, 500, 0);
        check(requestedRoute == "/api/library/ai/index/plan" && requestedBody!["limit"]!.GetValue<int>() == 500, "PlanAsync sends expected route and body");
        check(apiPlan.PlanId == planHex, "PlanAsync parses plan response");

        // StartAsync
        currentResponse = ValidStatusJson();
        var apiStart = await api.Continuation.StartAsync(apiPlan);
        check(requestedRoute == "/api/library/ai/index/start" && requestedBody!["plan_id"]!.GetValue<string>() == planHex, "StartAsync sends expected route and body");
        check(apiStart.JobId == jobHex && apiStart.Running, "StartAsync parses started status");

        // ResumeAsync
        currentResponse = ValidStatusJson();
        currentResponse["resumed_from"] = jobHex;
        var apiResume = await api.Continuation.ResumeAsync(apiStart with { State = "cancelled" }, scope);
        check(requestedRoute == "/api/library/ai/index/resume" && requestedBody!["job_id"]!.GetValue<string>() == jobHex, "ResumeAsync sends expected route and body");
        check(apiResume.ResumedFrom == jobHex, "ResumeAsync parses resumed status");

        // CancelAsync
        currentResponse = new JsonObject { ["cancel_requested"] = true, ["job_id"] = jobHex };
        var cancelSuccess = await api.Continuation.CancelAsync(jobHex);
        check(requestedRoute == "/api/library/ai/index/cancel" && requestedBody!["job_id"]!.GetValue<string>() == jobHex && cancelSuccess, "CancelAsync sends expected route and returns true");

        currentResponse = new JsonObject { ["cancel_requested"] = false, ["job_id"] = jobHex };
        var cancelFalse = await api.Continuation.CancelAsync(jobHex);
        check(!cancelFalse, "CancelAsync returns false when job already completed");

        currentResponse = new JsonObject { ["cancel_requested"] = true, ["job_id"] = planHex };
        var cancelWrongIdRejected = false;
        try { await api.Continuation.CancelAsync(jobHex); }
        catch (InvalidDataException) { cancelWrongIdRejected = true; }
        check(cancelWrongIdRejected, "CancelAsync rejects mismatched echo job_id");

        // StatusAsync
        currentResponse = ValidStatusJson();
        var apiStatus = await api.Continuation.StatusAsync(profile, jobHex, scope);
        check(requestedRoute == "/api/library/ai/status" && requestedBody is null, "StatusAsync gets ai/status");
        check(apiStatus.JobId == jobHex, "StatusAsync parses status response");
    }

    private sealed class Stub(Func<HttpRequestMessage, Task<HttpResponseMessage>> response) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => response(request);
    }
}
