using Aredoko.Core;
using Microsoft.UI.Xaml;
using System.Net;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private ResultSession? resultSession;
    private ResultWindow? resultWindow;
    private int resultPageSize = 60;
    private bool resultsNeedRefresh;

    private async Task RefreshResultRowsAfterEditAsync()
    {
        resultsNeedRefresh=true;
        var previous=resultSession;
        if(previous is null)return;
        ResultSession? replacement=null;
        try
        {
            resultWindow?.Dispose();resultWindow=null;resultSession=null;
            await CloseResultSessionAsync(previous);
            replacement=await api.Results.CreateAsync(previous.Conditions, CancellationToken.None);
            var targetPage=Math.Min(page,Math.Max(0,(replacement.Total-1)/resultPageSize));
            var window=new ResultWindow(replacement.Total,replacement.RangeAsync);
            try
            {
                var result=await window.ReadAsync(checked(targetPage*resultPageSize),resultPageSize,CancellationToken.None);
                if(disposed){window.Dispose();await CloseResultSessionAsync(replacement);return;}
                resultSession=replacement;resultWindow=window;resultsNeedRefresh=false;
                page=targetPage;rows=result.Items;
                Count.Text=$"{result.Total:N0} 件";
                PageNumber.Text=$"{page+1} / {Math.Max(1,(result.Total+resultPageSize-1)/resultPageSize)}";
                Previous.IsEnabled=page>0;Next.IsEnabled=(page+1)*resultPageSize<result.Total;
                Empty.Visibility=rows.Count==0?Visibility.Visible:Visibility.Collapsed;
                RenderRows();RestoreSelection();
            }
            catch{window.Dispose();throw;}
        }
        catch(Exception ex)
        {
            if(replacement is not null)await CloseResultSessionAsync(replacement);
            AppLog.Error(ex);
            // The edit already committed. Never report this as a failed save or
            // discard an unrelated tag/shelf draft (favorite saves only its flag).
            if(!disposed)Notice("保存しました","検索結果を更新できませんでした。同じ条件で検索し直してください。",Microsoft.UI.Xaml.Controls.InfoBarSeverity.Warning);
        }
    }


    private static async Task CloseResultSessionAsync(ResultSession? session)
    {
        if (session is null) return;
        try { await session.DisposeAsync(); }
        catch (Exception ex) { AppLog.Error(ex); }
    }

    private async Task<SearchResponse> ReadResultPageAsync(JsonObject? conditions, bool reuse, long version,
        int requestedPage, int pageSize, CancellationToken cancellation)
    {
        reuse = reuse && !resultsNeedRefresh;
        ResultSession? session = null;
        try
        {
            if (reuse)
            {
                session = resultSession;
                if (session is null || conditions is null || !JsonNode.DeepEquals(session.Conditions, conditions))
                    throw new ResultSessionException(HttpStatusCode.Conflict, conditions?.ToJsonString(), active?.Id);
            }
            else
            {
                resultWindow?.Dispose(); resultWindow = null;
                var previous = resultSession; resultSession = null;
                await CloseResultSessionAsync(previous);
                cancellation.ThrowIfCancellationRequested();
                if (!searches.IsCurrent(version) || disposed) throw new OperationCanceledException(cancellation);
                if (conditions is null) return new SearchResponse { Total = 0, Items = [] };
                session = await api.Results.CreateAsync(conditions, cancellation);
                if (!searches.IsCurrent(version) || disposed || cancellation.IsCancellationRequested)
                {
                    await CloseResultSessionAsync(session); session = null;
                    throw new OperationCanceledException(cancellation);
                }
                resultSession = session;
                resultsNeedRefresh=false;
                resultWindow = new ResultWindow(session.Total, session.RangeAsync);
            }
            var window = resultWindow ?? throw new InvalidOperationException("Result window is unavailable");
            var result = await window.ReadAsync(checked(requestedPage * pageSize), pageSize, cancellation);
            cancellation.ThrowIfCancellationRequested();
            _ = WarmResultWindowAsync(window, cancellation);
            return result;
        }
        catch
        {
            // An old cancelled read must not close a session a newer request uses.
            if (searches.IsCurrent(version) && ReferenceEquals(resultSession, session))
            {
                resultWindow?.Dispose(); resultWindow = null;
                resultSession = null; await CloseResultSessionAsync(session);
            }
            throw;
        }
    }

    private static async Task WarmResultWindowAsync(ResultWindow window, CancellationToken cancellation)
    {
        try { await window.PrefetchAsync(cancellation); }
        catch (OperationCanceledException) { }
        catch (ObjectDisposedException) { }
        catch (Exception ex) { AppLog.Error(ex); } // foreground range revalidates and explains expiry
    }

    private async Task RestoreViewerSelectionAsync(int itemId, int ordinal, ResultSession session, bool detailsWereOpen)
    {
        if (disposed || PendingSearch || !ReferenceEquals(resultSession, session)) return;
        if (active?.Id == itemId)
        {
            // Do not reload or overwrite a tag/shelf draft for the original row.
            RestoreSelection(); await FocusRowAsync(itemId); return;
        }
        if (Dirty && !await ConfirmDiscardAsync()) return;
        var targetPage = ordinal / resultPageSize;
        if (page != targetPage)
        {
            page = targetPage; await LoadAsync(reuseSession: true);
            if (disposed || PendingSearch || !ReferenceEquals(resultSession, session)) return;
        }
        var selected = rows.FirstOrDefault(row => row.Id == itemId);
        if (selected is null) return;
        ApplySelectedRow(selected); RestoreSelection();
        Details.IsPaneOpen = detailsWereOpen;
        await FocusRowAsync(itemId);
    }

    private async Task CloseResultsAndApiAsync(ResultSession session)
    {
        try { await CloseResultSessionAsync(session); }
        finally { api.Dispose(); }
    }
}
