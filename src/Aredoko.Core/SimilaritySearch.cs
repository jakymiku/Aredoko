using System.Text.Json.Nodes;
namespace Aredoko.Core;

public static class SimilaritySearch
{
    public static bool CanStart(MediaRow row) => row.Id > 0 && row.Availability == "present" && row.Kind is "image" or "book" or "archive";
    public static JsonObject Request(int itemId,string kind,string view,int page,JsonObject scope,int? rootId=null)
    {
        if(itemId<=0 || page<0)throw new ArgumentOutOfRangeException(nameof(itemId));
        return new JsonObject {{"item_id",itemId},{"kind",kind},{"view",view},{"page",page},
            {"scope",FolderSearch.RestrictAI(scope,rootId)}};
    }
    public static string Guidance(string status) => status switch
    {
        "unindexed" => "この画像・表紙の索引がないか古くなっています。「AI索引」で対象を確認して索引を作成してください。名前・タグ検索も利用できます。",
        "unsupported_profile" => "選択中のモデルは画像・表紙の類似検索に対応していません。「AI索引」で画像対応モデルを選ぶか、名前・タグ検索を利用してください。",
        "ready" => "画像・表紙の特徴が似た候補です。起点自身は除外しています。類似度は正解率ではありません。",
        _ => "類似検索を利用できません。元の検索に戻るか、AI索引の設定を確認してください。"
    };
}
