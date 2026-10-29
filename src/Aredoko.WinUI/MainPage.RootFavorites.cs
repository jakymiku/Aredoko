using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Collections.ObjectModel;
namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private readonly ObservableCollection<string> favoriteRootKeys=new();
    private void UpdateFavoriteRootList()
    {
        FavoriteRootList.ItemsSource=favoriteRootKeys;favoriteRootKeys.Clear();
        var roots=knownRoots.Where(r=>r.Enabled&&r.Favorite).ToArray();
        foreach(var root in roots)favoriteRootKeys.Add(root.Id.ToString(System.Globalization.CultureInfo.InvariantCulture));
        FavoriteRootArea.Visibility=view=="favorites"&&roots.Length>0?Visibility.Visible:Visibility.Collapsed;
        FavoriteRootArea.Header=$"お気に入りのフォルダ（{roots.Length}）";
    }
    private void FavoriteRoot_ContainerContentChanging(ListViewBase sender,ContainerContentChangingEventArgs args)
    {
        if(args.ItemContainer is not ListViewItem item||item.ContentTemplateRoot is not Border host)return;
        host.Child=null;item.ContextFlyout=null;
        if(args.InRecycleQueue||args.Item is not string key||!int.TryParse(key,out var id)||knownRoots.FirstOrDefault(r=>r.Id==id&&r.Enabled&&r.Favorite) is not {} root)return;
        var panel=new Grid{ColumnSpacing=8,Padding=new Thickness(8)};
        panel.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
        panel.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
        var text=new StackPanel{Spacing=4};
        text.Children.Add(new TextBlock{Text=root.Name,Style=(Style)Resources["MediaTitleStyle"],TextTrimming=TextTrimming.CharacterEllipsis});
        text.Children.Add(new TextBlock{Text=root.ShortPath+(root.Online?"":"（未接続）"),Style=(Style)Resources["MediaMetadataStyle"],TextTrimming=TextTrimming.CharacterEllipsis});panel.Children.Add(text);
        var menu=new MenuFlyout();
        var manage=new MenuFlyoutItem{Text="フォルダの設定"};AutomationProperties.SetAutomationId(manage,$"FavoriteRootManage{id}");
        manage.Click+=async(_,_)=>await SelectFolderForSettingsAsync(new[]{root.Id},false);menu.Items.Add(manage);
        var remove=new MenuFlyoutItem{Text="お気に入りから外す"};AutomationProperties.SetAutomationId(remove,$"FavoriteRootRemove{id}");
        remove.Click+=async(_,_)=>await SetRootFavoriteAsync(root,false);menu.Items.Add(remove);
        var more=new Button{Content="…",Flyout=menu,VerticalAlignment=VerticalAlignment.Center};
        AutomationProperties.SetAutomationId(more,$"FavoriteRootActions{id}");AutomationProperties.SetName(more,$"{root.Name}の操作");ToolTipService.SetToolTip(more,"フォルダの設定・お気に入り解除");
        Grid.SetColumn(more,1);panel.Children.Add(more);item.ContextFlyout=menu;
        ToolTipService.SetToolTip(panel,root.Path);AutomationProperties.SetAutomationId(item,$"FavoriteRoot{id}");AutomationProperties.SetName(item,$"お気に入りフォルダ {root.Name} を開く");
        host.Child=panel;args.Handled=true;
    }
    private async void FavoriteRoot_ItemClick(object sender,ItemClickEventArgs args)
    {if(args.ClickedItem is string key&&int.TryParse(key,out var id))await ReturnToLibraryAsync(new[]{id},allItems:true);}
    private async Task SetRootFavoriteAsync(RegisteredRootRow row,bool value)
    {
        if(saving||dialogOpen||!await transitions.WaitAsync(0))return;
        saving=true;
        try
        {
            await api.SetRootFavoriteAsync(row.Id,value);
            knownRoots=knownRoots.Select(root=>root.Id==row.Id?root with{Favorite=value}:root).ToArray();
            UpdateFavoriteRootList();if(folderHubOpen)RenderFolderHub();
            resultsNeedRefresh=true;
            if(!folderHubOpen&&!shelfHubOpen)await RefreshResultRowsAfterEditAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{saving=false;transitions.Release();if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
}
