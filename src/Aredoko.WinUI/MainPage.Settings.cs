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
        if(ready&&settingsHubOpen)RememberCurrentLocation();
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
            active=null;initialSavedItemId=null;
            Details.IsPaneOpen=false;
            DetailsButton.IsEnabled=false;
            MainViewTitle.Text=AppText.L("設定","Settings");
            Count.Text="";
            ItemSearchRow.Visibility=SearchTools.Visibility=ItemListContainer.Visibility=ItemPagerRow.Visibility=Visibility.Collapsed;
            SettingsHubView.Visibility=Visibility.Visible;
            settingsPopulating=true;
            try
            {
                if(SettingsLanguageCombo is not null)SettingsLanguageCombo.SelectedIndex=ViewerOptions.Value.Language switch{"ja"=>1,"en"=>2,_=>0};
                SettingsThemeCombo.SelectedIndex=ViewerOptions.Value.Theme switch{"light"=>1,"dark"=>2,_=>0};
                SettingsDoubleClickCheck.IsChecked=ViewerOptions.Value.OpenExternally;
                SettingsClickOpenDetailsCheck.IsChecked=ViewerOptions.Value.OpenDetailsOnClick;
                SettingsWheelCombo.SelectedIndex=ViewerOptions.Value.WheelUpAdvances?1:0;
                SettingsInstantStatus.Text=AppText.L("変更した設定はすぐに反映されます","Changes apply immediately");
            }
            finally{settingsPopulating=false;}
            SetSettingsCategory(category??"all");
            RecordNavigationLocation();
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
            var taggerReady=setup["tagger"]?["available"]?.GetValue<bool>()==true;
            if(SettingsAIStep4Status is not null)SettingsAIStep4Status.Text=taggerReady?AppText.L("✓ 使用可能 (WD Tagger)","✓ Ready (WD Tagger)"):AppText.L("モデル未導入","Model not installed");
            if(SettingsAIDownloadTaggerButton is not null)SettingsAIDownloadTaggerButton.Content=taggerReady?AppText.L("🏷 タグ付けモデルの再取得・設定","🏷 Re-download / configure tagger"):AppText.L("🏷 タグ付けモデルを取得","🏷 Download tagger model");
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
            var defaultButton=ThemeStyle("DefaultButtonStyle");
            var subtle=ThemeStyle("UnselectedSegmentButtonStyle");
            if(SettingsAIIndexButton is not null)
            {
                SettingsAIIndexButton.Style=available?accent:defaultButton;
                SettingsAIIndexButton.Content=AppText.L("AI検索を設定","Configure AI Search");
            }
            if(SettingsAIEnvironmentButton is not null)SettingsAIEnvironmentButton.Style=available?defaultButton:accent;
            if(SettingsAISetupPlanButton is not null)SettingsAISetupPlanButton.Style=defaultButton;
            if(SettingsAISetupRowLabel is not null)SettingsAISetupRowLabel.Text=available?AppText.L("環境の再構成・用途選び：","Reconfigure or switch profile:"):AppText.L("初回セットアップ：","Initial setup:");
            var state=statusData["state"]?.GetValue<string>()??"idle";
            var processed=statusData["processed"]?.GetValue<int>()??0;
            var total=statusData["total"]?.GetValue<int>()??0;
            var model=statusData["model"]?.GetValue<string>()??"";
            var statusCode=statusData["status_code"]?.GetValue<string>()??"";
            var errorText=statusData["error"]?.GetValue<string>()??"";
            if(available)
            {
                SettingsAIStep1Status.Text=AppText.L("✓ 導入済み","✓ Installed");
                SettingsAIStep2Status.Text=string.IsNullOrWhiteSpace(model)?AppText.L("✓ 使用可能","✓ Ready"):$"✓ {model}";
                int? covTarget=null,covFresh=null;
                var unscopedPresentTotal=0;
                var scopeInvalid=false;
                var scopeInvalidHint="";
                if(state is not ("running" or "cancelling"))
                {
                    System.Text.Json.Nodes.JsonObject? effectiveScope=null;
                    try
                    {
                        var scopeData=await api.GetAsync("api/library/ai/scope",token);
                        if(scopeData["valid"]?.GetValue<bool>()==true&&scopeData["scope"] is System.Text.Json.Nodes.JsonObject validScope)
                        {
                            effectiveScope=(System.Text.Json.Nodes.JsonObject)validScope.DeepClone();
                            aiScope=(System.Text.Json.Nodes.JsonObject)effectiveScope.DeepClone();
                        }
                        else
                        {
                            scopeInvalid=true;
                            scopeInvalidHint=AppText.TranslateBackend(scopeData["error"]?.GetValue<string>()??aiScopeError);
                        }
                    }
                    catch(OperationCanceledException) when(token.IsCancellationRequested){throw;}
                    catch(Exception scopeEx)
                    {
                        AppLog.Error(scopeEx);
                        effectiveScope=aiScope is not null?(System.Text.Json.Nodes.JsonObject)aiScope.DeepClone():null;
                    }
                    if(token.IsCancellationRequested||disposed||!settingsHubOpen)return;
                    if(!scopeInvalid&&effectiveScope is not null)
                    {
                        if(effectiveScope["root_ids"] is System.Text.Json.Nodes.JsonArray scopedRoots)
                        {
                            var scopedIds=scopedRoots.Select(node=>node?.GetValue<int>()??-1).Where(id=>id>0).ToHashSet();
                            unscopedPresentTotal=knownRoots.Where(root=>root.Enabled&&!scopedIds.Contains(root.Id)).Sum(root=>root.PresentCount);
                        }
                        try
                        {
                            var covData=await api.PostAsync("api/library/ai/coverage",AIScopeRequests.Scoped(effectiveScope),token);
                            covTarget=covData["target_total"]?.GetValue<int>();
                            covFresh=covData["fresh_total"]?.GetValue<int>();
                        }
                        catch(OperationCanceledException) when(token.IsCancellationRequested){throw;}
                        catch(Exception covEx){AppLog.Error(covEx);}
                        if(token.IsCancellationRequested||disposed||!settingsHubOpen)return;
                    }
                }
                if(scopeInvalid)
                {
                    SettingsAIStep3Status.Text=AppText.L("対象範囲の要確認","Scope needs attention");
                    SettingsAINextHint.Text=string.IsNullOrWhiteSpace(scopeInvalidHint)?AppText.L("［AI検索を設定］の「対象範囲」を選び直して保存してください。","Open \"Configure AI Search\" and re-save your \"Search Scope\"."):scopeInvalidHint;
                }
                else
                {
                    var (step3Text,nextHint)=AISearchStatus.SettingsDataStatus(state,processed,total,covTarget,covFresh,unscopedPresentTotal);
                    SettingsAIStep3Status.Text=step3Text;
                    SettingsAINextHint.Text=nextHint;
                    if(SettingsAIIndexButton is not null)
                    {
                        if(covTarget is int target&&covFresh is int fresh&&target>fresh)
                            SettingsAIIndexButton.Content=fresh==0?AppText.L($"✨ AI検索データを作成 ({target:N0}件)",$"✨ Build AI index ({target:N0})"):AppText.L($"✨ 未作成のAIデータを作成 ({target-fresh:N0}件)",$"✨ Build remaining AI index ({target-fresh:N0})");
                        else if(state is not ("running" or "cancelling")&&covTarget is int t&&covFresh==t&&t>0)
                            SettingsAIIndexButton.Content=AppText.L("AI検索の設定・モデル切替","AI Search Settings & Model Switch");
                    }
                }
                if(SettingsAIStatusArt is not null)
                    VisualAssets.State(SettingsAIStatusArt,state is "running" or "cancelling"?"indexing":state=="failed"?"error":(!scopeInvalid&&covTarget is int ct&&covFresh==ct&&ct>0)?"completed":"greeting");
            }
            else
            {
                var needsRuntime=statusCode.Contains("runtime")||errorText.Contains("Python")||errorText.Contains("ライブラリ")||errorText.Contains("library",StringComparison.OrdinalIgnoreCase);
                if(needsRuntime)
                {
                    SettingsAIStep1Status.Text=AppText.L("未導入","Not installed");
                    SettingsAIStep2Status.Text=AppText.L("環境導入後に設定","Set up after runtime");
                    SettingsAIStep3Status.Text=AppText.L("待機中","Waiting");
                    SettingsAINextHint.Text=AppText.L("［AIの自動セットアップ］または［AI検索を設定］から実行環境を用意してください。","Run \"AI Auto-Setup\" or \"Configure AI Search\" to install the runtime.");
                }
                else
                {
                    SettingsAIStep1Status.Text=AppText.L("✓ 導入済み","✓ Installed");
                    SettingsAIStep2Status.Text=AppText.L("未導入 / 要確認","Missing / needs setup");
                    SettingsAIStep3Status.Text=AppText.L("待機中","Waiting");
                    SettingsAINextHint.Text=AppText.L("［AI検索を設定］から検索モデルをダウンロードまたは指定してください。","Open \"Configure AI Search\" to download or select a search model.");
                }
                if(SettingsAIStatusArt is not null)
                    VisualAssets.State(SettingsAIStatusArt,state=="failed"?"error":"greeting");
            }
        }
        catch(OperationCanceledException) when(token.IsCancellationRequested){}
        catch(Exception ex)
        {
            AppLog.Error(ex);
            if(!token.IsCancellationRequested&&!disposed&&settingsHubOpen)
            {
                SettingsAIStep1Status.Text=AppText.L("確認できません","Unavailable");
                SettingsAIStep2Status.Text="—";
                SettingsAIStep3Status.Text="—";
                if(SettingsAIStep4Status is not null)SettingsAIStep4Status.Text="—";
                SettingsAINextHint.Text=AppText.L("バックエンドに接続できないため状態を取得できませんでした。","Could not retrieve status because the backend is unreachable.");
                if(SettingsAIStatusArt is not null)VisualAssets.State(SettingsAIStatusArt,"error");
            }
        }
    }

    private void SaveInstantViewerOptions(Func<string> statusMessageFactory)
    {
        var selectedLanguage=SettingsLanguageCombo?.SelectedIndex switch{1=>"ja",2=>"en",_=>"system"};
        var selectedTheme=SettingsThemeCombo.SelectedIndex switch{1=>"light",2=>"dark",_=>"system"};
        var openExternally=SettingsDoubleClickCheck.IsChecked==true;
        var openDetailsOnClick=SettingsClickOpenDetailsCheck?.IsChecked==true;
        var wheelUp=SettingsWheelCombo.SelectedIndex==1;
        var prevResolved=AppText.CurrentLanguage;
        ViewerOptions.SavePreferences(wheelUp,selectedTheme,ViewerOptions.Value.EnlargeSmallImages,openExternally,openDetailsOnClick,selectedLanguage);
        var nextResolved=AppText.Apply(selectedLanguage);
        MainWindow.Current.ApplyTheme(selectedTheme);
        if(prevResolved!=nextResolved)
        {
            MainWindow.Current.ApplyLanguage();
            ApplyLanguage();
            if(settingsHubOpen)_ = LoadSettingsStatusAsync();
        }
        RefreshThumbnailTooltips();
        SettingsInstantStatus.Text=statusMessageFactory();
    }

    private void ApplyLanguage()
    {
        UiText.Apply(this);
        for(var index=0;index<SearchMode.Items.Count;index++)
            if(SearchMode.Items[index] is ComboBoxItem option)
            {
                var hint=SearchModeDescription(index);
                ToolTipService.SetToolTip(option,hint);
                AutomationProperties.SetHelpText(option,hint);
            }
        if(tagReview is not null)UiText.Apply(tagReview);
        UpdateSearchMethod();
        UpdateLibraryHeading();
        UpdateSelectionSummaryDetails();
        if(settingsHubOpen)MainViewTitle.Text=AppText.L("設定","Settings");
        if(folderHubOpen)
        {
            RenderFolderHub();
            UpdateFolderDraftState();
        }
        if(shelfHubOpen&&!disposed)_ = ReloadShelfHubAsync();
        else if(resultSession is not null)RenderRows();
    }

    private void SettingsInstantCombo_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(!ready||settingsPopulating||disposed||!settingsHubOpen)return;
        try{SaveInstantViewerOptions(()=>ReferenceEquals(sender,SettingsLanguageCombo)?AppText.L("✓ 表示言語を反映しました","✓ Display language updated"):AppText.L("✓ 表示・操作設定を反映しました","✓ Display and control settings updated"));}
        catch(Exception ex){SettingsInstantStatus.Text=AppText.L("保存できません: ","Failed to save: ")+ex.Message;}
    }

    private async void SettingsInstantPreference_Changed(object sender,RoutedEventArgs e)
    {
        if(!ready||settingsPopulating||disposed||!settingsHubOpen)return;
        if(ReferenceEquals(sender,SettingsDoubleClickCheck)||ReferenceEquals(sender,SettingsClickOpenDetailsCheck))
        {
            try{SaveInstantViewerOptions(()=>ReferenceEquals(sender,SettingsClickOpenDetailsCheck)?AppText.L("✓ 作品クリック時の詳細表示を反映しました","✓ Open details on click updated"):AppText.L("✓ 閲覧設定を反映しました","✓ Viewing settings updated"));}
            catch(Exception ex){SettingsInstantStatus.Text=AppText.L("保存できません: ","Failed to save: ")+ex.Message;}
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
                SettingsInstantStatus.Text=enabled?AppText.L("✓ 起動時AIチェックを有効にしました（次回起動から）","✓ Startup AI check enabled (next launch)"):AppText.L("✓ 起動時AIチェックを簡略化しました（次回起動から）","✓ Startup AI check streamlined (next launch)");
            }
            catch(Exception ex)
            {
                SettingsInstantStatus.Text=AppText.L("保存できません: ","Failed to save: ")+ex.Message;
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
        var needLoad=resultSession is null||PendingAutoSearch;
        try
        {
            RememberCurrentLocation();
            CloseSettingsHubCore();
            RestoreNavigation();
            UpdateSearchMethod();
            UpdateLibraryHeading();
            if(!needLoad)
            {
                Count.Text=settingsReturnCount;
                RestoreSelection();
                RecordNavigationLocation();
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
    private async void SettingsAIMediaPrep_Click(object sender,RoutedEventArgs e)
    {
        await OpenAISettingsAsync(initialSection:"media");
        if(!disposed&&settingsHubOpen)await LoadSettingsStatusAsync();
    }
    private async void SettingsAIDownloadTagger_Click(object sender,RoutedEventArgs e)
    {
        await OpenAIDownloadDialogAsync(preferRole:"tagger");
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
            panel.Children.Add(new TextBlock{Text=AppText.L("アプリが起動する場合","If the app launches"),Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
            panel.Children.Add(new TextBlock
            {
                Text=AppText.L(
                    "同じ画面の「バックアップから復元」から復元できます。新しい保存先で検証され、元のライブラリと元ファイルは残ります。自動再起動は対応した配布版の Aredoko.exe から起動した場合に利用できます。\n\n"+
                    "バックアップにはライブラリ情報と、選択した設定・履歴・読書位置・AI検索データが含まれます。元の画像・動画、モデル、Python環境、サムネイルキャッシュは含みません。",
                    "You can restore from \"Restore from backup\" on the same screen. The backup is verified in a new destination while keeping your original library and files intact. Automatic restart is supported when launched via Aredoko.exe.\n\n"+
                    "Backups contain library metadata and selected settings, history, reading positions, and AI search data. Original images/videos, models, Python environment, and thumbnail caches are not included."),
                TextWrapping=TextWrapping.Wrap
            });
            var offline=new Expander{Header=AppText.L("起動できない場合","If the app cannot launch"),HorizontalAlignment=HorizontalAlignment.Stretch,Content=new TextBlock
            {
                Text=AppText.L(
                    "アプリを終了してから、復旧ツールで新しい復元先を指定してください。既存のDBや元のメディアへ上書きしないでください。\n\n"+
                    "バックアップ例：\npython tools/backup_library.py backup --catalog <catalog.sqlite> --output <新バックアップ先>\n\n"+
                    "復元例：\npython tools/backup_library.py restore --bundle <バックアップ先> --output <新復元先>\n\n"+
                    "破損したAI検索データを除いて復元する場合は --without-ai を指定します。CLIを使用できる環境が必要です。",
                    "Close the app, then specify a new restore destination using the recovery tool. Do not overwrite an existing DB or original media.\n\n"+
                    "Backup example:\npython tools/backup_library.py backup --catalog <catalog.sqlite> --output <new_backup_dir>\n\n"+
                    "Restore example:\npython tools/backup_library.py restore --bundle <backup_dir> --output <new_restore_dir>\n\n"+
                    "Pass --without-ai to restore without damaged AI search data. Requires a Python CLI environment."),
                TextWrapping=TextWrapping.Wrap
            }};
            AutomationProperties.SetAutomationId(offline,"BackupRecoveryAdvanced");panel.Children.Add(offline);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("復元の手順","Recovery instructions"),CloseButtonText=AppText.L("閉じる","Close"),Content=panel};
            if(fromBackup)
            {
                var backBtn=new Button{Content=AppText.L("バックアップと復元へ戻る","Back to Backup & Restore"),HorizontalAlignment=HorizontalAlignment.Left};
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

            var copyStatus = new TextBlock { TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed, Style = (Style)Resources["MediaMetadataStyle"] };
            AutomationProperties.SetAutomationId(copyStatus, "TxtDiagnosticsStatus");
            var copyBtn = new Button { Content = AppText.L("診断情報をコピー","Copy diagnostics"), HorizontalAlignment = HorizontalAlignment.Left, Style = (Style)Application.Current.Resources["AccentButtonStyle"] };
            AutomationProperties.SetAutomationId(copyBtn, "BtnCopyDiagnostics");
            copyBtn.Click += (_, _) =>
            {
                var package = new Windows.ApplicationModel.DataTransfer.DataPackage();
                package.SetText(report);
                Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(package);
                copyStatus.Text = AppText.L("✓ 診断情報をクリップボードにコピーしました。外部への自動送信は行われません。","✓ Diagnostics copied to clipboard. Nothing is sent automatically.");
                copyStatus.Visibility = Visibility.Visible;
            };
            var actions=new Grid{ColumnSpacing=8};
            actions.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            actions.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            var copyRow=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
            copyRow.Children.Add(copyBtn);
            copyRow.Children.Add(new TextBlock{Text=AppText.L("共有前に内容を確認","Review contents before sharing"),VerticalAlignment=VerticalAlignment.Center,TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]});
            actions.Children.Add(copyRow);
            panel.Children.Add(actions);
            panel.Children.Add(copyStatus);

            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("診断情報","Diagnostics"),CloseButtonText=AppText.L("閉じる","Close"),Content=panel};
            if(fromSettings)
            {
                var backBtn=new Button{Content=AppText.L("設定へ戻る","Back to Settings")};
                AutomationProperties.SetAutomationId(backBtn,"BtnBackToSettings");
                backBtn.Click+=(_,_)=>{returnToSettings=true;dialog.Hide();};
                Grid.SetColumn(backBtn,1);
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
