using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public static class IndexContinuationRequests
{
    public const int MaxLimit = 10000;

    internal static string Profile(string profile) =>
        profile.Length is > 0 and <= 256 ? profile : throw new ArgumentException(AppText.L("モデル設定を確認してください。", "Check the AI model setting."));

    public static JsonObject Plan(JsonObject scope, string profile, int limit = 1000, long afterId = 0)
    {
        if (limit is < 1 or > MaxLimit) throw new ArgumentOutOfRangeException(nameof(limit), AppText.L("継続索引の上限は1〜10,000件です。", "Continuation limit must be between 1 and 10,000 items."));
        if (afterId < 0) throw new ArgumentOutOfRangeException(nameof(afterId), AppText.L("カーソル位置が無効です。", "Invalid cursor position."));
        var normalizedScope = PageChunkRequests.Scope(scope);
        return new()
        {
            ["scope"] = normalizedScope,
            ["profile"] = Profile(profile),
            ["limit"] = limit,
            ["after_id"] = afterId
        };
    }

    public static JsonObject Start(string planId, JsonObject scope, string profile)
    {
        PageEvidenceProtocol.ValidateRequestId(planId);
        return new()
        {
            ["plan_id"] = planId,
            ["scope"] = PageChunkRequests.Scope(scope),
            ["profile"] = Profile(profile)
        };
    }

    public static JsonObject Start(IndexContinuationPlan plan)
    {
        if (!plan.CanStart) throw new ArgumentException(AppText.L("追加する範囲を確認してください。", "Check the scope to add."));
        return Start(plan.PlanId, plan.Scope, plan.Profile);
    }

    public static JsonObject Resume(string jobId, JsonObject scope, string profile)
    {
        PageEvidenceProtocol.ValidateRequestId(jobId);
        return new()
        {
            ["job_id"] = jobId,
            ["scope"] = PageChunkRequests.Scope(scope),
            ["profile"] = Profile(profile)
        };
    }

    public static JsonObject Resume(IndexContinuationStatus status, JsonObject scope)
    {
        if (!status.CanResume || !status.MatchesScope(scope))
            throw new ArgumentException(AppText.L("前回と同じ対象範囲を保存してから再開してください。", "Save the same target scope as before resuming."));
        return Resume(status.JobId, scope, status.Profile);
    }

    public static JsonObject Cancel(string jobId)
    {
        PageEvidenceProtocol.ValidateRequestId(jobId);
        return new() { ["job_id"] = jobId };
    }
}

public sealed record IndexContinuationPlan(
    string PlanId,
    string Profile,
    JsonObject Scope,
    int CandidateTotal,
    int FreshTotal,
    int RemainingTotal,
    int RemainingAfterId,
    int SelectedTotal,
    int IndexLimit,
    long AfterId,
    long UpperId,
    long NextAfterId,
    int ExpiresInSeconds)
{
    public bool CanStart => SelectedTotal > 0;
    public string Summary => SelectedTotal == 0
        ? AppText.L("追加する未準備アイテムはありません。", "No unready items to add.")
        : AppText.L($"今回追加: {SelectedTotal:N0}件（未準備 {RemainingTotal:N0}件中）", $"To add now: {SelectedTotal:N0} (of {RemainingTotal:N0} unready)");
    public string DetailSummary => AppText.L(
        $"対象 {CandidateTotal:N0}件中、準備済み {FreshTotal:N0}件 · 未準備 {RemainingTotal:N0}件",
        $"Of {CandidateTotal:N0} in scope: {FreshTotal:N0} ready · {RemainingTotal:N0} unready");

    public static IndexContinuationPlan Parse(byte[] bytes, string expectedProfile, JsonObject? expectedScope = null)
    {
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var r = doc.RootElement;
            var planId = TagReviewProtocol.Text(r, "plan_id", 32);
            PageEvidenceProtocol.ValidateRequestId(planId);
            var profile = TagReviewProtocol.Text(r, "profile", 256);
            if (profile != expectedProfile) throw new InvalidDataException(AppText.L("モデル設定が一致しません。", "AI model setting does not match."));
            var scope = PageChunkRequests.ReadScope(r);
            if (expectedScope is not null && !JsonNode.DeepEquals(scope, PageChunkRequests.Scope(expectedScope)))
                throw new InvalidDataException(AppText.L("対象範囲が一致しません。", "Target scope does not match."));
            var expires = r.GetProperty("expires_in_seconds").GetInt32();
            if (expires < 1) throw new InvalidDataException(AppText.L("有効期限が無効です。", "Invalid expiration time."));
            var candidate = r.GetProperty("candidate_total").GetInt32();
            var fresh = r.GetProperty("fresh_total").GetInt32();
            var remaining = r.GetProperty("remaining_total").GetInt32();
            var remainingAfter = r.GetProperty("remaining_after_id").GetInt32();
            var selected = r.GetProperty("selected_total").GetInt32();
            var limit = r.GetProperty("index_limit").GetInt32();
            var afterId = r.GetProperty("after_id").GetInt64();
            var upperId = r.GetProperty("upper_id").GetInt64();
            var nextAfterId = r.GetProperty("next_after_id").GetInt64();

            if (candidate < 0 || fresh < 0 || fresh > candidate || remaining != candidate - fresh
                || remainingAfter < 0 || remainingAfter > remaining
                || selected < 0 || selected > limit || selected > remainingAfter || limit is < 1 or > 10000
                || afterId < 0 || upperId < 0 || nextAfterId < 0)
                throw new InvalidDataException(AppText.L("索引の計画内容が無効です。", "Invalid indexing plan payload."));

            return new(planId, profile, scope, candidate, fresh, remaining, remainingAfter, selected, limit, afterId, upperId, nextAfterId, expires);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {
            throw new InvalidDataException(AppText.L("索引の計画を読み取れません。", "Unable to read the indexing plan."), ex);
        }
    }
}

