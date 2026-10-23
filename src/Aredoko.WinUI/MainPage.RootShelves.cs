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
            var names=ids.Count==0?"棚なし":string.Join("、",ids.Select(ShelfName));
            var option=new ComboBoxItem{Content=names,Tag="multiple"};ToolTipService.SetToolTip(option,names);
            RootInitialShelf.Items.Add(option);RootInitialShelf.SelectedItem=option;RootNewShelf.IsEnabled=false;
        }
        finally{folderPopulating=before;}
    }
    private async void ChooseRootShelves_Click(object sender,RoutedEventArgs args)
    {
        if(folderDraft is null||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try
        {
            var draft=folderDraft;await RefreshShelfDescriptorsAsync();
            if(disposed||saving||dialogOpen||!ReferenceEquals(folderDraft,draft))return;
            var ids=await PickShelfIdsAsync("初期棚を選択",draft.ShelfIdsToSave??Array.Empty<long>(),
                draft.IsBatch?$"選択した {draft.TargetIds.Count} フォルダに同じ初期棚を設定します。保存すると新規登録する作品に適用します。":"新規登録する作品に設定する棚を選択してください。",prefix:"ChooseRootShelf");
            if(ids is null||!ReferenceEquals(folderDraft,draft))return;
            draft.SelectShelfIds(ids);ShowRootShelfSelection(ids);UpdateFolderDraftState();
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();}
    }
}
