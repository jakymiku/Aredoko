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

    private async Task RefreshResultRowsAfterEditAsync(bool favoriteOnly=false)
    {
        resultsNeedRefresh=true;
        var previous=resultSession;
        if(previous is null)return;
        ResultSession? replacement=null;
        try
        {
            var selected=librarySelection.Ids.ToArray();var anchor=CaptureBrowseAnchor();
            var anchorId=anchor is {} point?RowForKey(point.Key)?.Id:null;
            var oldRows=rows.ToDictionary(row=>row.Id);var oldStart=browseStart;var oldCount=rows.Count;
            resultWindow?.Dispose();resultWindow=null;resultSession=null;
            await CloseResultSessionAsync(previous);
            replacement=await api.Results.CreateAsync(previous.Conditions, CancellationToken.None);
            var positions=selected.Length>0?await replacement.LocateAsync(selected,CancellationToken.None):[];
            ResultPosition? anchorPosition=positions.FirstOrDefault(row=>row.Id==anchorId);
            if(anchorPosition is null&&anchorId is int known)anchorPosition=(await replacement.LocateAsync([known],CancellationToken.None)).FirstOrDefault();
            var desired=anchorPosition is not null&&anchorId is int oldAnchor&&oldRows.ContainsKey(oldAnchor)
                ?anchorPosition.Ordinal-rows.FindIndex(row=>row.Id==oldAnchor):oldStart;
            var length=Math.Min(ResultBuffer.Capacity,Math.Max(resultPageSize,oldCount));
            var start=Math.Clamp(desired,0,Math.Max(0,replacement.Total-length));
            var count=Math.Min(length,replacement.Total-start);
            var window=new ResultWindow(replacement.Total,replacement.RangeAsync);
            try
            {
                var items=new List<MediaRow>();
                for(var offset=start;offset<start+Math.Max(1,count);)
                {
                    var chunk=await window.ReadAsync(offset,Math.Min(120,Math.Max(1,start+count-offset)),CancellationToken.None);
                    items.AddRange(chunk.Items);if(chunk.Items.Count==0)break;offset+=chunk.Items.Count;
                }
                var result=new SearchResponse{Total=replacement.Total,Items=items};
                if(disposed){window.Dispose();await CloseResultSessionAsync(replacement);return;}
                // Literal favorite edits cannot change visual evidence. Reuse
                // surviving native cells only when all displayed metadata agrees.
                var keepCards=favoriteOnly&&SearchMode.SelectedIndex==0
                    &&items.All(row=>!oldRows.TryGetValue(row.Id,out var old)||SameFavoriteCard(old,row));
                if(keepCards)result.Items=items.Select(row=>oldRows.GetValueOrDefault(row.Id,row)).ToList();
                resultSession=replacement;resultWindow=window;resultsNeedRefresh=false;
                librarySelection.Bind(replacement.Id,replacement.Total,positions);
                page=start/resultPageSize;ResetBrowse(start,result);rows=result.Items;
                Count.Text=$"{result.Total:N0} 件";
                PageNumber.Text=result.Total==0?"0 件":$"{start+1:N0}–{start+rows.Count:N0} / {result.Total:N0}";
                Previous.IsEnabled=start>0;Next.IsEnabled=start+rows.Count<result.Total;
                Empty.Visibility=rows.Count==0?Visibility.Visible:Visibility.Collapsed;
                if(!keepCards)RenderRows();
                else
                {
                    var before=populating;populating=true;
                    try
                    {
                        var wanted=rows.Select(row=>RowKey(row.Id)).ToArray();var set=wanted.ToHashSet();
                        for(var i=resultKeys.Count-1;i>=0;i--)if(!set.Contains(resultKeys[i]))resultKeys.RemoveAt(i);
                        for(var i=0;i<wanted.Length;i++)
                        {
                            if(i<resultKeys.Count&&resultKeys[i]==wanted[i])continue;
                            var existing=resultKeys.IndexOf(wanted[i]);
                            if(existing>=0)resultKeys.Move(existing,i);else resultKeys.Insert(i,wanted[i]);
                        }
                    }
                    finally{populating=before;}
                }
                RestoreSelection();if(active is null)ApplyLibrarySelection();
                if(anchor is {} retained&&rows.Any(row=>RowKey(row.Id)==retained.Key))await RestoreBrowseAnchorAsync(anchor);
            }
            catch{window.Dispose();throw;}
        }
        catch(Exception ex)
        {
            if(replacement is not null)await CloseResultSessionAsync(replacement);
            if(ReferenceEquals(resultSession,replacement)){resultWindow?.Dispose();resultWindow=null;resultSession=null;}
            resultsNeedRefresh=true;
            AppLog.Error(ex);
            // The edit already committed. Never report this as a failed save or
            // discard an unrelated tag/shelf draft (favorite saves only its flag).
            if(!disposed)Notice("保存しました","検索結果を更新できませんでした。同じ条件で検索し直してください。",Microsoft.UI.Xaml.Controls.InfoBarSeverity.Warning);
        }
    }
    private static bool SameFavoriteCard(MediaRow a,MediaRow b)=>
        a.Id==b.Id&&a.Title==b.Title&&a.Kind==b.Kind&&a.Location==b.Location&&a.Availability==b.Availability
        &&a.PreviewKey==b.PreviewKey&&a.Favorite==b.Favorite&&a.Reviewed==b.Reviewed&&a.Shelf==b.Shelf
        &&a.Tags.SequenceEqual(b.Tags)&&a.ShelfIds.SequenceEqual(b.ShelfIds)&&a.MatchLabel==b.MatchLabel
        &&a.AIEvidence==b.AIEvidence&&a.Proposal?.Summary==b.Proposal?.Summary&&a.AIPage?.Summary==b.AIPage?.Summary
        &&a.PageText?.Summary==b.PageText?.Summary&&Protocol.DescribeEvidence(a.Evidence)==Protocol.DescribeEvidence(b.Evidence);


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
                var mode = conditions["mode"]?.GetValue<string>();
                var usesAI = mode is "semantic" or "similar" or "pending-proposals-semantic";
                if (usesAI)
                {
                    await WaitForRuntimeVerificationBeforeSearchAsync(version, cancellation);
                }
                if (usesAI && !aiModelResident)
                {
                    SetAiSearchModelLoading(true);
                }
                try
                {
                    session = await api.Results.CreateAsync(conditions, cancellation);
                }
                finally
                {
                    if (usesAI) SetAiSearchModelLoading(false);
                }
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
        if (ordinal<browseStart||ordinal>=browseStart+rows.Count)
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
