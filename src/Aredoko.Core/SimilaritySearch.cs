using System.Text.Json.Nodes;
using System.Text.Json;
namespace Aredoko.Core;

public static class SimilaritySearch
{
    public static string AudioIndexingGuidance=>AppText.L(
        "内容から探すには、設定 → AI検索の準備 → 音声の内容検索で索引を作成し、検索方法の「音声の内容（AI）」を選んでください。ファイル名・タグ検索と再生はそのまま利用できます。",
        "To search inside audio, open Settings → Prepare AI Search → Audio content search, build the index, and choose \"Audio content (AI)\". Filename/tag search and playback remain available.");
    public static string VideoIndexingGuidance=>AppText.L(
        "内容から探すには、設定 → AI検索の準備 → 動画の内容検索で索引を作成してください。ファイル名・タグ検索や代表フレームによる検索も利用できます。",
        "To search inside videos, open Settings → Prepare AI Search → Video content search and build the index. Filename/tag search and keyframe search remain available.");
    public static string VideoAudioIndexingGuidance=>AppText.L(
        "音で似た動画を探すには、設定 → AI検索の準備 → 動画内の音声で索引を作成してください。先頭の音声トラックが対象です。",
        "To find similar videos by sound, open Settings → Prepare AI Search → Video audio and build the index (uses the first audio track).");
    public const int MaxResponseBytes=2*1024*1024;
    public static bool CanStart(MediaRow row) => row.Id > 0 && row.Availability == "present" && row.Kind is "image" or "book" or "archive" or "video" or "audio";
    public static JsonObject Request(int itemId,string kind,string view,int page,JsonObject scope,int? rootId=null,int? originPage=null,int? originMs=null) =>
        RequestMulti(itemId,kind,view,page,scope,rootId is int id ? new[]{id} : null,originPage,originMs);
    public static JsonObject RequestMulti(int itemId,string kind,string view,int page,JsonObject scope,IReadOnlyList<int>? rootIds,int? originPage=null,int? originMs=null)
    {
        if(itemId<=0 || page<0)throw new ArgumentOutOfRangeException(nameof(itemId));
        if(originPage is not null && originMs is not null)throw new ArgumentException("originPage and originMs cannot both be set.");
        if(originPage is < 0 or >= 10000)throw new ArgumentOutOfRangeException(nameof(originPage));
        if(originMs is < 0 or > 86_400_000)throw new ArgumentOutOfRangeException(nameof(originMs));
        var req=new JsonObject {{"item_id",itemId},{"kind",kind},{"view",view},{"page",page},
            {"scope",FolderSearch.RestrictAIMulti(scope,rootIds)}};
        if(originPage is int p)req["origin_page"]=p;
        if(originMs is int ms)req["origin_ms"]=ms;
        return req;
    }
    public static string Guidance(string status, string originKind = "",bool directAudio=false,bool directVideo=false,bool directVideoAudio=false) => directVideoAudio
        ? status=="ready"?AppText.L("動画内の音声・音の特徴が似た候補です。起点自身は除外しています。一致区間から動画を再生できます。類似度は正解率ではありません。", "Matches with similar spoken audio or sound in video (excluding the source item). You can play from the matched interval. Scores are similarity, not accuracy.")
            :AppText.L("この動画の音声索引がないか古くなっています。", "This video's audio index is missing or outdated. ")+VideoAudioIndexingGuidance
        :directVideo
        ? status=="ready"?AppText.L("動画の内容が似た候補です。起点自身は除外しています。一致区間から再生できます。類似度は正解率ではありません。", "Matches with similar video content (excluding the source item). You can play from the matched interval. Scores are similarity, not accuracy.")
            :AppText.L("この動画の内容索引がないか古くなっています。", "This video's content index is missing or outdated. ")+VideoIndexingGuidance
        :directAudio
        ? status=="ready"?AppText.L("音声の内容・特徴が似た候補です。起点自身は除外しています。一致時刻から再生できます。類似度は正解率ではありません。", "Matches with similar audio content (excluding the source item). You can play from the matched time. Scores are similarity, not accuracy.")
            :AppText.L("この音声の内容索引がないか古くなっています。", "This audio's content index is missing or outdated. ")+AudioIndexingGuidance
        :status switch
    {
        "unindexed" => originKind == "video"
            ? AppText.L("この動画の索引がないか古くなっています。「AI索引」で対象を確認して索引を作成してください。名前・タグ検索も利用できます。", "This video's index is missing or outdated. Check AI Indexing settings to build it, or use Name/Tag search.")
            : originKind == "audio"
            ? AppText.L("この音声・曲の類似検索に使える音響特徴がないか古くなっています。文章から探すための索引とは別です。", "Acoustic features for audio similarity are missing or outdated (separate from text-to-audio search). ") + AudioIndexingGuidance
            : AppText.L("この画像・表紙の索引がないか古くなっています。「AI索引」で対象を確認して索引を作成してください。名前・タグ検索も利用できます。", "This image/cover index is missing or outdated. Check AI Indexing settings to build it, or use Name/Tag search."),
        "unsupported_profile" => originKind == "video"
            ? AppText.L("選択中のモデルは動画の類似検索に対応していません。「AI索引」で画像・動画対応モデルを選ぶか、名前・タグ検索を利用してください。", "The selected model does not support video similarity. Choose an image/video model in AI Indexing, or use Name/Tag search.")
            : originKind == "audio"
            ? AppText.L("この音声・曲の類似検索を利用できません。", "Similarity search is unavailable for this audio file. ") + AudioIndexingGuidance
            : AppText.L("選択中のモデルは画像・表紙の類似検索に対応していません。「AI索引」で画像対応モデルを選ぶか、名前・タグ検索を利用してください。", "The selected model does not support image/cover similarity. Choose an image model in AI Indexing, or use Name/Tag search."),
        "ready" => originKind == "video"
            ? AppText.L("動画の内容・シーンが似た候補です。起点自身は除外しています。類似度は正解率ではありません。", "Items with similar video scenes (excluding the source item). Scores are similarity, not accuracy.")
            : originKind == "audio"
            ? AppText.L("音声・音楽の音響特徴が似た候補です。起点自身は除外しています。類似度は正解率ではありません。", "Items with similar audio/music characteristics (excluding the source item). Scores are similarity, not accuracy.")
            : AppText.L("画像・表紙の特徴が似た候補です。起点自身は除外しています。類似度は正解率ではありません。", "Items with similar image/cover features (excluding the source item). Scores are similarity, not accuracy."),
        _ => AppText.L("類似検索を利用できません。元の検索に戻るか、AI索引の設定を確認してください。", "Similarity search is unavailable. Return to search or check AI Indexing settings.")
    };

