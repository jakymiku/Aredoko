using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private async Task<long[]?> PickShelfIdsAsync(string title,IReadOnlyList<long> initial,string description,string prefix="ChooseShelf")
    {
        var options=shelfDescriptors.ToList();
        foreach(var id in initial.Where(id=>options.All(s=>s.Id!=id)))options.Add(new(id,"見つからない棚（所属を維持）",0));
        var selected=initial.ToHashSet();
        var filter=new TextBox{PlaceholderText="棚の名前で絞り込み",MaxLength=128,HorizontalAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(filter,prefix+"Filter");AutomationProperties.SetName(filter,"棚の名前で絞り込み");
        var list=new ListView{SelectionMode=ListViewSelectionMode.Multiple,MaxHeight=320,MinHeight=96,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(list,prefix+"List");AutomationProperties.SetName(list,title);
        var guidance=new TextBlock{TextWrapping=TextWrapping.Wrap};
        var count=new TextBlock{TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
        AutomationProperties.SetAutomationId(count,prefix+"SelectionCount");AutomationProperties.SetLiveSetting(count,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        var panel=new StackPanel{Spacing=8};panel.Children.Add(guidance);panel.Children.Add(filter);panel.Children.Add(count);panel.Children.Add(list);
        dialogOpen=true;
        var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=title,Content=panel,PrimaryButtonText="適用",CloseButtonText="キャンセル",DefaultButton=ContentDialogButton.Close};
        bool rebuilding=false;
        void UpdateSummary()
        {
            var hidden=selected.Count(id=>!list.Items.OfType<ListViewItem>().Any(row=>(long)row.Tag==id));
            count.Text=$"{list.Items.Count:N0} 件を表示・{selected.Count:N0} 件を選択"+(hidden>0?$"（表示外 {hidden:N0} 件）":"");
            dialog.IsPrimaryButtonEnabled=selected.Count<=64;
            guidance.Text=selected.Count>64?"棚は64件以内で選択してください。":options.Count==0?"棚がありません。左側の「棚」から作成できます。":description;
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
