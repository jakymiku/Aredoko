using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.System;
namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private readonly LibrarySelection librarySelection=new();
    private CancellationTokenSource? selectionPreparation;
    private bool preparingSelection;
    private static bool SelectionKey(VirtualKey key)=>(Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(key)&Windows.UI.Core.CoreVirtualKeyStates.Down)!=0;
    private ResultPosition? SelectionPosition(int id)
        => ordinalById.TryGetValue(id, out var ord) ? new ResultPosition(id, ord) : null;
    private void BindLibrarySelection()
    {
        if(librarySelection.SessionId==resultSession?.Id)return;
        selectionPreparation?.Cancel();librarySelection.Bind(resultSession?.Id,resultSession?.Total??0);UpdateLibrarySelectionTools();
    }
    private string FormatSelectionSummaryDetails(bool summarizeShelves=true)
    {
        if(librarySelection.Count==0)return "";
        var selectedRows=librarySelection.Ids.Select(id=>rowById.GetValueOrDefault(id)).Where(row=>row is not null).Select(row=>row!).ToArray();
        if(selectedRows.Length==0)return AppText.L($"表示外に {librarySelection.Count:N0} 件選択中",$"{librarySelection.Count:N0} selected outside view");
        var titles=string.Join(AppText.L("、",", "),selectedRows.Take(3).Select(row=>row.Title));
        var extra=librarySelection.Count-Math.Min(3,selectedRows.Length);
        if(extra>0)titles+=AppText.L($" ほか{extra:N0}件",$" and {extra:N0} more");
        var favorites=selectedRows.Count(row=>row.Favorite);
        var outside=librarySelection.Count-selectedRows.Length;
        var shelves=selectedRows.SelectMany(row=>row.ShelfIds.Length>0?row.ShelfIds.Select(ShelfName):string.IsNullOrWhiteSpace(row.Shelf)?[]:new[]{row.Shelf}).Where(name=>!string.IsNullOrWhiteSpace(name)).Distinct().ToArray();
        var shelfLabel=shelves.Length>0?AppText.L("棚: ","Shelves: ")+ShelfProtocol.SummarizeNames(shelves,maxVisible:summarizeShelves?3:0):AppText.L("棚なし","No shelf");
        return AppText.L(
            $"対象: {titles}\n現在: お気に入り {favorites:N0}/{selectedRows.Length:N0} 件{(outside>0?$"（一覧外 {outside:N0} 件）":"")} · {shelfLabel}",
            $"Items: {titles}\nSelected: Favorites {favorites:N0}/{selectedRows.Length:N0}{(outside>0?$" ({outside:N0} outside list)":"")} · {shelfLabel}");
    }
    private void UpdateSelectionSummaryDetails()
    {
        var details=FormatSelectionSummaryDetails();
        SelectionSummaryDetails.Text=details;
        ToolTipService.SetToolTip(SelectionSummaryDetails,details.Length>0?FormatSelectionSummaryDetails(summarizeShelves:false):null);
        SelectionSummaryDetails.Visibility=details.Length>0?Visibility.Visible:Visibility.Collapsed;
    }
    private void ShowSelectionSummary()
    {
        folderSettingsActive=false;folderDraft=null;DetailKindBadge.Visibility=Visibility.Collapsed;DetailPaneTitle.Visibility=Visibility.Visible;DetailPaneTitle.Text=AppText.L("選択した作品","Selected items");
        FolderEditorPanel.Visibility=Editor.Visibility=Visibility.Collapsed;SelectionSummaryScroll.Visibility=Visibility.Visible;
        SelectionSummaryText.Text=AppText.L($"{librarySelection.Count:N0} 件選択中",$"{librarySelection.Count:N0} selected");
        UpdateSelectionSummaryDetails();
    }
    private void UpdateLibrarySelectionTools()
    {
        var outside=librarySelection.Ids.Count(id=>!rowById.ContainsKey(id));
        SelectionCountText.Text=preparingSelection?AppText.L("選択中…","Selecting…"):AppText.L($"{librarySelection.Count:N0} 件選択",$"{librarySelection.Count:N0} selected")+(outside>0?AppText.L($"（表示外 {outside:N0} 件）",$" ({outside:N0} outside view)"):"");
        SelectionTools.Visibility=preparingSelection||librarySelection.Count>1||outside>0?Visibility.Visible:Visibility.Collapsed;
        var canActDirect=!preparingSelection&&librarySelection.Count>0;
        SelectionDirectFavoriteButton.Visibility=SelectionDirectShelfButton.Visibility=canActDirect?Visibility.Visible:Visibility.Collapsed;
        SelectionDirectFavoriteButton.IsEnabled=SelectionDirectShelfButton.IsEnabled=canActDirect&&!saving&&!dialogOpen;
        SelectionBulkActions.Visibility=librarySelection.Count>1?Visibility.Visible:Visibility.Collapsed;
        CancelSelectionPreparation.Visibility=preparingSelection?Visibility.Visible:Visibility.Collapsed;
        SelectionSummaryText.Text=AppText.L($"{librarySelection.Count:N0} 件選択中",$"{librarySelection.Count:N0} selected");
        UpdateSelectionSummaryDetails();
        FooterSelection.Text=AppText.L($"{librarySelection.Count:N0} 件選択",$"{librarySelection.Count:N0} selected");
        ToolTipService.SetToolTip(FooterSelection,librarySelection.Count==1?AppText.L("Space: 詳細・タグ編集を開閉 / Enter: 作品を開く","Space: Toggle Details & Tag Editor / Enter: Open item"):null);
        FooterSelection.Visibility=librarySelection.Count>0?Visibility.Visible:Visibility.Collapsed;
        FooterSelectionActions.Visibility=Visibility.Collapsed;
        SelectionBulkActions.IsEnabled=FooterBulkActions.IsEnabled=FooterClearSelection.IsEnabled=!saving&&!dialogOpen&&!preparingSelection;
        if(SelectVisibleItemsMenuItem is not null)
        {
            var loadedCount=rowByOrdinal.Count;
            var overLimit=loadedCount>LibrarySelection.Maximum;
            SelectVisibleItemsMenuItem.Text=overLimit
                ? AppText.L($"表示中をすべて選択（上限 {LibrarySelection.Maximum} 件）",$"Select all loaded (max {LibrarySelection.Maximum})")
                : AppText.L("表示中をすべて選択","Select all loaded");
            SelectVisibleItemsMenuItem.IsEnabled=!overLimit&&!saving&&!dialogOpen&&!preparingSelection&&loadedCount>0&&resultSession is not null;
            if(SelectFirstMaxItemsMenuItem is not null)
            {
                SelectFirstMaxItemsMenuItem.Text=AppText.L($"先頭 {LibrarySelection.Maximum} 件を選択",$"Select first {LibrarySelection.Maximum}");
                SelectFirstMaxItemsMenuItem.Visibility=overLimit?Visibility.Visible:Visibility.Collapsed;
                SelectFirstMaxItemsMenuItem.IsEnabled=overLimit&&!saving&&!dialogOpen&&!preparingSelection&&resultSession is not null;
            }
            if(SelectRangeSpanMenuItem is not null)
            {
                if(librarySelection.Anchor is {} currentAnchor&&librarySelection.PreviousAnchor is {} prevAnchor&&prevAnchor.Id!=currentAnchor.Id)
                {
                    var spanCount=Math.Abs((long)currentAnchor.Ordinal-prevAnchor.Ordinal)+1;
                    var overSpanLimit=spanCount>LibrarySelection.Maximum;
                    SelectRangeSpanMenuItem.Visibility=Visibility.Visible;
                    SelectRangeSpanMenuItem.Text=overSpanLimit
                        ? AppText.L($"ここまで範囲選択（{spanCount:N0} 件・上限 {LibrarySelection.Maximum} 件）",$"Select range to here ({spanCount:N0}, max {LibrarySelection.Maximum})")
                        : AppText.L($"ここまで範囲選択（{spanCount:N0} 件）",$"Select range to here ({spanCount:N0})");
                    SelectRangeSpanMenuItem.IsEnabled=!overSpanLimit&&!saving&&!dialogOpen&&!preparingSelection&&resultSession is not null&&resultWindow is not null;
                }
                else
                {
                    SelectRangeSpanMenuItem.Visibility=Visibility.Collapsed;
                    SelectRangeSpanMenuItem.Text=AppText.L("ここまで範囲選択","Select range to here");
                    SelectRangeSpanMenuItem.IsEnabled=false;
                }
            }
        }
        DetailsButton.IsEnabled=!saving&&!preparingSelection&&(librarySelection.Count>0||active is not null);
        ClearSelectionButton.IsEnabled=!saving&&!preparingSelection&&!dialogOpen;
        foreach(var container in realizedItems.ToArray())
        {
            UpdateSelectionFrame(container);
        }
    }
    private void ApplyLibrarySelection()
    {
        if(!saving)SetSelectionSaveStatus("");
        var row=librarySelection.Count==1&&rowById.TryGetValue(librarySelection.Ids.First(),out var found)?found:null;
        if(row is not null){ShowItemDetailsPane();if(ViewerOptions.Value.OpenDetailsOnClick)Details.IsPaneOpen=true;ApplySelectedRow(row);}
        else
        {
            active=null;initialSavedItemId=null;detailCancellation?.Cancel();DetailPreview.Source=null;Editor.IsEnabled=false;
            if(librarySelection.Count>0&&Details.IsPaneOpen)ShowSelectionSummary();
            else if(librarySelection.Count==0&&!folderSettingsActive)Details.IsPaneOpen=false;
        }
        UpdateLibrarySelectionTools();
    }
    private async Task ChangeLibrarySelectionAsync()
    {
        foreach(var container in realizedItems.ToArray())UpdateSelectionFrame(container);
        if(populating||!ready||disposed)return;
        if(saving||preparingSelection||dialogOpen||!await transitions.WaitAsync(0)){RestoreSelection();return;}
        var detailsWereOpen=Details.IsPaneOpen;
        try
        {
            var selected=Items.SelectedItems.OfType<string>().Select(RowForKey).Where(row=>row is not null).Select(row=>row!.Id).ToArray();
            if(selected.Length==1&&librarySelection.Count==1&&librarySelection.Contains(selected[0]))
            {
                if((detailsWereOpen||ViewerOptions.Value.OpenDetailsOnClick)&&active is not null)
                {
                    ShowItemDetailsPane();
                    Details.IsPaneOpen=true;
                    _ = ShowDetailPreviewAsync(active, preserveExisting:true);
                }
                return;
            }
            if(!await ConfirmDiscardAsync())
            {
                RestoreSelection();
                if(detailsWereOpen&&(active is not null||librarySelection.Count>0))Details.IsPaneOpen=true;
                return;
            }
            BindLibrarySelection();
            if(selected.Length==1&&!SelectionKey(VirtualKey.Control)&&!SelectionKey(VirtualKey.Shift))librarySelection.Single(SelectionPosition(selected[0])!);
            else librarySelection.Visible(rowByOrdinal.Select(kv=>new ResultPosition(kv.Value.Id,kv.Key)).ToArray(),selected,!SelectionKey(VirtualKey.Shift)&&selected.Length>0?selected[^1]:null);
            ApplyLibrarySelection();
            if(detailsWereOpen&&(active is not null||librarySelection.Count>0))Details.IsPaneOpen=true;
        }
        catch(Exception ex){RestoreSelection();Failure(ex);}
        finally{transitions.Release();}
    }
    private async void LibrarySelectionPointerPressed(object sender,PointerRoutedEventArgs args)
    {
        if(args.Handled||!args.GetCurrentPoint(Items).Properties.IsLeftButtonPressed||(args.KeyModifiers&VirtualKeyModifiers.Shift)==0)return;
        for(var source=args.OriginalSource as DependencyObject;source is not null&&source!=Items;source=VisualTreeHelper.GetParent(source))
            if(source is ListViewItem{Tag:int id}&&SelectionPosition(id) is {} target)
            {args.Handled=true;previewClicks.Reset();await SelectLibraryRangeAsync(target,(args.KeyModifiers&VirtualKeyModifiers.Control)!=0);return;}
    }
    private async Task SelectLibraryRangeAsync(ResultPosition target,bool additive,ResultPosition? explicitOrigin=null)
    {
        if(disposed||saving||dialogOpen||preparingSelection||resultSession is not {} session||resultWindow is not {} window)return;
        var origin=explicitOrigin??librarySelection.Anchor;
        if(origin is not null&&Math.Abs((long)target.Ordinal-origin.Ordinal)+1>LibrarySelection.Maximum)
        {
            Notice(AppText.L($"一度に {LibrarySelection.Maximum} 件まで",$"Up to {LibrarySelection.Maximum} items at once"),AppText.L("検索や棚で絞り込んでから選択してください","Narrow your search or shelves before selecting."),InfoBarSeverity.Warning);
            return;
        }
        if(!await transitions.WaitAsync(0))return;
        var detailsWereOpen=Details.IsPaneOpen;
        var previousTarget=librarySelection.Anchor;
        var previousOrigin=librarySelection.PreviousAnchor;
        var anchorSwapped=false;
        try
        {
            if(!await ConfirmDiscardAsync())
            {
                if(detailsWereOpen&&(active is not null||librarySelection.Count>0))Details.IsPaneOpen=true;
                return;
            }
            BindLibrarySelection();
            if(explicitOrigin is {} originPos)
            {
                librarySelection.Single(originPos);
                anchorSwapped=true;
            }
            selectionPreparation?.Dispose();selectionPreparation=new();preparingSelection=true;UpdateLibrarySelectionTools();
            await librarySelection.RangeAsync(target,additive,async(offset,count,cancellation)=>
            {var result=await window.ReadAsync(offset,count,cancellation);return result.Items.Select(row=>row.Id).ToArray();},selectionPreparation.Token);
            if(disposed||!ReferenceEquals(session,resultSession))return;
            RestoreSelection();ApplyLibrarySelection();
            if(detailsWereOpen&&(active is not null||librarySelection.Count>0))Details.IsPaneOpen=true;
        }
        catch(OperationCanceledException)
        {
            if(!disposed&&anchorSwapped&&ReferenceEquals(session,resultSession)&&previousTarget is {} restoredTarget)
            {
                if(previousOrigin is {} restoredOrigin)librarySelection.Single(restoredOrigin);
                librarySelection.Single(restoredTarget);
                RestoreSelection();ApplyLibrarySelection();
            }
        }
        catch(Exception ex)
        {
            if(!disposed&&anchorSwapped&&ReferenceEquals(session,resultSession)&&previousTarget is {} restoredTarget)
            {
                if(previousOrigin is {} restoredOrigin)librarySelection.Single(restoredOrigin);
                librarySelection.Single(restoredTarget);
                RestoreSelection();ApplyLibrarySelection();
            }
            if(!disposed){RestoreSelection();Failure(ex);}
        }
        finally{preparingSelection=false;if(!disposed)UpdateLibrarySelectionTools();transitions.Release();if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void SelectRangeSpan_Click(object sender,RoutedEventArgs e)
    {
        CloseBrowseMenus();
        if(librarySelection.Anchor is {} target&&librarySelection.PreviousAnchor is {} origin&&origin.Id!=target.Id)
            await SelectLibraryRangeAsync(target,false,origin);
    }
    private async void ClearLibrarySelection_Click(object sender,RoutedEventArgs e)
    {
        if(saving||dialogOpen||preparingSelection||!await transitions.WaitAsync(0))return;
        try{if(await ConfirmDiscardAsync()){librarySelection.Clear();active=null;initialSavedItemId=null;RestoreSelection();ApplyLibrarySelection();}}
        finally{transitions.Release();}
    }
    private void CancelSelectionPreparation_Click(object sender,RoutedEventArgs e)=>selectionPreparation?.Cancel();
    private void FooterBulkActions_Click(object sender,RoutedEventArgs e)
    {
        if(disposed||saving||dialogOpen||preparingSelection||librarySelection.Count<2)return;
        SelectionMenu().ShowAt(sender as FrameworkElement??FooterBulkActions);
    }
    private MenuFlyout SelectionMenu()
    {
        var menu=new MenuFlyout();var expected=librarySelection.Ids.ToArray();var session=resultSession?.Id;
        var enabled=!saving&&!dialogOpen&&!preparingSelection;
        var summary=new MenuFlyoutItem{Text=AppText.L($"{expected.Length:N0} 件の詳細",$"Details for {expected.Length:N0}"),IsEnabled=enabled};AutomationProperties.SetAutomationId(summary,"BulkDetails");
        summary.Click+=(_,_)=>{ShowSelectionSummary();Details.IsPaneOpen=true;};menu.Items.Add(summary);
        foreach(var (label,id,operation) in new[]{(AppText.L("お気に入りに登録","Add to favorites"),"BulkFavoriteAdd",SelectionOperation.FavoriteAdd),(AppText.L("お気に入りを解除","Remove from favorites"),"BulkFavoriteRemove",SelectionOperation.FavoriteRemove),(AppText.L("棚に追加…","Add to shelves…"),"BulkShelfAdd",SelectionOperation.ShelvesAdd),(AppText.L("棚から外す…","Remove from shelves…"),"BulkShelfRemove",SelectionOperation.ShelvesRemove)})
        {
            var action=new MenuFlyoutItem{Text=label,IsEnabled=enabled};AutomationProperties.SetAutomationId(action,id);
            action.Click+=async(_,_)=>{if(session==resultSession?.Id&&expected.SequenceEqual(librarySelection.Ids))await EditLibrarySelectionAsync(operation);};menu.Items.Add(action);
        }
        var bulkTagSuggestions=new MenuFlyoutItem{Text=AppText.L("✨ AIタグ候補をまとめて生成","✨ Generate AI tag suggestions"),IsEnabled=enabled};
        AutomationProperties.SetAutomationId(bulkTagSuggestions,"BulkTagSuggestions");
        bulkTagSuggestions.Click+=async(_,_)=>{if(session==resultSession?.Id&&expected.SequenceEqual(librarySelection.Ids))await GenerateSelectionTagSuggestionsAsync();};
        menu.Items.Add(bulkTagSuggestions);
        menu.Items.Add(new MenuFlyoutSeparator());
        var clear=new MenuFlyoutItem{Text=AppText.L("選択を解除","Clear selection"),IsEnabled=enabled};AutomationProperties.SetAutomationId(clear,"BulkClearSelection");
        clear.Click+=ClearLibrarySelection_Click;menu.Items.Add(clear);
        return menu;
    }
    private async void SelectVisibleItems_Click(object sender,RoutedEventArgs e)=>await SelectLoadedRowsAsync(capToMaximum:false);
    private async void SelectFirstMaxItems_Click(object sender,RoutedEventArgs e)=>await SelectLoadedRowsAsync(capToMaximum:true);
    private async Task SelectLoadedRowsAsync(bool capToMaximum)
    {
        CloseBrowseMenus();
        var loadedCount=rowByOrdinal.Count;
        var overLimit=loadedCount>LibrarySelection.Maximum;
        if(!ready||disposed||saving||dialogOpen||preparingSelection||loadedCount==0||resultSession is null
            ||(capToMaximum?!overLimit:overLimit)||!await transitions.WaitAsync(0))return;
        var detailsWereOpen=Details.IsPaneOpen;
        try
        {
            if(!await ConfirmDiscardAsync())
            {
                if(detailsWereOpen&&(active is not null||librarySelection.Count>0))Details.IsPaneOpen=true;
                return;
            }
            BindLibrarySelection();
            var visiblePositions=rowByOrdinal.OrderBy(kv=>kv.Key).Select(kv=>new ResultPosition(kv.Value.Id,kv.Key)).ToArray();
            var selectedIds=(capToMaximum?visiblePositions.Take(LibrarySelection.Maximum):visiblePositions).Select(position=>position.Id).ToArray();
            librarySelection.Clear();
            librarySelection.Visible(visiblePositions,selectedIds,selectedIds[^1]);
            RestoreSelection();ApplyLibrarySelection();
            if(detailsWereOpen&&(active is not null||librarySelection.Count>0))Details.IsPaneOpen=true;
        }
        catch(Exception ex){RestoreSelection();Failure(ex);}
        finally{transitions.Release();}
    }
    private async void SelectionFavoriteAdd_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.FavoriteAdd);
    private async void SelectionFavoriteRemove_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.FavoriteRemove);
    private async void SelectionShelfAdd_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.ShelvesAdd);
    private async void SelectionShelfRemove_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.ShelvesRemove);
    private async void SelectionTagSuggestions_Click(object sender,RoutedEventArgs e)=>await GenerateSelectionTagSuggestionsAsync();

    private CancellationTokenSource? bulkTagGenerationCts;

    private async Task GenerateSelectionTagSuggestionsAsync()
    {
        if(disposed||saving||dialogOpen||preparingSelection||librarySelection.Count==0||resultSession is not {} session||librarySelection.SessionId!=session.Id||!await transitions.WaitAsync(0))return;
        saving=true;searchTimer.Stop();
        var ids=librarySelection.Ids.ToArray();
        var detailsWereOpen=Details.IsPaneOpen;
        var loadedRows=new Dictionary<int,MediaRow>(rowById);
        var succeeded=0;var skipped=0;var failed=0;
        string? availabilityError=null;
        var summaryText="";
        bulkTagGenerationCts?.Dispose();
        bulkTagGenerationCts=new CancellationTokenSource();
        var cts=bulkTagGenerationCts;
        try
        {
            await Task.Yield();if(disposed)return;
            UpdateLibrarySelectionTools();
            foreach(var button in SelectionSummaryPanel.Children.OfType<Button>())button.IsEnabled=false;
            SetSelectionSaveStatus(AppText.L($"AIタグ候補の対象を確認中… (0/{ids.Length:N0} 件)",$"Checking items for AI tag suggestions… (0/{ids.Length:N0})"));

            var targets=new List<int>(ids.Length);
            foreach(var id in ids)
            {
                if(disposed||cts.IsCancellationRequested)break;
                MediaRow? row;
                if(!loadedRows.TryGetValue(id,out row))
                {
                    try{row=await api.TagReviews.ItemAsync(id,cts.Token);}
                    catch(OperationCanceledException) when(cts.IsCancellationRequested){break;}
                    catch{skipped++;continue;}
                }
                if(TagReviewProtocol.CanOpen(row))targets.Add(id);
                else skipped++;
            }

            if(targets.Count==0)
            {
                summaryText=AppText.L("選択した作品にAIタグ候補の対象（画像・本）がありません。","None of the selected items support AI tag suggestions (images/books).");
                Notice(AppText.L("AIタグ候補の対象がありません","No eligible items for AI tag suggestions"),summaryText,InfoBarSeverity.Warning);
                return;
            }

            var firstHistory=await api.TagReviews.HistoryAsync(targets[0],null,cts.Token);
            if(!firstHistory.Available)
            {
                availabilityError=AppText.TranslateBackend(firstHistory.Reason);
                summaryText=AppText.L("AIタグ候補を生成できません","Cannot generate AI tag suggestions");
                Notice(AppText.L("AIタグ候補を作成できません","Cannot create AI tag suggestions"),availabilityError,InfoBarSeverity.Warning);
                return;
            }

            var done=0;
            foreach(var id in targets)
            {
                if(disposed||cts.IsCancellationRequested)break;
                SetSelectionSaveStatus(AppText.L($"AIタグ候補を生成中… ({done:N0}/{targets.Count:N0} 件)",$"Generating AI tag suggestions… ({done:N0}/{targets.Count:N0})"));
                var reqId=Guid.NewGuid().ToString("N");
                try
                {
                    await api.TagReviews.GenerateAsync(id,reqId,cts.Token);
                    succeeded++;
                }
                catch(OperationCanceledException) when(cts.IsCancellationRequested)
                {
                    try{await api.TagReviews.CancelAsync(reqId,CancellationToken.None);}catch{}
                    break;
                }
                catch(Exception ex)
                {
                    AppLog.Error(ex);
                    failed++;
                    if(succeeded==0&&(ex.Message.Contains("未導入")||ex.Message.Contains("not installed",StringComparison.OrdinalIgnoreCase)||ex.Message.Contains("missing",StringComparison.OrdinalIgnoreCase)))
                    {
                        availabilityError=AppText.TranslateBackend(ex.Message);
                        break;
                    }
                }
                done++;
            }

            if(availabilityError is not null)
            {
                summaryText=availabilityError;
                Notice(AppText.L("AIタグ候補を作成できません","Cannot create AI tag suggestions"),availabilityError,InfoBarSeverity.Warning);
            }
            else
            {
                var detail=AppText.L($"{succeeded:N0} 件の候補を作成しました（詳細の「✨ AI候補」または「AIタグ候補（文字）」検索で確認できます）。",$"Created suggestions for {succeeded:N0} items (review them under \"✨ AI Suggestions\" in Details or \"AI Tag Suggestions (Text)\" search).")
                    +(skipped>0?AppText.L($" 対象外 {skipped:N0} 件はスキップ。",$" Skipped {skipped:N0} unsupported."):"")
                    +(failed>0?AppText.L($" 失敗 {failed:N0} 件。",$" Failed {failed:N0}."):"");
                summaryText=AppText.L($"AIタグ候補：{succeeded:N0} 件生成",$"AI tag suggestions: {succeeded:N0} created")+(skipped>0?AppText.L($" · 対象外 {skipped:N0} 件",$" · {skipped:N0} unsupported"):"")+(failed>0?AppText.L($" · 失敗 {failed:N0} 件",$" · {failed:N0} failed"):"");
                Notice(AppText.L("AIタグ候補を生成しました","Generated AI tag suggestions"),detail,failed>0?InfoBarSeverity.Warning:InfoBarSeverity.Success);
                Status.IsOpen=true;
            }
        }
        catch(OperationCanceledException) when(cts.IsCancellationRequested)
        {
            summaryText=AppText.L("AIタグ候補の生成を中止しました。","Canceled AI tag suggestion generation.");
        }
        catch(Exception ex)
        {
            summaryText=ex.Message;
            Failure(ex);
        }
        finally
        {
            if(ReferenceEquals(bulkTagGenerationCts,cts))bulkTagGenerationCts=null;
            cts.Dispose();
            saving=false;dialogOpen=false;transitions.Release();
            if(!disposed)
            {
                foreach(var button in SelectionSummaryPanel.Children.OfType<Button>())button.IsEnabled=true;
                SetSelectionSaveStatus(summaryText);
                if(detailsWereOpen&&(active is not null||librarySelection.Count>0))
                {
                    if(active is null)ShowSelectionSummary();
                    Details.IsPaneOpen=true;
                }
                UpdateLibrarySelectionTools();
                UpdateDirty();
                if(PendingAutoSearch){searchTimer.Stop();searchTimer.Start();}
            }
        }
    }
    private void SetSelectionSaveStatus(string text)
    {
        SelectionEditStatus.Text=SelectionInlineStatus.Text=text;
        SelectionEditStatus.Visibility=SelectionInlineStatus.Visibility=string.IsNullOrEmpty(text)?Visibility.Collapsed:Visibility.Visible;
    }
    private async Task EditLibrarySelectionAsync(SelectionOperation operation)
    {
        if(disposed||saving||dialogOpen||preparingSelection||librarySelection.Count==0||resultSession is not {} session||librarySelection.SessionId!=session.Id||!await transitions.WaitAsync(0))return;
        saving=true;searchTimer.Stop();var ids=librarySelection.Ids.ToArray();var favorite=operation is SelectionOperation.FavoriteAdd or SelectionOperation.FavoriteRemove;var committed=false;var detailsWereOpen=Details.IsPaneOpen;
        SetSelectionSaveStatus(AppText.L("保存しています…","Saving…"));
        try
        {
            // Let the invoking native provider finish before disabling its parent.
            await Task.Yield();if(disposed)return;
            UpdateLibrarySelectionTools();
            foreach(var button in SelectionSummaryPanel.Children.OfType<Button>())button.IsEnabled=false;
            long[] shelves=[];
            if(!favorite)
            {
                shelfDescriptors=(await api.Shelves.ListAsync()).ToList();
                var picked=await PickShelfIdsAsync(operation==SelectionOperation.ShelvesAdd?AppText.L("選択した作品を棚に追加","Add selected items to shelves"):AppText.L("選択した作品を棚から外す","Remove selected items from shelves"),[],
                    operation==SelectionOperation.ShelvesAdd?AppText.L("指定した棚を追加します。ほかの棚への所属はそのまま残ります。","Adds the selected shelves while keeping other shelf assignments intact."):AppText.L("指定した棚からだけ外します。作品と元ファイルは残ります。","Removes only from the selected shelves. Items and original files remain."),"BulkShelfChoice",allowCreate:operation==SelectionOperation.ShelvesAdd);
                if(picked is null||picked.Length==0)return;shelves=picked;
            }
            var kept=false;
            if(favorite)kept=await session.EditFavoritesAsync(ids,operation==SelectionOperation.FavoriteAdd,CancellationToken.None);
            else await session.EditSelectionAsync(ids,operation,shelves,CancellationToken.None);
            committed=true;
            if(!kept)SetSelectionSaveStatus(AppText.L("保存済み・一覧を更新しています…","Saved — refreshing list…"));
            if(favorite)
            {
                foreach(var id in ids)if(rowById.TryGetValue(id,out var hit)){hit.Favorite=operation==SelectionOperation.FavoriteAdd;RefreshFavoriteCard(hit);}
                foreach(var row in rows.Where(row=>ids.Contains(row.Id)))row.Favorite=operation==SelectionOperation.FavoriteAdd;
            }
            if(favorite&&active is {} selected&&ids.Contains(selected.Id))
            {
                // A one-item selection may still have an unsaved tag/shelf draft.
                // A retained snapshot needs only the saved favorite flag updated.
                var value=operation==SelectionOperation.FavoriteAdd;
                saved=saved with {Favorite=value};
                if(initialSavedItemId==selected.Id)initialSaved=initialSaved with {Favorite=value};
                selected.Favorite=value;updatingFavorite=true;
                try{SyncFavoriteToggle(value);}finally{updatingFavorite=false;}
            }
            if(detailsWereOpen&&!disposed)Details.IsPaneOpen=true;
            if(!kept)await RefreshResultRowsAfterEditAsync(favoriteOnly:favorite);
            UpdateLibrarySelectionTools();if(!resultsNeedRefresh)Notice(AppText.L("保存しました","Saved"),AppText.L($"{ids.Length:N0} 件の整理を保存しました。",$"Saved changes for {ids.Length:N0} items."));
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            saving=false;dialogOpen=false;transitions.Release();
            if(!disposed)
            {
                foreach(var button in SelectionSummaryPanel.Children.OfType<Button>())button.IsEnabled=true;
                SetSelectionSaveStatus(committed?(resultsNeedRefresh?AppText.L("保存済みです。一覧を検索し直してください。","Saved. Run search again to refresh the list."):AppText.L($"{ids.Length:N0} 件を保存しました。",$"Saved {ids.Length:N0} items.")):"");
                if(detailsWereOpen&&(active is not null||librarySelection.Count>0))
                {
                    if(active is null)ShowSelectionSummary();
                    Details.IsPaneOpen=true;
                }
                UpdateLibrarySelectionTools();
                UpdateDirty();
                if(PendingAutoSearch){searchTimer.Stop();searchTimer.Start();}
            }
        }
    }
}
