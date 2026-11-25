using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private bool startupUpdatesRequested, startupUpdatesRunning, startupPollBusy;
    private Microsoft.UI.Dispatching.DispatcherQueueTimer? startupUpdateTimer;

    private async Task BeginStartupUpdatesAsync()
    {
        if(disposed||startupUpdatesRequested)return;
        startupUpdatesRequested=true;
        try
        {
            await api.PostAsync("api/library/startup-scan/start",new JsonObject{["frontend_ready"]=true});
            if(disposed)return;
            startupUpdateTimer=DispatcherQueue.CreateTimer();
            startupUpdateTimer.Interval=TimeSpan.FromMilliseconds(750);
            startupUpdateTimer.Tick+=async(_,_)=>await PollStartupUpdatesAsync();
            startupUpdateTimer.Start();
            await PollStartupUpdatesAsync();
        }
        catch(Exception ex)
        {
            AppLog.Error(ex);
            if(disposed)return;
            StartupUpdateBar.Title=AppText.L("起動時の更新を開始できません", "Unable to start startup scan");
            StartupUpdateBar.Message=AppText.L("登録フォルダの設定から手動でスキャンできます。", "You can manually scan from Registered Folders settings.");
            StartupUpdateBar.Severity=InfoBarSeverity.Warning;
            StartupUpdateAction.Visibility=Visibility.Collapsed;
            StartupUpdateBar.IsOpen=true;
        }
    }

    private async Task PollStartupUpdatesAsync()
    {
        if(disposed||startupPollBusy)return;
        startupPollBusy=true;
        try
        {
            var state=await api.GetAsync("api/library/startup-scan");
            if(disposed)return;
            startupUpdatesRunning=state["state"]?.GetValue<string>()=="running";
            var total=state["total"]?.GetValue<int>()??0;
            var done=state["processed"]?.GetValue<int>()??0;
            StartupUpdateAction.Visibility=Visibility.Visible;
            StartupUpdateAction.IsEnabled=true;
            StartupUpdateAction.Content=startupUpdatesRunning?AppText.L("中止", "Cancel"):AppText.L("一覧を更新", "Refresh");
            StartupUpdateBar.Title=AppText.L("起動時の更新", "Startup Update");
            if(startupUpdatesRunning)
            {
                StartupUpdateBar.Message=AppText.L($"起動時の更新 {done}/{total} フォルダ", $"Startup update: {done}/{total} folder(s)");
                StartupUpdateBar.Severity=InfoBarSeverity.Informational;
                StartupUpdateBar.IsOpen=true;
            }
            else
            {
                startupUpdateTimer?.Stop();
                if(total==0){StartupUpdateBar.IsOpen=false;return;}
                // Do not replace the current selection or discard an editing draft
                // when the background queue completes. Refresh is explicit.
                resultsNeedRefresh=true;
                var warning=state["state"]?.GetValue<string>()=="cancelled"
                    ||state["results"]?.AsArray().Any(row=>row?["state"]?.GetValue<string>()!="complete"
                        ||row?["ai_state"]?.GetValue<string>() is "failed" or "error" or "skipped" or "cancelled" or "unknown")==true;
                StartupUpdateBar.Message=warning
                    ?AppText.L($"一部のフォルダを更新できませんでした（{done}/{total}）", $"Some folders could not be updated ({done}/{total})")
                    :AppText.L($"{done}フォルダを更新しました", $"Updated {done} folder(s)");
                StartupUpdateBar.Severity=warning?InfoBarSeverity.Warning:InfoBarSeverity.Success;
                StartupUpdateBar.IsOpen=true;
            }
        }
        catch(Exception ex)
        {
            AppLog.Error(ex);startupUpdateTimer?.Stop();
            if(!disposed)
            {
                StartupUpdateBar.Title=AppText.L("起動時の更新状況を取得できません", "Cannot read startup update status");
                StartupUpdateBar.Message=AppText.L("登録フォルダ画面でスキャンの状態を確認できます。", "Check scan status in the Registered Folders screen.");
                StartupUpdateBar.Severity=InfoBarSeverity.Warning;
                StartupUpdateAction.Visibility=Visibility.Collapsed;
                StartupUpdateBar.IsOpen=true;
            }
        }
        finally{startupPollBusy=false;}
    }

    private async void StartupUpdateAction_Click(object sender,RoutedEventArgs e)
    {
        if(disposed||saving||dialogOpen)return;
        StartupUpdateAction.IsEnabled=false;
        try
        {
            if(startupUpdatesRunning)
            {
                await api.PostAsync("api/library/startup-scan/cancel",new JsonObject());
                await PollStartupUpdatesAsync();
            }
            else
            {
                await NavigateAsync(0,true);
                if(!resultsNeedRefresh)StartupUpdateBar.IsOpen=false;
            }
        }
        catch(Exception ex){Failure(ex);}
        finally{if(!disposed)StartupUpdateAction.IsEnabled=true;}
    }

    private void RestoreStartupScanChoice()
    {
        if(folderDraft is null)return;
        var targets=knownRoots.Where(root=>folderDraft.TargetIds.Contains(root.Id)).ToArray();
        var previous=folderPopulating;folderPopulating=true;
        try
        {
            RootStartupScan.SelectedIndex=targets.Length>0&&targets.All(root=>root.StartupScan==targets[0].StartupScan)
                ?targets[0].StartupScan switch{"list"=>1,"list_and_ai"=>2,_=>0}:-1;
        }
        finally{folderPopulating=previous;}
    }

    private async void RootStartupScan_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(folderPopulating||disposed||folderDraft is null||RootStartupScan.SelectedIndex<0)return;
        if(saving||dialogOpen||!await transitions.WaitAsync(0)){RestoreStartupScanChoice();return;}
        var targets=folderDraft.TargetIds.ToArray();
        var mode=RootStartupScan.SelectedIndex switch{1=>"list",2=>"list_and_ai",_=>"none"};
        // Do not disable a ComboBox synchronously inside SelectionChanged:
        // its native SelectionItem provider may still be completing the action.
        // The saving/transition guard serializes requests and restores rapid input.
        saving=true;FolderEditStatus.Text=AppText.L("起動時の設定を保存しています…", "Saving startup settings...");
        try
        {
            await api.PostAsync("api/library/roots/startup-scan",new JsonObject
                {["root_ids"]=new JsonArray(targets.Select(id=>JsonValue.Create(id)).ToArray()),["mode"]=mode});
            knownRoots=knownRoots.Select(root=>targets.Contains(root.Id)?root with{StartupScan=mode}:root).ToArray();
            if(!disposed)RestoreStartupScanChoice();
            if(!disposed)FolderEditStatus.Text=AppText.L("起動時の設定を保存しました。次回起動から適用します。", "Saved startup settings. Changes apply on next launch.")+(FolderDirty?AppText.L("ほかに未保存の変更があります。", " Other edits are still unsaved."):"");
        }
        catch(Exception ex){if(!disposed){RestoreStartupScanChoice();Failure(ex);}}
        finally
        {
            saving=false;transitions.Release();
            if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
}
