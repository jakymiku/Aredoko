using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Collections.ObjectModel;
using System.Net;
using Windows.Foundation;

namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private const int BrowseBufferCapacity = 2400;
    private const int MaxVirtualSlots = 20_000;
    private const int VirtualBlockSize = ResultWindow.BlockSize;
    private const int MaxCachedVirtualBlocks = 24;

    private readonly ObservableCollection<string> resultKeys = new();
    private readonly Dictionary<int, MediaRow> rowByOrdinal = new();
    private readonly Dictionary<int, int> ordinalById = new();
    private readonly Dictionary<int, List<MediaRow>> cachedBlocks = new();
    private readonly LinkedList<int> blockLru = new();
    private readonly Dictionary<int, Task> inflightBlocks = new();
    private readonly Dictionary<int, ListViewItem> pendingOrdinalContainers = new();
    private readonly HashSet<ListViewItem> realizedItems = new();
    private readonly SemaphoreSlim virtualBlockSemaphore = new(2, 2);

    private ResultBuffer? browseBuffer;
    private int browseStart, virtualTotal;
    private long virtualGeneration;
    private bool browseFailed, extending, browseReflowing, fastScrolling, virtualSessionRefreshing;
    private ScrollViewer? resultScroll;
    private readonly SmoothWheelScroller smoothWheelScroller = new();
    private Microsoft.UI.Dispatching.DispatcherQueueTimer? scrollSettleTimer;
    private long lastScrollTick;
    private double lastScrollOffset;

    private static string OrdinalKey(int ordinal)
        => "@" + ordinal.ToString(System.Globalization.CultureInfo.InvariantCulture);

    private static bool TryParseOrdinalKey(object? key, out int ordinal)
    {
        if (key is string value && value.Length > 1 && value[0] == '@'
            && int.TryParse(value.AsSpan(1), System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out ordinal))
            return true;
        ordinal = -1;
        return false;
    }

    private string? KeyForItem(int itemId)
        => ordinalById.TryGetValue(itemId, out var ord) ? OrdinalKey(ord) : null;

    private int PreviousBrowsePage() => Math.Max(0, (browseStart - 1) / resultPageSize);
    private int NextBrowsePage() => browseBuffer?.End / resultPageSize ?? page + 1;

    private void ClearVirtualBlocks()
    {
        virtualGeneration++;
        virtualTotal = 0;
        browseStart = 0;
        browseFailed = false;
        virtualSessionRefreshing = false;
        rowByOrdinal.Clear();
        ordinalById.Clear();
        rowById.Clear();
        cachedBlocks.Clear();
        blockLru.Clear();
        inflightBlocks.Clear();
        pendingOrdinalContainers.Clear();
    }

    private void ResetBrowse(int start, SearchResponse result)
    {
        browseBuffer = new ResultBuffer(start, result, BrowseBufferCapacity);
        ClearVirtualBlocks();
        virtualTotal = result.Total;
        browseStart = result.Total <= MaxVirtualSlots ? 0 : start;
        StoreRowsRange(start, result.Items);
    }

    private void StoreRowsRange(int start, IReadOnlyList<MediaRow> items)
    {
        for (var i = 0; i < items.Count; i++)
        {
            var ord = start + i;
            var row = items[i];
            rowByOrdinal[ord] = row;
            rowById[row.Id] = row;
            ordinalById[row.Id] = ord;
        }
        if (start % VirtualBlockSize == 0 && items.Count > 0)
        {
            var firstBlock = start / VirtualBlockSize;
            var expectedFull = Math.Min(VirtualBlockSize, Math.Max(0, virtualTotal - firstBlock * VirtualBlockSize));
            if (items.Count >= expectedFull)
            {
                for (var offset = 0; offset + expectedFull <= items.Count;)
                {
                    var blockStart = start + offset;
                    var blockIndex = blockStart / VirtualBlockSize;
                    var blockLen = Math.Min(VirtualBlockSize, Math.Max(0, virtualTotal - blockStart));
                    if (offset + blockLen > items.Count) break;
                    var list = new List<MediaRow>(blockLen);
                    for (var k = 0; k < blockLen; k++) list.Add(items[offset + k]);
                    RecordCachedBlock(blockIndex, list);
                    offset += blockLen;
                }
            }
        }
    }

    private void RecordCachedBlock(int blockIndex, List<MediaRow> blockItems)
    {
        cachedBlocks[blockIndex] = blockItems;
        blockLru.Remove(blockIndex);
        blockLru.AddLast(blockIndex);
        if (cachedBlocks.Count <= MaxCachedVirtualBlocks) return;

        var realizedBlockSet = new HashSet<int>();
        foreach (var item in realizedItems)
        {
            if (item.ContentTemplateRoot is Border { Tag: MediaCardSlot { CurrentOrdinal: >= 0 } slot })
                realizedBlockSet.Add(slot.CurrentOrdinal / VirtualBlockSize);
        }
        var node = blockLru.First;
        while (node is not null && cachedBlocks.Count > MaxCachedVirtualBlocks)
        {
            var next = node.Next;
            var candidate = node.Value;
            if (!realizedBlockSet.Contains(candidate))
            {
                blockLru.Remove(node);
                if (cachedBlocks.Remove(candidate, out var evicted))
                {
                    var bStart = candidate * VirtualBlockSize;
                    for (var i = 0; i < evicted.Count; i++)
                    {
                        var ord = bStart + i;
                        var evictedRow = evicted[i];
                        if (rowByOrdinal.TryGetValue(ord, out var current) && ReferenceEquals(current, evictedRow))
                            rowByOrdinal.Remove(ord);
                        if (ordinalById.TryGetValue(evictedRow.Id, out var mappedOrd) && mappedOrd == ord)
                        {
                            ordinalById.Remove(evictedRow.Id);
                            rowById.Remove(evictedRow.Id);
                        }
                    }
                }
            }
            node = next;
        }
    }

    private Task EnsureVirtualBlockAsync(int blockIndex, ResultSession session, long expectedGen, bool warmNext = false)
    {
        if (disposed || expectedGen != virtualGeneration || !ReferenceEquals(session, resultSession))
            return Task.CompletedTask;
        var blockStart = blockIndex * VirtualBlockSize;
        if (blockStart < 0 || blockStart >= virtualTotal) return Task.CompletedTask;
        if (cachedBlocks.ContainsKey(blockIndex))
        {
            blockLru.Remove(blockIndex);
            blockLru.AddLast(blockIndex);
            return Task.CompletedTask;
        }
        if (inflightBlocks.TryGetValue(blockIndex, out var existing))
            return existing;

        var task = LoadVirtualBlockCoreAsync(blockIndex, blockStart, session, expectedGen, warmNext);
        inflightBlocks[blockIndex] = task;
        return task;
    }

    private async Task LoadVirtualBlockCoreAsync(int blockIndex, int blockStart, ResultSession session, long expectedGen, bool warmNext)
    {
        var token = renderCancellation.Token;
        try
        {
            await virtualBlockSemaphore.WaitAsync(token);
            SearchResponse result;
            try
            {
                if (disposed || token.IsCancellationRequested || expectedGen != virtualGeneration || !ReferenceEquals(session, resultSession))
                    return;
                var blockCount = Math.Min(VirtualBlockSize, virtualTotal - blockStart);
                if (blockCount <= 0) return;
                result = await session.RangeAsync(blockStart, blockCount, token);
            }
            finally
            {
                virtualBlockSemaphore.Release();
            }
            if (disposed || token.IsCancellationRequested || expectedGen != virtualGeneration || !ReferenceEquals(session, resultSession))
                return;

            var list = result.Items.ToList();
            for (var i = 0; i < list.Count; i++)
            {
                var ord = blockStart + i;
                var row = list[i];
                rowByOrdinal[ord] = row;
                rowById[row.Id] = row;
                ordinalById[row.Id] = ord;
            }
            RecordCachedBlock(blockIndex, list);

            for (var i = 0; i < list.Count; i++)
            {
                var ord = blockStart + i;
                if (pendingOrdinalContainers.Remove(ord, out var container))
                    HydratePendingOrdinalContainer(container, list[i], ord);
            }

            if (!fastScrolling && list.Count > 0)
            {
                _ = thumbnails.PrefetchRowsAsync(list.ToArray(), CurrentThumbnailEdge(), token);
                if (warmNext && blockStart + list.Count < virtualTotal && !cachedBlocks.ContainsKey(blockIndex + 1) && !inflightBlocks.ContainsKey(blockIndex + 1))
                    _ = EnsureVirtualBlockAsync(blockIndex + 1, session, expectedGen, warmNext: false);
            }
        }
        catch (OperationCanceledException) { }
        catch (ResultSessionException ex) when (ex.Status == HttpStatusCode.Gone && !disposed && expectedGen == virtualGeneration && ReferenceEquals(session, resultSession))
        {
            if (!saving && !dialogOpen && !PendingSearch && !virtualSessionRefreshing)
            {
                virtualSessionRefreshing = true;
                _ = RecoverExpiredSessionAsync(session);
            }
        }
        catch (ResultSessionException ex) when (ex.AIIndexing && !disposed && expectedGen == virtualGeneration && ReferenceEquals(session, resultSession))
        {
            if (!disposed)
            {
                browseFailed = true;
                resultsNeedRefresh = true;
                Notice(AppText.L("AI検索データを作成中", "Building AI search index"), ex.Message, InfoBarSeverity.Warning);
            }
        }
        catch (Exception ex)
        {
            if (!disposed && expectedGen == virtualGeneration && ReferenceEquals(session, resultSession))
            {
                browseFailed = true;
                Failure(ex);
            }
        }
        finally
        {
            if (expectedGen == virtualGeneration)
                inflightBlocks.Remove(blockIndex);
        }
    }

    private async Task RecoverExpiredSessionAsync(ResultSession expired)
    {
        if (disposed || !ReferenceEquals(resultSession, expired) || !await transitions.WaitAsync(0)) return;
        try
        {
            if (!disposed && ReferenceEquals(resultSession, expired) && !PendingSearch)
                await RefreshResultRowsAfterEditAsync();
        }
        catch (Exception ex)
        {
            if (!disposed) Failure(ex);
        }
        finally
        {
            virtualSessionRefreshing = false;
            transitions.Release();
        }
    }

    private void ResumeVisibleContainers()
    {
        if (disposed) return;
        if (resultSession is { } session && pendingOrdinalContainers.Count > 0)
        {
            var neededBlocks = new HashSet<int>();
            foreach (var ord in pendingOrdinalContainers.Keys)
                neededBlocks.Add(ord / VirtualBlockSize);
            foreach (var block in neededBlocks)
                _ = EnsureVirtualBlockAsync(block, session, virtualGeneration, warmNext: false);
        }
        foreach (var item in realizedItems.ToArray())
        {
            if (item.ContentTemplateRoot is Border { Tag: MediaCardSlot { CurrentRow: not null } slot })
                slot.RefreshThumbnail?.Invoke();
        }
    }

    private static T? Descendant<T>(DependencyObject parent) where T : DependencyObject
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            var child = VisualTreeHelper.GetChild(parent, i);
            if (child is T match) return match;
            if (Descendant<T>(child) is T nested) return nested;
        }
        return null;
    }

    private void Items_Loaded(object sender, RoutedEventArgs args)
    {
        var scroll = Descendant<ScrollViewer>(Items);
        if (ReferenceEquals(resultScroll, scroll)) return;
        if (resultScroll is not null)
        {
            resultScroll.ViewChanged -= ResultScroll_Changed;
            smoothWheelScroller.Detach();
        }
        resultScroll = scroll;
        if (scroll is not null)
        {
            scroll.ViewChanged += ResultScroll_Changed;
            smoothWheelScroller.Attach(
                scroll,
                canHandleWheel: () => !disposed && ready && Items.IsEnabled && !dialogOpen && !folderHubOpen && !shelfHubOpen && !settingsHubOpen,
                onVelocityChanged: velocity =>
                {
                    if (disposed || resultScroll is not { ViewportHeight: > 0 } currentScroll) return;
                    var viewportsPerSec = Math.Abs(velocity) / currentScroll.ViewportHeight;
                    if (!fastScrolling && viewportsPerSec > 3.5)
                        fastScrolling = true;
                    else if (fastScrolling && viewportsPerSec < 1.8)
                    {
                        fastScrolling = false;
                        ResumeVisibleContainers();
                    }
                },
                onStopped: () =>
                {
                    lastScrollTick = 0;
                    if (disposed || !fastScrolling) return;
                    fastScrolling = false;
                    ResumeVisibleContainers();
                });
        }
    }

    private void EnsureScrollSettleTimer()
    {
        if (scrollSettleTimer is not null) return;
        scrollSettleTimer = DispatcherQueue.CreateTimer();
        scrollSettleTimer.Interval = TimeSpan.FromMilliseconds(60);
        scrollSettleTimer.IsRepeating = false;
        scrollSettleTimer.Tick += (_, _) =>
        {
            if (disposed || !fastScrolling) return;
            fastScrolling = false;
            ResumeVisibleContainers();
        };
    }

    private void ResetFastScroll()
    {
        fastScrolling = false;
        scrollSettleTimer?.Stop();
        smoothWheelScroller.Stop();
        lastScrollTick = 0;
        lastScrollOffset = 0;
    }

    private void ResultScroll_Changed(object? sender, ScrollViewerViewChangedEventArgs args)
    {
        if (resultScroll is { ViewportHeight: > 0 } scroll)
        {
            var now = Environment.TickCount64;
            var offset = scroll.VerticalOffset;
            if (args.IsIntermediate)
            {
                if (smoothWheelScroller.IsActive)
                    smoothWheelScroller.Stop();
                var elapsed = now - lastScrollTick;
                if (lastScrollTick > 0 && elapsed < 300)
                {
                    var delta = Math.Abs(offset - lastScrollOffset);
                    if (elapsed >= 8)
                    {
                        if (delta / scroll.ViewportHeight / (elapsed / 1000.0) > 3.0)
                            fastScrolling = true;
                        lastScrollTick = now;
                        lastScrollOffset = offset;
                    }
                    else if (delta > scroll.ViewportHeight * 0.25)
                    {
                        fastScrolling = true;
                    }
                }
                else
                {
                    lastScrollTick = now;
                    lastScrollOffset = offset;
                }
                if (fastScrolling)
                {
                    EnsureScrollSettleTimer();
                    scrollSettleTimer!.Stop();
                    scrollSettleTimer.Start();
                }
            }
            else if (!smoothWheelScroller.IsActive)
            {
                lastScrollTick = now;
                lastScrollOffset = offset;
                if (fastScrolling)
                {
                    fastScrolling = false;
                    scrollSettleTimer?.Stop();
                    ResumeVisibleContainers();
                }
            }
        }
        if (resultKeys.Count < virtualTotal)
            _ = TryExtendBrowseWindowAsync(args.IsIntermediate || smoothWheelScroller.IsActive);
    }

    private (bool Forward, bool Backward) GetNeededBrowseEdge(ScrollViewer scroll, ResultBuffer buffer, bool isIntermediate)
    {
        if (resultKeys.Count >= virtualTotal) return (false, false);
        if (scroll.ViewportHeight <= 0) return (false, false);
        var forward = scroll.VerticalOffset + scroll.ViewportHeight * 3 >= scroll.ExtentHeight && buffer.End < buffer.Total;
        if (forward && isIntermediate && buffer.Items.Count + ResultWindow.BlockSize > buffer.MaxCapacity)
            forward = false;
        var backward = !forward && !isIntermediate && scroll.VerticalOffset < scroll.ViewportHeight && buffer.Start > 0;
        return (forward, backward);
    }

    private async Task TryExtendBrowseWindowAsync(bool isIntermediate)
    {
        if (resultKeys.Count >= virtualTotal) return;
        if (!ready || !Items.IsEnabled || disposed || extending || browseReflowing || browseFailed || saving || dialogOpen || PendingAutoSearch || folderHubOpen) return;
        if (resultScroll is not ScrollViewer scroll || browseBuffer is not ResultBuffer buffer || resultWindow is not ResultWindow window) return;
        var (forward, backward) = GetNeededBrowseEdge(scroll, buffer, isIntermediate);
        if (!forward && !backward || !await transitions.WaitAsync(0)) return;
        extending = true; var session = resultSession; var token = renderCancellation.Token;
        try
        {
            var offset = forward ? buffer.End : Math.Max(0, buffer.Start - ResultWindow.BlockSize);
            var count = forward ? Math.Min(ResultWindow.BlockSize, buffer.Total - offset) : buffer.Start - offset;
            var result = await window.ReadAsync(offset, count, token);
            if (disposed || token.IsCancellationRequested || !ReferenceEquals(session, resultSession) || !ReferenceEquals(buffer, browseBuffer)) return;
            var previousStart = buffer.Start;
            var needAnchor = forward ? (buffer.Items.Count + result.Items.Count > buffer.MaxCapacity) : true;
            var anchor = needAnchor ? CaptureBrowseAnchor() : null;
            buffer.Extend(offset, result); browseStart = buffer.Start; rows = buffer.Items.ToList(); StoreRowsRange(offset, result.Items); SyncRowsState(updateCaptionHeight: false);
            var startShifted = buffer.Start != previousStart;
            var wasPopulating = populating; populating = true;
            try
            {
                if (forward && !startShifted)
                {
                    for (var i = 0; i < result.Items.Count; i++)
                    {
                        var ord = offset + i;
                        var key = OrdinalKey(ord);
                        resultKeys.Add(key);
                        if (librarySelection.Contains(result.Items[i].Id)) Items.SelectedItems.Add(key);
                    }
                }
                else if (forward)
                {
                    var evicted = Math.Max(0, buffer.Start - previousStart);
                    for (var i = 0; i < evicted && resultKeys.Count > 0; i++) resultKeys.RemoveAt(0);
                    for (var i = 0; i < result.Items.Count; i++) resultKeys.Add(OrdinalKey(offset + i));
                    RestoreSelection();
                }
                else
                {
                    var wanted = new string[rows.Count];
                    for (var i = 0; i < rows.Count; i++) wanted[i] = OrdinalKey(browseStart + i);
                    var keep = wanted.ToHashSet();
                    for (var i = resultKeys.Count - 1; i >= 0; i--) if (!keep.Contains(resultKeys[i])) resultKeys.RemoveAt(i);
                    for (var i = 0; i < wanted.Length; i++) if (i >= resultKeys.Count || resultKeys[i] != wanted[i]) resultKeys.Insert(i, wanted[i]);
                    RestoreSelection();
                }
            }
            finally { populating = wasPopulating; }
            if (forward && !startShifted && librarySelection.Count > 0) UpdateLibrarySelectionTools();
            if (startShifted)
            {
                Items.UpdateLayout(); await RestoreBrowseAnchorAsync(anchor);
            }
            if (disposed || token.IsCancellationRequested) return;
            UpdateBrowseFooter(FormatLoadedPageRange(browseStart, buffer.End - browseStart, buffer.Total), browseStart > 0, buffer.End < buffer.Total);
            if (!fastScrolling && result.Items.Count > 0) _ = thumbnails.PrefetchRowsAsync(result.Items.ToArray(), CurrentThumbnailEdge(), renderCancellation.Token);
        }
        catch (OperationCanceledException) { }
        catch (ResultSessionException ex) when (ex.AIIndexing)
        {
            if (!disposed)
            {
                browseFailed = true;
                resultsNeedRefresh = true;
                Notice(AppText.L("AI検索データを作成中", "Building AI search index"), ex.Message, InfoBarSeverity.Warning);
            }
        }
        catch (Exception ex) { if (!disposed) { browseFailed = true; Failure(ex); } }
        finally
        {
            extending = false; transitions.Release();
            if (PendingAutoSearch && !disposed) { searchTimer.Stop(); searchTimer.Start(); }
            else if (!disposed && resultScroll is { } currentScroll && browseBuffer is { } currentBuffer)
            {
                var (moreForward, moreBackward) = GetNeededBrowseEdge(currentScroll, currentBuffer, isIntermediate);
                if (moreForward || moreBackward) DispatcherQueue.TryEnqueue(() => _ = TryExtendBrowseWindowAsync(isIntermediate));
            }
        }
    }

    private async void BrowseEdgeShortcut(KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        if (!ready || disposed || dialogOpen || saving || viewerWindow is not null || folderHubOpen || shelfHubOpen) return;
        // Preserve Ctrl+Home/End for caret movement and native editor selection.
        for (var node = FocusManager.GetFocusedElement(XamlRoot) as DependencyObject; node is not null && node != this; node = VisualTreeHelper.GetParent(node))
            if (node is TextBox or RichEditBox or PasswordBox or ComboBox or NumberBox or Slider) return;
        args.Handled = true; await JumpBrowseEdgeAsync(sender.Key == Windows.System.VirtualKey.End);
    }

    private async Task JumpBrowseEdgeAsync(bool last)
    {
        smoothWheelScroller.Stop();
        if (extending || browseReflowing || PendingAutoSearch || resultSession is not { } session || resultWindow is not { } window || session.Total == 0 || !await transitions.WaitAsync(0)) return;
        extending = true; var token = renderCancellation.Token;
        try
        {
            if (browseStart == 0 && resultKeys.Count == virtualTotal)
            {
                var targetOrdinal = last ? Math.Max(0, virtualTotal - 1) : 0;
                await EnsureVirtualBlockAsync(targetOrdinal / VirtualBlockSize, session, virtualGeneration, warmNext: false);
                if (disposed || token.IsCancellationRequested || PendingAutoSearch || !ReferenceEquals(session, resultSession)) return;
                Items.ScrollIntoView(OrdinalKey(targetOrdinal), ScrollIntoViewAlignment.Leading);
                await YieldBrowseLayoutAsync(); if (disposed) return; Items.UpdateLayout();
                resultScroll?.ChangeView(null, last ? resultScroll.ScrollableHeight : 0, null, true);
                await YieldBrowseLayoutAsync();
                ResumeVisibleContainers();
                return;
            }
            var start = last ? Math.Max(0, session.Total - ResultWindow.BlockSize) : 0;
            var result = await window.ReadAsync(start, Math.Min(ResultWindow.BlockSize, session.Total - start), token);
            if (disposed || token.IsCancellationRequested || PendingAutoSearch || !ReferenceEquals(session, resultSession)) return;
            ResetBrowse(start, result); rows = browseBuffer!.Items.ToList(); SyncRowsState(); page = start / resultPageSize;
            RenderRows(); RestoreSelection(); Items.UpdateLayout(); await YieldBrowseLayoutAsync();
            if (disposed || !ReferenceEquals(session, resultSession)) return;
            resultScroll?.ChangeView(null, last ? resultScroll.ScrollableHeight : 0, null, true);
            await YieldBrowseLayoutAsync();
            UpdateBrowseFooter(FormatLoadedPageRange(start, rows.Count, browseBuffer.Total), start > 0, browseBuffer.End < browseBuffer.Total);
        }
        catch (OperationCanceledException) { }
        catch (Exception error) { if (!disposed) Failure(error); }
        finally
        {
            extending = false; transitions.Release();
            if (PendingAutoSearch && !disposed) { searchTimer.Stop(); searchTimer.Start(); }
        }
    }

    private (string Key, double Y)? CaptureBrowseAnchor()
    {
        (string Key, double Y, int Index)? first = null;
        foreach (var container in realizedItems)
        {
            if (!container.IsLoaded) continue;
            int ord;
            if (container.ContentTemplateRoot is Border { Tag: MediaCardSlot { CurrentOrdinal: >= 0 } slot })
                ord = slot.CurrentOrdinal;
            else if (TryParseOrdinalKey(Items.ItemFromContainer(container), out var parsed))
                ord = parsed;
            else
                continue;
            var y = container.TransformToVisual(Items).TransformPoint(new Point()).Y;
            if (!double.IsFinite(y) || y + container.ActualHeight <= 0 || y >= Items.ActualHeight) continue;
            // Recycled container insertion order is not visual order. Preserve
            // the leading visible row, and the first result within a tile row.
            if (first is null || y < first.Value.Y || y == first.Value.Y && ord < first.Value.Index)
                first = (OrdinalKey(ord), y, ord);
        }
        return first is { } value ? (value.Key, value.Y) : null;
    }

    private void ReflowBrowse(Action change)
    {
        smoothWheelScroller.Stop();
        if (browseReflowing || extending || !ready || disposed || folderHubOpen || shelfHubOpen || Items.Visibility != Visibility.Visible)
        { change(); return; }
        var anchor = CaptureBrowseAnchor();
        var atEnd = resultScroll is not null && resultScroll.ScrollableHeight > 2 && virtualTotal > 0
            && Math.Abs(resultScroll.ScrollableHeight - resultScroll.VerticalOffset) < 2;
        if (anchor is null && !atEnd) { change(); return; }
        var session = resultSession; var gen = virtualGeneration;
        browseReflowing = true;
        try { change(); Items.UpdateLayout(); _ = FinishBrowseReflowAsync(anchor, atEnd, session, gen); }
        catch { browseReflowing = false; throw; }
    }

    private async Task FinishBrowseReflowAsync((string Key, double Y)? anchor, bool atEnd, object? session, long gen)
    {
        try
        {
            await YieldBrowseLayoutAsync();
            if (disposed || !ReferenceEquals(session, resultSession) || gen != virtualGeneration) return;
            Items.UpdateLayout();
            if (atEnd && resultScroll is not null)
            {
                resultScroll.ChangeView(null, resultScroll.ScrollableHeight, null, true);
                await YieldBrowseLayoutAsync();
            }
            else await RestoreBrowseAnchorAsync(anchor);
        }
        catch (Exception error) { if (!disposed) Failure(error); }
        finally { browseReflowing = false; }
    }

    private Task YieldBrowseLayoutAsync()
    {
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => completion.TrySetResult())) completion.TrySetResult();
        return completion.Task;
    }

    private async Task RestoreBrowseAnchorAsync((string Key, double Y)? anchor)
    {
        smoothWheelScroller.Stop();
        if (anchor is not { } value || resultScroll is null) return;
        // ScrollIntoView and native collection anchoring can finish after this
        // callback. Keep extending=true through layout so those transient offsets
        // cannot start a reverse fetch and immediately restore evicted rows.
        Items.ScrollIntoView(value.Key, ScrollIntoViewAlignment.Leading);
        await YieldBrowseLayoutAsync(); if (disposed) return; Items.UpdateLayout();
        if (Items.ContainerFromItem(value.Key) is ListViewItem container)
        {
            var y = container.TransformToVisual(Items).TransformPoint(new Point()).Y;
            resultScroll.ChangeView(null, resultScroll.VerticalOffset + y - value.Y, null, true);
        }
        await YieldBrowseLayoutAsync();
    }
}
