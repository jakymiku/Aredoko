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
    private void ShowSelectionSummary()
    {
        folderSettingsActive=false;folderDraft=null;DetailPaneTitle.Text="選択した作品";
        FolderEditorPanel.Visibility=Editor.Visibility=Visibility.Collapsed;SelectionSummaryPanel.Visibility=Visibility.Visible;
        SelectionSummaryText.Text=$"{librarySelection.Count:N0} 件を選択しています。";
    }
    private void UpdateLibrarySelectionTools()
    {
        var outside=librarySelection.Ids.Count(id=>rows.All(row=>row.Id!=id));
        SelectionCountText.Text=preparingSelection?"範囲を選択しています…":$"{librarySelection.Count:N0} 件選択"+(outside>0?$"（一覧外 {outside:N0} 件）":"");
        SelectionTools.Visibility=preparingSelection||librarySelection.Count>1||outside>0?Visibility.Visible:Visibility.Collapsed;
        CancelSelectionPreparation.Visibility=preparingSelection?Visibility.Visible:Visibility.Collapsed;
        SelectionSummaryText.Text=$"{librarySelection.Count:N0} 件を選択しています。";
        DetailsButton.IsEnabled=librarySelection.Count>0||active is not null;
        foreach(var container in containerCleanup.Keys.ToArray())
        {
            UpdateSelectionFrame(container);
            if(container.Tag is int id&&rows.FirstOrDefault(row=>row.Id==id) is {} row)container.ContextFlyout=SimilarityMenu(row);
        }
    }
    private void ApplyLibrarySelection()
    {
        if(!saving)SelectionEditStatus.Visibility=Visibility.Collapsed;
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
        try
        {
            var selected=Items.SelectedItems.OfType<string>().Select(RowForKey).Where(row=>row is not null).Select(row=>row!.Id).ToArray();
            if(selected.Length==1&&librarySelection.Count==1&&librarySelection.Contains(selected[0]))return;
            if(!await ConfirmDiscardAsync()){RestoreSelection();return;}
            BindLibrarySelection();
            if(selected.Length==1&&!SelectionKey(VirtualKey.Control)&&!SelectionKey(VirtualKey.Shift))librarySelection.Single(SelectionPosition(selected[0])!);
            else librarySelection.Visible(rows.Select((row,index)=>new ResultPosition(row.Id,browseStart+index)).ToArray(),selected,!SelectionKey(VirtualKey.Shift)&&selected.Length>0?selected[^1]:null);
            ApplyLibrarySelection();
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
    private async Task SelectLibraryRangeAsync(ResultPosition target,bool additive)
    {
        if(disposed||saving||dialogOpen||preparingSelection||resultSession is not {} session||resultWindow is not {} window||!await transitions.WaitAsync(0))return;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            BindLibrarySelection();selectionPreparation?.Dispose();selectionPreparation=new();preparingSelection=true;UpdateLibrarySelectionTools();
            await librarySelection.RangeAsync(target,additive,async(offset,count,cancellation)=>
            {var result=await window.ReadAsync(offset,count,cancellation);return result.Items.Select(row=>row.Id).ToArray();},selectionPreparation.Token);
            if(disposed||!ReferenceEquals(session,resultSession))return;
            RestoreSelection();ApplyLibrarySelection();
        }
        catch(OperationCanceledException){}
        catch(Exception ex){if(!disposed){RestoreSelection();Failure(ex);}}
        finally{preparingSelection=false;if(!disposed)UpdateLibrarySelectionTools();transitions.Release();if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void ClearLibrarySelection_Click(object sender,RoutedEventArgs e)
    {
        if(saving||dialogOpen||preparingSelection||!await transitions.WaitAsync(0))return;
        try{if(await ConfirmDiscardAsync()){librarySelection.Clear();active=null;RestoreSelection();ApplyLibrarySelection();}}
        finally{transitions.Release();}
    }
    private void CancelSelectionPreparation_Click(object sender,RoutedEventArgs e)=>selectionPreparation?.Cancel();
    private MenuFlyout SelectionMenu()
    {
        var menu=new MenuFlyout();var expected=librarySelection.Ids.ToArray();var session=resultSession?.Id;
        var summary=new MenuFlyoutItem{Text=$"{expected.Length:N0} 件の詳細"};AutomationProperties.SetAutomationId(summary,"BulkDetails");
        summary.Click+=(_,_)=>{ShowSelectionSummary();Details.IsPaneOpen=true;};menu.Items.Add(summary);
        foreach(var (label,id,operation) in new[]{("お気に入りに登録","BulkFavoriteAdd",SelectionOperation.FavoriteAdd),("お気に入りを解除","BulkFavoriteRemove",SelectionOperation.FavoriteRemove),("棚に追加…","BulkShelfAdd",SelectionOperation.ShelvesAdd),("棚から外す…","BulkShelfRemove",SelectionOperation.ShelvesRemove)})
        {
            var action=new MenuFlyoutItem{Text=label};AutomationProperties.SetAutomationId(action,id);
            action.Click+=async(_,_)=>{if(session==resultSession?.Id&&expected.SequenceEqual(librarySelection.Ids))await EditLibrarySelectionAsync(operation);};menu.Items.Add(action);
        }
        return menu;
    }
    private async void SelectionFavoriteAdd_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.FavoriteAdd);
    private async void SelectionFavoriteRemove_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.FavoriteRemove);
    private async void SelectionShelfAdd_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.ShelvesAdd);
    private async void SelectionShelfRemove_Click(object sender,RoutedEventArgs e)=>await EditLibrarySelectionAsync(SelectionOperation.ShelvesRemove);
    private async Task EditLibrarySelectionAsync(SelectionOperation operation)
    {
        if(disposed||saving||dialogOpen||preparingSelection||librarySelection.Count==0||resultSession is not {} session||librarySelection.SessionId!=session.Id||!await transitions.WaitAsync(0))return;
        saving=true;searchTimer.Stop();var ids=librarySelection.Ids.ToArray();var favorite=operation is SelectionOperation.FavoriteAdd or SelectionOperation.FavoriteRemove;var committed=false;
        SelectionEditStatus.Text="保存しています…";SelectionEditStatus.Visibility=Visibility.Visible;
        try
        {
            // Let the invoking native provider finish before disabling its parent.
            await Task.Yield();if(disposed)return;
            foreach(var button in SelectionSummaryPanel.Children.OfType<Button>())button.IsEnabled=false;
            long[] shelves=[];
            if(!favorite)
            {
                shelfDescriptors=(await api.Shelves.ListAsync()).ToList();
                var picked=await PickShelfIdsAsync(operation==SelectionOperation.ShelvesAdd?"選択した作品を棚に追加":"選択した作品を棚から外す",[],
                    operation==SelectionOperation.ShelvesAdd?"指定した棚を追加します。ほかの棚への所属はそのまま残ります。":"指定した棚からだけ外します。作品と元ファイルは残ります。","BulkShelfChoice");
                if(picked is null||picked.Length==0)return;shelves=picked;
            }
            await session.EditSelectionAsync(ids,operation,shelves,CancellationToken.None);
            committed=true;
            if(favorite)foreach(var row in rows.Where(row=>ids.Contains(row.Id))){row.Favorite=operation==SelectionOperation.FavoriteAdd;RefreshFavoriteCard(row);}
            await RefreshResultRowsAfterEditAsync(favoriteOnly:favorite);
            UpdateLibrarySelectionTools();if(!resultsNeedRefresh)Notice("保存しました",$"{ids.Length:N0} 件の整理を保存しました。");
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            saving=false;dialogOpen=false;transitions.Release();
            if(!disposed)
            {
                foreach(var button in SelectionSummaryPanel.Children.OfType<Button>())button.IsEnabled=true;
                SelectionEditStatus.Text=committed?(resultsNeedRefresh?"保存済みです。一覧を検索し直してください。":$"{ids.Length:N0} 件を保存しました。") : "";
                SelectionEditStatus.Visibility=committed?Visibility.Visible:Visibility.Collapsed;
                UpdateDirty();
                if(PendingSearch){searchTimer.Stop();searchTimer.Start();}
            }
        }
    }
}
