using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Windows.Storage.Pickers;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task OpenBackupDialogAsync(bool fromSettings=false)
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;bool showGuide=false,showRestore=false,returnToSettings=false,open=true,submitting=false;long revision=0;
        using var lifetime=new CancellationTokenSource();BackupJob? current=null;Task? polling=null;string? lastError=null;
        var timer=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(650)};
        try
        {
            var selected=BackupSelection.Load(ViewerOptions.BackupChoicesPath);
            var panel=new StackPanel{Spacing=12};
            var basic=new TextBlock{Text=AppText.L("必ず含む　登録フォルダ・タグ・棚・お気に入り", "Always included: Registered folders, tags, shelves, favorites"),TextWrapping=TextWrapping.Wrap,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]};
            var optionalHeading=new TextBlock{Text=AppText.L("追加で含める項目", "Optional items"),Style=(Style)Resources["MediaMetadataStyle"],Margin=new Thickness(0,4,0,0)};
            var settings=new CheckBox{Content=AppText.L("設定", "Settings"),IsChecked=selected.Settings};
            var history=new CheckBox{Content=AppText.L("閲覧履歴", "Reading History"),IsChecked=selected.History};
            var position=new CheckBox{Content=AppText.L("本の読書位置", "Book Reading Progress"),IsChecked=selected.ReaderProgress};
            var vectors=new CheckBox{Content=AppText.L("AI検索データ（大容量・あとで再作成可）", "AI Search Index Data (large, rebuildable later)"),IsChecked=selected.Vectors};
            var destination=new TextBox{Header=AppText.L("保存先", "Destination"),IsReadOnly=true,PlaceholderText=AppText.L("保存するフォルダを選んでください", "Choose a folder to save backup"),TextWrapping=TextWrapping.Wrap};
            var choose=new Button{Content=AppText.L("保存先を選ぶ", "Choose Folder"),VerticalAlignment=VerticalAlignment.Bottom};
            var excludeNote=new TextBlock{Text=AppText.L("対象外：元ファイル・AIモデル・環境・サムネイル（閉じても続行）", "Excluded: source files, AI models/runtime, thumbnails (continues if closed)"),TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            var status=new TextBlock{Text=AppText.L("バックアップの状態を確認しています。", "Checking backup status."),TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{IsIndeterminate=false,Minimum=0,Maximum=100,Value=0,Visibility=Visibility.Collapsed};
            var reconnect=new Button{Content=AppText.L("状態を更新", "Refresh")};
            var guide=new Button{Content=AppText.L("バックアップから復元", "Restore from Backup")};
            var help=new Button{Content=AppText.L("復元の手順", "Recovery Guide")};
            AutomationProperties.SetAutomationId(help,"BackupRecoveryHelp");
            var restoreRow=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};restoreRow.Children.Add(guide);restoreRow.Children.Add(help);
            var utilRow=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};utilRow.Children.Add(reconnect);
            Button? backToSettings=fromSettings?new Button{Content=AppText.L("設定へ戻る", "Back to Settings")}:null;
            if(backToSettings is not null){AutomationProperties.SetAutomationId(backToSettings,"BtnBackToSettings");utilRow.Children.Add(backToSettings);}
            foreach(var (control,id) in new (DependencyObject,string)[]{(basic,"BackupBasic"),(settings,"BackupSettings"),(history,"BackupHistory"),(position,"BackupReaderPosition"),(vectors,"BackupVectors"),(destination,"BackupDestination"),(choose,"BackupChoose"),(status,"BackupStatus"),(progress,"BackupProgress"),(reconnect,"BackupRefresh"),(guide,"BackupRestoreGuide")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(progress,AppText.L("バックアップの進捗", "Backup progress"));
            var itemsStack=new StackPanel{Spacing=4};
            foreach(var control in new UIElement[]{basic,optionalHeading,settings,history,position,vectors})itemsStack.Children.Add(control);
            var itemsCard=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=itemsStack};
            var destRow=new Grid{ColumnSpacing=8};
            destRow.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            destRow.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            destRow.Children.Add(destination);Grid.SetColumn(choose,1);destRow.Children.Add(choose);
            var destStack=new StackPanel{Spacing=8};destStack.Children.Add(destRow);destStack.Children.Add(excludeNote);
            var destCard=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=destStack};
            foreach(var control in new UIElement[]{itemsCard,destCard,progress,status,restoreRow,utilRow})panel.Children.Add(control);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("バックアップと復元", "Backup & Restore"),PrimaryButtonText=AppText.L("バックアップを作成", "Create Backup"),SecondaryButtonText=AppText.L("作成を中止", "Cancel"),CloseButtonText=AppText.L("閉じる", "Close"),IsPrimaryButtonEnabled=false,IsSecondaryButtonEnabled=false,DefaultButton=ContentDialogButton.None,
                Content=new ScrollViewer{Content=panel,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,Padding=new Thickness(0,0,16,0)}};
            AutomationProperties.SetAutomationId(dialog,"BackupDialog");
            void Render(BackupJob job)
            {
                if(!open||disposed)return;
                current=job;bool busy=submitting||job.Active;
                foreach(var control in new Control[]{settings,history,position,vectors,choose})control.IsEnabled=!busy;
                if(backToSettings is not null)backToSettings.IsEnabled=!submitting;
                dialog.IsPrimaryButtonEnabled=!busy&&!string.IsNullOrEmpty(destination.Text)&&!(job.Published&&job.Output==destination.Text);
                dialog.IsSecondaryButtonEnabled=job.Active&&job.State is not ("cancelling" or "publishing")&&!submitting;
                progress.Visibility=job.Active||job.Published?Visibility.Visible:Visibility.Collapsed;
                progress.IsIndeterminate=job.Active&&job.BytesTotal is not >0;
                progress.Value=job.BytesTotal is >0?Math.Clamp(100d*job.BytesDone/job.BytesTotal.Value,0,100):job.Published?100:0;
                status.Text=job.Message;
                if(job.Active&&job.BytesTotal is >0)status.Text+=$"\n{job.BytesDone/1048576d:N1} / {job.BytesTotal.Value/1048576d:N1} MB";
                if(job.Published&&job.Output is not null)status.Text+=AppText.L("\n保存先: ", "\nSaved to: ")+job.Output;
                if(job.State=="idle")status.Text=AppText.L("保存先と対象を選んで作成してください。ライブラリ情報は必ず含まれます。", "Select destination and options, then create backup. Core library data is always included.");
                if(lastError is not null)status.Text+="\n"+lastError;
                if(job.Active&&job.Selection is {} choices)
                {settings.IsChecked=choices.Settings;history.IsChecked=choices.History;position.IsChecked=choices.ReaderProgress;vectors.IsChecked=choices.Vectors;destination.Text=job.Output??"";}
            }
            async Task RefreshAsync()
            {
                var requested=revision;
                try{var job=await api.Backups.StatusAsync(lifetime.Token);if(requested==revision&&!submitting){lastError=null;Render(job);}}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){if(open&&!disposed)status.Text=AppText.L("状態を確認できません。作成済みのデータは保持されます。\n", "Unable to check status. Created data is preserved.\n")+ex.Message;}
            }
            choose.Click+=async(_,_)=>
            {
                try
                {
                    var picker=new FolderPicker(MainWindow.Current.AppWindow.Id){Title=AppText.L("バックアップの保存先", "Backup Destination"),CommitButtonText=AppText.L("ここに保存", "Save Here")};
                    var folder=await picker.PickSingleFolderAsync();
                    if(folder is not null&&open&&!disposed){destination.Text=System.IO.Path.Combine(folder.Path,"Aredoko-backup-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N")[..6]);if(current is not null)Render(current);}
                }
                catch(Exception ex){if(open&&!disposed)status.Text=AppText.L("保存先を選べませんでした。\n", "Could not select destination.\n")+ex.Message;}
            };
            reconnect.Click+=async(_,_)=>{if(!submitting&&(polling is null||polling.IsCompleted)){polling=RefreshAsync();await polling;}};
            guide.Click+=(_,_)=>{showRestore=true;dialog.Hide();};
            help.Click+=(_,_)=>{showGuide=true;dialog.Hide();};
            if(backToSettings is not null)backToSettings.Click+=(_,_)=>{if(!submitting){returnToSettings=true;dialog.Hide();}};
            dialog.PrimaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(submitting||current is null||current.Active)return;
                var deferral=args.GetDeferral();submitting=true;lastError=null;++revision;Render(current);
                try
                {
                    var choices=new BackupSelection(settings.IsChecked==true,history.IsChecked==true,position.IsChecked==true,vectors.IsChecked==true);
                    var viewer=ViewerOptions.Value with{LibraryItemScale=libraryItemScale};
                    var job=await api.Backups.StartAsync(destination.Text,choices,viewer,lifetime.Token);
                    current=job;
                    try{choices.Save(ViewerOptions.BackupChoicesPath);}catch(Exception error)when(error is IOException or UnauthorizedAccessException){AppLog.Error(error);}
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){lastError=AppText.L("開始を確認できません。「状態を更新」で確認してください。\n", "Unable to confirm start. Click Refresh to check.\n")+ex.Message;}
                finally{submitting=false;if(current is not null)Render(current);deferral.Complete();}
            };
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(submitting||current?.Id is not {} id)return;
                var deferral=args.GetDeferral();submitting=true;lastError=null;++revision;Render(current);
                try{current=await api.Backups.CancelAsync(id,lifetime.Token);}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){lastError=AppText.L("中止を確認できません。「状態を更新」で確認してください。\n", "Unable to confirm cancellation. Click Refresh to check.\n")+ex.Message;}
                finally{submitting=false;if(current is not null)Render(current);deferral.Complete();}
            };
            timer.Tick+=(_,_)=>{if(!submitting&&current?.Active==true&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            var closed=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed+=(_,_)=>closed.TrySetResult(true);
            dialog.Opened+=(_,_)=>{polling=RefreshAsync();timer.Start();};
            await dialog.ShowAsync();await Task.WhenAny(closed.Task,Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;
            dialogOpen=false;transitions.Release();RestoreNavigation();
        }
        if(showRestore&&!disposed)await OpenRestoreDialogAsync(fromBackup:true,fromSettings:fromSettings);
        else if(showGuide&&!disposed)await OpenRecoveryGuideDialogAsync(fromBackup:true,fromSettings:fromSettings);
        else if(returnToSettings&&!disposed)await OpenSettingsAsync();
    }
}
