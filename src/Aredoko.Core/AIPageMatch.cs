using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record AIPageMatch(string SourceRevision,string SourceState,string PageId,int Page,
    string Model,string ModelRevision,string Profile,string Preprocessing,double Score)
{
    public int? InitialReaderPage(ArchiveManifest manifest) =>
        SourceState=="current" && SourceRevision==manifest.Revision && Page>=0 && Page<manifest.PageCount ? Page : null;
    public string Summary => AppText.L($"内部ページの意味一致（{Page+1}ページ） · 類似度 {Score:F3}\nモデル: {Model} · 元ファイル一致", $"Matched inner page (p.{Page+1}) · Similarity {Score:F3}\nModel: {Model} · File verified");
    public static AIPageMatch? Read(JsonElement row)
    {
        if(!row.TryGetProperty("ai_page_match",out var value))return null;
        try
        {
            var revision=TagReviewProtocol.Text(value,"source_revision",64);
            var state=TagReviewProtocol.Text(value,"source_state",16);
            var pid=TagReviewProtocol.Text(value,"page_id",64);
            var page=value.GetProperty("page").GetInt32();
            var model=TagReviewProtocol.Text(value,"model",128);
            var modelRevision=TagReviewProtocol.Text(value,"model_revision",64);
            var profile=TagReviewProtocol.Text(value,"profile",256);
            var contract=TagReviewProtocol.Text(value,"preprocessing",64);
            var score=value.GetProperty("semantic_score").GetDouble();
            if(!TagReviewProtocol.IsRevision(revision)||!TagReviewProtocol.IsRevision(pid)||state!="current"||page is <0 or >=10000
                ||modelRevision.Length is not (40 or 64)||modelRevision.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))
                ||profile.Length==0||contract!="book-page-image:v1"||!double.IsFinite(score)||score is < -1.000001 or >1.000001)
                throw new InvalidDataException(AppText.L("内部ページの一致情報が無効です。","Invalid inner-page match data."));
            return new(revision,state,pid,page,model,modelRevision,profile,contract,score);
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException(AppText.L("内部ページの一致情報を読み取れません。","Unable to read inner-page match data."),ex);}
    }
}

public static class PageImageRequests
{
    public const int MaxPages=16;
    public static JsonObject Create(int itemId,IReadOnlyList<string> pageIds,string revision,JsonObject scope)
    {
        PageEvidenceProtocol.ValidateId(itemId);PageEvidenceProtocol.ValidateToken(revision,nameof(revision));
        if(pageIds.Count is <1 or >MaxPages||pageIds.Distinct().Count()!=pageIds.Count)throw new ArgumentException(AppText.L("1〜16ページを選択してください。","Select between 1 and 16 pages."));
        foreach(var id in pageIds)PageEvidenceProtocol.ValidateToken(id,nameof(pageIds));
        return new(){{"item_id",itemId},{"page_ids",new JsonArray(pageIds.Select(id=>(JsonNode?)JsonValue.Create(id)).ToArray())},
            {"revision",revision},{"scope",scope.DeepClone()}};
    }
}
