using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record BookPageSelection(int ItemId,string Revision,IReadOnlyList<string> PageIds);
public static class PageBatchRequests
{
    public const int MaxBooks=8,MaxTotal=128;
    public static JsonObject Create(IReadOnlyList<BookPageSelection> books,JsonObject scope,int pageLimit,string profile)
    {
        if(books.Count is <1 or >MaxBooks||books.Select(b=>b.ItemId).Distinct().Count()!=books.Count
            ||pageLimit is <1 or >MaxTotal||books.Sum(b=>b.PageIds.Count)>pageLimit)throw new ArgumentException(AppText.L("8冊・合計128ページまでを選択してください。", "Select up to 8 books and 128 pages total."));
        var items=new JsonArray();
        foreach(var book in books)
        {
            var item=PageImageRequests.Create(book.ItemId,book.PageIds,book.Revision,scope);
            item.Remove("scope");items.Add((JsonNode)item);
        }
        var result=AIScopeRequests.Scoped(scope);result["items"]=items;result["page_limit"]=pageLimit;result["profile"]=Profile(profile);return result;
    }
    public static JsonObject Resume(string jobId,JsonObject scope,string profile)
    {
        PageEvidenceProtocol.ValidateRequestId(jobId);
        var result=AIScopeRequests.Scoped(scope);result["job_id"]=jobId;result["profile"]=Profile(profile);return result;
    }
    private static string Profile(string value)=>value.Length is >0 and <=256?value:throw new ArgumentException(AppText.L("モデル設定を確認してください。", "Check the AI model setting."));
}
public sealed record BookPageProgress(int ItemId,string Revision,string State,int Total,int Processed,int Indexed,int Reused,string Error);
public sealed record PageBatchStatus(string JobId,string Profile,string State,int Total,int Processed,int Indexed,int Reused,
    int BooksCompleted,int BooksFailed,IReadOnlyList<BookPageProgress> Books,string Error)
{
    public bool Running=>State is "running" or "cancelling";
    public bool CanResume=>State is "cancelled" or "interrupted" or "partial" or "failed";
    public string Summary=>AppText.L($"完了: {BooksCompleted}/{Books.Count}冊 · 保存済み {Indexed}/{Total}ページ", $"Completed: {BooksCompleted}/{Books.Count} books · Saved {Indexed}/{Total} pages");
    private static string ErrorText(JsonElement element)
    {
        var text=element.GetProperty("error").GetString();
        return text is not null&&text.Length<=1024?AppText.TranslateBackend(text):throw new InvalidDataException(AppText.L("処理結果が無効です。", "Invalid processing result."));
    }
    public static PageBatchStatus Parse(byte[] bytes,string expectedProfile,string? expectedJob=null)
    {
        try
        {
            using var doc=JsonDocument.Parse(bytes);var root=doc.RootElement;
            var job=TagReviewProtocol.Text(root,"job_id",32);var profile=TagReviewProtocol.Text(root,"profile",256);
            var state=TagReviewProtocol.Text(root,"state",16);
            var total=root.GetProperty("total").GetInt32();var processed=root.GetProperty("processed").GetInt32();
            var indexed=root.GetProperty("indexed").GetInt32();var reused=root.GetProperty("reused").GetInt32();
            var complete=root.GetProperty("books_completed").GetInt32();var failed=root.GetProperty("books_failed").GetInt32();
            var error=ErrorText(root);
            if(root.GetProperty("job").GetString()!="book-page-batch"||job.Length!=32||job.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))
                ||profile!=expectedProfile||expectedJob is not null&&job!=expectedJob||total is <1 or >128
                ||processed<0||processed>total||indexed<0||indexed>processed||reused<0||reused>processed
                ||state is not ("running" or "cancelling" or "complete" or "cancelled" or "interrupted" or "partial" or "failed"))throw new InvalidDataException(AppText.L("複数本の処理状況が変わりました。", "Multi-book processing status has changed."));
            var array=root.GetProperty("books");if(array.ValueKind!=JsonValueKind.Array||array.GetArrayLength() is <1 or >8)throw new InvalidDataException(AppText.L("本の件数が無効です。", "Invalid book count."));
            var books=new List<BookPageProgress>();
            foreach(var b in array.EnumerateArray())
            {
                var item=b.GetProperty("item_id").GetInt32();var rev=TagReviewProtocol.Text(b,"revision",64);
                var status=TagReviewProtocol.Text(b,"state",16);var count=b.GetProperty("total").GetInt32();
                var done=b.GetProperty("processed").GetInt32();var saved=b.GetProperty("indexed").GetInt32();var cached=b.GetProperty("reused").GetInt32();
                if(item<1||!TagReviewProtocol.IsRevision(rev)||count is <1 or >16||done<0||done>count||cached<0||cached>done
                    ||saved!=(status=="complete"?count:0)||status=="complete"&&done!=count
                    ||status is not ("pending" or "running" or "complete" or "cancelled" or "failed"))throw new InvalidDataException(AppText.L("本の処理範囲が無効です。", "Invalid book processing range."));
                books.Add(new(item,rev,status,count,done,saved,cached,ErrorText(b)));
            }
            if(root.GetProperty("books_total").GetInt32()!=books.Count||books.Select(b=>b.ItemId).Distinct().Count()!=books.Count
                ||books.Sum(b=>b.Total)!=total||books.Sum(b=>b.Indexed)!=indexed||books.Count(b=>b.State=="complete")!=complete||books.Count(b=>b.State=="failed")!=failed
                ||books.Sum(b=>b.Processed)>processed||books.Sum(b=>b.Reused)>reused
                ||(state is "complete" or "partial" or "failed" or "cancelled")&&(books.Sum(b=>b.Processed)!=processed||books.Sum(b=>b.Reused)!=reused)
                ||state=="complete"&&complete!=books.Count||state=="partial"&&(complete==0||failed==0))throw new InvalidDataException(AppText.L("複数本の件数が一致しません。", "Multi-book counts do not match."));
            return new(job,profile,state,total,processed,indexed,reused,complete,failed,books,error);
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException(AppText.L("複数本の処理状況を読み取れません。", "Unable to read multi-book processing status."),ex);}
    }
}
