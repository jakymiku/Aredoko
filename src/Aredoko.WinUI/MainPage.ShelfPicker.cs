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
        var list=new ListView{SelectionMode=ListViewSelectionMode.Multiple,MaxHeight=320,MinHeight=96,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(list,prefix+"List");AutomationProperties.SetName(list,title);
        foreach(var shelf in options)
        {
            var choice=new ListViewItem{Content=shelf.Name,Tag=shelf.Id};AutomationProperties.SetAutomationId(choice,prefix+shelf.Id);list.Items.Add(choice);
            if(initial.Contains(shelf.Id))list.SelectedItems.Add(choice);
        }
        var guidance=new TextBlock{Text=options.Count==0?"棚がありません。左側の「棚」から作成できます。":description,TextWrapping=TextWrapping.Wrap};
        var panel=new StackPanel{Spacing=8};panel.Children.Add(guidance);panel.Children.Add(list);
        dialogOpen=true;
        var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=title,Content=panel,PrimaryButtonText="適用",CloseButtonText="キャンセル",DefaultButton=ContentDialogButton.Close};
        list.SelectionChanged+=(_,_)=>{dialog.IsPrimaryButtonEnabled=list.SelectedItems.Count<=64;guidance.Text=list.SelectedItems.Count>64?"棚は64件以内で選択してください。":description;};
        if(await dialog.ShowAsync()!=ContentDialogResult.Primary)return null;
        var ids=list.SelectedItems.OfType<ListViewItem>().Select(x=>(long)x.Tag).Order().ToArray();ShelfProtocol.ValidateIds(ids);return ids;
    }
}
