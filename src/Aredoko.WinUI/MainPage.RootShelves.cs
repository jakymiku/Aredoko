using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private void ShowRootShelfSelection(IReadOnlyList<long> ids)
    {
        var before=folderPopulating;folderPopulating=true;
        try
        {
            foreach(var previous in RootInitialShelf.Items.OfType<ComboBoxItem>().Where(x=>x.Tag?.ToString()=="multiple").ToArray())RootInitialShelf.Items.Remove(previous);
            var names=ids.Count==0?AppText.L("棚なし", "None"):string.Join(AppText.L("、", ", "),ids.Select(ShelfName));
            var option=new ComboBoxItem{Content=names,Tag="multiple"};ToolTipService.SetToolTip(option,names);
            RootInitialShelf.Items.Add(option);RootInitialShelf.SelectedItem=option;RootNewShelf.IsEnabled=false;
        }
        finally{folderPopulating=before;}
    }
    private async void ChooseRootShelves_Click(object sender,RoutedEventArgs args)
    {
        if(folderDraft is null||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        var detailsWereOpen=Details.IsPaneOpen;
        var draft=folderDraft;
        try
        {
            await RefreshShelfDescriptorsAsync();
            if(disposed||saving||dialogOpen||!ReferenceEquals(folderDraft,draft))return;
            var ids=await PickShelfIdsAsync(AppText.L("自動で入れる棚を選択", "Choose Default Shelves"),draft.ShelfIdsToSave??Array.Empty<long>(),
                draft.IsBatch?AppText.L($"{draft.TargetIds.Count}フォルダの「自動で入れる棚」を設定します", $"Choose default shelves for {draft.TargetIds.Count} folder(s)"):AppText.L("新規作品を入れる棚を選びます", "Choose shelves for newly scanned items"),prefix:"ChooseRootShelf");
            if(ids is null||!ReferenceEquals(folderDraft,draft))return;
            draft.SelectShelfIds(ids);ShowRootShelfSelection(ids);UpdateFolderDraftState();
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            dialogOpen=false;
            if(!disposed&&detailsWereOpen&&folderSettingsActive&&ReferenceEquals(folderDraft,draft))
                Details.IsPaneOpen=true;
            transitions.Release();
        }
    }
}
