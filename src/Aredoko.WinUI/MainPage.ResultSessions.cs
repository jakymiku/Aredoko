using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private ResultSession? resultSession;
    private ResultWindow? resultWindow;
    private int resultPageSize = 60;
    private bool resultsNeedRefresh;
    private Microsoft.UI.Dispatching.DispatcherQueueTimer? resultKeepAliveTimer;

    private void EnsureResultKeepAliveTimer()
    {
        if (disposed || resultKeepAliveTimer is not null)
        {
            if (!disposed && resultSession is not null && resultKeepAliveTimer is { IsRunning: false })
                resultKeepAliveTimer.Start();
            return;
        }
        resultKeepAliveTimer = DispatcherQueue.CreateTimer();
        resultKeepAliveTimer.Interval = TimeSpan.FromMinutes(5);
        resultKeepAliveTimer.IsRepeating = true;
        resultKeepAliveTimer.Tick += async (_, _) =>
        {
            if (disposed || resultsNeedRefresh || resultSession is not { } current) return;
            await TouchActiveSessionAsync(current);
        };
        if (resultSession is not null) resultKeepAliveTimer.Start();
    }

    private async Task TouchActiveSessionAsync(ResultSession activeSession)
    {
        try
        {
            await activeSession.TouchAsync(CancellationToken.None);
        }
        catch (ResultSessionException)
        {
            if (!disposed && ReferenceEquals(resultSession, activeSession))
                resultsNeedRefresh = true;
        }
        catch (ObjectDisposedException) { }
        catch (OperationCanceledException) { }
        catch (HttpRequestException) { }
    }

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
            var oldAnchorOrd=anchor is {} aPt&&TryParseOrdinalKey(aPt.Key,out var parsedOrd)?parsedOrd:browseStart;
            var oldRows=new Dictionary<int,MediaRow>(rowById);
            var oldStart=browseStart;var oldCount=rows.Count;
            resultWindow?.Dispose();resultWindow=null;resultSession=null;
            await CloseResultSessionAsync(previous);
            replacement=await api.Results.CreateAsync(previous.Conditions, CancellationToken.None);
            var positions=selected.Length>0?await replacement.LocateAsync(selected,CancellationToken.None):[];
            ResultPosition? anchorPosition=positions.FirstOrDefault(row=>row.Id==anchorId);
            if(anchorPosition is null&&anchorId is int known)anchorPosition=(await replacement.LocateAsync([known],CancellationToken.None)).FirstOrDefault();
            var useVirtual=replacement.Total<=MaxVirtualSlots;
            int start,count;
            if(useVirtual)
            {
                var desiredOrd=anchorPosition?.Ordinal??oldAnchorOrd;
                start=replacement.Total==0?0:Math.Clamp((desiredOrd/VirtualBlockSize)*VirtualBlockSize,0,Math.Max(0,replacement.Total-1));
                count=Math.Min(VirtualBlockSize,Math.Max(0,replacement.Total-start));
            }
            else
            {
                var desired=anchorPosition is not null&&anchorId is int oldAnchor&&ordinalById.TryGetValue(oldAnchor,out var prevOrd)
                    ?anchorPosition.Ordinal-(prevOrd-oldStart):oldStart;
                var length=Math.Min(BrowseBufferCapacity,Math.Max(resultPageSize,oldCount));
                start=Math.Clamp(desired,0,Math.Max(0,replacement.Total-length));
                count=Math.Min(length,replacement.Total-start);
            }
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
                EnsureResultKeepAliveTimer();
                librarySelection.Bind(replacement.Id,replacement.Total,positions);
                page=start/resultPageSize;ResetBrowse(start,result);rows=result.Items;SyncRowsState();
                Count.Text=AppText.L($"{result.Total:N0} 件", $"{result.Total:N0} item(s)");
                var slotTotal=virtualTotal<=MaxVirtualSlots?virtualTotal:rows.Count;
                UpdateBrowseFooter(FormatLoadedPageRange(browseStart,slotTotal,virtualTotal),browseStart>0,browseStart+slotTotal<virtualTotal);
                Empty.Visibility=virtualTotal==0?Visibility.Visible:Visibility.Collapsed;
                if(!keepCards)RenderRows();
                else
                {
                    var before=populating;populating=true;
                    try
                    {
                        if(resultKeys.Count!=slotTotal)
                        {
                            resultKeys.Clear();
                            for(var i=0;i<slotTotal;i++)resultKeys.Add(OrdinalKey(browseStart+i));
                        }
                    }
                    finally{populating=before;}
                    foreach(var container in realizedItems.ToArray())
                    {
                        if(container.ContentTemplateRoot is Border{Tag:MediaCardSlot{CurrentOrdinal:>=0} slot})
                        {
                            if(rowByOrdinal.TryGetValue(slot.CurrentOrdinal,out var freshRow))
                                HydratePendingOrdinalContainer(container,freshRow,slot.CurrentOrdinal);
                            else
                            {
                                pendingOrdinalContainers[slot.CurrentOrdinal]=container;
                                _ = EnsureVirtualBlockAsync(slot.CurrentOrdinal/VirtualBlockSize,replacement,virtualGeneration,warmNext:false);
                            }
                        }
                    }
                }
                UpdateBrowseTagsFlyout();
                RestoreSelection();if(active is null)ApplyLibrarySelection();
                var targetAnchor=anchor is not null&&anchorPosition is not null?(OrdinalKey(anchorPosition.Ordinal),anchor.Value.Y)
                    :anchor is not null&&TryParseOrdinalKey(anchor.Value.Key,out var retainedOrd)&&retainedOrd>=browseStart&&retainedOrd<browseStart+slotTotal?anchor
                    :null;
                if(targetAnchor is not null)await RestoreBrowseAnchorAsync(targetAnchor);
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
            if(!disposed)Notice(ex is ResultSessionException{AIIndexing:true}?AppText.L("AI検索データを作成中","Building AI search index"):AppText.L("保存しました", "Saved"),
                ex is ResultSessionException{AIIndexing:true}?ex.Message:AppText.L("検索結果を更新できませんでした。同じ条件で検索し直してください。", "Could not refresh search results. Search again with the same filters."),
                Microsoft.UI.Xaml.Controls.InfoBarSeverity.Warning);
        }
    }
    private bool CanRestoreLoadedResultSession(int targetPage, out bool pageInLoadedWindow)
    {
        pageInLoadedWindow = false;
        if (resultSession is null || resultsNeedRefresh || rows.Count == 0 || PendingSearch)
            return false;
        try
        {
            var method = SearchMethod.FromIndex(SearchMode.SelectedIndex);
            var origin = similarityOrigin;
            if ((origin is not null && !DirectContentSimilarity || origin is null && method.IsAI && !method.IsDirectContent && !string.IsNullOrWhiteSpace(Query.Text)) && aiScope is null)
                return false;
            var conditions = ResultSearchConditions.Create(
                Query.Text, KindValue(), view, method, aiScope, selectedSearchRoots?.ToArray(),
                origin?.Id, AIMatchedOnly.IsChecked == true, BoundaryValue(), ResultGroup(),
                selectedShelfIds, directAudioSimilarity, directVideoSimilarity, directVideoAudioSimilarity,
                selectedTagScope, similarityOriginPage, similarityOriginMs);
            if (conditions is null || !JsonNode.DeepEquals(resultSession.Conditions, conditions))
                return false;
            var pageSize = method.IsPageText ? 20 : 60;
            if (resultPageSize != pageSize) return false;
            if (resultSession.Total <= MaxVirtualSlots)
            {
                pageInLoadedWindow = true;
                return true;
            }
            var offset = checked(targetPage * pageSize);
            pageInLoadedWindow = offset >= browseStart && offset < browseStart + rows.Count;
            return true;
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidDataException or OverflowException)
        {
            return false;
        }
    }

    private void RestoreLoadedLibraryView()
    {
        if (resultSession is null) return;
        UpdateLibraryHeading();
        UpdateSearchMethod();
        UpdateActiveSearchScopeBar();
        UpdateFavoriteRootList();
        EmptyAIRecovery.Visibility = EmptyResetConditionsButton.Visibility = EmptyOpenFoldersButton.Visibility = Visibility.Collapsed;
        GettingStarted.Visibility = Visibility.Collapsed;
        Empty.Visibility = Visibility.Collapsed;
        Count.Text = AppText.L($"{resultSession.Total:N0} 件", $"{resultSession.Total:N0} items");
        var slotTotal = virtualTotal <= MaxVirtualSlots ? virtualTotal : rows.Count;
        UpdateBrowseFooter(FormatLoadedPageRange(browseStart, slotTotal, virtualTotal), browseStart > 0, browseStart + slotTotal < virtualTotal);
        Items.IsEnabled = true;
        startupSearchSucceeded = true;
        BindLibrarySelection();
        if (active is null && librarySelection.Count == 1 && rowById.TryGetValue(librarySelection.Ids.First(), out var selectedRow))
            ApplySelectedRow(selectedRow);
        else
            Editor.IsEnabled = active is not null;
        RestoreSelection();
        DetailsButton.IsEnabled=!saving&&!preparingSelection&&(librarySelection.Count>0||active is not null);
        ResumeVisibleContainers();
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
                var usesAI = mode is "semantic" or "similar" or "pending-proposals-semantic" or "audio-direct" or "video-direct" or "video-audio-direct";
                if (usesAI)
                {
                    await WaitForRuntimeVerificationBeforeSearchAsync(version, cancellation);
                }
                if (usesAI && !aiModelResident)
                {
                    SetAiSearchModelLoading(true,version);
                }
                var reporting=true;
                var progress=new Progress<ResultBuildProgress>(value=>
                {
                    if(!reporting||disposed||!searches.IsCurrent(version)||cancellation.IsCancellationRequested)return;
                    Count.Text=value.Total is int total?AppText.L($"準備中 {value.Processed:N0} / {total:N0}", $"Preparing {value.Processed:N0} / {total:N0}"):AppText.L("準備中…", "Preparing...");
                    if(rows.Count==0)Empty.Text=value.Total is int expected
                        ?AppText.L($"一覧を準備しています…（{value.Processed:N0} / {expected:N0}件）", $"Preparing list... ({value.Processed:N0} / {expected:N0})"):AppText.L("検索結果を準備しています…", "Preparing search results...");
                });
                try
                {
                    session = await api.Results.CreateAsync(conditions, cancellation,progress);
                }
                finally
                {
                    reporting=false;
                    if (usesAI) SetAiSearchModelLoading(false,version);
                }
                if (!searches.IsCurrent(version) || disposed || cancellation.IsCancellationRequested)
                {
                    await CloseResultSessionAsync(session); session = null;
                    throw new OperationCanceledException(cancellation);
                }
                resultSession = session;
                resultsNeedRefresh=false;
                EnsureResultKeepAliveTimer();
                resultWindow = new ResultWindow(session.Total, session.RangeAsync);
            }
            var window = resultWindow ?? throw new InvalidOperationException("Result window is unavailable");
            var result = await window.ReadAsync(checked(requestedPage * pageSize), pageSize, cancellation);
            cancellation.ThrowIfCancellationRequested();
            if(session.Total>MaxVirtualSlots)_ = WarmResultWindowAsync(window, cancellation);
            return result;
        }
        catch(OperationCanceledException) when(reuse&&cancellation.IsCancellationRequested&&
            searches.IsCurrent(version)&&ReferenceEquals(resultSession,session))
        {
            // Cancelling navigation cancels that read, not the frozen search.
            // Keep the previous valid rows and let the user retry the range.
            throw;
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
        if (disposed || !ReferenceEquals(resultSession, session)) return;
        if (active?.Id == itemId)
        {
            // Do not reload or overwrite a tag/shelf draft for the original row.
            if (SelectionPosition(itemId) is { } samePos)
            {
                BindLibrarySelection();
                librarySelection.Single(samePos);
            }
            RestoreSelection(); await FocusRowAsync(itemId); UpdateLibrarySelectionTools(); return;
        }
        if (Dirty && !await ConfirmDiscardAsync()) return;
        MediaRow? selected;
        if (browseStart == 0 && resultKeys.Count == virtualTotal)
        {
            if (!rowByOrdinal.TryGetValue(ordinal, out selected) || selected.Id != itemId)
            {
                await EnsureVirtualBlockAsync(ordinal / VirtualBlockSize, session, virtualGeneration, warmNext: false);
                if (disposed || !ReferenceEquals(resultSession, session)) return;
                rowByOrdinal.TryGetValue(ordinal, out selected);
            }
        }
        else
        {
            var targetPage = ordinal / resultPageSize;
            if (ordinal < browseStart || ordinal >= browseStart + rows.Count)
            {
                var start = Math.Clamp(targetPage * resultPageSize, 0, Math.Max(0, session.Total - 1));
                var count = Math.Min(resultPageSize, session.Total - start);
                if (resultWindow is not { } window || count <= 0) return;
                var result = await window.ReadAsync(start, count, CancellationToken.None);
                if (disposed || !ReferenceEquals(resultSession, session)) return;
                ResetBrowse(start, result);
                rows = browseBuffer!.Items.ToList();
                SyncRowsState();
                page = start / resultPageSize;
                RenderRows();
                UpdateBrowseFooter(FormatLoadedPageRange(start, rows.Count, browseBuffer.Total), start > 0, browseBuffer.End < browseBuffer.Total);
            }
            selected = rowById.TryGetValue(itemId, out var found) ? found : rows.FirstOrDefault(row => row.Id == itemId);
        }
        if (selected is null) return;
        BindLibrarySelection();
        librarySelection.Single(new ResultPosition(selected.Id, ordinal));
        ApplySelectedRow(selected); RestoreSelection();
        Details.IsPaneOpen = detailsWereOpen;
        await FocusRowAsync(selected.Id);
        UpdateLibrarySelectionTools();
    }

    private async Task CloseResultsAndApiAsync(ResultSession session)
    {
        try { await CloseResultSessionAsync(session); }
        finally { api.Dispose(); }
    }
}
