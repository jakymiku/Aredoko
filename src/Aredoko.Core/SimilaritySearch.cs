using System.Text.Json.Nodes;
using System.Text.Json;
namespace Aredoko.Core;

public static class SimilaritySearch
{
    public const string AudioIndexingGuidance="内容から探すには、設定 → AI検索の準備 → 音声の内容検索で索引を作成し、検索方法の「音声の内容（AI）」を選んでください。ファイル名・タグ検索と再生はそのまま利用できます。";
    public const int MaxResponseBytes=2*1024*1024;
    public static bool CanStart(MediaRow row) => row.Id > 0 && row.Availability == "present" && row.Kind is "image" or "book" or "archive" or "video" or "audio";
    public static JsonObject Request(int itemId,string kind,string view,int page,JsonObject scope,int? rootId=null) =>
        RequestMulti(itemId,kind,view,page,scope,rootId is int id ? new[]{id} : null);
    public static JsonObject RequestMulti(int itemId,string kind,string view,int page,JsonObject scope,IReadOnlyList<int>? rootIds)
    {
        if(itemId<=0 || page<0)throw new ArgumentOutOfRangeException(nameof(itemId));
        return new JsonObject {{"item_id",itemId},{"kind",kind},{"view",view},{"page",page},
            {"scope",FolderSearch.RestrictAIMulti(scope,rootIds)}};
    }
    public static string Guidance(string status, string originKind = "",bool directAudio=false) => directAudio
        ? status=="ready"?"音声の内容・特徴が似た候補です。起点自身は除外しています。一致時刻から再生できます。類似度は正解率ではありません。"
            :"この音声の内容索引がないか古くなっています。"+AudioIndexingGuidance
        :status switch
    {
        "unindexed" => originKind == "video"
            ? "この動画の索引がないか古くなっています。「AI索引」で対象を確認して索引を作成してください。名前・タグ検索も利用できます。"
            : originKind == "audio"
            ? "この音声・曲の類似検索に使える音響特徴がないか古くなっています。文章から探すための索引とは別です。" + AudioIndexingGuidance
            : "この画像・表紙の索引がないか古くなっています。「AI索引」で対象を確認して索引を作成してください。名前・タグ検索も利用できます。",
        "unsupported_profile" => originKind == "video"
            ? "選択中のモデルは動画の類似検索に対応していません。「AI索引」で画像・動画対応モデルを選ぶか、名前・タグ検索を利用してください。"
            : originKind == "audio"
            ? "この音声・曲の類似検索を利用できません。" + AudioIndexingGuidance
            : "選択中のモデルは画像・表紙の類似検索に対応していません。「AI索引」で画像対応モデルを選ぶか、名前・タグ検索を利用してください。",
        "ready" => originKind == "video"
            ? "動画の内容・シーンが似た候補です。起点自身は除外しています。類似度は正解率ではありません。"
            : originKind == "audio"
            ? "音声・音楽の音響特徴が似た候補です。起点自身は除外しています。類似度は正解率ではありません。"
            : "画像・表紙の特徴が似た候補です。起点自身は除外しています。類似度は正解率ではありません。",
        _ => "類似検索を利用できません。元の検索に戻るか、AI索引の設定を確認してください。"
    };

    public static SearchResponse Parse(string text,int expectedId,int expectedPage,int expectedLimit=60,int? expectedOffset=null,bool directAudio=false)
    {
        if(expectedLimit is <1 or >120 || expectedOffset is <0)throw new ArgumentOutOfRangeException(nameof(expectedLimit));
        try
        {
            using var doc=JsonDocument.Parse(text);var root=doc.RootElement;
            var status=root.GetProperty("similarity_status").GetString();
            var revision=root.GetProperty("origin_revision").GetString();
            var profile=root.GetProperty("profile").GetString();
            var source=root.GetProperty("source").GetString();
            var originKind=root.TryGetProperty("origin_kind",out var okProp)?okProp.GetString():null;
            if(root.GetProperty("origin_id").GetInt32()!=expectedId||root.GetProperty("page").GetInt32()!=expectedPage||
               root.GetProperty("mode").GetString()!=(directAudio?"audio-similar":"similar")||
               (directAudio?source!="audio-direct":source is not ("cover" or "acoustic"))||
               root.GetProperty("score_kind").GetString()!="cosine"||root.GetProperty("limit").GetInt32()!=expectedLimit||
               status is not ("ready" or "unindexed" or "unsupported_profile")||
               revision is null||revision.Length!=64||revision.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))||
               string.IsNullOrWhiteSpace(profile)||profile.Length>256||
               (source == "cover" && originKind is not (null or "image" or "book" or "archive" or "video"))||
               (source is "acoustic" or "audio-direct" && originKind != "audio"))
                throw new InvalidDataException("類似検索の応答が要求と一致しません。検索をやり直してください。");
            var result=Protocol.ParseSearch(text);
            if(result.Total<0||(!result.SearchComplete&&result.Total>10000)||result.Items.Count>expectedLimit||result.Items.Count>result.Total||
               (result.SearchComplete&&result.Total!=result.IndexedTotal)||
               (status!="ready"&&(result.Total!=0||result.Items.Count!=0))||
               result.Items.Count!=Math.Min(expectedLimit,Math.Max(0,result.Total-(expectedOffset is int offset ? offset : (long)expectedPage*expectedLimit)))||
               result.Items.Select(row=>row.Id).Distinct().Count()!=result.Items.Count||
               result.Items.Any(row=>row.Id<1||row.Id==expectedId||row.SimilarityOriginId!=expectedId||
                   (source == "cover" ? row.Kind is not ("image" or "book" or "archive" or "video") : row.Kind != "audio")||
                   (directAudio&&(row.AudioMatchSource!="direct-audio"||row.AudioMatchMs is not >=0||row.OriginMatchMs is not >=0))||
                   row.SemanticScore is not double score||score < -1.000001||score > 1.000001))
                throw new InvalidDataException("類似候補の内容が無効です。検索をやり直してください。");
            return result;
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            throw new InvalidDataException("類似検索の応答を読み取れません。検索をやり直してください。",ex);
        }
    }
}
