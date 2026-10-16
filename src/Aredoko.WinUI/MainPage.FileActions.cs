using System.Diagnostics;
using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private void UpdateFileProperties()
    {
        FileProperties.IsExpanded=false;
        FilePropertyText.Text=active is null?"":LibraryFilePath.Describe(active,knownRoots.FirstOrDefault(r=>r.Id==active.RootId)?.Path??"登録先を確認できません");
    }
    private void OpenInShell(MediaRow row,bool explorer)
    {
        try
        {
            var root=knownRoots.FirstOrDefault(r=>r.Id==row.RootId&&r.Enabled)??throw new InvalidOperationException("フォルダを再登録してください。");
            if(row.Availability!="present")throw new InvalidOperationException("元ファイルにアクセスできません。");
            var path=LibraryFilePath.Resolve(root.Path,row.Location);
            for(var current=path;current is not null;current=System.IO.Path.GetDirectoryName(current))
            {
                if((System.IO.File.GetAttributes(current)&System.IO.FileAttributes.ReparsePoint)!=0)throw new InvalidOperationException("リンク先は開けません。登録先を確認してください。");
                if(string.Equals(System.IO.Path.TrimEndingDirectorySeparator(current),System.IO.Path.TrimEndingDirectorySeparator(root.Path),StringComparison.OrdinalIgnoreCase))break;
            }
            if(explorer&&!System.IO.Directory.Exists(path))
            {
                var start=new ProcessStartInfo("explorer.exe"){UseShellExecute=true};start.ArgumentList.Add("/select,"+path);Process.Start(start);
            }
            else Process.Start(new ProcessStartInfo(path){UseShellExecute=true});
        }
        catch(Exception ex){Failure(new InvalidOperationException("元ファイルを開けません。登録先・ファイルの状態と既定のアプリを確認してください。",ex));AppLog.Error(ex);}
    }
    private static bool IsFolderActionSource(object source)
    {
        for(var node=source as DependencyObject;node is not null&&node is not ListViewItem;node=VisualTreeHelper.GetParent(node))
            if(node is ButtonBase or TextBox)return true;
        return false;
    }
    private async Task RestoreRootAsync(RegisteredRootRow row)
    {
        if(disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        try
        {
            await api.PostAsync("api/library/roots",new System.Text.Json.Nodes.JsonObject{{"path",row.Path},{"consent",true},{"excludes",new System.Text.Json.Nodes.JsonArray(row.Exclusions.Select(s=>(System.Text.Json.Nodes.JsonNode?)System.Text.Json.Nodes.JsonValue.Create(s)).ToArray())},{"default_shelf",row.DefaultShelf},{"folder_books",row.FolderBooks},{"recursive",row.Recursive}});
            await RefreshSearchRootsAsync();await LoadAIScopeAsync();RenderFolderHub();
            Notice("再登録しました","タグ・棚を復元しました。必要に応じて設定からスキャンできます。");
        }
        catch(Exception ex){Failure(ex);}
        finally{transitions.Release();}
    }
    private void Folder_DragOver(object sender,DragEventArgs args)
    {
        if(args.DataView.Contains(StandardDataFormats.StorageItems))
        {args.AcceptedOperation=DataPackageOperation.Link;args.DragUIOverride.Caption="フォルダを登録候補にする";args.Handled=true;}
    }
    private async void Folder_Drop(object sender,DragEventArgs args)
    {
        if(disposed||dialogOpen||saving||!args.DataView.Contains(StandardDataFormats.StorageItems))return;
        args.Handled=true;var deferral=args.GetDeferral();
        try
        {
            var items=await args.DataView.GetStorageItemsAsync();
            if(items.Count!=1||items[0] is not StorageFolder folder)throw new InvalidOperationException("登録するフォルダを1つドロップしてください。");
            FolderAddPanel.Visibility=Visibility.Visible;RootPath.Text=folder.Path;RootFolderBooks.IsChecked=false;RootRecursive.IsChecked=true;RootPath.Focus(FocusState.Programmatic);
            Notice("フォルダを受け取りました","設定を確認して「登録」を押してください。");
        }
        catch(Exception ex){Failure(ex);}
        finally{deferral.Complete();}
    }
}
