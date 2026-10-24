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
    private string ShelfScopeName()=>selectedShelfIds is null?"ライブラリ":string.Join("、",selectedShelfIds.Select(ShelfName));
    private void SetShelfScope(IReadOnlyList<long>? ids)
    {
        selectedShelfIds=ids?.ToArray();UpdateShelfScopeLabel();
    }
    private void UpdateShelfScopeLabel()
    {
        if(ShelfScopeBar is null)return;
        ShelfScopeBar.Visibility=selectedShelfIds is null?Visibility.Collapsed:Visibility.Visible;
        ShelfScopeText.Text=selectedShelfIds is null?"":"検索対象: "+ShelfScopeName();
        ToolTipService.SetToolTip(ShelfScopeText,ShelfScopeText.Text);
    }
    private void UpdateShelfEditorLabel()
    {
        Shelf.Text=editingShelfIds.Length==0?"棚なし":string.Join("、",editingShelfIds.Select(ShelfName));
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
            searches.Next();similarityCancellation?.Cancel();
            CloseFolderHubCore();CloseShelfHubCore();ClearSimilarity();
            resultWindow?.Dispose();resultWindow=null;
            var previous=resultSession;resultSession=null;await CloseResultSessionAsync(previous);
            shelfHubOpen=true;active=null;Details.IsPaneOpen=false;DetailsButton.IsEnabled=false;
            MainViewTitle.Text="棚";Count.Text="";
            ItemSearchRow.Visibility=SearchTools.Visibility=ItemListContainer.Visibility=ItemPagerRow.Visibility=Visibility.Collapsed;
            ShelfHubView.Visibility=Visibility.Visible;ShelfList.ItemsSource=shelfKeys;
            Busy.Visibility=Visibility.Collapsed;CancelSearchButton.Visibility=Visibility.Collapsed;
            RenderShelfLayout();RestoreNavigation();await ReloadShelfHubAsync();RecordNavigationLocation();
        }
        catch(Exception ex){Failure(ex);ShelfHubMessage.Text="棚を取得できませんでした。「更新」で再試行できます。";}
        finally{transitions.Release();}
    }
    private async Task ReloadShelfHubAsync()
    {
        ShelfHubMessage.Text="読み込み中…";
        await RefreshShelfDescriptorsAsync();
        if(disposed||!shelfHubOpen)return;
        shelfRefresh.Clear();
        foreach(var load in shelfLoads.Values){load.Cancel();load.Dispose();}shelfLoads.Clear();
        shelfKeys.Clear();foreach(var shelf in shelfDescriptors)shelfKeys.Add(shelf.Id.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Count.Text=$"{shelfDescriptors.Count:N0} 棚";
        ShelfHubMessage.Text=shelfDescriptors.Count==0?"「棚を作成」から追加できます。作品の詳細で所属する棚を選べます。":"棚を開くと、その棚の作品を表示します。";
    }
    private async Task OpenShelfItemsAsync(long id)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            CloseShelfHubCore();CloseFolderHubCore();SetShelfScope(new[]{id});
            ClearSimilarity();view="all";page=0;RestoreNavigation();UpdateSearchMethod();await LoadAsync();
        }
        finally{transitions.Release();}
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
        var artwork=new Grid();var icon=new SymbolIcon(Symbol.Folder);artwork.Children.Add(icon);
        var image=new Image{Stretch=Stretch.Uniform};artwork.Children.Add(image);row.Children.Add(artwork);
        var text=new StackPanel{Spacing=4,VerticalAlignment=VerticalAlignment.Center};
        var name=new TextBlock{Text=shelf.Name,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaTitleStyle"]};
        ToolTipService.SetToolTip(name,shelf.Name);text.Children.Add(name);
        text.Children.Add(new TextBlock{Text=$"{shelf.ItemCount:N0} 件",Style=(Style)Resources["MediaMetadataStyle"]});row.Children.Add(text);
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
                    if(!force)await Task.Delay(80,cancellation);
                    var bitmap=await thumbnails.GetAsync(representative,cancellation,edge);
                    if(cancellation.IsCancellationRequested||disposed||!shelfHubOpen||ownVersion!=version)return;
                    image.Source=bitmap;icon.Visibility=bitmap is null?Visibility.Visible:Visibility.Collapsed;
                }
                catch(OperationCanceledException){}
                catch(Exception ex){AppLog.Error(ex);}
            }
            image.Loaded+=async(_,_)=>await RefreshAsync(true);artwork.SizeChanged+=async(_,_)=>await RefreshAsync();
            image.Unloaded+=(_,_)=>{++version;requestedEdge=0;shelfRefresh.Remove(item);if(shelfLoads.TryGetValue(item,out var active)&&ReferenceEquals(active,request))active.Cancel();image.Source=null;};
            shelfRefresh[item]=()=>_=RefreshAsync();
        }
        host.Child=row;
    }
    private ItemsPanelTemplate MediaItemsPanel()=>(ItemsPanelTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load(tiles
        ? "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsWrapGrid Orientation=\"Horizontal\" CacheLength=\"1\"/></ItemsPanelTemplate>"
        : "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsStackPanel CacheLength=\"1\"/></ItemsPanelTemplate>");
    private void RenderShelfLayout()
    {
        ShelfList.ItemsSource=null;
        foreach(var request in shelfLoads.Values){request.Cancel();request.Dispose();}shelfLoads.Clear();shelfRealized.Clear();shelfRefresh.Clear();
        ShelfList.ItemsPanel=MediaItemsPanel();ShelfList.ItemsSource=shelfKeys;
        ShelfLayoutButton.Content=tiles?"リスト表示":"グリッド表示";
    }
    private void SizeShelfItem(ListViewItem item,Grid artwork)
    {
        var scale=libraryItemScale/100d;
        var width=LibraryTileLayout.Width(Math.Max(1,ShelfList.ActualWidth-16),libraryItemScale);
        item.Width=tiles?width:double.NaN;
        artwork.Width=tiles?Math.Max(96,width-32):48*scale;
        artwork.Height=tiles?Math.Min(144*scale,Math.Max(48,ShelfList.ActualHeight-108)):64*scale;
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
        try
        {
            var itemId=active.Id;await RefreshShelfDescriptorsAsync();
            if(disposed||saving||dialogOpen||active?.Id!=itemId)return;
            var ids=await PickShelfIdsAsync("棚を選択",editingShelfIds,"所属する棚を選択してください。選択を外すと、その棚から解除します。");
            if(ids is not null&&active?.Id==itemId){editingShelfIds=ids;UpdateShelfEditorLabel();UpdateDirty();}
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();}
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
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=shelf is null?"棚を作成":"棚の名前を変更",Content=panel,PrimaryButtonText=shelf is null?"作成":"変更",CloseButtonText="キャンセル",DefaultButton=ContentDialogButton.Close};
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
            if(selectedShelfIds?.Contains(shelf.Id)==true)SetShelfScope(null);
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
