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
        shelfHubOpen=false;ShelfHubView.Visibility=Visibility.Collapsed;
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
            RestoreNavigation();await ReloadShelfHubAsync();
        }
        catch(Exception ex){Failure(ex);ShelfHubMessage.Text="棚を取得できませんでした。「更新」で再試行できます。";}
        finally{transitions.Release();}
    }
    private async Task ReloadShelfHubAsync()
    {
        ShelfHubMessage.Text="読み込み中…";
        await RefreshShelfDescriptorsAsync();
        if(disposed||!shelfHubOpen)return;
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
        if(shelfLoads.Remove(item,out var previous)){previous.Cancel();previous.Dispose();}
        item.Content=null;
        if(args.InRecycleQueue||args.Item is not string key||!long.TryParse(key,out var id))return;
        var shelf=shelfDescriptors.FirstOrDefault(x=>x.Id==id);if(shelf is null)return;
        var row=new Grid{ColumnSpacing=12,Padding=new Thickness(8)};
        row.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
        row.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
        row.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
        var artwork=new Grid{Width=64,Height=64};
        var icon=new SymbolIcon(Symbol.Folder);artwork.Children.Add(icon);
        var image=new Image{Stretch=Stretch.Uniform};artwork.Children.Add(image);row.Children.Add(artwork);
        var text=new StackPanel{Spacing=4,VerticalAlignment=VerticalAlignment.Center};Grid.SetColumn(text,1);
        var name=new TextBlock{Text=shelf.Name,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]};
        ToolTipService.SetToolTip(name,shelf.Name);text.Children.Add(name);
        text.Children.Add(new TextBlock{Text=$"{shelf.ItemCount:N0} 件",Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"]});row.Children.Add(text);
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8,VerticalAlignment=VerticalAlignment.Center};Grid.SetColumn(actions,2);
        void Action(string label,string suffix,Func<Task> run)
        {
            var button=new Button{Content=label};AutomationProperties.SetAutomationId(button,$"Shelf{suffix}{id}");AutomationProperties.SetName(button,$"{shelf.Name}：{label}");
            button.Click+=async(_,_)=>await run();actions.Children.Add(button);
        }
        Action("開く","Open",()=>OpenShelfItemsAsync(id));
        Action("名前変更","Rename",()=>EditShelfNameAsync(shelf));
        Action("削除","Delete",()=>DeleteShelfAsync(shelf));row.Children.Add(actions);
        AutomationProperties.SetAutomationId(item,$"ShelfRow{id}");AutomationProperties.SetName(item,$"{shelf.Name}、{shelf.ItemCount:N0}件");
        item.Content=row;args.Handled=true;
        if(shelf.Representative is not null)
        {
            var cancel=new CancellationTokenSource();shelfLoads[item]=cancel;
            _=LoadShelfArtworkAsync(item,image,icon,shelf.Representative,cancel.Token);
        }
    }
    private async Task LoadShelfArtworkAsync(ListViewItem owner,Image image,SymbolIcon fallback,MediaRow row,CancellationToken cancellation)
    {
        try
        {
            var bitmap=await thumbnails.GetAsync(row,cancellation,128);
            if(cancellation.IsCancellationRequested||disposed||!shelfHubOpen||!owner.IsLoaded)return;
            image.Source=bitmap;fallback.Visibility=bitmap is null?Visibility.Visible:Visibility.Collapsed;
        }
        catch(OperationCanceledException){}
        catch(Exception ex){AppLog.Error(ex);}
    }
    private async void ChooseShelves_Click(object sender,RoutedEventArgs args)
    {
        if(active is null||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try
        {
            var itemId=active.Id;await RefreshShelfDescriptorsAsync();
            if(disposed||saving||dialogOpen||active?.Id!=itemId)return;
            var options=shelfDescriptors.ToList();
            foreach(var id in editingShelfIds.Where(id=>options.All(s=>s.Id!=id)))options.Add(new(id,"見つからない棚（所属を維持）",0));
            var list=new ListView{SelectionMode=ListViewSelectionMode.Multiple,MaxHeight=320,MinHeight=96,HorizontalContentAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(list,"ChooseShelfList");AutomationProperties.SetName(list,"所属する棚を複数選択");
            foreach(var shelf in options)
            {
                var choice=new ListViewItem{Content=shelf.Name,Tag=shelf.Id};AutomationProperties.SetAutomationId(choice,$"ChooseShelf{shelf.Id}");list.Items.Add(choice);
                if(editingShelfIds.Contains(shelf.Id))list.SelectedItems.Add(choice);
            }
            var panel=new StackPanel{Spacing=8};panel.Children.Add(new TextBlock{Text=options.Count==0?"棚がありません。左側の「棚」から作成できます。":"所属する棚を選択してください。選択を外すと、その棚から解除します。",TextWrapping=TextWrapping.Wrap});panel.Children.Add(list);
            dialogOpen=true;
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="棚を選択",Content=panel,PrimaryButtonText="適用",CloseButtonText="キャンセル",DefaultButton=ContentDialogButton.Close};
            if(await dialog.ShowAsync()==ContentDialogResult.Primary&&active?.Id==itemId)
            {
                var ids=list.SelectedItems.OfType<ListViewItem>().Select(x=>(long)x.Tag).Order().ToArray();
                ShelfProtocol.ValidateIds(ids);editingShelfIds=ids;UpdateShelfEditorLabel();UpdateDirty();
            }
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();}
    }
    private async Task EditShelfNameAsync(ShelfDescriptor? shelf=null)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
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
        finally{dialogOpen=false;transitions.Release();}
    }
    private async Task DeleteShelfAsync(ShelfDescriptor shelf)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
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
        finally{dialogOpen=false;transitions.Release();}
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
