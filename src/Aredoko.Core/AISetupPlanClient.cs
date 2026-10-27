using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public static class AISetupSelection
{
    public static IReadOnlyList<string> Features {get;}=Array.AsReadOnly(new[]{"semantic","image_similarity","video","audio"});
    public static int Normalize(int mask)=>mask is >=0 and <=15?mask:3;
    public static string[] FromMask(int mask)=>Features.Where((_,index)=>(Normalize(mask)&(1<<index))!=0).ToArray();
}
public sealed record AISetupRequirement(string Id,bool FilesPresent,string Action,IReadOnlyList<string> CatalogIds);
public sealed record AISetupPlan(bool SkipAI,long KnownBytes,long? TotalBytes,bool RestartRequired,
    IReadOnlyList<string> Unsupported,IReadOnlyList<AISetupRequirement> Requirements)
{
    public string Summary
    {
        get
        {
            if(SkipAI)return "AIは使わず、ファイル名・タグ検索と閲覧から始められます。後から設定で追加できます。";
            var lines=new List<string>();
            if(Unsupported.Count>0)lines.Add("選んだ機能の一部は現在のモデルに対応していません。準備画面で対応モデルを選択してください。");
            foreach(var requirement in Requirements)
            {
                var label=requirement.Id=="embedding-runtime"?"実行環境":"検索用モデル";
                lines.Add(requirement.FilesPresent?$"{label}：配置を確認できました。":requirement.CatalogIds.Count>0?$"{label}：ダウンロード候補があります。":$"{label}：自動取得は準備中です。配置済みの環境・モデルを指定できます。");
            }
            if(KnownBytes>0)lines.Add($"取得候補の容量：{KnownBytes/(1024d*1024*1024):N2} GB"+(TotalBytes is null?"（未確定の実行環境等は別途必要）":""));
            if(RestartRequired)lines.Add("保存済みの環境変更は再起動後に反映されます。");
            lines.Add("この確認では取得やAI処理を開始しません。配置の確認後、索引の作成が必要です。");
            return string.Join("\n",lines);
        }
    }
    public static AISetupPlan Parse(string json,IReadOnlyList<string> requested)
    {
        using var document=JsonDocument.Parse(json);var root=document.RootElement;
        if(root.GetProperty("version").GetInt32()!=1||!root.GetProperty("basic_available").GetBoolean()||!root.GetProperty("ai_optional").GetBoolean()
            ||root.GetProperty("acquisition_started").GetBoolean()||root.GetProperty("settings_saved").GetBoolean()
            ||root.GetProperty("hardware_checked_by_plan").GetBoolean()||root.GetProperty("inference_checked_by_plan").GetBoolean())
            throw new InvalidDataException("AI準備の確認応答が無効です。");
        var features=root.GetProperty("features").EnumerateArray().Select(row=>row.GetProperty("id").GetString()??"").ToArray();
        if(features.Length>4||features.Distinct().Count()!=features.Length||!features.Order().SequenceEqual(requested.Order()))throw new InvalidDataException("AI準備の用途が要求と一致しません。");
        var requirements=new List<AISetupRequirement>();
        foreach(var row in root.GetProperty("requirements").EnumerateArray())
        {
            var id=row.GetProperty("id").GetString()??"";var action=row.GetProperty("action").GetString()??"";
            if(id is not ("embedding-runtime" or "embedding-model")||requirements.Any(r=>r.Id==id)
                ||action is not ("none" or "review_download" or "choose_download" or "select_existing_environment" or "select_existing_model"))throw new InvalidDataException("AI準備の依存関係が無効です。");
            var catalogs=row.GetProperty("download_candidates").EnumerateArray().Select(value=>value.GetProperty("catalog_id").GetString()??"").ToArray();
            if(catalogs.Length>256||catalogs.Distinct().Count()!=catalogs.Length||catalogs.Any(id=>id.Length!=64||id.Any(c=>!char.IsAsciiHexDigitLower(c))))throw new InvalidDataException("取得候補が無効です。");
            requirements.Add(new(id,row.GetProperty("files_present").GetBoolean(),action,catalogs));
        }
        var known=root.GetProperty("known_download_bytes").GetInt64();var totalValue=root.GetProperty("total_download_bytes");long? total=totalValue.ValueKind==JsonValueKind.Null?null:totalValue.GetInt64();
        var skip=root.GetProperty("skip_ai").GetBoolean();var unsupported=root.GetProperty("unresolved_features").EnumerateArray().Select(row=>row.GetString()??"").ToArray();
        if(known<0||total is <0||total is long bytes&&bytes<known||skip!=(requested.Count==0)||skip&&(known!=0||requirements.Count!=0)
            ||unsupported.Distinct().Count()!=unsupported.Length||unsupported.Any(id=>!requested.Contains(id)))throw new InvalidDataException("AI準備の状態が無効です。");
        return new(skip,known,total,root.GetProperty("restart_required").GetBoolean(),unsupported,requirements.AsReadOnly());
    }
}
public sealed class AISetupPlanClient(HttpClient client)
{
    public async Task<AISetupPlan> CreateAsync(int selection,CancellationToken token=default)
    {
        var features=AISetupSelection.FromMask(selection);var values=new JsonArray();foreach(var id in features)values.Add((JsonNode?)JsonValue.Create(id));
        using var body=new StringContent(new JsonObject{["features"]=values}.ToJsonString(),Encoding.UTF8,"application/json");
        using var response=await client.PostAsync("api/library/ai/setup/plan",body,token);
        var text=await response.Content.ReadAsStringAsync(token);
        if(!response.IsSuccessStatusCode)throw new InvalidOperationException(ErrorText.FromResponse(text,(int)response.StatusCode));
        return AISetupPlan.Parse(text,features);
    }
}
