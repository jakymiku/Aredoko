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
            var capacity=new TextBlock{Text="容量を確認しています…",TextWrapping=TextWrapping.Wrap};
            var path=new TextBox{Header="ダウンロードキャッシュの保存先",IsReadOnly=true,TextWrapping=TextWrapping.Wrap};
            var help=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var status=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{IsIndeterminate=true,Visibility=Visibility.Collapsed};
            var consent=new CheckBox{Content="修復や再構築のときに再ダウンロードが必要になることに同意する"};
            var folder=new Button{Content="保存先を開く",IsEnabled=false};
            var refresh=new Button{Content="状態を更新"};
            var buttons=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};buttons.Children.Add(folder);buttons.Children.Add(refresh);
            Button? backToSettings=fromSettings?new Button{Content="設定へ戻る"}:null;
            if(backToSettings is not null){AutomationProperties.SetAutomationId(backToSettings,"BtnBackToSettings");buttons.Children.Add(backToSettings);}
            var manualDeleteNote=new Expander{Header="手動で削除する場合の注意",HorizontalAlignment=HorizontalAlignment.Stretch,Content=new TextBlock{Text="取得・構築・検証が完了してから、上の保存先フォルダ内にある .whl ファイル（wheel）だけを対象にしてください。",TextWrapping=TextWrapping.Wrap}};
            var panel=new StackPanel{Spacing=12,MaxWidth=650};
            panel.Children.Add(capacity);panel.Children.Add(path);panel.Children.Add(help);panel.Children.Add(buttons);
            panel.Children.Add(new TextBlock{Text="モデル本体・実行環境・登録情報は削除しません（取得・構築・検証中は削除できません）。",TextWrapping=TextWrapping.Wrap});
            panel.Children.Add(manualDeleteNote);
            panel.Children.Add(consent);panel.Children.Add(progress);panel.Children.Add(status);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AIのダウンロードキャッシュ",PrimaryButtonText="キャッシュを削除…",SecondaryButtonText="中止",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,Content=panel,IsPrimaryButtonEnabled=false,IsSecondaryButtonEnabled=false};
            AutomationProperties.SetAutomationId(dialog,"RuntimeCacheDialog");AutomationProperties.SetAutomationId(path,"RuntimeCachePath");
            AutomationProperties.SetAutomationId(capacity,"RuntimeCacheCapacity");AutomationProperties.SetAutomationId(consent,"RuntimeCacheConsent");
            AutomationProperties.SetAutomationId(folder,"RuntimeCacheOpenFolder");AutomationProperties.SetAutomationId(status,"RuntimeCacheStatus");
            AutomationProperties.SetLiveSetting(status,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
            bool Active()=>current?["state"]?.GetValue<string>() is "checking" or "deleting";
            void Render()
            {
                if(!open||disposed)return;
                var bytes=summary?["bytes"]?.GetValue<long>()??0;var files=summary?["files"]?.GetValue<int>()??0;
                if(summary is not null){capacity.Text=summary["bytes"] is not null&&summary["files"] is not null?$"対象　{bytes/1_000_000_000d:N2} GB・{files:N0}ファイル":"対象　未確認";path.Text=summary["path"]?.GetValue<string>()??"";help.Text=summary["message"]?.GetValue<string>()??"";}
                var active=Active();dialog.IsPrimaryButtonEnabled=!busy&&!active&&consent.IsChecked==true&&(summary?["can_delete"]?.GetValue<bool>()??false);
                dialog.IsSecondaryButtonEnabled=!busy&&current?["state"]?.GetValue<string>()=="checking";
                folder.IsEnabled=!busy&&!active&&(summary?["exists"]?.GetValue<bool>()??false);refresh.IsEnabled=!busy;
                if(backToSettings is not null)backToSettings.IsEnabled=!busy;
                consent.IsEnabled=!busy&&!active;progress.Visibility=active?Visibility.Visible:Visibility.Collapsed;
                var total=current?["bytes_total"]?.GetValue<long>()??0;var done=current?["bytes_done"]?.GetValue<long>()??0;
                progress.IsIndeterminate=total<=0;progress.Value=total>0?Math.Clamp(100d*done/total,0,100):0;
                status.Text=current?["message"]?.GetValue<string>()??"";
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
                catch(Exception ex){if(open&&!disposed){status.Text="状態を確認できません。「状態を更新」で再確認してください。\n"+ex.Message;dialog.IsPrimaryButtonEnabled=false;}}
            }
            consent.Checked+=(_,_)=>Render();consent.Unchecked+=(_,_)=>Render();
            folder.Click+=async(_,_)=>{try{if(!await Windows.System.Launcher.LaunchFolderPathAsync(path.Text))status.Text="保存先を開けませんでした。表示されたパスを確認してください。";}catch(Exception ex){status.Text="保存先を開けません: "+ex.Message;}};
            refresh.Click+=async(_,_)=>{if(polling is null||polling.IsCompleted){polling=RefreshAsync();await polling;}};
            if(backToSettings is not null)backToSettings.Click+=(_,_)=>{if(!busy){returnToSettings=true;dialog.Hide();}};
            dialog.PrimaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(!dialog.IsPrimaryButtonEnabled)return;
                var deferral=args.GetDeferral();busy=true;operationError=null;Render();
                try{current=await api.PostAsync("api/library/runtime-cache/clear",new JsonObject{["consent"]=true});consent.IsChecked=false;}
                catch(Exception ex){operationError="削除の開始を確認できません。状態を更新してください。\n"+ex.Message;}
                finally{busy=false;deferral.Complete();Render();}
            };
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy)return;var deferral=args.GetDeferral();busy=true;operationError=null;Render();
                try{current=await api.PostAsync("api/library/runtime-cache/cancel",new JsonObject());}
                catch(Exception ex){operationError="中止を確認できません。状態を更新してください。\n"+ex.Message;}
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
