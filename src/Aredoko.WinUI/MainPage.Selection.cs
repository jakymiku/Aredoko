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
    {var index=rows.FindIndex(row=>row.Id==id);return index<0?null:new(id,browseStart+index);}
    private void BindLibrarySelection()
    {
        if(librarySelection.SessionId==resultSession?.Id)return;
        selectionPreparation?.Cancel();librarySelection.Bind(resultSession?.Id,resultSession?.Total??0);UpdateLibrarySelectionTools();
    }
    private string FormatSelectionSummaryDetails(bool summarizeShelves=true)
    {
        if(librarySelection.Count==0)return "";
        var selectedRows=rows.Where(row=>librarySelection.Contains(row.Id)).ToArray();
        if(selectedRows.Length==0)return $"表示外に {librarySelection.Count:N0} 件選択中";
        var titles=string.Join("、",selectedRows.Take(3).Select(row=>row.Title));
        var extra=librarySelection.Count-Math.Min(3,selectedRows.Length);
        if(extra>0)titles+=$" ほか{extra:N0}件";
        var favorites=selectedRows.Count(row=>row.Favorite);
        var outside=librarySelection.Count-selectedRows.Length;
        var shelves=selectedRows.SelectMany(row=>row.ShelfIds.Length>0?row.ShelfIds.Select(ShelfName):string.IsNullOrWhiteSpace(row.Shelf)?[]:new[]{row.Shelf}).Where(name=>!string.IsNullOrWhiteSpace(name)).Distinct().ToArray();
        var shelfLabel=shelves.Length>0?"棚: "+ShelfProtocol.SummarizeNames(shelves,maxVisible:summarizeShelves?3:0):"棚なし";
        return $"対象: {titles}\n現在: お気に入り {favorites:N0}/{selectedRows.Length:N0} 件{(outside>0?$"（一覧外 {outside:N0} 件）":"")} · {shelfLabel}";
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
        folderSettingsActive=false;folderDraft=null;DetailKindBadge.Visibility=Visibility.Collapsed;DetailPaneTitle.Visibility=Visibility.Visible;DetailPaneTitle.Text="選択した作品";
        FolderEditorPanel.Visibility=Editor.Visibility=Visibility.Collapsed;SelectionSummaryScroll.Visibility=Visibility.Visible;
        SelectionSummaryText.Text=$"{librarySelection.Count:N0} 件選択中";
        UpdateSelectionSummaryDetails();
    }
    private void UpdateLibrarySelectionTools()
    {
        var outside=librarySelection.Ids.Count(id=>rows.All(row=>row.Id!=id));
        SelectionCountText.Text=preparingSelection?"選択中…":$"{librarySelection.Count:N0} 件選択"+(outside>0?$"（表示外 {outside:N0} 件）":"");
        SelectionTools.Visibility=preparingSelection||librarySelection.Count>1||outside>0?Visibility.Visible:Visibility.Collapsed;
        var canActDirect=!preparingSelection&&librarySelection.Count>0;
        SelectionDirectFavoriteButton.Visibility=SelectionDirectShelfButton.Visibility=canActDirect?Visibility.Visible:Visibility.Collapsed;
        SelectionDirectFavoriteButton.IsEnabled=SelectionDirectShelfButton.IsEnabled=canActDirect&&!saving&&!dialogOpen;
        SelectionBulkActions.Visibility=librarySelection.Count>1?Visibility.Visible:Visibility.Collapsed;
        CancelSelectionPreparation.Visibility=preparingSelection?Visibility.Visible:Visibility.Collapsed;
        SelectionSummaryText.Text=$"{librarySelection.Count:N0} 件選択中";
        UpdateSelectionSummaryDetails();
        FooterSelection.Text=$"{librarySelection.Count:N0} 件選択";
        FooterSelection.Visibility=librarySelection.Count>0?Visibility.Visible:Visibility.Collapsed;
        FooterSelectionActions.Visibility=librarySelection.Count>1?Visibility.Visible:Visibility.Collapsed;
        SelectionBulkActions.IsEnabled=FooterBulkActions.IsEnabled=FooterClearSelection.IsEnabled=!saving&&!dialogOpen&&!preparingSelection;
        if(SelectVisibleItemsMenuItem is not null)
        {
            var overLimit=rows.Count>LibrarySelection.Maximum;
            SelectVisibleItemsMenuItem.Text=overLimit
                ? $"表示中をすべて選択（上限 {LibrarySelection.Maximum} 件）"
                : "表示中をすべて選択";
            SelectVisibleItemsMenuItem.IsEnabled=!overLimit&&!saving&&!dialogOpen&&!preparingSelection&&rows.Count>0&&resultSession is not null;
            if(SelectFirstMaxItemsMenuItem is not null)
            {
                SelectFirstMaxItemsMenuItem.Text=$"先頭 {LibrarySelection.Maximum} 件を選択";
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
                        ? $"ここまで範囲選択（{spanCount:N0} 件・上限 {LibrarySelection.Maximum} 件）"
                        : $"ここまで範囲選択（{spanCount:N0} 件）";
                    SelectRangeSpanMenuItem.IsEnabled=!overSpanLimit&&!saving&&!dialogOpen&&!preparingSelection&&resultSession is not null&&resultWindow is not null;
                }
                else
                {
                    SelectRangeSpanMenuItem.Visibility=Visibility.Collapsed;
                    SelectRangeSpanMenuItem.Text="ここまで範囲選択";
                    SelectRangeSpanMenuItem.IsEnabled=false;
                }
            }
        }
        DetailsButton.IsEnabled=!saving&&!preparingSelection&&(librarySelection.Count>0||active is not null);
        ClearSelectionButton.IsEnabled=!saving&&!preparingSelection&&!dialogOpen;
        foreach(var container in containerCleanup.Keys.ToArray())
        {
            UpdateSelectionFrame(container);
            if(container.Tag is int id&&rows.FirstOrDefault(row=>row.Id==id) is {} row)container.ContextFlyout=SimilarityMenu(row);
        }
    }
    private void ApplyLibrarySelection()
    {
        if(!saving)SetSelectionSaveStatus("");
        var row=librarySelection.Count==1?rows.FirstOrDefault(item=>librarySelection.Contains(item.Id)):null;
        if(row is not null){ShowItemDetailsPane();ApplySelectedRow(row);}
        else
        {
            active=null;detailCancellation?.Cancel();DetailPreview.Source=null;Editor.IsEnabled=false;
            if(librarySelection.Count>0&&Details.IsPaneOpen)ShowSelectionSummary();
            else if(librarySelection.Count==0&&!folderSettingsActive)Details.IsPaneOpen=false;
        }
        UpdateLibrarySelectionTools();
    }
    private async Task ChangeLibrarySelectionAsync()
    {
        foreach(var container in containerCleanup.Keys.ToArray())UpdateSelectionFrame(container);
        if(populating||!ready||disposed)return;
        if(saving||preparingSelection||dialogOpen||!await transitions.WaitAsync(0)){RestoreSelection();return;}
        var detailsWereOpen=Details.IsPaneOpen;
        try
        {
            var selected=Items.SelectedItems.OfType<string>().Select(RowForKey).Where(row=>row is not null).Select(row=>row!.Id).ToArray();
            if(selected.Length==1&&librarySelection.Count==1&&librarySelection.Contains(selected[0]))
            {
                if(detailsWereOpen&&active is not null)Details.IsPaneOpen=true;
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
            else librarySelection.Visible(rows.Select((row,index)=>new ResultPosition(row.Id,browseStart+index)).ToArray(),selected,!SelectionKey(VirtualKey.Shift)&&selected.Length>0?selected[^1]:null);
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
            Notice($"一度に {LibrarySelection.Maximum} 件まで","検索や棚で絞り込んでから選択してください",InfoBarSeverity.Warning);
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
        finally{preparingSelection=false;if(!disposed)UpdateLibrarySelectionTools();transitions.Release();if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
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
        try{if(await ConfirmDiscardAsync()){librarySelection.Clear();active=null;RestoreSelection();ApplyLibrarySelection();}}
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
        var summary=new MenuFlyoutItem{Text=$"{expected.Length:N0} 件の詳細",IsEnabled=enabled};AutomationProperties.SetAutomationId(summary,"BulkDetails");
        summary.Click+=(_,_)=>{ShowSelectionSummary();Details.IsPaneOpen=true;};menu.Items.Add(summary);
        foreach(var (label,id,operation) in new[]{("お気に入りに登録","BulkFavoriteAdd",SelectionOperation.FavoriteAdd),("お気に入りを解除","BulkFavoriteRemove",SelectionOperation.FavoriteRemove),("棚に追加…","BulkShelfAdd",SelectionOperation.ShelvesAdd),("棚から外す…","BulkShelfRemove",SelectionOperation.ShelvesRemove)})
        {
            var action=new MenuFlyoutItem{Text=label,IsEnabled=enabled};AutomationProperties.SetAutomationId(action,id);
            action.Click+=async(_,_)=>{if(session==resultSession?.Id&&expected.SequenceEqual(librarySelection.Ids))await EditLibrarySelectionAsync(operation);};menu.Items.Add(action);
        }
        menu.Items.Add(new MenuFlyoutSeparator());
        var clear=new MenuFlyoutItem{Text="選択を解除",IsEnabled=enabled};AutomationProperties.SetAutomationId(clear,"BulkClearSelection");
        clear.Click+=ClearLibrarySelection_Click;menu.Items.Add(clear);
        return menu;
    }
    private async void SelectVisibleItems_Click(object sender,RoutedEventArgs e)=>await SelectLoadedRowsAsync(capToMaximum:false);
    private async void SelectFirstMaxItems_Click(object sender,RoutedEventArgs e)=>await SelectLoadedRowsAsync(capToMaximum:true);
    private async Task SelectLoadedRowsAsync(bool capToMaximum)
    {
        CloseBrowseMenus();
        var overLimit=rows.Count>LibrarySelection.Maximum;
        if(!ready||disposed||saving||dialogOpen||preparingSelection||rows.Count==0||resultSession is null
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
            var visiblePositions=rows.Select((row,index)=>new ResultPosition(row.Id,browseStart+index)).ToArray();
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
    private void SetSelectionSaveStatus(string text)
    {
        SelectionEditStatus.Text=SelectionInlineStatus.Text=text;
        SelectionEditStatus.Visibility=SelectionInlineStatus.Visibility=string.IsNullOrEmpty(text)?Visibility.Collapsed:Visibility.Visible;
    }
    private async Task EditLibrarySelectionAsync(SelectionOperation operation)
    {
        if(disposed||saving||dialogOpen||preparingSelection||librarySelection.Count==0||resultSession is not {} session||librarySelection.SessionId!=session.Id||!await transitions.WaitAsync(0))return;
        saving=true;searchTimer.Stop();var ids=librarySelection.Ids.ToArray();var favorite=operation is SelectionOperation.FavoriteAdd or SelectionOperation.FavoriteRemove;var committed=false;var detailsWereOpen=Details.IsPaneOpen;
        SetSelectionSaveStatus("保存しています…");
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
                var picked=await PickShelfIdsAsync(operation==SelectionOperation.ShelvesAdd?"選択した作品を棚に追加":"選択した作品を棚から外す",[],
                    operation==SelectionOperation.ShelvesAdd?"指定した棚を追加します。ほかの棚への所属はそのまま残ります。":"指定した棚からだけ外します。作品と元ファイルは残ります。","BulkShelfChoice",allowCreate:operation==SelectionOperation.ShelvesAdd);
                if(picked is null||picked.Length==0)return;shelves=picked;
            }
            var kept=false;
            if(favorite)kept=await session.EditFavoritesAsync(ids,operation==SelectionOperation.FavoriteAdd,CancellationToken.None);
            else await session.EditSelectionAsync(ids,operation,shelves,CancellationToken.None);
            committed=true;
            if(!kept)SetSelectionSaveStatus("保存済み・一覧を更新しています…");
            if(favorite)foreach(var row in rows.Where(row=>ids.Contains(row.Id))){row.Favorite=operation==SelectionOperation.FavoriteAdd;RefreshFavoriteCard(row);}
            if(favorite&&active is {} selected&&ids.Contains(selected.Id))
            {
                // A one-item selection may still have an unsaved tag/shelf draft.
                // A retained snapshot needs only the saved favorite flag updated.
                var value=operation==SelectionOperation.FavoriteAdd;
                saved=saved with {Favorite=value};selected.Favorite=value;updatingFavorite=true;
                try{SyncFavoriteToggle(value);}finally{updatingFavorite=false;}
            }
            if(detailsWereOpen&&!disposed)Details.IsPaneOpen=true;
            if(!kept)await RefreshResultRowsAfterEditAsync(favoriteOnly:favorite);
            UpdateLibrarySelectionTools();if(!resultsNeedRefresh)Notice("保存しました",$"{ids.Length:N0} 件の整理を保存しました。");
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            saving=false;dialogOpen=false;transitions.Release();
            if(!disposed)
            {
                foreach(var button in SelectionSummaryPanel.Children.OfType<Button>())button.IsEnabled=true;
                SetSelectionSaveStatus(committed?(resultsNeedRefresh?"保存済みです。一覧を検索し直してください。":$"{ids.Length:N0} 件を保存しました。") : "");
                if(detailsWereOpen&&(active is not null||librarySelection.Count>0))
                {
                    if(active is null)ShowSelectionSummary();
                    Details.IsPaneOpen=true;
                }
                UpdateLibrarySelectionTools();
                UpdateDirty();
                if(PendingSearch){searchTimer.Stop();searchTimer.Start();}
            }
        }
    }
}
