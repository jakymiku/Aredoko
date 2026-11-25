using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Windows.Storage.Pickers;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task OpenRestoreDialogAsync(bool fromBackup=false,bool fromSettings=false)
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        bool open=true,busy=false,restart=false,returnToBackup=false;long revision=0;RestoreJob? current=null;Task? polling=null;string? operationError=null;
        using var lifetime=new CancellationTokenSource();
        var timer=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(650)};
        try
        {
            if(!await ConfirmDiscardAsync())return;
            dialogOpen=true;
            var panel=new StackPanel{Spacing=12};
            var source=new TextBox{Header=AppText.L("復元元", "Backup Source"),IsReadOnly=true,PlaceholderText=AppText.L("バックアップを選んでください", "Choose a backup"),TextWrapping=TextWrapping.Wrap};
            var folder=new Button{Content=AppText.L("フォルダを選ぶ", "Choose Folder")};var zip=new Button{Content=AppText.L("ZIPを選ぶ", "Choose ZIP")};
            var choose=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};choose.Children.Add(folder);choose.Children.Add(zip);
            var omit=new CheckBox{Content=AppText.L("AI検索データも復元", "Also restore AI search index"),IsChecked=false};
            var consent=new CheckBox{Content=AppText.L("復元後に再起動して切り替える（元のライブラリは残ります）", "Restart to switch after restore (previous library stays intact)"),Visibility=Visibility.Collapsed};
            var status=new TextBlock{Text=AppText.L("状態を確認中…", "Checking status..."),TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{Minimum=0,Maximum=100,Visibility=Visibility.Collapsed};var refresh=new Button{Content=AppText.L("状態を更新", "Refresh")};
            var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};actions.Children.Add(refresh);
            Button? backToBackup=fromBackup?new Button{Content=AppText.L("バックアップと復元へ戻る", "Back to Backup & Restore")}:null;
            if(backToBackup is not null){AutomationProperties.SetAutomationId(backToBackup,"BtnBackToBackup");actions.Children.Add(backToBackup);}
            foreach(var (control,id) in new (DependencyObject,string)[]{(source,"RestoreSource"),(folder,"RestoreChooseFolder"),(zip,"RestoreChooseZip"),(omit,"RestoreOmitVectors"),(consent,"RestoreConsent"),(status,"RestoreStatus"),(progress,"RestoreProgress"),(refresh,"RestoreRefresh")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(progress,AppText.L("復元準備の進捗", "Restore preparation progress"));
            var sourceStack=new StackPanel{Spacing=8};
            sourceStack.Children.Add(new TextBlock{Text=AppText.L("新しい場所に復元します（現在のライブラリ・元ファイルは残ります）", "Restores into a staged location (your current library and source files remain intact)"),TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]});
            sourceStack.Children.Add(source);sourceStack.Children.Add(choose);sourceStack.Children.Add(omit);
            var sourceCard=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=sourceStack};
            foreach(var control in new UIElement[]{sourceCard,progress,status,consent,actions})panel.Children.Add(control);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("バックアップから復元", "Restore from Backup"),PrimaryButtonText=AppText.L("復元先を準備", "Prepare Restore"),SecondaryButtonText=AppText.L("中止", "Cancel"),CloseButtonText=AppText.L("閉じる", "Close"),IsPrimaryButtonEnabled=false,IsSecondaryButtonEnabled=false,DefaultButton=ContentDialogButton.None,
                Content=new ScrollViewer{Content=panel,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,Padding=new Thickness(0,0,16,0)}};
            AutomationProperties.SetAutomationId(dialog,"RestoreDialog");
            void Render(RestoreJob value)
            {
                if(!open||disposed)return;
                var first=current is null;current=value;
                // Failed/cancelled jobs retain their own evidence; a new picker
                // selection and AI policy are the inputs for the next attempt.
                var syncInputs=value.Active||value.State=="completed"||value.RestartRequested;
                if(value.Source is not null&&(syncInputs||string.IsNullOrEmpty(source.Text)))source.Text=value.Source;
                if(value.WithoutVectors is {} policy&&(syncInputs||first))omit.IsChecked=!policy;
                var frozen=busy||value.Active||value.State=="completed"||value.RestartRequested;
                folder.IsEnabled=zip.IsEnabled=omit.IsEnabled=!frozen;
                consent.Visibility=value.State=="completed"?Visibility.Visible:Visibility.Collapsed;
                consent.IsEnabled=!busy&&!value.RestartRequested&&value.SwitchSupported;
                if(backToBackup is not null)backToBackup.IsEnabled=!busy&&!value.RestartRequested;
                dialog.PrimaryButtonText=value.State=="completed"?AppText.L("切り替えて再起動", "Switch & Restart"):AppText.L("復元先を準備", "Prepare Restore");
                dialog.IsPrimaryButtonEnabled=!busy&&!value.RestartRequested&&(value.State=="completed"?value.SwitchSupported&&consent.IsChecked==true:!value.Active&&!string.IsNullOrEmpty(source.Text));
                dialog.SecondaryButtonText=value.State=="completed"?AppText.L("準備した復元先を破棄", "Discard Staged Restore"):AppText.L("中止", "Cancel");
                dialog.IsSecondaryButtonEnabled=!busy&&!value.RestartRequested&&(value.Active||value.State=="completed");
                progress.Visibility=value.Active||value.State=="completed"?Visibility.Visible:Visibility.Collapsed;
                progress.Value=value.Progress*100;progress.IsIndeterminate=value.Active&&value.Progress==0;
                status.Text=value.State=="idle"?AppText.L("バックアップを選んで復元を開始してください", "Choose a backup to start restore"):value.Message;
                if(value.State=="completed"&&!value.SwitchSupported)status.Text+=AppText.L("\n自動再起動できません。Aredoko.exe から起動し直してください", "\nCannot restart automatically. Relaunch from Aredoko.exe.");
                if(operationError is not null)status.Text+="\n"+operationError;
                if(value.RestartRequested){status.Text=AppText.L("再起動の準備ができました。画面を閉じて切り替えています。", "Ready to restart. Closing and switching libraries...");restart=true;dialog.Hide();}
            }
            async Task RefreshAsync()
            {
                var requested=revision;
                try{var value=await api.Restores.StatusAsync(lifetime.Token);if(requested==revision&&!busy){operationError=null;Render(value);}}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){if(open&&!disposed)status.Text=AppText.L("状態を確認できません。「状態を更新」で再確認してください。\n", "Unable to check status. Click Refresh to retry.\n")+ex.Message;}
            }
            folder.Click+=async(_,_)=>
            {
                try{var picker=new FolderPicker(MainWindow.Current.AppWindow.Id){Title=AppText.L("復元元のバックアップ", "Backup to Restore"),CommitButtonText=AppText.L("このバックアップを選ぶ", "Choose Backup")};var picked=await picker.PickSingleFolderAsync();if(picked is not null&&open&&!disposed){source.Text=picked.Path;if(current is not null)Render(current);}}
                catch(Exception ex){if(open&&!disposed)status.Text=ex.Message;}
            };
            zip.Click+=async(_,_)=>
            {
                try{var picker=new FileOpenPicker(MainWindow.Current.AppWindow.Id){Title=AppText.L("復元元のZIPバックアップ", "ZIP Backup to Restore")};picker.FileTypeFilter.Add(".zip");var picked=await picker.PickSingleFileAsync();if(picked is not null&&open&&!disposed){source.Text=picked.Path;if(current is not null)Render(current);}}
                catch(Exception ex){if(open&&!disposed)status.Text=ex.Message;}
            };
            consent.Checked+=(_,_)=>{if(current is not null)Render(current);};consent.Unchecked+=(_,_)=>{if(current is not null)Render(current);};
            refresh.Click+=async(_,_)=>{if(!busy&&(polling is null||polling.IsCompleted)){polling=RefreshAsync();await polling;}};
            if(backToBackup is not null)backToBackup.Click+=(_,_)=>{if(!busy&&current?.RestartRequested!=true){returnToBackup=true;dialog.Hide();}};
            dialog.PrimaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy||current is null||current.Active||current.RestartRequested)return;
                if(current.State=="completed"&&(!current.SwitchSupported||consent.IsChecked!=true))return;
                var deferral=args.GetDeferral();busy=true;operationError=null;++revision;Render(current);
                try
                {
                    if(current.State=="completed")
                    {await FlushReaderProgressAsync();current=await api.Restores.RestartAsync(current.Id!,lifetime.Token);}
                    else current=await api.Restores.StartAsync(source.Text,omit.IsChecked!=true,lifetime.Token);
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError=AppText.L("操作を確認できません。「状態を更新」で再確認してください。\n", "Unable to confirm operation. Click Refresh to retry.\n")+ex.Message;}
                finally{busy=false;deferral.Complete();if(current is not null)Render(current);}
            };
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy||current?.Id is not {} id||current.RestartRequested)return;
                var deferral=args.GetDeferral();busy=true;operationError=null;++revision;Render(current);
                try{current=current.State=="completed"?await api.Restores.DiscardAsync(id,lifetime.Token):await api.Restores.CancelAsync(id,lifetime.Token);consent.IsChecked=false;}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError=AppText.L("操作を確認できません。「状態を更新」で再確認してください。\n", "Unable to confirm operation. Click Refresh to retry.\n")+ex.Message;}
                finally{busy=false;deferral.Complete();if(current is not null)Render(current);}
            };
            dialog.Closing+=(_,args)=>{if(busy)args.Cancel=true;};
            timer.Tick+=(_,_)=>{if(!busy&&current?.Active==true&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            dialog.Opened+=(_,_)=>{polling=RefreshAsync();timer.Start();};
            var closedTcs=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed+=(_,_)=>closedTcs.TrySetResult(true);
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task,Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;
            dialogOpen=false;transitions.Release();RestoreNavigation();
        }
        if(restart&&!disposed)MainWindow.Current.CompleteRestoreRestart();
        else if(returnToBackup&&!disposed)await OpenBackupDialogAsync(fromSettings:fromSettings);
    }
}
