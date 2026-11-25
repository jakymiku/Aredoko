using System.Diagnostics;
using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.System;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private bool rootPathComposing;
    private void RootPath_CompositionStarted(TextBox sender,TextCompositionStartedEventArgs args)=>rootPathComposing=true;
    private void RootPath_CompositionEnded(TextBox sender,TextCompositionEndedEventArgs args)=>rootPathComposing=false;
    private static bool IsUnmodifiedEnter(KeyRoutedEventArgs e)=>!e.Handled&&e.Key==VirtualKey.Enter&&
        !SelectionKey(VirtualKey.Control)&&!SelectionKey(VirtualKey.Shift)&&!SelectionKey(VirtualKey.Menu)&&
        !SelectionKey(VirtualKey.LeftWindows)&&!SelectionKey(VirtualKey.RightWindows);
    private void RootPath_KeyDown(object sender,KeyRoutedEventArgs e)
    {
        if(!IsUnmodifiedEnter(e)||rootPathComposing||!ready||disposed||saving||dialogOpen||
           !FolderRegistrationEditor.IsEnabled||!AddRoot.IsEnabled||string.IsNullOrWhiteSpace(RootPath.Text))return;
        e.Handled=true;
        AddRoot_Click(AddRoot,new RoutedEventArgs());
    }
    private void UpdateFileProperties()
    {
        FileProperties.IsExpanded=false;
        FilePropertyText.Text=active is null?"":LibraryFilePath.Describe(active,knownRoots.FirstOrDefault(r=>r.Id==active.RootId)?.Path??AppText.L("登録先を確認できません", "Unable to verify folder path"));
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
            var root=knownRoots.FirstOrDefault(r=>r.Id==row.RootId&&r.Enabled)??throw new InvalidOperationException(AppText.L("フォルダを再登録してください。", "Please re-register the folder."));
            if(row.Availability!="present")throw new InvalidOperationException(AppText.L("元ファイルにアクセスできません。", "Cannot access the source file."));
            var path=LibraryFilePath.Resolve(root.Path,row.Location);
            for(var current=path;current is not null;current=System.IO.Path.GetDirectoryName(current))
            {
                if((System.IO.File.GetAttributes(current)&System.IO.FileAttributes.ReparsePoint)!=0)throw new InvalidOperationException(AppText.L("リンク先は開けません。登録先を確認してください。", "Cannot open reparse points or symbolic links. Check the registered path."));
                if(string.Equals(System.IO.Path.TrimEndingDirectorySeparator(current),System.IO.Path.TrimEndingDirectorySeparator(root.Path),StringComparison.OrdinalIgnoreCase))break;
            }
            if(explorer&&!System.IO.Directory.Exists(path))
            {
                ShellReveal.SelectFile(path);
            }
            else Process.Start(new ProcessStartInfo(path){UseShellExecute=true});
            return true;
        }
        catch(Exception ex){if(reportFailure)Failure(new InvalidOperationException(AppText.L("外部アプリで開けません。状態と既定のアプリを確認してください", "Cannot open in external app. Check file status and default app settings."),ex));AppLog.Error(ex);return false;}
    }
    private void CopyFilePath(MediaRow row)
    {
        try
        {
            var root=knownRoots.FirstOrDefault(r=>r.Id==row.RootId&&r.Enabled)
                ??throw new InvalidOperationException(AppText.L("登録フォルダを確認してください。", "Check the registered folder."));
            var path=LibraryFilePath.Resolve(root.Path,row.Location);
            var package=new DataPackage();package.SetText(path);Clipboard.SetContent(package);
            Notice(AppText.L("パスをコピーしました", "Path copied"),AppText.L("他のアプリへ貼り付けできます。", "Ready to paste into other apps."),InfoBarSeverity.Success);
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
                Title=AppText.L("外部アプリで開けませんでした", "Could not open in external app"),
                Content=$"{row.Title}\n\n"+AppText.L("Aredoko で開きますか？", "Open inside Aredoko instead?"),
                PrimaryButtonText=AppText.L("Aredokoで開く", "Open in Aredoko"),CloseButtonText=AppText.L("閉じる", "Close"),DefaultButton=ContentDialogButton.Close};
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
            thumbnails.ResetSession();
            await RefreshSearchRootsAsync();await LoadAIScopeAsync();RenderFolderHub();
            Notice(AppText.L("再登録しました", "Re-registered"),AppText.L("タグ・棚を復元しました。必要に応じて「⟳ 更新」から一覧を更新できます。", "Tags and shelves were restored. Click Refresh if you want to update the list."));
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
                Title=AppText.L("記録を完全に削除しますか？", "Permanently purge catalog records?"),
                Content=AppText.L(
                    $"{row.ShortPath}（{row.Path}）\n\n• 削除されるもの：登録履歴・タグ・棚・お気に入り・履歴・読書位置・AI検索データ\n• 残るもの：PC上の元ファイル（変更・削除されません）\n\n⚠ この操作は元に戻せません。",
                    $"{row.ShortPath} ({row.Path})\n\n• Deleted: registration history, tags, shelves, favorites, history, reading progress, AI index data\n• Kept: original files on your PC (untouched)\n\n⚠ This cannot be undone."),
                PrimaryButtonText=AppText.L("記録を削除", "Purge Records"),
                CloseButtonText=AppText.L("キャンセル", "Cancel"),
                DefaultButton=ContentDialogButton.Close
            };
            var accepted=await dialog.ShowAsync()==ContentDialogResult.Primary;
            dialogOpen=false;
            if(!accepted||disposed)return;
            var result=await api.PostAsync("api/library/roots/purge",new System.Text.Json.Nodes.JsonObject{{"root_id",row.Id},{"consent",true}});
            var removed=result["removed_items"]?.GetValue<int>()??0;
            thumbnails.ResetSession();
            await RefreshSearchRootsAsync();await LoadAIScopeAsync();RenderFolderHub();
            Notice(AppText.L("記録を削除しました", "Records purged"),AppText.L($"{removed:N0}件（元ファイルは変更なし）", $"{removed:N0} item(s) removed (source files untouched)"));
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();}
    }
    private void Folder_DragOver(object sender,DragEventArgs args)
    {
        if(args.DataView.Contains(StandardDataFormats.StorageItems))
        {args.AcceptedOperation=DataPackageOperation.Link;args.DragUIOverride.Caption=AppText.L("フォルダを登録候補にする", "Add folder");args.Handled=true;}
    }
    private async void Folder_Drop(object sender,DragEventArgs args)
    {
        if(disposed||dialogOpen||saving||!args.DataView.Contains(StandardDataFormats.StorageItems))return;
        args.Handled=true;var deferral=args.GetDeferral();
        try
        {
            var items=await args.DataView.GetStorageItemsAsync();
            var folders=items.OfType<StorageFolder>().Select(f=>f.Path).Where(p=>!string.IsNullOrWhiteSpace(p)).ToArray();
            if(folders.Length==0)throw new InvalidOperationException(AppText.L("登録するフォルダをドロップしてください。", "Drop folders to register."));
            FolderAddPanel.Visibility=Visibility.Visible;RootPath.Text=string.Join("; ",folders);RootFolderBooks.IsChecked=false;RootRecursive.IsChecked=true;RootPath.Focus(FocusState.Programmatic);
            Notice(AppText.L("フォルダを受け取りました", "Folders received"),AppText.L("設定を確認して「追加」を押してください。", "Check the options and click Add."));
        }
        catch(Exception ex){Failure(ex);}
        finally{deferral.Complete();}
    }
}
