using Aredoko.Core;
using Microsoft.UI.Xaml;
using System.Net;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private ResultSession? resultSession;
    private int resultPageSize = 60;

    private static async Task CloseResultSessionAsync(ResultSession? session)
    {
        if (session is null) return;
        try { await session.DisposeAsync(); }
        catch (Exception ex) { AppLog.Error(ex); }
    }

    private async Task<SearchResponse> ReadResultPageAsync(JsonObject? conditions, bool reuse, long version,
        int requestedPage, int pageSize, CancellationToken cancellation)
    {
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
            }
            var result = await session.RangeAsync(checked(requestedPage * pageSize), pageSize, cancellation);
            cancellation.ThrowIfCancellationRequested();
            return result;
        }
        catch
        {
            // An old cancelled read must not close a session a newer request uses.
            if (searches.IsCurrent(version) && ReferenceEquals(resultSession, session))
            {
                resultSession = null; await CloseResultSessionAsync(session);
            }
            throw;
        }
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
