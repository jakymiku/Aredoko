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
            var source=new TextBox{Header="復元元",IsReadOnly=true,PlaceholderText="バックアップを選んでください",TextWrapping=TextWrapping.Wrap};
            var folder=new Button{Content="フォルダを選ぶ"};var zip=new Button{Content="ZIPを選ぶ"};
            var choose=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};choose.Children.Add(folder);choose.Children.Add(zip);
            var omit=new CheckBox{Content="AI検索用データも復元（含めなかったデータはあとで作り直せます）",IsChecked=false};
            var consent=new CheckBox{Content="元のライブラリを残したまま、復元先に切り替えて再起動する",Visibility=Visibility.Collapsed};
            var status=new TextBlock{Text="復元の状態を確認しています。",TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{Minimum=0,Maximum=100};var refresh=new Button{Content="状態を更新"};
            var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};actions.Children.Add(refresh);
            Button? backToBackup=fromBackup?new Button{Content="バックアップと復元へ戻る"}:null;
            if(backToBackup is not null){AutomationProperties.SetAutomationId(backToBackup,"BtnBackToBackup");actions.Children.Add(backToBackup);}
            foreach(var (control,id) in new (DependencyObject,string)[]{(source,"RestoreSource"),(folder,"RestoreChooseFolder"),(zip,"RestoreChooseZip"),(omit,"RestoreOmitVectors"),(consent,"RestoreConsent"),(status,"RestoreStatus"),(progress,"RestoreProgress"),(refresh,"RestoreRefresh")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(progress,"復元準備の進捗");
            panel.Children.Add(new TextBlock{Text="新しい場所に復元先を用意して確認します。現在のライブラリと元ファイルはそのまま残ります（画面を閉じても準備は続きます）。",TextWrapping=TextWrapping.Wrap});
            foreach(var control in new UIElement[]{source,choose,omit,progress,status,consent,actions})panel.Children.Add(control);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="バックアップから復元",PrimaryButtonText="復元先を準備して確認",SecondaryButtonText="準備を中止",CloseButtonText="閉じる",IsPrimaryButtonEnabled=false,IsSecondaryButtonEnabled=false,DefaultButton=ContentDialogButton.None,
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
                dialog.PrimaryButtonText=value.State=="completed"?"復元先に切り替えて再起動":"復元先を準備して確認";
                dialog.IsPrimaryButtonEnabled=!busy&&!value.RestartRequested&&(value.State=="completed"?value.SwitchSupported&&consent.IsChecked==true:!value.Active&&!string.IsNullOrEmpty(source.Text));
                dialog.SecondaryButtonText=value.State=="completed"?"準備した復元先を破棄":"準備を中止";
                dialog.IsSecondaryButtonEnabled=!busy&&!value.RestartRequested&&(value.Active||value.State=="completed");
                progress.Value=value.Progress*100;progress.IsIndeterminate=value.Active&&value.Progress==0;
                status.Text=value.State=="idle"?"バックアップを選んで復元の準備を始めてください。":value.Message;
                if(value.State=="completed"&&!value.SwitchSupported)status.Text+="\nこの起動方法では自動再起動に対応していません。配布版のAredoko.exeから起動してください。";
                if(operationError is not null)status.Text+="\n"+operationError;
                if(value.RestartRequested){status.Text="再起動の準備ができました。画面を閉じて切り替えています。";restart=true;dialog.Hide();}
            }
            async Task RefreshAsync()
            {
                var requested=revision;
                try{var value=await api.Restores.StatusAsync(lifetime.Token);if(requested==revision&&!busy){operationError=null;Render(value);}}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){if(open&&!disposed)status.Text="状態を確認できません。「状態を更新」で再確認してください。\n"+ex.Message;}
            }
            folder.Click+=async(_,_)=>
            {
                try{var picker=new FolderPicker(MainWindow.Current.AppWindow.Id){Title="復元元のバックアップ",CommitButtonText="このバックアップを選ぶ"};var picked=await picker.PickSingleFolderAsync();if(picked is not null&&open&&!disposed){source.Text=picked.Path;if(current is not null)Render(current);}}
                catch(Exception ex){if(open&&!disposed)status.Text=ex.Message;}
            };
            zip.Click+=async(_,_)=>
            {
                try{var picker=new FileOpenPicker(MainWindow.Current.AppWindow.Id){Title="復元元のZIPバックアップ"};picker.FileTypeFilter.Add(".zip");var picked=await picker.PickSingleFileAsync();if(picked is not null&&open&&!disposed){source.Text=picked.Path;if(current is not null)Render(current);}}
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
                catch(Exception ex){operationError="操作を確認できません。「状態を更新」で再確認してください。\n"+ex.Message;}
                finally{busy=false;deferral.Complete();if(current is not null)Render(current);}
            };
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy||current?.Id is not {} id||current.RestartRequested)return;
                var deferral=args.GetDeferral();busy=true;operationError=null;++revision;Render(current);
                try{current=current.State=="completed"?await api.Restores.DiscardAsync(id,lifetime.Token):await api.Restores.CancelAsync(id,lifetime.Token);consent.IsChecked=false;}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError="操作を確認できません。「状態を更新」で再確認してください。\n"+ex.Message;}
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
