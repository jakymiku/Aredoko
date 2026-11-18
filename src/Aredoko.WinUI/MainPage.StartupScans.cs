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
            StartupUpdateBar.Title="起動時の更新を開始できません";
            StartupUpdateBar.Message="登録フォルダの設定から手動でスキャンできます。";
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
            StartupUpdateAction.Content=startupUpdatesRunning?"中止":"一覧を更新";
            StartupUpdateBar.Title=startupUpdatesRunning?"起動時の更新":"起動時の更新";
            if(startupUpdatesRunning)
            {
                StartupUpdateBar.Message=$"起動時の更新 {done}/{total} フォルダ";
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
                    ?$"一部のフォルダを更新できませんでした（{done}/{total}）"
                    :$"{done}フォルダを更新しました";
                StartupUpdateBar.Severity=warning?InfoBarSeverity.Warning:InfoBarSeverity.Success;
                StartupUpdateBar.IsOpen=true;
            }
        }
        catch(Exception ex)
        {
            AppLog.Error(ex);startupUpdateTimer?.Stop();
            if(!disposed)
            {
                StartupUpdateBar.Title="起動時の更新状況を取得できません";
                StartupUpdateBar.Message="登録フォルダ画面でスキャンの状態を確認できます。";
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
        saving=true;FolderEditStatus.Text="起動時の設定を保存しています…";
        try
        {
            await api.PostAsync("api/library/roots/startup-scan",new JsonObject
                {["root_ids"]=new JsonArray(targets.Select(id=>JsonValue.Create(id)).ToArray()),["mode"]=mode});
            knownRoots=knownRoots.Select(root=>targets.Contains(root.Id)?root with{StartupScan=mode}:root).ToArray();
            if(!disposed)RestoreStartupScanChoice();
            if(!disposed)FolderEditStatus.Text="起動時の設定を保存しました。次回起動から適用します。"+(FolderDirty?"ほかに未保存の変更があります。":"");
        }
        catch(Exception ex){if(!disposed){RestoreStartupScanChoice();Failure(ex);}}
        finally
        {
            saving=false;transitions.Release();
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
}
