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
public sealed record AISetupRequirement(string Id,bool FilesPresent,string Action,IReadOnlyList<string> CatalogIds,string State="unknown");
public sealed record AISetupPlan(bool SkipAI,long KnownBytes,long? TotalBytes,bool RestartRequired,
    IReadOnlyList<string> Unsupported,IReadOnlyList<AISetupRequirement> Requirements,
    bool ProfileRestartRequired=false,bool ProfileOverride=false,bool ProfileSelectionInvalid=false,
    bool AutomaticSetupSupported=false)
{
    public string Summary
    {
        get
        {
            if(SkipAI)return AppText.L("AIは使わず、ファイル名・タグ検索と閲覧から始められます。後から設定で追加できます。","You can start with filename/tag search and browsing without AI, and enable AI later in Settings.");
            var lines=new List<string>();
            if(ProfileSelectionInvalid)lines.Add(AppText.L("⚠ 保存したモデル選択を確認できません。「AI検索を設定へ」で設定を確認してください。","⚠ Could not verify saved model selection. Check settings in Configure AI."));
            if(ProfileRestartRequired)lines.Add(AppText.L("⚠ モデルの変更待ちです。以下は起動中のモデルの確認結果です。新しいモデルの準備は再起動後に確認してください。","⚠ Model change pending restart. Status below reflects the currently loaded model."));
            if(ProfileOverride)lines.Add(AppText.L("⚠ 起動引数のモデル指定が優先されています。保存したモデルへ切り替えるには、その指定を外して起動し直してください。","⚠ Startup -AIProfile argument overrides saved model selection."));
            if(Unsupported.Count>0)lines.Add(AppText.L("⚠ 選んだ機能の一部は現在のモデルに対応していません。設定画面で対応モデルを選択してください。","⚠ Some selected features are unsupported by the active model. Choose a compatible model in Settings."));
            foreach(var requirement in Requirements)
            {
                var label=requirement.Id=="embedding-runtime"?AppText.L("実行環境","AI Runtime"):AppText.L("検索用モデル","Search Model");
                var suffix=requirement.CatalogIds.Count>0
                    ?AppText.L("（個別ダウンロード可）"," (individual download available)")
                    :AutomaticSetupSupported
                        ?AppText.L("（自動セットアップを使えます／用意したフォルダを指定することもできます）"," (Auto-Setup supported, or choose an existing folder)")
                        :AppText.L("（用意したフォルダを指定してください）"," (select an existing folder)");
                lines.Add(requirement.FilesPresent
                    ?AppText.L($"✓ {label}：ファイルの配置を確認済み（推論の動作確認とは別）",$"✓ {label}: Files verified (inference not yet tested)")
                    :$"⚠ {label}{AppText.L("："," — ")}{AISetupRecovery.Reason(requirement.State)}{suffix}");
            }
            if(KnownBytes>0)lines.Add(AppText.L($"個別ダウンロードの目安：{KnownBytes/1_000_000_000d:N2} GB",$"Estimated download size: {KnownBytes/1_000_000_000d:N2} GB")+(TotalBytes is null?AppText.L("（ほかに必要なファイルあり）"," (additional files required)"):""));
            if(RestartRequired)lines.Add(AppText.L("⚠ 保存済みの環境変更は再起動後に反映されます。","⚠ Saved AI environment changes require restarting Aredoko."));
            lines.Add(AppText.L("※ この確認だけではダウンロードやAI検索データの作成は行われません（取得やAI処理を開始しません）。","Note: Checking requirements never starts downloads or builds AI indexes automatically."));
            return string.Join("\n",lines);
        }
    }
    public static AISetupPlan Parse(string json,IReadOnlyList<string> requested)
    {
        using var document=JsonDocument.Parse(json);var root=document.RootElement;
        if(root.GetProperty("version").GetInt32()!=1||!root.GetProperty("basic_available").GetBoolean()||!root.GetProperty("ai_optional").GetBoolean()
            ||root.GetProperty("acquisition_started").GetBoolean()||root.GetProperty("settings_saved").GetBoolean()
            ||root.GetProperty("hardware_checked_by_plan").GetBoolean()||root.GetProperty("inference_checked_by_plan").GetBoolean())
            throw new InvalidDataException(AppText.L("AI準備の確認応答が無効です。","Invalid AI setup plan response."));
        var features=root.GetProperty("features").EnumerateArray().Select(row=>row.GetProperty("id").GetString()??"").ToArray();
        if(features.Length>4||features.Distinct().Count()!=features.Length||!features.Order().SequenceEqual(requested.Order()))throw new InvalidDataException(AppText.L("AI準備の用途が要求と一致しません。","AI setup features do not match request."));
        var requirements=new List<AISetupRequirement>();
        foreach(var row in root.GetProperty("requirements").EnumerateArray())
        {
            var id=row.GetProperty("id").GetString()??"";var action=row.GetProperty("action").GetString()??"";
            if(id is not ("embedding-runtime" or "embedding-model")||requirements.Any(r=>r.Id==id)
                ||action is not ("none" or "review_download" or "choose_download" or "select_existing_environment" or "select_existing_model"))throw new InvalidDataException(AppText.L("AI準備の依存関係が無効です。","Invalid AI setup requirement."));
            var catalogs=row.GetProperty("download_candidates").EnumerateArray().Select(value=>value.GetProperty("catalog_id").GetString()??"").ToArray();
            if(catalogs.Length>256||catalogs.Distinct().Count()!=catalogs.Length||catalogs.Any(id=>id.Length!=64||id.Any(c=>!char.IsAsciiHexDigitLower(c))))throw new InvalidDataException(AppText.L("取得候補が無効です。","Invalid download candidate."));
            var state=row.TryGetProperty("state",out var stateValue)?stateValue.GetString()??"unknown":"unknown";
            if(state.Length>80||state.Any(c=>c is not (>= 'a' and <= 'z') and not (>= '0' and <= '9') and not '_'))throw new InvalidDataException(AppText.L("AI準備の検査状態が無効です。","Invalid AI setup inspection state."));
            requirements.Add(new(id,row.GetProperty("files_present").GetBoolean(),action,catalogs,state));
        }
        var known=root.GetProperty("known_download_bytes").GetInt64();var totalValue=root.GetProperty("total_download_bytes");long? total=totalValue.ValueKind==JsonValueKind.Null?null:totalValue.GetInt64();
        var skip=root.GetProperty("skip_ai").GetBoolean();var unsupported=root.GetProperty("unresolved_features").EnumerateArray().Select(row=>row.GetString()??"").ToArray();
        if(known<0||total is <0||total is long bytes&&bytes<known||skip!=(requested.Count==0)||skip&&(known!=0||requirements.Count!=0)
            ||unsupported.Distinct().Count()!=unsupported.Length||unsupported.Any(id=>!requested.Contains(id)))throw new InvalidDataException(AppText.L("AI準備の状態が無効です。","Invalid AI setup state."));
        static bool Flag(JsonElement root,string name)=>root.TryGetProperty(name,out var value)&&value.GetBoolean();
        var profileRestart=Flag(root,"profile_restart_required");var restart=root.GetProperty("restart_required").GetBoolean();
        if(profileRestart&&!restart)throw new InvalidDataException(AppText.L("モデル変更の再起動状態が無効です。","Invalid model restart state."));
        return new(skip,known,total,restart,unsupported,requirements.AsReadOnly(),profileRestart,Flag(root,"profile_override"),Flag(root,"profile_selection_invalid"),Flag(root,"automatic_setup_supported"));
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