public sealed record IndexContinuationStatus(
    string JobId,
    string Profile,
    JsonObject Scope,
    string State,
    int Total,
    int Processed,
    int Indexed,
    int Skipped,
    int Reused,
    int SelectedTotal,
    int UnreadyTotal,
    long AfterId,
    long UpperId,
    long NextAfterId,
    string Error,
    string? ResumedFrom)
{
    public bool Running => State is "running" or "cancelling";
    public bool CanResume => State is "cancelled" or "interrupted" or "failed";
    public string Summary => AppText.L(
        $"継続索引: {Processed:N0}/{Total:N0}件 · 保存 {Indexed:N0} · 再利用 {Reused:N0} · 未準備 {UnreadyTotal:N0}",
        $"Continuation index: {Processed:N0}/{Total:N0} · Saved {Indexed:N0} · Reused {Reused:N0} · Unready {UnreadyTotal:N0}");

    public bool MatchesScope(JsonObject scope)
    {
        try { return JsonNode.DeepEquals(Scope, PageChunkRequests.Scope(scope)); }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or FormatException) { return false; }
    }

    public static IndexContinuationStatus Parse(byte[] bytes, string expectedProfile, string? expectedJobId = null, JsonObject? expectedScope = null)
    {
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var r = doc.RootElement;
            if (r.GetProperty("job").GetString() != "library-continuation-v1")
                throw new InvalidDataException(AppText.L("ジョブの種類が無効です。", "Invalid job type."));
            var jobId = TagReviewProtocol.Text(r, "job_id", 32);
            PageEvidenceProtocol.ValidateRequestId(jobId);
            if (expectedJobId is not null && jobId != expectedJobId)
                throw new InvalidDataException(AppText.L("ジョブIDが一致しません。", "Job ID does not match."));
            var profile = TagReviewProtocol.Text(r, "profile", 256);
            if (profile != expectedProfile)
                throw new InvalidDataException(AppText.L("モデル設定が一致しません。", "AI model setting does not match."));
            var scope = PageChunkRequests.ReadScope(r);
            if (expectedScope is not null && !JsonNode.DeepEquals(scope, PageChunkRequests.Scope(expectedScope)))
                throw new InvalidDataException(AppText.L("対象範囲が一致しません。", "Target scope does not match."));
            var state = TagReviewProtocol.Text(r, "state", 16);
            if (state is not ("running" or "cancelling" or "complete" or "cancelled" or "interrupted" or "failed"))
                throw new InvalidDataException(AppText.L("処理状態が無効です。", "Invalid processing state."));
            var total = r.GetProperty("total").GetInt32();
            var processed = r.GetProperty("processed").GetInt32();
            var indexed = r.GetProperty("indexed").GetInt32();
            var skipped = r.GetProperty("skipped").GetInt32();
            var reused = r.GetProperty("reused").GetInt32();
            var selectedTotal = r.GetProperty("selected_total").GetInt32();
            var unreadyTotal = r.GetProperty("unready_total").GetInt32();
            var afterId = r.GetProperty("after_id").GetInt64();
            var upperId = r.GetProperty("upper_id").GetInt64();
            var nextAfterId = r.GetProperty("next_after_id").GetInt64();
            var error = AppText.TranslateBackend(r.GetProperty("error").GetString());

            string? resumedFrom = null;
            if (r.TryGetProperty("resumed_from", out var rf) && rf.ValueKind != JsonValueKind.Null)
            {
                var candidate = rf.GetString();
                if (candidate is not null)
                {
                    PageEvidenceProtocol.ValidateRequestId(candidate);
                    resumedFrom = candidate;
                }
            }

            if (total is < 0 or > 10000 || processed < 0 || processed > total
                || indexed < 0 || indexed > processed || skipped < 0 || skipped > processed
                || reused < 0 || reused > processed || selectedTotal != total || unreadyTotal != skipped
                || afterId < 0 || upperId < 0 || nextAfterId < 0 || error.Length > 1024
                || (state == "complete" && (processed != total || indexed + skipped != total)))
                throw new InvalidDataException(AppText.L("継続索引の処理件数が無効です。", "Invalid continuation indexing counts."));

            return new(jobId, profile, scope, state, total, processed, indexed, skipped, reused, selectedTotal, unreadyTotal, afterId, upperId, nextAfterId, error, resumedFrom);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {
            throw new InvalidDataException(AppText.L("継続索引の状況を読み取れません。", "Unable to read continuation indexing status."), ex);
        }
    }
}

