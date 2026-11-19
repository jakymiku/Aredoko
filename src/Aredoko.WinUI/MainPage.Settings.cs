using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private bool settingsPopulating;
    private bool? savedVerificationState;
    private string settingsReturnCount="";
    private CancellationTokenSource? settingsLoadLifetime;

    private async void Navigation_ItemInvoked(NavigationView sender,NavigationViewItemInvokedEventArgs args)
    {
        if(args.InvokedItemContainer is NavigationViewItem {Tag:"settings"})await OpenSettingsAsync("all");
        else if(args.InvokedItemContainer is NavigationViewItem {Tag:"ai"})await OpenSettingsAsync("ai");
        else if(!shelfHubOpen&&selectedShelfIds is not null&&args.InvokedItemContainer is NavigationViewItem {Tag:"shelf"})await OpenShelfHubAsync();
    }

    private void CloseSettingsHubCore()
    {
        if(!settingsHubOpen&&SettingsHubView?.Visibility!=Visibility.Visible)return;
        settingsLoadLifetime?.Cancel();
        settingsLoadLifetime?.Dispose();
        settingsLoadLifetime=null;
        settingsHubOpen=false;
        if(SettingsHubView is not null)SettingsHubView.Visibility=Visibility.Collapsed;
        UpdateLibraryHeading();
        ItemSearchRow.Visibility=SearchTools.Visibility=ItemListContainer.Visibility=ItemPagerRow.Visibility=Visibility.Visible;
    }

    private void SetSettingsCategory(string category)
    {
        currentSettingsCategory=category;
        var selected=ThemeStyle("SelectedSegmentButtonStyle");
        var unselected=ThemeStyle("UnselectedSegmentButtonStyle");
        if(SettingsCatAllButton is not null)SettingsCatAllButton.Style=category=="all"?selected:unselected;
        if(SettingsCatGeneralButton is not null)SettingsCatGeneralButton.Style=category=="general"?selected:unselected;
        if(SettingsCatLibraryButton is not null)SettingsCatLibraryButton.Style=category=="library"?selected:unselected;
        if(SettingsCatAIButton is not null)SettingsCatAIButton.Style=category=="ai"?selected:unselected;
        if(SettingsCatMaintenanceButton is not null)SettingsCatMaintenanceButton.Style=category=="maintenance"?selected:unselected;
        if(SettingsSectionAI is not null)SettingsSectionAI.Visibility=category is "all" or "ai"?Visibility.Visible:Visibility.Collapsed;
        if(SettingsSectionGeneral is not null)SettingsSectionGeneral.Visibility=category is "all" or "general"?Visibility.Visible:Visibility.Collapsed;
        if(SettingsSectionLibrary is not null)SettingsSectionLibrary.Visibility=category is "all" or "library"?Visibility.Visible:Visibility.Collapsed;
        if(SettingsSectionMaintenance is not null)SettingsSectionMaintenance.Visibility=category is "all" or "maintenance"?Visibility.Visible:Visibility.Collapsed;
        SettingsScroll?.ChangeView(null,0,null,true);
        RestoreNavigation();
    }

    private async Task OpenSettingsAsync(string? category=null)
    {
        if(!ready||disposed||dialogOpen||saving)
        {
            RestoreNavigation();
            return;
        }
        if(settingsHubOpen)
        {
            if(category is not null)SetSettingsCategory(category);
            return;
        }
        if(!await transitions.WaitAsync(0))
        {
            RestoreNavigation();
            return;
        }
        try
        {
            if(!await ConfirmDiscardAsync())
            {
                RestoreNavigation();
                return;
            }
            CloseBrowseMenus();
            if(!folderHubOpen&&!shelfHubOpen)settingsReturnCount=Count.Text;
            CloseFolderHubCore();
            CloseShelfHubCore();
            settingsHubOpen=true;
            active=null;
            Details.IsPaneOpen=false;
            DetailsButton.IsEnabled=false;
            MainViewTitle.Text="設定";
            Count.Text="";
            ItemSearchRow.Visibility=SearchTools.Visibility=ItemListContainer.Visibility=ItemPagerRow.Visibility=Visibility.Collapsed;
            SettingsHubView.Visibility=Visibility.Visible;
            settingsPopulating=true;
            try
            {
                SettingsThemeCombo.SelectedIndex=ViewerOptions.Value.Theme switch{"light"=>1,"dark"=>2,_=>0};
                SettingsDoubleClickCheck.IsChecked=ViewerOptions.Value.OpenExternally;
                SettingsWheelCombo.SelectedIndex=ViewerOptions.Value.WheelUpAdvances?1:0;
                SettingsInstantStatus.Text="変更した設定はすぐに反映されます";
            }
            finally{settingsPopulating=false;}
            SetSettingsCategory(category??"all");
        }
        catch(Exception ex){Failure(ex);}
        finally{transitions.Release();}
        if(settingsHubOpen&&!disposed)_ = LoadSettingsStatusAsync();
    }

    private async Task LoadSettingsStatusAsync()
    {
        settingsLoadLifetime?.Cancel();
        settingsLoadLifetime?.Dispose();
        var cts=new CancellationTokenSource();
        settingsLoadLifetime=cts;
        var token=cts.Token;
        if(SettingsVerifyAIRuntimeCheck is not null)SettingsVerifyAIRuntimeCheck.IsEnabled=false;
        try
        {
            var setupTask=api.GetAsync("api/library/ai/setup",token);
            var statusTask=api.GetAsync("api/library/ai/status",token);
            await Task.WhenAll(setupTask,statusTask);
            if(token.IsCancellationRequested||disposed||!settingsHubOpen)return;

            var setup=await setupTask;
            savedVerificationState=setup["verify_ai_runtime"]?.GetValue<bool>()??true;
            settingsPopulating=true;
            try
            {
                if(SettingsVerifyAIRuntimeCheck is not null)
                {
                    SettingsVerifyAIRuntimeCheck.IsChecked=savedVerificationState;
                    SettingsVerifyAIRuntimeCheck.IsEnabled=true;
                }
            }
            finally{settingsPopulating=false;}

            var statusData=await statusTask;
            ApplyRuntimeVerificationSnapshot(statusData);
            var available=statusData["available"]?.GetValue<bool>()==true;
            var accent=ThemeStyle("AccentButtonStyle");
            if(SettingsAIIndexButton is not null)SettingsAIIndexButton.Style=available?accent:null;
            if(SettingsAIEnvironmentButton is not null)SettingsAIEnvironmentButton.Style=available?null:accent;
            var state=statusData["state"]?.GetValue<string>()??"idle";
            var processed=statusData["processed"]?.GetValue<int>()??0;
            var total=statusData["total"]?.GetValue<int>()??0;
            var model=statusData["model"]?.GetValue<string>()??"";
            var statusCode=statusData["status_code"]?.GetValue<string>()??"";
            var errorText=statusData["error"]?.GetValue<string>()??"";
            if(available)
            {
                SettingsAIStep1Status.Text="✓ 導入済み";
                SettingsAIStep2Status.Text=string.IsNullOrWhiteSpace(model)?"✓ 使用可能":$"✓ {model}";
                SettingsAIStep3Status.Text=state switch
                {
                    "complete"=>$"✓ 作成済み（{processed}/{total}）",
                    "running"=>$"作成中（{processed}/{total}）",
                    "cancelling"=>"中断中",
                    "partial"=>$"一部作成（{processed}/{total}）",
                    _=>"未作成"
                };
                SettingsAINextHint.Text=state=="complete"
                    ?"AI検索の準備が整っています。検索欄の［AI］から使えます。"
                    :"［AI検索を設定］から対象フォルダのAI検索データを作成できます。";
            }
            else
            {
                var needsRuntime=statusCode.Contains("runtime")||errorText.Contains("Python")||errorText.Contains("ライブラリ");
                if(needsRuntime)
                {
                    SettingsAIStep1Status.Text="未導入";
                    SettingsAIStep2Status.Text="環境導入後に設定";
                    SettingsAIStep3Status.Text="待機中";
                    SettingsAINextHint.Text="［AIの自動セットアップ］または［AI検索を設定］から実行環境を用意してください。";
                }
                else
                {
                    SettingsAIStep1Status.Text="✓ 導入済み";
                    SettingsAIStep2Status.Text="未導入 / 要確認";
                    SettingsAIStep3Status.Text="待機中";
                    SettingsAINextHint.Text="［AI検索を設定］から検索モデルをダウンロードまたは指定してください。";
                }
            }
        }
        catch(OperationCanceledException) when(token.IsCancellationRequested){}
        catch(Exception ex)
        {
            AppLog.Error(ex);
            if(!token.IsCancellationRequested&&!disposed&&settingsHubOpen)
            {
                SettingsAIStep1Status.Text="確認できません";
                SettingsAIStep2Status.Text="—";
                SettingsAIStep3Status.Text="—";
                SettingsAINextHint.Text="バックエンドに接続できないため状態を取得できませんでした。";
            }
        }
    }

    private void SaveInstantViewerOptions(string statusMessage)
    {
        var selectedTheme=SettingsThemeCombo.SelectedIndex switch{1=>"light",2=>"dark",_=>"system"};
        var openExternally=SettingsDoubleClickCheck.IsChecked==true;
        var wheelUp=SettingsWheelCombo.SelectedIndex==1;
        ViewerOptions.SavePreferences(wheelUp,selectedTheme,ViewerOptions.Value.EnlargeSmallImages,openExternally);
        MainWindow.Current.ApplyTheme(selectedTheme);
        RefreshThumbnailTooltips();
        SettingsInstantStatus.Text=statusMessage;
    }

    private void SettingsInstantCombo_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(!ready||settingsPopulating||disposed||!settingsHubOpen)return;
        try{SaveInstantViewerOptions("✓ 表示・操作設定を反映しました");}
        catch(Exception ex){SettingsInstantStatus.Text="保存できません: "+ex.Message;}
    }

    private async void SettingsInstantPreference_Changed(object sender,RoutedEventArgs e)
    {
        if(!ready||settingsPopulating||disposed||!settingsHubOpen)return;
        if(ReferenceEquals(sender,SettingsDoubleClickCheck))
        {
            try{SaveInstantViewerOptions("✓ 閲覧設定を反映しました");}
            catch(Exception ex){SettingsInstantStatus.Text="保存できません: "+ex.Message;}
            return;
        }
        if(ReferenceEquals(sender,SettingsVerifyAIRuntimeCheck))
        {
            var enabled=SettingsVerifyAIRuntimeCheck.IsChecked==true;
            if(savedVerificationState is bool prev&&prev==enabled)return;
            SettingsVerifyAIRuntimeCheck.IsEnabled=false;
            try
            {
                await api.PostAsync("api/library/ai/runtime-verification",new System.Text.Json.Nodes.JsonObject{["enabled"]=enabled});
                savedVerificationState=enabled;
                SettingsInstantStatus.Text=enabled?"✓ 起動時AIチェックを有効にしました（次回起動から）":"✓ 起動時AIチェックを簡略化しました（次回起動から）";
            }
            catch(Exception ex)
            {
                SettingsInstantStatus.Text="保存できません: "+ex.Message;
                settingsPopulating=true;
                try{SettingsVerifyAIRuntimeCheck.IsChecked=savedVerificationState??true;}
                finally{settingsPopulating=false;}
            }
            finally{if(!disposed&&SettingsVerifyAIRuntimeCheck is not null)SettingsVerifyAIRuntimeCheck.IsEnabled=true;}
        }
    }

    private void SettingsCategory_Click(object sender,RoutedEventArgs e)
    {
        if(sender is Button {Tag:string cat})SetSettingsCategory(cat);
    }

    private async void CloseSettings_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        var needLoad=resultSession is null||PendingSearch;
        try
        {
            CloseSettingsHubCore();
            RestoreNavigation();
            UpdateSearchMethod();
            UpdateLibraryHeading();
            if(!needLoad)
            {
                Count.Text=settingsReturnCount;
                RestoreSelection();
            }
        }
        finally{transitions.Release();}
        if(needLoad&&!disposed)await LoadAsync();
    }

    private async void SettingsGettingStarted_Click(object sender,RoutedEventArgs e)=>await OpenGettingStartedGuideAsync(fromSettings:true);
    private async void SettingsAIIndex_Click(object sender,RoutedEventArgs e)
    {
        await OpenAISettingsAsync();
        if(!disposed&&settingsHubOpen)await LoadSettingsStatusAsync();
    }
    private async void SettingsAIEnvironment_Click(object sender,RoutedEventArgs e)
    {
        await OpenAIAutoEnvironmentDialogAsync(fromSettings:true);
        if(!disposed&&settingsHubOpen)await LoadSettingsStatusAsync();
    }
    private async void SettingsAISetupPlan_Click(object sender,RoutedEventArgs e)
    {
        await OpenAISetupPlanAsync();
        if(!disposed&&settingsHubOpen)await LoadSettingsStatusAsync();
    }
    private async void SettingsOpenFolders_Click(object sender,RoutedEventArgs e)=>await OpenFolderHubAsync();
    private async void SettingsOpenShelves_Click(object sender,RoutedEventArgs e)=>await OpenShelfHubAsync();
    private void SettingsRelatedTerms_Click(object sender,RoutedEventArgs e)=>RelatedTerms_Click(sender,e);
    private async void SettingsClearHistory_Click(object sender,RoutedEventArgs e)=>await DeleteHistoryAsync();
    private async void SettingsBackup_Click(object sender,RoutedEventArgs e)=>await OpenBackupDialogAsync(fromSettings:true);
    private async void SettingsDiagnostics_Click(object sender,RoutedEventArgs e)=>await OpenDiagnosticsDialogAsync(fromSettings:true);
    private async void SettingsRuntimeCache_Click(object sender,RoutedEventArgs e)=>await OpenRuntimeCacheDialogAsync(fromSettings:true);
    private async Task OpenRecoveryGuideDialogAsync(bool fromBackup=false,bool fromSettings=false)
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;bool returnToBackup=false;
        try
        {
            var panel=new StackPanel{Spacing=12};
            panel.Children.Add(new TextBlock{Text="アプリが起動する場合",Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
            panel.Children.Add(new TextBlock
            {
                Text="同じ画面の「バックアップから復元」から復元できます。新しい保存先で検証され、元のライブラリと元ファイルは残ります。自動再起動は対応した配布版の Aredoko.exe から起動した場合に利用できます。\n\n"+
                     "バックアップにはライブラリ情報と、選択した設定・履歴・読書位置・AI検索データが含まれます。元の画像・動画、モデル、Python環境、サムネイルキャッシュは含みません。",
                TextWrapping=TextWrapping.Wrap
            });
            var offline=new Expander{Header="起動できない場合",HorizontalAlignment=HorizontalAlignment.Stretch,Content=new TextBlock
            {
                Text="アプリを終了してから、復旧ツールで新しい復元先を指定してください。既存のDBや元のメディアへ上書きしないでください。\n\n"+
                     "バックアップ例：\npython tools/backup_library.py backup --catalog <catalog.sqlite> --output <新バックアップ先>\n\n"+
                     "復元例：\npython tools/backup_library.py restore --bundle <バックアップ先> --output <新復元先>\n\n"+
                     "破損したAI検索データを除いて復元する場合は --without-ai を指定します。CLIを使用できる環境が必要です。",
                TextWrapping=TextWrapping.Wrap
            }};
            AutomationProperties.SetAutomationId(offline,"BackupRecoveryAdvanced");panel.Children.Add(offline);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="復元の手順",CloseButtonText="閉じる",Content=panel};
            if(fromBackup)
            {
                var backBtn=new Button{Content="バックアップと復元へ戻る",HorizontalAlignment=HorizontalAlignment.Left};
                AutomationProperties.SetAutomationId(backBtn,"BtnBackToBackup");
                backBtn.Click+=(_,_)=>{returnToBackup=true;dialog.Hide();};
                panel.Children.Add(backBtn);
            }
            AutomationProperties.SetAutomationId(dialog,"BackupGuideDialog");
            var closedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed += (_, _) => closedTcs.TrySetResult(true);
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task, Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(returnToBackup&&!disposed)await OpenBackupDialogAsync(fromSettings:fromSettings);
    }
    private async Task OpenDiagnosticsDialogAsync(bool fromSettings=false)
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;bool returnToSettings=false;
        try
        {
            System.Text.Json.Nodes.JsonNode? aiStatus = null;
            try { aiStatus = await api.GetAsync("api/library/ai/status"); } catch { }
            int termCount = -1;
            try { termCount = RelatedTerms.ParseList(await api.GetAsync("api/library/terms")).Count; } catch { }
            var shelfCount = knownShelves is not null ? knownShelves.Count : -1;
            var build=AppBuildIdentity.FromAssembly(typeof(App).Assembly,AppContext.BaseDirectory);
            var report=DiagnosticsReport.Generate(aiStatus,aiScope,knownRoots,shelfCount,termCount,ActualTheme.ToString(),
                appVersion:build.Version,basicRuntime:api.BasicRuntime)
                +"\n"+build.ToDiagnosticText();

            var panel=new StackPanel{Spacing=12};
            var txt = new TextBox
            {
                IsReadOnly = true,
                AcceptsReturn = true,
                Text = report,
                TextWrapping = TextWrapping.Wrap,
                Height = 280,
                FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas, Cascadia Code, monospace")
            };
            AutomationProperties.SetAutomationId(txt, "TxtDiagnostics");
            panel.Children.Add(txt);

            var copyStatus = new TextBlock { TextWrapping = TextWrapping.Wrap, Style = (Style)Resources["MediaMetadataStyle"] };
            AutomationProperties.SetAutomationId(copyStatus, "TxtDiagnosticsStatus");
            var copyBtn = new Button { Content = "診断情報をコピー", HorizontalAlignment = HorizontalAlignment.Left };
            AutomationProperties.SetAutomationId(copyBtn, "BtnCopyDiagnostics");
            copyBtn.Click += (_, _) =>
            {
                var package = new Windows.ApplicationModel.DataTransfer.DataPackage();
                package.SetText(report);
                Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(package);
                copyStatus.Text = "診断情報をクリップボードにコピーしました。外部への自動送信は行われません。";
            };
            var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
            actions.Children.Add(copyBtn);
            actions.Children.Add(new TextBlock{Text="共有前に内容を確認",VerticalAlignment=VerticalAlignment.Center,Style=(Style)Resources["MediaMetadataStyle"]});
            panel.Children.Add(actions);
            panel.Children.Add(copyStatus);

            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="診断情報",CloseButtonText="閉じる",Content=panel};
            if(fromSettings)
            {
                var backBtn=new Button{Content="設定へ戻る"};
                AutomationProperties.SetAutomationId(backBtn,"BtnBackToSettings");
                backBtn.Click+=(_,_)=>{returnToSettings=true;dialog.Hide();};
                actions.Children.Add(backBtn);
            }
            AutomationProperties.SetAutomationId(dialog,"DiagnosticsDialog");
            var closedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed += (_, _) => closedTcs.TrySetResult(true);
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task, Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(returnToSettings&&!disposed)await OpenSettingsAsync();
    }
}
