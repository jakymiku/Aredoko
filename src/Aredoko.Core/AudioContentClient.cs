using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record AudioItemProgress(int ItemId,int PreparedMs,int? TotalMs,int PreparedWindows,string Phase)
{
    private static string Clock(int ms)=>ms>=3600000?$"{ms/3600000}:{ms/60000%60:00}:{ms/1000%60:00}":$"{ms/60000}:{ms/1000%60:00}";
    public string Message=>Phase=="saving"&&TotalMs is int total?$"現在の音声：{Clock(total)}の解析データを保存しています…"
        :(TotalMs is int known?$"現在の音声：{Clock(PreparedMs)} / {Clock(known)}（未保存）\n":$"現在の音声：{Clock(PreparedMs)}まで解析済み（総尺確認中・未保存）\n")+
            (Phase=="encoding"?"内容を解析しています…":"音声の読み取りを続けています…");
    internal static AudioItemProgress Parse(JsonElement row)
    {
        if(row.ValueKind!=JsonValueKind.Object)throw new InvalidDataException("Invalid audio item progress");
        int Count(string name,int maximum)=>row.TryGetProperty(name,out var count)&&count.ValueKind==JsonValueKind.Number
            &&count.TryGetInt32(out var value)&&value>=0&&value<=maximum?value:throw new InvalidDataException("Invalid audio item count");
        var id=Count("item_id",int.MaxValue);var prepared=Count("prepared_ms",86400000);var windows=Count("prepared_windows",2880);
        if(!row.TryGetProperty("total_ms",out var duration))throw new InvalidDataException("Missing audio duration");
        int? total=duration.ValueKind==JsonValueKind.Null?null:Count("total_ms",86400000);
        var phase=row.TryGetProperty("phase",out var named)&&named.ValueKind==JsonValueKind.String?named.GetString():null;
        if(id<1||phase is not ("decoding" or "encoding" or "saving")||windows!=(prepared+29999)/30000
            ||total is int known&&(known<1||prepared>known)
            ||phase=="saving"&&(total is null||prepared!=total))throw new InvalidDataException("Invalid audio item progress");
        return new(id,prepared,total,windows,phase);
    }
}

public sealed record AudioContentStatus(bool Supported,bool Available,string State,int CandidateTotal,int Target,
    int Processed,int Indexed,int Reused,int Unavailable,int RemainingCandidates,bool Resident,string? ErrorCode)
{
    public AudioItemProgress? ItemProgress {get;init;}
    public string SourceKind {get;init;}="audio";
    public bool Busy=>State is "planning" or "waiting" or "running" or "cancelling";
    public string Message=>!Supported?"現在のAIモデルは音声の内容検索に対応していません。"
        :!Available?"AI環境を準備すると、音声の内容から検索できます。"
        :State switch
        {
            "planning"=>"音声の準備状況を確認しています…",
            "waiting"=>"ほかのAI処理が終わるのを待っています…",
            "running"=>$"{(SourceKind=="video"?"動画内の音声":"音声")}を準備しています（{Processed:N0} / {Target:N0}件）"+(ItemProgress is {} item?"\n"+item.Message:""),
            "cancelling"=>"現在の処理を安全に中断しています…",
            "cancelled"=>$"中断しました。準備済みの{Indexed:N0}件は保持されています。",
            "failed"=>ErrorCode=="scope_changed"?"検索対象が変更されました。もう一度作成してください。":"音声を準備できませんでした。AI環境とファイルの状態を確認してください。",
            "completed"=>$"準備完了：{Indexed:N0}件。準備済み{Reused:N0}件は再利用しました。"+
                (Unavailable>0?$" 読み取れない候補{Unavailable:N0}件。":"")+
                (RemainingCandidates>0?$" 残りの候補{RemainingCandidates:N0}件は、もう一度作成すると続きへ進みます。":""),
            _=>"先に音声の索引を作成すると、録音や曲の内容・特徴を文章で探せます。"
        };
    public static AudioContentStatus Parse(string json)
    {
        using var document=JsonDocument.Parse(json);var row=document.RootElement;
        bool Flag(string name)=>row.TryGetProperty(name,out var flag)&&flag.ValueKind is JsonValueKind.True or JsonValueKind.False
            ?flag.GetBoolean():throw new InvalidDataException("Invalid audio flag");
        int Count(string name)=>row.TryGetProperty(name,out var count)&&count.ValueKind==JsonValueKind.Number&&count.TryGetInt32(out var value)&&value>=0?value:throw new InvalidDataException("Invalid audio count");
        var state=row.TryGetProperty("state",out var named)&&named.ValueKind==JsonValueKind.String?named.GetString():null;
        if(state is not ("idle" or "planning" or "waiting" or "running" or "cancelling" or "cancelled" or "completed" or "failed"))
            throw new InvalidDataException("Invalid audio state");
        var target=Count("target");var processed=Count("processed");var indexed=Count("indexed");
        if(target>1000||processed>target||indexed>processed)throw new InvalidDataException("Invalid audio progress");
        var progress=row.TryGetProperty("item_progress",out var current)&&current.ValueKind!=JsonValueKind.Null?AudioItemProgress.Parse(current):null;
        if(progress is not null&&(state is not ("running" or "cancelling")||processed>=target))throw new InvalidDataException("Invalid current audio state");
        var sourceKind=row.TryGetProperty("source_kind",out var source)&&source.ValueKind==JsonValueKind.String?source.GetString():row.TryGetProperty("source_kind",out _)?null:"audio";
        if(sourceKind is not ("audio" or "video"))throw new InvalidDataException("Invalid audio source kind");
        return new(Flag("supported"),Flag("available"),state,Count("candidate_total"),target,processed,indexed,
            Count("reused"),Count("unavailable"),Count("remaining_candidates"),Flag("resident"),
            row.TryGetProperty("error_code",out var error)&&error.ValueKind==JsonValueKind.String?error.GetString():null){ItemProgress=progress,SourceKind=sourceKind};
    }
}

public sealed class AudioContentClient(HttpClient client)
{
    public async Task<AudioContentStatus> StatusAsync(CancellationToken token=default)
    {
        using var response=await client.GetAsync("api/library/audio-ai/status",token);
        return AudioContentStatus.Parse(await ReadAsync(response,token));
    }
    public Task<AudioContentStatus> StartAsync(JsonObject conditions,CancellationToken token=default)=>
        PostAsync("start",new(){["consent"]=true,["conditions"]=conditions.DeepClone(),["limit"]=128},token);
    public Task<AudioContentStatus> CancelAsync(CancellationToken token=default)=>PostAsync("cancel",new(),token);
    private async Task<AudioContentStatus> PostAsync(string operation,JsonObject body,CancellationToken token)
    {
        using var content=new StringContent(body.ToJsonString(),Encoding.UTF8,"application/json");
        using var response=await client.PostAsync("api/library/audio-ai/"+operation,content,token);
        return AudioContentStatus.Parse(await ReadAsync(response,token));
    }
    private static async Task<string> ReadAsync(HttpResponseMessage response,CancellationToken token)
    {
        var text=await response.Content.ReadAsStringAsync(token);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return text;
    }
}