    public static SearchResponse Parse(string text,int expectedId,int expectedPage,int expectedLimit=60,int? expectedOffset=null,bool directAudio=false,bool directVideo=false,bool directVideoAudio=false)
    {
        if((directAudio?1:0)+(directVideo?1:0)+(directVideoAudio?1:0)>1)throw new ArgumentException("Select one direct similarity mode");
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
               root.GetProperty("mode").GetString()!=(directVideoAudio?"video-audio-similar":directVideo?"video-similar":directAudio?"audio-similar":"similar")||
               (directVideoAudio?source!="video-audio-direct":directVideo?source!="video-direct":directAudio?source!="audio-direct":source is not ("cover" or "acoustic"))||
               root.GetProperty("score_kind").GetString()!="cosine"||root.GetProperty("limit").GetInt32()!=expectedLimit||
               status is not ("ready" or "unindexed" or "unsupported_profile")||
               revision is null||revision.Length!=64||revision.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))||
               string.IsNullOrWhiteSpace(profile)||profile.Length>256||
               (source == "cover" && originKind is not (null or "image" or "book" or "archive" or "video"))||
               ((source is "video-direct" or "video-audio-direct") && originKind != "video")||
               (source is "acoustic" or "audio-direct" && originKind != "audio"))
                throw new InvalidDataException(AppText.L("類似検索の応答が要求と一致しません。検索をやり直してください。", "Similarity search response does not match request. Please search again."));
            var result=Protocol.ParseSearch(text);
            if(result.Total<0||(!result.SearchComplete&&result.Total>10000)||result.Items.Count>expectedLimit||result.Items.Count>result.Total||
               (result.SearchComplete&&result.Total!=result.IndexedTotal)||
               (status!="ready"&&(result.Total!=0||result.Items.Count!=0))||
               result.Items.Count!=Math.Min(expectedLimit,Math.Max(0,result.Total-(expectedOffset is int offset ? offset : (long)expectedPage*expectedLimit)))||
               result.Items.Select(row=>row.Id).Distinct().Count()!=result.Items.Count||
               result.Items.Any(row=>row.Id<1||row.Id==expectedId||row.SimilarityOriginId!=expectedId||
                   (source == "cover" ? row.Kind is not ("image" or "book" or "archive" or "video") : (source is "video-direct" or "video-audio-direct") ? row.Kind != "video" : row.Kind != "audio")||
                   (directAudio&&(row.AudioMatchSource!="direct-audio"||row.AudioMatchMs is not >=0||row.OriginMatchMs is not >=0))||
                   (directVideo&&(row.VideoMatchSource!="direct-video"||row.VideoMatchContract!="direct-video-window:v1"||row.VideoMatchEndMs is null||row.OriginMatchEndMs is null))||
                   (directVideoAudio&&(row.AudioMatchSource!="video-audio"||row.AudioMatchContract!="direct-audio-window:v1"||row.AudioMatchEndMs is null||row.OriginMatchEndMs is null))||
                   row.SemanticScore is not double score||score < -1.000001||score > 1.000001))
                throw new InvalidDataException(AppText.L("類似候補の内容が無効です。検索をやり直してください。", "Invalid similarity match payload. Please search again."));
            return result;
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {
            throw new InvalidDataException(AppText.L("類似検索の応答を読み取れません。検索をやり直してください。", "Unable to read similarity search response. Please search again."),ex);
        }
    }
}
