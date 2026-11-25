using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task OpenRuntimeCacheDialogAsync(bool fromSettings=false)
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;bool open=true,busy=false,returnToSettings=false;Task? polling=null;
        using var lifetime=new CancellationTokenSource();
        var timer=new DispatcherTimer{Interval=TimeSpan.FromSeconds(1)};
        try
        {
            JsonNode? summary=null,current=null;string? operationError=null;
            var capacity=new TextBlock{Text=AppText.L("容量を確認しています…", "Checking cache size..."),TextWrapping=TextWrapping.Wrap,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]};
            var path=new TextBox{Header=AppText.L("ダウンロードキャッシュの保存先", "Download cache folder"),IsReadOnly=true,TextWrapping=TextWrapping.Wrap};
            var help=new TextBlock{TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            var status=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{IsIndeterminate=true,Visibility=Visibility.Collapsed};
            var consent=new CheckBox{Content=AppText.L("修復や再構築のときに再ダウンロードが必要になることに同意する", "I understand that repairing or rebuilding the runtime will require re-downloading")};
            var folder=new Button{Content=AppText.L("保存先を開く", "Open Folder"),IsEnabled=false};
            var refresh=new Button{Content=AppText.L("状態を更新", "Refresh")};
            var buttons=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};buttons.Children.Add(folder);buttons.Children.Add(refresh);
            Button? backToSettings=fromSettings?new Button{Content=AppText.L("設定へ戻る", "Back to Settings")}:null;
            if(backToSettings is not null){AutomationProperties.SetAutomationId(backToSettings,"BtnBackToSettings");buttons.Children.Add(backToSettings);}
            var manualDeleteNote=new Expander{Header=AppText.L("手動削除の注意", "Manual deletion note"),HorizontalAlignment=HorizontalAlignment.Stretch,Content=new TextBlock{Text=AppText.L("処理完了後に、上の保存先内の .whl ファイルだけを削除してください", "Only delete .whl files inside the folder above after downloads finish"),TextWrapping=TextWrapping.Wrap}};
            var panel=new StackPanel{Spacing=12,MaxWidth=650};
            var infoStack=new StackPanel{Spacing=8};
            infoStack.Children.Add(capacity);infoStack.Children.Add(path);infoStack.Children.Add(help);infoStack.Children.Add(buttons);
            panel.Children.Add(new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=infoStack});
            var cacheSafeNote=new TextBlock{Text=AppText.L("不要になったダウンロードファイル（.whl）だけを削除します。モデル・登録情報は残ります", "Deletes only unused installer files (.whl). AI models and your library remain intact"),TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            ToolTipService.SetToolTip(cacheSafeNote,AppText.L("取得・構築・検証中は削除できません", "Cannot delete while downloading, building, or verifying"));
            var cleanStack=new StackPanel{Spacing=8};
            cleanStack.Children.Add(cacheSafeNote);cleanStack.Children.Add(consent);cleanStack.Children.Add(manualDeleteNote);
            panel.Children.Add(new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=cleanStack});
            panel.Children.Add(progress);panel.Children.Add(status);
            var scroll=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),Padding=new Thickness(0,0,16,0),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("ダウンロード済みファイルの整理", "Clean Up Downloaded Files"),PrimaryButtonText=AppText.L("キャッシュを削除…", "Delete Cache..."),SecondaryButtonText=AppText.L("中止", "Cancel"),CloseButtonText=AppText.L("閉じる", "Close"),DefaultButton=ContentDialogButton.None,Content=scroll,IsPrimaryButtonEnabled=false,IsSecondaryButtonEnabled=false};
            AutomationProperties.SetAutomationId(dialog,"RuntimeCacheDialog");AutomationProperties.SetAutomationId(path,"RuntimeCachePath");
            AutomationProperties.SetAutomationId(capacity,"RuntimeCacheCapacity");AutomationProperties.SetAutomationId(consent,"RuntimeCacheConsent");
            AutomationProperties.SetAutomationId(folder,"RuntimeCacheOpenFolder");AutomationProperties.SetAutomationId(status,"RuntimeCacheStatus");
            AutomationProperties.SetLiveSetting(status,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
            bool Active()=>current?["state"]?.GetValue<string>() is "checking" or "deleting";
            void Render()
            {
                if(!open||disposed)return;
                var bytes=summary?["bytes"]?.GetValue<long>()??0;var files=summary?["files"]?.GetValue<int>()??0;
                if(summary is not null){capacity.Text=summary["bytes"] is not null&&summary["files"] is not null?AppText.L($"対象　{bytes/1_000_000_000d:N2} GB・{files:N0}ファイル", $"Target: {bytes/1_000_000_000d:N2} GB · {files:N0} file(s)"):AppText.L("対象　未確認", "Target: Unconfirmed");path.Text=summary["path"]?.GetValue<string>()??"";help.Text=AppText.TranslateBackend(summary["message"]?.GetValue<string>());}
                var active=Active();dialog.IsPrimaryButtonEnabled=!busy&&!active&&consent.IsChecked==true&&(summary?["can_delete"]?.GetValue<bool>()??false);
                dialog.IsSecondaryButtonEnabled=!busy&&current?["state"]?.GetValue<string>()=="checking";
                folder.IsEnabled=!busy&&!active&&(summary?["exists"]?.GetValue<bool>()??false);refresh.IsEnabled=!busy;
                if(backToSettings is not null)backToSettings.IsEnabled=!busy;
                consent.IsEnabled=!busy&&!active;progress.Visibility=active?Visibility.Visible:Visibility.Collapsed;
                var total=current?["bytes_total"]?.GetValue<long>()??0;var done=current?["bytes_done"]?.GetValue<long>()??0;
                progress.IsIndeterminate=total<=0;progress.Value=total>0?Math.Clamp(100d*done/total,0,100):0;
                status.Text=AppText.TranslateBackend(current?["message"]?.GetValue<string>());
                if(operationError is not null)status.Text+="\n"+operationError;
                if(active&&total>0)status.Text+=$"\n{done/1_000_000d:N1} / {total/1_000_000d:N1} MB";
            }
            async Task RefreshAsync()
            {
                try
                {
                    if(Active())current=await api.GetAsync("api/library/runtime-cache/job",lifetime.Token);
                    if(!Active()){summary=await api.GetAsync("api/library/runtime-cache",lifetime.Token);current=summary["job"];}
                    operationError=null;Render();
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){if(open&&!disposed){status.Text=AppText.L("状態を確認できません。「状態を更新」で再確認してください。\n", "Unable to check status. Click Refresh to retry.\n")+ex.Message;dialog.IsPrimaryButtonEnabled=false;}}
            }
            consent.Checked+=(_,_)=>Render();consent.Unchecked+=(_,_)=>Render();
            folder.Click+=async(_,_)=>{try{if(!await Windows.System.Launcher.LaunchFolderPathAsync(path.Text))status.Text=AppText.L("保存先を開けませんでした。表示されたパスを確認してください。", "Could not open folder. Check the displayed path.");}catch(Exception ex){status.Text=AppText.L("保存先を開けません: ", "Cannot open folder: ")+ex.Message;}};
            refresh.Click+=async(_,_)=>{if(polling is null||polling.IsCompleted){polling=RefreshAsync();await polling;}};
            if(backToSettings is not null)backToSettings.Click+=(_,_)=>{if(!busy){returnToSettings=true;dialog.Hide();}};
            dialog.PrimaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(!dialog.IsPrimaryButtonEnabled)return;
                var deferral=args.GetDeferral();busy=true;operationError=null;Render();
                try{current=await api.PostAsync("api/library/runtime-cache/clear",new JsonObject{["consent"]=true});consent.IsChecked=false;}
                catch(Exception ex){operationError=AppText.L("削除の開始を確認できません。状態を更新してください。\n", "Could not confirm deletion start. Click Refresh.\n")+ex.Message;}
                finally{busy=false;deferral.Complete();Render();}
            };
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy)return;var deferral=args.GetDeferral();busy=true;operationError=null;Render();
                try{current=await api.PostAsync("api/library/runtime-cache/cancel",new JsonObject());}
                catch(Exception ex){operationError=AppText.L("中止を確認できません。状態を更新してください。\n", "Could not confirm cancellation. Click Refresh.\n")+ex.Message;}
                finally{busy=false;deferral.Complete();Render();}
            };
            dialog.Closing+=(_,args)=>{if(busy)args.Cancel=true;};
            dialog.Opened+=(_,_)=>{polling=RefreshAsync();timer.Start();};
            timer.Tick+=(_,_)=>{if(Active()&&!busy&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            var closedTcs=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed+=(_,_)=>closedTcs.TrySetResult(true);
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task,Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally{open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(returnToSettings&&!disposed)await OpenSettingsAsync();
    }
}
