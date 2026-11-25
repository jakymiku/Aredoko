using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.System;
namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private async Task<long[]?> PickShelfIdsAsync(string title,IReadOnlyList<long> initial,string description,string prefix="ChooseShelf",bool allowCreate=true)
    {
        var options=new List<ShelfDescriptor>();
        void SyncOptions(ShelfDescriptor? fallback=null)
        {
            options=shelfDescriptors.ToList();
            if(fallback is not null&&options.All(s=>s.Id!=fallback.Id))options.Add(fallback);
            foreach(var id in initial.Where(id=>options.All(s=>s.Id!=id)))options.Add(new(id,AppText.L("見つからない棚（所属を維持）", "Missing shelf (membership kept)"),0));
        }
        SyncOptions();
        var selected=initial.ToHashSet();
        var filter=new TextBox{PlaceholderText=AppText.L("棚の名前で絞り込み", "Filter by shelf name"),MaxLength=128,HorizontalAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(filter,prefix+"Filter");AutomationProperties.SetName(filter,AppText.L("棚の名前で絞り込み", "Filter by shelf name"));
        var list=new ListView{SelectionMode=ListViewSelectionMode.Multiple,MaxHeight=260,MinHeight=96,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(list,prefix+"List");AutomationProperties.SetName(list,title);
        var guidance=new TextBlock{TextWrapping=TextWrapping.Wrap};
        var count=new TextBlock{TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
        AutomationProperties.SetAutomationId(count,prefix+"SelectionCount");AutomationProperties.SetLiveSetting(count,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        var panel=new StackPanel{Spacing=8};panel.Children.Add(guidance);
        TextBox? newShelfBox=null;
        Button? createShelfButton=null;
        TextBlock? createError=null;
        TextBlock? createNote=null;
        var createStayNote=AppText.L("作成した棚はキャンセルしても残ります", "Created shelves stay even if you click Cancel");
        if(allowCreate)
        {
            newShelfBox=new TextBox{PlaceholderText=AppText.L("新しい棚を作成", "Create new shelf"),MaxLength=80,MinWidth=0,HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(newShelfBox,prefix+"NewName");AutomationProperties.SetName(newShelfBox,AppText.L("新しい棚の名前", "New shelf name"));
            createShelfButton=new Button{Content=AppText.L("作成して選択", "Create & Select"),IsEnabled=false,VerticalAlignment=VerticalAlignment.Center};
            AutomationProperties.SetAutomationId(createShelfButton,prefix+"CreateNew");AutomationProperties.SetName(createShelfButton,AppText.L("新しい棚を作成して選択", "Create and select new shelf"));
            createNote=new TextBlock{Text=createStayNote,TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            AutomationProperties.SetAutomationId(createNote,prefix+"CreateNote");
            createError=new TextBlock{Visibility=Visibility.Collapsed,TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            AutomationProperties.SetAutomationId(createError,prefix+"CreateError");
            var createRow=new Grid{ColumnSpacing=8};
            createRow.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            createRow.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            Grid.SetColumn(newShelfBox,0);Grid.SetColumn(createShelfButton,1);
            createRow.Children.Add(newShelfBox);createRow.Children.Add(createShelfButton);
            panel.Children.Add(createRow);panel.Children.Add(createNote);panel.Children.Add(createError);
        }
        panel.Children.Add(filter);panel.Children.Add(count);panel.Children.Add(list);
        dialogOpen=true;
        var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=title,Content=panel,PrimaryButtonText=AppText.L("適用", "Apply"),CloseButtonText=AppText.L("キャンセル", "Cancel"),DefaultButton=ContentDialogButton.Primary};
        bool rebuilding=false;
        bool creating=false;
        dialog.Closing+=(_,closing)=>{if(creating)closing.Cancel=true;};
        void UpdateSummary()
        {
            var hidden=selected.Count(id=>!list.Items.OfType<ListViewItem>().Any(row=>(long)row.Tag==id));
            count.Text=AppText.L($"{list.Items.Count:N0} 件を表示・{selected.Count:N0} 件を選択", $"Showing {list.Items.Count:N0} · Selected {selected.Count:N0}")+(hidden>0?AppText.L($"（表示外 {hidden:N0} 件）", $" ({hidden:N0} hidden)"):"");
            dialog.IsPrimaryButtonEnabled=!creating&&selected.Count<=64;
            guidance.Text=selected.Count>64?AppText.L("棚は64件以内で選択してください。", "Select up to 64 shelves.")
                :options.Count==0?(allowCreate?AppText.L("棚がありません。上の欄から新しい棚を作成できます。", "No shelves yet. Create one using the field above."):AppText.L("棚がありません。左側の「棚」から作成できます。", "No shelves yet. Create one from Shelves on the left."))
                :description;
        }
        void Rebuild()
        {
            rebuilding=true;list.Items.Clear();
            foreach(var shelf in options.Where(shelf=>shelf.Name.Contains(filter.Text.Trim(),StringComparison.OrdinalIgnoreCase)))
            {
                var choice=new ListViewItem{Content=shelf.Name,Tag=shelf.Id};AutomationProperties.SetAutomationId(choice,prefix+shelf.Id);list.Items.Add(choice);
                if(selected.Contains(shelf.Id))list.SelectedItems.Add(choice);
            }
            rebuilding=false;UpdateSummary();
        }
        if(allowCreate&&newShelfBox is not null&&createShelfButton is not null&&createError is not null)
        {
            async Task CreateAndSelectShelfAsync()
            {
                if(creating)return;
                var name=newShelfBox.Text.Trim();
                if(name.Length==0)return;
                createError.Visibility=Visibility.Collapsed;createError.Text="";
                if(options.FirstOrDefault(s=>string.Equals(s.Name,name,StringComparison.CurrentCultureIgnoreCase)) is {} existing)
                {
                    selected.Add(existing.Id);newShelfBox.Text="";filter.Text="";Rebuild();return;
                }
                creating=true;newShelfBox.IsEnabled=false;createShelfButton.IsEnabled=false;dialog.IsPrimaryButtonEnabled=false;
                try
                {
                    var createdId=await api.Shelves.CreateAsync(name);
                    await RefreshShelfDescriptorsAsync();
                    SyncOptions(new ShelfDescriptor(createdId,name,0));
                    selected.Add(createdId);resultsNeedRefresh=true;
                    if(createNote is not null)createNote.Text=AppText.L($"棚「{name}」を作成しました（キャンセルしても残ります）", $"Created shelf \"{name}\" (kept even if you click Cancel)");
                    newShelfBox.Text="";filter.Text="";
                    Rebuild();
                }
                catch(Exception ex)
                {
                    AppLog.Error(ex);
                    createError.Text=string.IsNullOrWhiteSpace(ex.Message)?AppText.L("棚を作成できませんでした。別の名前で再試行してください。", "Could not create shelf. Try again with a different name."):ex.Message;
                    createError.Visibility=Visibility.Visible;
                }
                finally
                {
                    creating=false;
                    newShelfBox.IsEnabled=true;
                    createShelfButton.IsEnabled=!string.IsNullOrWhiteSpace(newShelfBox.Text);
                    UpdateSummary();
                }
            }
            newShelfBox.TextChanged+=(_,_)=>
            {
                if(createError.Visibility==Visibility.Visible){createError.Visibility=Visibility.Collapsed;createError.Text="";}
                createShelfButton.IsEnabled=!creating&&!string.IsNullOrWhiteSpace(newShelfBox.Text);
            };
            newShelfBox.KeyDown+=async(_,e)=>
            {
                if(e.Key==VirtualKey.Enter&&!string.IsNullOrWhiteSpace(newShelfBox.Text))
                {
                    e.Handled=true;
                    await CreateAndSelectShelfAsync();
                }
            };
            createShelfButton.Click+=async(_,_)=>await CreateAndSelectShelfAsync();
        }
        list.SelectionChanged+=(_,args)=>
        {
            if(rebuilding)return;
            foreach(var row in args.RemovedItems.OfType<ListViewItem>())selected.Remove((long)row.Tag);
            foreach(var row in args.AddedItems.OfType<ListViewItem>())selected.Add((long)row.Tag);
            UpdateSummary();
        };
        filter.TextChanged+=(_,_)=>Rebuild();Rebuild();
        if(await dialog.ShowAsync()!=ContentDialogResult.Primary)return null;
        var ids=selected.Order().ToArray();ShelfProtocol.ValidateIds(ids);return ids;
    }
}
