using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record VideoItemProgress(int ItemId,int PreparedMs,int? TotalMs,int PreparedWindows,string Phase)
{
    public string? ItemTitle {get;init;}
    private static string Clock(int ms)=>ms>=3600000?$"{ms/3600000}:{ms/60000%60:00}:{ms/1000%60:00}":$"{ms/60000}:{ms/1000%60:00}";
    public string Message=>TotalMs is not int total?"現在の動画を読み取っています（長さを確認中）…"
        :Phase=="saving"?$"現在の動画：{Clock(total)}の解析データを保存しています…"
        :$"現在の動画：{Clock(PreparedMs)} / {Clock(total)}（未保存）\n"+
            (Phase=="encoding"?"内容を解析しています…":PreparedMs==total?"読み取りの終了を確認しています…":"次の区間を読み取っています…");
    internal static VideoItemProgress Parse(JsonElement row)
    {
        if(row.ValueKind!=JsonValueKind.Object)throw new InvalidDataException("Invalid video item progress");
        int Count(string name,int maximum)=>row.TryGetProperty(name,out var count)&&count.ValueKind==JsonValueKind.Number
            &&count.TryGetInt32(out var value)&&value>=0&&value<=maximum?value:throw new InvalidDataException("Invalid video item count");
        var id=Count("item_id",int.MaxValue);var prepared=Count("prepared_ms",86400000);var windows=Count("prepared_windows",5400);
        if(!row.TryGetProperty("total_ms",out var duration))throw new InvalidDataException("Missing video duration");
        int? total=duration.ValueKind==JsonValueKind.Null?null:Count("total_ms",86400000);
        var phase=row.TryGetProperty("phase",out var named)&&named.ValueKind==JsonValueKind.String?named.GetString():null;
        if(id<1||phase is not ("decoding" or "encoding" or "saving")||windows!=(prepared+15999)/16000
            ||total is int known&&(known<1||prepared>known)
            ||total is null&&(prepared!=0||windows!=0||phase!="decoding")
            ||phase=="saving"&&(total is null||prepared!=total))throw new InvalidDataException("Invalid video item progress");
        return new(id,prepared,total,windows,phase){ItemTitle=MediaProgressTitle.Read(row)};
    }
}

public sealed record VideoContentStatus(bool Supported,bool Available,string State,int CandidateTotal,int Target,
    int Processed,int Indexed,int Reused,int Unavailable,int RemainingCandidates,bool Resident,string? ErrorCode)
{
    public VideoItemProgress? ItemProgress {get;init;}
    public bool Busy=>State is "planning" or "waiting" or "running" or "cancelling";
    public string Message=>ErrorCode=="video_initialization_failed"?"AI検索の初期化に失敗しました。アプリを再起動してから、もう一度実行してください。"
        :State=="failed"&&ErrorText.AIWorkerFailure(ErrorCode) is {} failure?failure
        :!Supported?"現在のAIモデルは動画の内容検索に対応していません。"
        :!Available?"AI環境を準備すると、動画の内容から検索できます。"
        :State switch
        {
            "planning"=>"動画の準備状況を確認しています…",
            "waiting"=>"ほかのAI処理が終わるのを待っています…",
            "running"=>$"動画を準備しています（{Processed:N0} / {Target:N0}件）"+(ItemProgress is {} item?"\n"+item.Message:""),
            "cancelling"=>"現在の処理を安全に中断しています…",
            "cancelled"=>$"中断しました。準備済みの{Indexed:N0}件は保持されています。",
            "failed"=>ErrorCode=="scope_changed"?"検索対象が変更されました。もう一度作成してください。":"動画を準備できませんでした。AI環境とファイルの状態を確認してください。",
            "completed"=>$"準備完了：{Indexed:N0}件。準備済み{Reused:N0}件は再利用しました。"+
                (Unavailable>0?$" 読み取れない候補{Unavailable:N0}件。":"")+
                (RemainingCandidates>0?$" 残りの候補{RemainingCandidates:N0}件は、もう一度作成すると続きへ進みます。":""),
            _=>"先に動画の索引を作成すると、動画内のシーンや内容を文章で探せます。"
        };
    public static VideoContentStatus Parse(string json)
    {
        using var document=JsonDocument.Parse(json);var row=document.RootElement;
        bool Flag(string name)=>row.TryGetProperty(name,out var flag)&&flag.ValueKind is JsonValueKind.True or JsonValueKind.False
            ?flag.GetBoolean():throw new InvalidDataException("Invalid video flag");
        int Count(string name)=>row.TryGetProperty(name,out var count)&&count.ValueKind==JsonValueKind.Number&&count.TryGetInt32(out var value)&&value>=0?value:throw new InvalidDataException("Invalid video count");
        var state=row.TryGetProperty("state",out var named)&&named.ValueKind==JsonValueKind.String?named.GetString():null;
        if(state is not ("idle" or "planning" or "waiting" or "running" or "cancelling" or "cancelled" or "completed" or "failed"))
            throw new InvalidDataException("Invalid video state");
        var target=Count("target");var processed=Count("processed");var indexed=Count("indexed");
        if(target>1000||processed>target||indexed>processed)throw new InvalidDataException("Invalid video progress");
        var progress=row.TryGetProperty("item_progress",out var current)&&current.ValueKind!=JsonValueKind.Null?VideoItemProgress.Parse(current):null;
        if(progress is not null&&(state is not ("running" or "cancelling")||processed>=target))throw new InvalidDataException("Invalid current video state");
        return new(Flag("supported"),Flag("available"),state,Count("candidate_total"),target,processed,indexed,
            Count("reused"),Count("unavailable"),Count("remaining_candidates"),Flag("resident"),
            row.TryGetProperty("error_code",out var error)&&error.ValueKind==JsonValueKind.String?error.GetString():null){ItemProgress=progress};
    }
}

public sealed class VideoContentClient(HttpClient client)
{
    public async Task<VideoContentStatus> StatusAsync(CancellationToken token=default)
    {
        using var response=await client.GetAsync("api/library/video-ai/status",token);
        return VideoContentStatus.Parse(await ReadAsync(response,token));
    }
    public Task<VideoContentStatus> StartAsync(JsonObject conditions,CancellationToken token=default)=>
        PostAsync("start",new(){["consent"]=true,["conditions"]=conditions.DeepClone(),["limit"]=128},token);
    public Task<VideoContentStatus> CancelAsync(CancellationToken token=default)=>PostAsync("cancel",new(),token);
    private async Task<VideoContentStatus> PostAsync(string operation,JsonObject body,CancellationToken token)
    {
        using var content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");
        using var response=await client.PostAsync("api/library/video-ai/"+operation,content,token);
        return VideoContentStatus.Parse(await ReadAsync(response,token));
    }
    private static async Task<string> ReadAsync(HttpResponseMessage response,CancellationToken token)
    {
        var text=await response.Content.ReadAsStringAsync(token);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return text;
    }
}
