using System.Text.Json;

namespace Aredoko.Core;

public sealed record PageImageRange(int Start,int Count)
{
    public int End => Start+Count;
    public string Label => Count==1?$"{Start+1}":$"{Start+1}–{End}";
}

public sealed record PageImageCoverage(int ItemId,string SourceRevision,string SourceState,string Profile,string Model,
    bool Supported,bool Available,int PageCount,int IndexedPages,int RemainingPages,
    IReadOnlyList<PageImageRange> IndexedRanges,PageImageRange? NextRange)
{
    public bool CanPrepare => Supported&&Available&&SourceState=="current";
    public string Summary => SourceState switch
    {
        "stale"=>"元ファイルが変わりました。閉じて開き直してください。",
        "unverified"=>"元ファイルを確認できません。少し待って開き直してください。",
        "unavailable"=>"元ファイルを利用できません。登録先を確認してください。",
        _=>!Supported?"選択中のモデルは画像検索に対応していません。":
            $"準備済み: {IndexedPages:N0} / {PageCount:N0}ページ（残り{RemainingPages:N0}）"+(!Available?"\nAI実行環境を確認してください。保存済みの索引は保持しています。":"")
    };
    public string RangeSummary => IndexedRanges.Count==0?"まだ準備されていません。":string.Join("、",IndexedRanges.Select(r=>r.Label))+"ページ";

    public static PageImageCoverage Parse(byte[] json,int expectedItemId,string expectedRevision,string? expectedProfile=null)
    {
        try
        {
            using var document=JsonDocument.Parse(json);var root=document.RootElement;
            var item=root.GetProperty("item_id").GetInt32();
            var revision=TagReviewProtocol.Text(root,"source_revision",64);
            var state=TagReviewProtocol.Text(root,"source_state",16);
            var profile=TagReviewProtocol.Text(root,"profile",256);
            var model=TagReviewProtocol.Text(root,"model",128);
            var supported=root.GetProperty("supported").GetBoolean();var available=root.GetProperty("available").GetBoolean();
            var total=root.GetProperty("page_count").GetInt32();var ready=root.GetProperty("indexed_pages").GetInt32();var remaining=root.GetProperty("remaining_pages").GetInt32();
            if(item!=expectedItemId||revision!=expectedRevision||!TagReviewProtocol.IsRevision(revision)||profile.Length==0||model.Length==0
                ||expectedProfile is not null&&profile!=expectedProfile||state is not ("current" or "stale" or "unverified" or "unavailable")
                ||total is <1 or >10000||ready<0||ready>total||remaining!=total-ready)
                throw new InvalidDataException("ページ索引の準備状況が無効です。開き直してください。");
            PageImageRange ReadRange(JsonElement value,int maximum)
            {
                var range=new PageImageRange(value.GetProperty("start").GetInt32(),value.GetProperty("count").GetInt32());
                if(range.Start<0||range.Start>=total||range.Count<1||range.Count>maximum||range.Count>total-range.Start)
                    throw new InvalidDataException("ページ索引の範囲が無効です。");
                return range;
            }
            var array=root.GetProperty("indexed_ranges");
            if(array.ValueKind!=JsonValueKind.Array||array.GetArrayLength()>5000)throw new InvalidDataException("ページ索引の範囲数が無効です。");
            var ranges=new List<PageImageRange>();var sum=0;
            foreach(var value in array.EnumerateArray())
            {
                var range=ReadRange(value,total);
                if(ranges.Count>0&&range.Start<=ranges[^1].End)throw new InvalidDataException("ページ索引の範囲が重複しています。");
                ranges.Add(range);sum+=range.Count;
            }
            var nextValue=root.GetProperty("next_range");
            var next=nextValue.ValueKind==JsonValueKind.Null?null:ReadRange(nextValue,PageImageRequests.MaxPages);
            var missing=0;
            foreach(var range in ranges){if(range.Start==missing)missing=range.End;else break;}
            PageImageRange? expectedNext=null;
            if(state=="current"&&supported&&remaining>0)
            {
                var stop=ranges.FirstOrDefault(r=>r.Start>missing)?.Start??total;
                expectedNext=new(missing,Math.Min(PageImageRequests.MaxPages,stop-missing));
            }
            if(sum!=ready||next!=expectedNext||((state!="current"||!supported)&&(ready!=0||ranges.Count!=0)))
                throw new InvalidDataException("ページ索引の件数または次の範囲が一致しません。");
            return new(item,revision,state,profile,model,supported,available,total,ready,remaining,ranges,next);
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException("ページ索引の準備状況を読み取れません。",ex);}
    }
}