public sealed class IndexContinuationClient
{
    private readonly HttpClient client;
    public const int MaxJsonBytes = 1024 * 1024;

    public IndexContinuationClient(HttpClient client) => this.client = client;

    private async Task<byte[]> SendJsonAsync(string route, JsonObject? data, CancellationToken cancellation)
    {
        using var request = new HttpRequestMessage(data is null ? HttpMethod.Get : HttpMethod.Post, route);
        if (data is not null)
            request.Content = new StringContent(data.ToJsonString(), Encoding.UTF8, "application/json");
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        var bytes = await response.Content.ReadAsByteArrayAsync(cancellation);
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException(ErrorText.FromResponse(Encoding.UTF8.GetString(bytes), (int)response.StatusCode));
        if (bytes.Length > MaxJsonBytes)
            throw new InvalidDataException(AppText.L("応答サイズが上限を超えました。", "Response size exceeded the limit."));
        return bytes;
    }

    public async Task<IndexContinuationPlan> PlanAsync(JsonObject scope, string profile, int limit = 1000, long afterId = 0, CancellationToken cancellation = default)
    {
        var request = IndexContinuationRequests.Plan(scope, profile, limit, afterId);
        var bytes = await SendJsonAsync("api/library/ai/index/plan", request, cancellation);
        return IndexContinuationPlan.Parse(bytes, profile, scope);
    }

    public async Task<IndexContinuationStatus> StartAsync(IndexContinuationPlan plan, CancellationToken cancellation = default)
    {
        var request = IndexContinuationRequests.Start(plan);
        var bytes = await SendJsonAsync("api/library/ai/index/start", request, cancellation);
        return IndexContinuationStatus.Parse(bytes, plan.Profile, expectedScope: plan.Scope);
    }

    public async Task<IndexContinuationStatus> ResumeAsync(IndexContinuationStatus saved, JsonObject scope, CancellationToken cancellation = default)
    {
        var request = IndexContinuationRequests.Resume(saved, scope);
        var bytes = await SendJsonAsync("api/library/ai/index/resume", request, cancellation);
        return IndexContinuationStatus.Parse(bytes, saved.Profile, expectedScope: scope);
    }

    public async Task<bool> CancelAsync(string jobId, CancellationToken cancellation = default)
    {
        var request = IndexContinuationRequests.Cancel(jobId);
        var bytes = await SendJsonAsync("api/library/ai/index/cancel", request, cancellation);
        try
        {
            using var doc = JsonDocument.Parse(bytes);
            var r = doc.RootElement;
            var echoJob = TagReviewProtocol.Text(r, "job_id", 32);
            PageEvidenceProtocol.ValidateRequestId(echoJob);
            if (echoJob != jobId) throw new InvalidDataException(AppText.L("取消応答のジョブIDが一致しません。", "Cancellation response job ID does not match."));
            return r.GetProperty("cancel_requested").GetBoolean();
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException or ArgumentException)
        {
            throw new InvalidDataException(AppText.L("取消結果を読み取れません。", "Unable to read cancellation result."), ex);
        }
    }

    public async Task<IndexContinuationStatus> StatusAsync(string profile, string? expectedJobId = null, JsonObject? expectedScope = null, CancellationToken cancellation = default)
    {
        var bytes = await SendJsonAsync("api/library/ai/status", null, cancellation);
        return IndexContinuationStatus.Parse(bytes, profile, expectedJobId, expectedScope);
    }
}
