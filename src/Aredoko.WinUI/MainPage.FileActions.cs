using System.Diagnostics;
using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
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
        OpenFileLocation.IsEnabled=CopySelectedFilePath.IsEnabled=active is {Availability:"present"};
    }
    private void OpenFileLocation_Click(object sender,RoutedEventArgs e)
    {
        if(active is {Availability:"present"} row)OpenInShell(row,true);
    }
    private void CopySelectedFilePath_Click(object sender,RoutedEventArgs e)
    {
        if(active is {Availability:"present"} row)CopyFilePath(row);
    }
    private bool OpenInShell(MediaRow row,bool explorer,bool reportFailure=true)
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
                ShellReveal.SelectFile(path);
            }
            else Process.Start(new ProcessStartInfo(path){UseShellExecute=true});
            return true;
        }
        catch(Exception ex){if(reportFailure)Failure(new InvalidOperationException("元ファイルを開けません。登録先・ファイルの状態と既定のアプリを確認してください。",ex));AppLog.Error(ex);return false;}
    }
    private void CopyFilePath(MediaRow row)
    {
        try
        {
            var root=knownRoots.FirstOrDefault(r=>r.Id==row.RootId&&r.Enabled)
                ??throw new InvalidOperationException("登録フォルダを確認してください。");
            var path=LibraryFilePath.Resolve(root.Path,row.Location);
            var package=new DataPackage();package.SetText(path);Clipboard.SetContent(package);
            Notice("パスをコピーしました","他のアプリへ貼り付けできます。",InfoBarSeverity.Success);
            Status.IsOpen=true;
        }
        catch(Exception ex){Failure(ex);}
    }
    private readonly ExternalActivationGate externalActivation=new();
    // True only when the user explicitly chooses the internal fallback.
    private async Task<bool> OpenPreferredExternalAsync(MediaRow row)
    {
        if(!externalActivation.TryActivate(row.Id,Environment.TickCount64,(int)GetDoubleClickTime()))return false;
        if(!await transitions.WaitAsync(0))return false;
        dialogOpen=true;
        try
        {
            if(OpenInShell(row,false,reportFailure:false))
            {
                RecordContentOpened(row.Id);
                return false;
            }
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,
                Title="既定のアプリで開けませんでした",
                Content=$"{row.Title}\n\nファイルへのアクセスやWindowsの関連付けを確認してください。Aredokoの内蔵ビューアでも開けます。",
                PrimaryButtonText="内蔵ビューアで開く",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.Close};
            AutomationProperties.SetAutomationId(dialog,"ExternalViewerFallback");
            return await dialog.ShowAsync()==ContentDialogResult.Primary;
        }
        catch(Exception ex){Failure(ex);return false;}
        finally{dialogOpen=false;transitions.Release();}
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
    private async Task PurgeInactiveRootAsync(RegisteredRootRow row)
    {
        if(disposed||dialogOpen||saving||row.Enabled||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        try
        {
            var dialog=new ContentDialog
            {
                RequestedTheme=ActualTheme,
                XamlRoot=XamlRoot,
                Title="解除済みフォルダの記録を完全削除",
                Content=$"{row.ShortPath}（{row.Path}）の登録履歴・タグ・棚・お気に入り・閲覧履歴・読書位置・AI索引をデータベースから完全に削除します。\nPC上の元ファイルは変更・削除されません。この操作は元に戻せません。",
                PrimaryButtonText="記録を完全削除",
                CloseButtonText="キャンセル",
                DefaultButton=ContentDialogButton.Close
            };
            var accepted=await dialog.ShowAsync()==ContentDialogResult.Primary;
            dialogOpen=false;
            if(!accepted||disposed)return;
            var result=await api.PostAsync("api/library/roots/purge",new System.Text.Json.Nodes.JsonObject{{"root_id",row.Id},{"consent",true}});
            var removed=result["removed_items"]?.GetValue<int>()??0;
            await RefreshSearchRootsAsync();await LoadAIScopeAsync();RenderFolderHub();
            Notice("記録を完全削除しました",$"解除済みフォルダのデータベース記録（{removed:N0}件）を削除しました。元ファイルは変更していません。");
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();}
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
            var folders=items.OfType<StorageFolder>().Select(f=>f.Path).Where(p=>!string.IsNullOrWhiteSpace(p)).ToArray();
            if(folders.Length==0)throw new InvalidOperationException("登録するフォルダをドロップしてください。");
            FolderAddPanel.Visibility=Visibility.Visible;RootPath.Text=string.Join("; ",folders);RootFolderBooks.IsChecked=false;RootRecursive.IsChecked=true;RootPath.Focus(FocusState.Programmatic);
            Notice("フォルダを受け取りました","設定を確認して「登録」を押してください。");
        }
        catch(Exception ex){Failure(ex);}
        finally{deferral.Complete();}
    }
}
