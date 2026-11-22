using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Collections.ObjectModel;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private IReadOnlyList<ShelfDescriptor> shelfDescriptors=[];
    private long[] editingShelfIds=[];
    private long[]? selectedShelfIds;
    private bool shelfHubOpen;
    private readonly ObservableCollection<string> shelfKeys=new();
    private readonly Dictionary<ListViewItem,CancellationTokenSource> shelfLoads=new();
    private readonly Dictionary<ListViewItem,Action> shelfRefresh=new();
    private readonly HashSet<ListViewItem> shelfRealized=new();

    private async Task RefreshShelfDescriptorsAsync()
    {
        shelfDescriptors=await api.Shelves.ListAsync();
        knownShelves=shelfDescriptors.Select(x=>x.Name).ToArray();
        UpdateShelfScopeLabel();
    }
    private string ShelfName(long id)=>shelfDescriptors.FirstOrDefault(s=>s.Id==id)?.Name??"見つからない棚";
    private string ShelfScopeName(bool summarize=true)=>selectedShelfIds is null?"すべての作品":ShelfProtocol.SummarizeNames(selectedShelfIds.Select(ShelfName),"すべての作品",summarize?3:0);
    private void SetShelfScope(IReadOnlyList<long>? ids)
    {
        selectedShelfIds=ids?.ToArray();UpdateShelfScopeLabel();UpdateClearSearchConditionsVisibility();
    }
    private void UpdateShelfScopeLabel()
    {
        if(ShelfScopeBar is null)return;
        ShelfScopeBar.Visibility=selectedShelfIds is null?Visibility.Collapsed:Visibility.Visible;
        ShelfScopeText.Text=selectedShelfIds is null?"":"📚 "+ShelfScopeName();
        ToolTipService.SetToolTip(ShelfScopeText,selectedShelfIds is null?"":"📚 "+ShelfScopeName(summarize:false));
    }
    private void UpdateShelfEditorLabel()
    {
        var names=editingShelfIds.Select(ShelfName).ToArray();
        Shelf.Text=ShelfProtocol.SummarizeNames(names,"棚なし",3);
        ToolTipService.SetToolTip(Shelf,ShelfProtocol.SummarizeNames(names,"棚なし",0));
        if(ActiveShelfChipsPanel is null)return;
        ActiveShelfChipsPanel.Children.Clear();
        if(editingShelfIds.Length==0)
        {
            ActiveShelfChipsPanel.Children.Add(new TextBlock{Text="棚なし",Style=ThemeStyle("MediaMetadataStyle")});
            AutomationProperties.SetName(ActiveShelfChipsPanel,"棚なし");
            return;
        }
        var chipElements=new List<FrameworkElement>(editingShelfIds.Length);
        for(var i=0;i<editingShelfIds.Length;i++)
        {
            var shelfId=editingShelfIds[i];
            var shelfName=ShelfName(shelfId);
            var label=new TextBlock{Text="📚 "+shelfName,MaxWidth=140,TextTrimming=TextTrimming.CharacterEllipsis,VerticalAlignment=VerticalAlignment.Center,Style=ThemeStyle("MediaMetadataStyle")};
            var chipBtn=new Button
            {
                Content=label,
                Padding=new Thickness(6,2,6,2),
                MinWidth=0,
                MinHeight=0,
                Background=new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                BorderThickness=new Thickness(0)
            };
            ToolTipService.SetToolTip(chipBtn,$"棚「{shelfName}」の作品を表示");
            AutomationProperties.SetAutomationId(chipBtn,$"DetailShelfChip{i}");
            AutomationProperties.SetName(chipBtn,$"棚「{shelfName}」を開く");
            chipBtn.Click+=async(_,_)=>await OpenShelfScopeAsync(new[]{shelfId});
            chipElements.Add(new Border{Style=ThemeStyle("CardBadgeBorderStyle"),Padding=new Thickness(2),Child=chipBtn});
        }
        var maxRowWidth=DetailScroll is not null&&DetailScroll.ActualWidth>60?DetailScroll.ActualWidth-28:Math.Max(180,Details.OpenPaneLength-56);
        PopulateWrappedChips(ActiveShelfChipsPanel,maxRowWidth,chipElements);
        AutomationProperties.SetName(ActiveShelfChipsPanel,ShelfProtocol.SummarizeNames(names,"棚なし",0));
    }
    private void CloseShelfHubCore()
    {
        shelfHubOpen=false;ShelfHubView.Visibility=Visibility.Collapsed;shelfRealized.Clear();shelfRefresh.Clear();
        foreach(var load in shelfLoads.Values){load.Cancel();load.Dispose();}shelfLoads.Clear();
    }
    private async Task OpenShelfHubAsync()
    {
        if(!ready||disposed||saving||dialogOpen||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            CloseBrowseMenus();searches.Next();similarityCancellation?.Cancel();
            CloseSettingsHubCore();CloseFolderHubCore();CloseShelfHubCore();ClearSimilarity();
            resultWindow?.Dispose();resultWindow=null;
            var previous=resultSession;resultSession=null;await CloseResultSessionAsync(previous);
            shelfHubOpen=true;active=null;Details.IsPaneOpen=false;DetailsButton.IsEnabled=false;
            MainViewTitle.Text="棚";Count.Text="";
            ItemSearchRow.Visibility=SearchTools.Visibility=ItemListContainer.Visibility=ItemPagerRow.Visibility=Visibility.Collapsed;
            ShelfHubView.Visibility=Visibility.Visible;ShelfList.ItemsSource=shelfKeys;UpdateLayoutToggleVisuals();
            Busy.Visibility=Visibility.Collapsed;CancelSearchButton.Visibility=Visibility.Collapsed;
            RenderShelfLayout();RestoreNavigation();await ReloadShelfHubAsync();RecordNavigationLocation();
        }
        catch(Exception ex){Failure(ex);ShelfHubStatus.Text="棚を取得できませんでした。「更新」で再試行できます。";ShelfHubStatus.Visibility=Visibility.Visible;ShelfEmptyState.Visibility=Visibility.Collapsed;}
        finally{transitions.Release();}
    }
    private async Task ReloadShelfHubAsync()
    {
        ShelfHubStatus.Text="読み込み中…";
        ShelfHubStatus.Visibility=Visibility.Visible;
        ShelfEmptyState.Visibility=Visibility.Collapsed;
        await RefreshShelfDescriptorsAsync();
        if(disposed||!shelfHubOpen)return;
        shelfRefresh.Clear();
        foreach(var load in shelfLoads.Values){load.Cancel();load.Dispose();}shelfLoads.Clear();
        shelfKeys.Clear();foreach(var shelf in shelfDescriptors)shelfKeys.Add(shelf.Id.ToString(System.Globalization.CultureInfo.InvariantCulture));
        var hasShelves=shelfDescriptors.Count>0;
        Count.Text=$"{shelfDescriptors.Count:N0} 棚";
        OpenMultipleShelvesButton.IsEnabled=shelfDescriptors.Count>1;
        ShelfViewTools.Visibility=hasShelves?Visibility.Visible:Visibility.Collapsed;
        ShelfHubStatus.Text="";
        ShelfHubStatus.Visibility=Visibility.Collapsed;
        ShelfHubMessage.Text=hasShelves?"":"お気に入りのシリーズや作業用の素材をテーマごとにまとめられます。「棚を作成」から追加できます（元ファイルは移動しません）。";
        ShelfEmptyState.Visibility=hasShelves?Visibility.Collapsed:Visibility.Visible;
    }
    private Task OpenShelfItemsAsync(long id)=>OpenShelfScopeAsync(new[]{id});
    private async Task OpenShelfScopeAsync(IReadOnlyList<long> ids)
    {
        if(ids.Count==0||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            CloseShelfHubCore();CloseFolderHubCore();SetShelfScope(ids);
            ClearSimilarity();view="all";page=0;RestoreNavigation();UpdateSearchMethod();await LoadAsync();
        }
        finally{transitions.Release();}
    }
    private async void OpenActiveShelves_Click(object sender,RoutedEventArgs args)
    {
        if(active is {ShelfIds.Length:>0} row)await OpenShelfScopeAsync(row.ShelfIds.ToArray());
    }
    private async void OpenMultipleShelves_Click(object sender,RoutedEventArgs args)=>await ChooseShelfScopeAsync();
    private async void ChangeShelfScope_Click(object sender,RoutedEventArgs args)=>await ChooseShelfScopeAsync();
    private async Task ChooseShelfScopeAsync()
    {
        if(!ready||disposed||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        var detailsWereOpen=Details.IsPaneOpen;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            await RefreshShelfDescriptorsAsync();
            if(disposed||saving||dialogOpen||shelfDescriptors.Count==0)return;
            var initial=selectedShelfIds??[];
            var picked=await PickShelfIdsAsync("表示する棚を選択",initial,
                "選択した棚の作品を表示します",
                "ScopeShelfChoice",allowCreate:false);
            if(picked is null||disposed)return;
            dialogOpen=false;
            if(picked.Length==0)
            {
                if(selectedShelfIds is null)return;
                SetShelfScope(null);
                if(shelfHubOpen)return;
                page=0;RestoreNavigation();await LoadAsync();
                return;
            }
            if(!shelfHubOpen&&selectedShelfIds is not null&&selectedShelfIds.Order().SequenceEqual(picked.Order()))return;
            CloseShelfHubCore();CloseFolderHubCore();SetShelfScope(picked);
            ClearSimilarity();view="all";page=0;RestoreNavigation();UpdateSearchMethod();await LoadAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            dialogOpen=false;
            if(!disposed&&detailsWereOpen&&!shelfHubOpen&&(active is not null||librarySelection.Count>0))Details.IsPaneOpen=true;
            transitions.Release();
        }
    }
    private async void ShelfList_ItemClick(object sender,ItemClickEventArgs args)
    {
        if(args.ClickedItem is string key&&long.TryParse(key,out var id))await OpenShelfItemsAsync(id);
    }
    private void ShelfList_ContainerContentChanging(ListViewBase sender,ContainerContentChangingEventArgs args)
    {
        if(args.ItemContainer is not ListViewItem item)return;
        shelfRealized.Remove(item);shelfRefresh.Remove(item);
        if(shelfLoads.Remove(item,out var previous)){previous.Cancel();previous.Dispose();}
        if(item.ContentTemplateRoot is Border oldHost)oldHost.Child=null;
        if(args.InRecycleQueue||args.Item is not string key||!long.TryParse(key,out var id))return;
        var shelf=shelfDescriptors.FirstOrDefault(x=>x.Id==id);if(shelf is null||item.ContentTemplateRoot is not Border host)return;
        shelfRealized.Add(item);item.Width=double.NaN;item.ContextFlyout=null;
        var row=new Grid{ColumnSpacing=12,RowSpacing=8,Padding=new Thickness(8)};
        var artwork=new Grid();
        var thumbPlate=new Border{Tag="ThumbPlate",Style=ThemeStyle("ThumbPlateStyle")};
        Canvas.SetZIndex(thumbPlate,-1);
        var icon=new Viewbox{Width=32,Height=32,HorizontalAlignment=HorizontalAlignment.Center,VerticalAlignment=VerticalAlignment.Center,IsHitTestVisible=false,
            Child=new SymbolIcon(Symbol.Library){Style=ThemeStyle("MediaPlaceholderIconStyle")}};
        artwork.Children.Add(thumbPlate);artwork.Children.Add(icon);
        var image=new Image{Stretch=Stretch.Uniform};artwork.Children.Add(image);row.Children.Add(artwork);
        var text=new StackPanel{Spacing=4,VerticalAlignment=VerticalAlignment.Center,MaxWidth=1};
        var name=new TextBlock{Text=shelf.Name,TextWrapping=TextWrapping.NoWrap,MaxLines=1,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaTitleStyle"]};
        AutomationProperties.SetAutomationId(name,$"ShelfTitle{id}");AutomationProperties.SetName(name,shelf.Name);
        ToolTipService.SetToolTip(name,shelf.Name);text.Children.Add(name);
        text.Children.Add(new TextBlock{Text=$"{shelf.ItemCount:N0} 作品",Style=(Style)Resources["MediaMetadataStyle"]});row.Children.Add(text);
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
        var open=new Button{Content="開く"};AutomationProperties.SetAutomationId(open,$"ShelfOpen{id}");AutomationProperties.SetName(open,$"{shelf.Name}を開く");
        open.Click+=async(_,_)=>await OpenShelfItemsAsync(id);actions.Children.Add(open);
        var menu=new MenuFlyout();
        void Action(string label,string suffix,Func<Task> run)
        {
            var action=new MenuFlyoutItem{Text=label};AutomationProperties.SetAutomationId(action,$"Shelf{suffix}{id}");
            action.Click+=async(_,_)=>await run();menu.Items.Add(action);
        }
        Action("名前変更","Rename",()=>EditShelfNameAsync(shelf));Action("削除","Delete",()=>DeleteShelfAsync(shelf));
        var more=new Button{Content="…",Flyout=menu};AutomationProperties.SetAutomationId(more,$"ShelfMore{id}");AutomationProperties.SetName(more,$"{shelf.Name}の操作");actions.Children.Add(more);
        if(tiles)
        {
            for(var i=0;i<3;i++)row.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
            Grid.SetRow(text,1);Grid.SetRow(actions,2);
        }
        else
        {
            row.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});row.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});row.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            Grid.SetColumn(text,1);Grid.SetColumn(actions,2);actions.VerticalAlignment=VerticalAlignment.Center;
        }
        row.Children.Add(actions);SizeShelfItem(item,artwork);
        row.SizeChanged+=(_,_)=>ConstrainCardCaption(row,text);
        artwork.SizeChanged+=(_,_)=>ConstrainCardCaption(row,text);
        AutomationProperties.SetAutomationId(item,$"ShelfRow{id}");AutomationProperties.SetName(item,$"{shelf.Name}、{shelf.ItemCount:N0}件");args.Handled=true;
        if(shelf.Representative is {} representative)
        {
            CancellationTokenSource? request=null;long version=0;int requestedEdge=0;
            async Task RefreshAsync(bool force=false)
            {
                if(!image.IsLoaded||disposed||!shelfHubOpen||!ReferenceEquals(host.Child,row)||!shelfKeys.Contains(key))return;
                var edge=ThumbnailPolicy.EdgeFor(artwork.Width,artwork.Height,XamlRoot?.RasterizationScale??1);
                if(!force&&requestedEdge==edge)return;requestedEdge=edge;var ownVersion=++version;
                if(shelfLoads.Remove(item,out var old)){old.Cancel();old.Dispose();}
                request=new();shelfLoads[item]=request;var cancellation=request.Token;
                try
                {
                    if(!force&&image.Source is not null)await Task.Delay(80,cancellation);
                    var bitmap=await thumbnails.GetAsync(representative,cancellation,edge);
                    if(cancellation.IsCancellationRequested||disposed||!shelfHubOpen||ownVersion!=version)return;
                    image.Source=bitmap;icon.Visibility=bitmap is null?Visibility.Visible:Visibility.Collapsed;
                }
                catch(OperationCanceledException){}
                catch(Exception ex){AppLog.Error(ex);}
            }
            image.Loaded+=async(_,_)=>
            {
                // Unloaded may be temporary, without a recycled container.
                if(ReferenceEquals(host.Child,row))shelfRefresh[item]=()=>_=RefreshAsync();
                await RefreshAsync(true);
            };
            artwork.SizeChanged+=async(_,_)=>await RefreshAsync();
            image.Unloaded+=(_,_)=>{++version;requestedEdge=0;shelfRefresh.Remove(item);if(shelfLoads.TryGetValue(item,out var active)&&ReferenceEquals(active,request))active.Cancel();image.Source=null;};
            shelfRefresh[item]=()=>_=RefreshAsync();
        }
        host.Child=row;
    }
    private ItemsPanelTemplate MediaItemsPanel()=>(ItemsPanelTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load(tiles
        ? "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsWrapGrid Orientation=\"Horizontal\" CacheLength=\"2.0\"/></ItemsPanelTemplate>"
        : "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsStackPanel CacheLength=\"2.0\"/></ItemsPanelTemplate>");
    private void RenderShelfLayout()
    {
        ShelfList.ItemsSource=null;
        foreach(var request in shelfLoads.Values){request.Cancel();request.Dispose();}shelfLoads.Clear();shelfRealized.Clear();shelfRefresh.Clear();
        ShelfList.ItemsPanel=MediaItemsPanel();ShelfList.ItemsSource=shelfKeys;
        UpdateLayoutToggleVisuals();
    }
    private void SizeShelfItem(ListViewItem item,Grid artwork)
    {
        var scale=libraryItemScale/100d;
        var width=Math.Floor(LibraryTileLayout.Width(Math.Max(1,ShelfList.ActualWidth-16),libraryItemScale));
        item.Width=tiles?Math.Max(1,width-2):double.NaN;
        artwork.Width=tiles?Math.Max(64,width-22):48*scale;
        artwork.Height=tiles?Math.Min(144*scale,Math.Max(48,ShelfList.ActualHeight-108)):64*scale;
        if(artwork.Children.OfType<Border>().FirstOrDefault(border=>Equals(border.Tag,"ThumbPlate")) is {} thumbPlate)
        {
            thumbPlate.Width=artwork.Width;
            thumbPlate.Height=artwork.Height;
        }
        if(item.ContentTemplateRoot is Border {Child:Grid row}&&row.Children.OfType<StackPanel>().FirstOrDefault() is {} text)
            ConstrainCardCaption(row,text);
        if(ShelfList.ItemsPanelRoot is ItemsWrapGrid wrap)wrap.ItemWidth=width+8;
    }
    private void UpdateShelfItemSizes()
    {
        if(!shelfHubOpen)return;
        foreach(var item in shelfRealized.ToArray())
            if(item.ContentTemplateRoot is Border {Child:Grid row}&&row.Children.FirstOrDefault() is Grid artwork)SizeShelfItem(item,artwork);
        foreach(var refresh in shelfRefresh.Values.ToArray())refresh();
    }
    private void ShelfList_SizeChanged(object sender,SizeChangedEventArgs args)=>UpdateShelfItemSizes();
    private void ShelfSize_Click(object sender,RoutedEventArgs args)=>ItemSizeFlyout.ShowAt((Button)sender);
    private async void ChooseShelves_Click(object sender,RoutedEventArgs args)
    {
        if(active is null||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        var detailsWereOpen=Details.IsPaneOpen;
        var itemId=active.Id;
        try
        {
            await RefreshShelfDescriptorsAsync();
            if(disposed||saving||dialogOpen||active?.Id!=itemId)return;
            var ids=await PickShelfIdsAsync("棚を選択",editingShelfIds,"チェックで追加、外すと解除します。");
            if(ids is not null&&active?.Id==itemId){editingShelfIds=ids;UpdateShelfEditorLabel();UpdateDirty();}
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            dialogOpen=false;
            if(!disposed&&detailsWereOpen&&active?.Id==itemId)
            {
                Details.IsPaneOpen=true;
                ChooseShelvesButton.Focus(FocusState.Programmatic);
            }
            transitions.Release();
        }
    }
    private async Task EditShelfNameAsync(ShelfDescriptor? shelf=null)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
        ShelfList.IsEnabled=false;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            var name=new TextBox{Header="棚の名前",Text=shelf?.Name??"",MaxLength=80,MinWidth=280};AutomationProperties.SetAutomationId(name,"TxtShelfName");
            var error=new TextBlock{TextWrapping=TextWrapping.Wrap};AutomationProperties.SetAutomationId(error,"TxtShelfNameError");
            var panel=new StackPanel{Spacing=8};panel.Children.Add(name);panel.Children.Add(error);
            dialogOpen=true;
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=shelf is null?"棚を作成":"棚の名前を変更",Content=panel,PrimaryButtonText=shelf is null?"作成":"変更",CloseButtonText="キャンセル",DefaultButton=ContentDialogButton.Primary};
            var committing=false;
            dialog.Closing+=(_,closing)=>{if(committing)closing.Cancel=true;};
            dialog.PrimaryButtonClick+=async(_,eventArgs)=>
            {
                eventArgs.Cancel=true;if(committing)return;var deferral=eventArgs.GetDeferral();committing=true;dialog.IsPrimaryButtonEnabled=false;name.IsEnabled=false;error.Text="保存中…";
                try
                {
                    if(shelf is null)await api.Shelves.CreateAsync(name.Text);else await api.Shelves.RenameAsync(shelf.Id,name.Text);
                    eventArgs.Cancel=false;
                }
                catch(Exception ex){error.Text=ex.Message;AppLog.Error(ex);}
                finally{committing=false;name.IsEnabled=true;dialog.IsPrimaryButtonEnabled=true;deferral.Complete();}
            };
            if(await dialog.ShowAsync()==ContentDialogResult.Primary){resultsNeedRefresh=true;await ReloadShelfHubAsync();}
        }
        catch(Exception ex){Failure(ex);}
        finally{ShelfList.IsEnabled=true;dialogOpen=false;transitions.Release();}
    }
    private async Task DeleteShelfAsync(ShelfDescriptor shelf)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
        ShelfList.IsEnabled=false;
        try
        {
            if(!await ConfirmDiscardAsync())return;dialogOpen=true;
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="棚を削除しますか？",Content=$"「{shelf.Name}」を削除します。作品と元ファイルは残ります。",PrimaryButtonText="棚を削除",CloseButtonText="キャンセル",DefaultButton=ContentDialogButton.Close};
            if(await dialog.ShowAsync()!=ContentDialogResult.Primary)return;
            await api.Shelves.DeleteAsync(shelf.Id);resultsNeedRefresh=true;
            if(selectedShelfIds?.Contains(shelf.Id)==true)
            {
                var remaining=selectedShelfIds.Where(id=>id!=shelf.Id).ToArray();
                SetShelfScope(remaining.Length>0?remaining:null);
            }
            await ReloadShelfHubAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{ShelfList.IsEnabled=true;dialogOpen=false;transitions.Release();}
    }
    private async void CreateShelf_Click(object sender,RoutedEventArgs args)=>await EditShelfNameAsync();
    private async void ShelfList_Click(object sender,RoutedEventArgs args)=>await OpenShelfHubAsync();
    private async void RefreshShelves_Click(object sender,RoutedEventArgs args)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try{await ReloadShelfHubAsync();}catch(Exception ex){Failure(ex);}finally{transitions.Release();}
    }
    private async void ClearShelfScope_Click(object sender,RoutedEventArgs args)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try{if(!await ConfirmDiscardAsync())return;SetShelfScope(null);page=0;RestoreNavigation();await LoadAsync();}
        finally{transitions.Release();}
    }
}
