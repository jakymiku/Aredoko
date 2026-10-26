using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record AudioContentStatus(bool Supported,bool Available,string State,int CandidateTotal,int Target,
    int Processed,int Indexed,int Reused,int Unavailable,int RemainingCandidates,bool Resident,string? ErrorCode)
{
    public bool Busy=>State is "planning" or "waiting" or "running" or "cancelling";
    public string Message=>!Supported?"現在のAIモデルは音声の内容検索に対応していません。"
        :!Available?"AI環境を準備すると、音声の内容から検索できます。"
        :State switch
        {
            "planning"=>"音声の準備状況を確認しています…",
            "waiting"=>"ほかのAI処理が終わるのを待っています…",
            "running"=>$"音声を準備しています（{Processed:N0} / {Target:N0}件）",
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
        return new(Flag("supported"),Flag("available"),state,Count("candidate_total"),target,processed,indexed,
            Count("reused"),Count("unavailable"),Count("remaining_candidates"),Flag("resident"),
            row.TryGetProperty("error_code",out var error)&&error.ValueKind==JsonValueKind.String?error.GetString():null);
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
