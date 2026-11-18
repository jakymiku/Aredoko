using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async void Navigation_ItemInvoked(NavigationView sender,NavigationViewItemInvokedEventArgs args)
    {
        if(args.InvokedItemContainer is NavigationViewItem {Tag:"settings"})await OpenSettingsAsync();
        else if(!shelfHubOpen&&selectedShelfIds is not null&&args.InvokedItemContainer is NavigationViewItem {Tag:"shelf"})await OpenShelfHubAsync();
    }
    private async Task OpenSettingsAsync()
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;string? destination=null;
        try
        {
            var panel=new StackPanel{Spacing=12};
            panel.Children.Add(new TextBlock{Text="表示と閲覧",Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
            var theme=new ComboBox{Header="表示テーマ",HorizontalAlignment=HorizontalAlignment.Stretch};
            theme.Items.Add("Windowsの設定に合わせる");theme.Items.Add("ライト");theme.Items.Add("ダーク");
            theme.SelectedIndex=ViewerOptions.Value.Theme switch{"light"=>1,"dark"=>2,_=>0};
            AutomationProperties.SetAutomationId(theme,"SettingsTheme");
            panel.Children.Add(theme);
            var viewer=new ComboBox{Header="作品を開くアプリ",HorizontalAlignment=HorizontalAlignment.Stretch};
            viewer.Items.Add("Aredoko");viewer.Items.Add("Windowsの既定アプリ");
            viewer.SelectedIndex=ViewerOptions.Value.OpenExternally?1:0;
            AutomationProperties.SetAutomationId(viewer,"SettingsDoubleClickViewer");
            panel.Children.Add(viewer);
            var externalHint=new TextBlock{Text="Aredokoの一覧順で続けて見るには、詳細から開いてください。",TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"],Visibility=viewer.SelectedIndex==1?Visibility.Visible:Visibility.Collapsed};
            panel.Children.Add(externalHint);
            var wheel=new ComboBox{Header="次の画像・ページに進む方向",HorizontalAlignment=HorizontalAlignment.Stretch};
            wheel.Items.Add("ホイールを下に回す");wheel.Items.Add("ホイールを上に回す");wheel.SelectedIndex=ViewerOptions.Value.WheelUpAdvances?1:0;
            AutomationProperties.SetAutomationId(wheel,"SettingsWheel");
            panel.Children.Add(wheel);
            var verification=new CheckBox{Content="起動時にAI環境の全ファイルを確認（次回起動から適用）",IsEnabled=false};
            AutomationProperties.SetAutomationId(verification,"SettingsVerifyAIRuntime");
            const string verificationHelpDefault="既定はオンです。オフにすると破損や変更を検出しにくくなります。";
            const string verificationHelpOff="オフにすると破損や変更を検出しにくくなります（次回起動から適用）。基本確認と新規取得ファイルの検証は続きます。";
            var verificationHint=new TextBlock{Text="確認設定を読み込んでいます…",TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            var advancedContent=new StackPanel{Spacing=8};advancedContent.Children.Add(verification);advancedContent.Children.Add(verificationHint);
            var advanced=new Expander{Header="高度な設定",Content=advancedContent,HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(advanced,"SettingsAdvanced");
            bool? savedVerification=null;
            using var verificationLifetime=new CancellationTokenSource();
            Task? verificationLoad=null;
            var initialTheme=theme.SelectedIndex;
            var initialViewer=viewer.SelectedIndex;
            var initialWheel=wheel.SelectedIndex;
            var initialVerification=true;
            bool IsDirty()=>theme.SelectedIndex!=initialTheme||viewer.SelectedIndex!=initialViewer||wheel.SelectedIndex!=initialWheel
                ||(savedVerification is not null&&(verification.IsChecked==true)!=initialVerification);
            var savedText=new TextBlock{TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            AutomationProperties.SetAutomationId(savedText,"SettingsStatus");
            AutomationProperties.SetLiveSetting(savedText,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
            var unsavedPrompt=new TextBlock{Text="変更が保存されていません。保存してから続けますか？",TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(unsavedPrompt,"SettingsUnsavedPrompt");
            var saveAndContinueBtn=new Button{Content="保存して続ける",Style=(Style)Application.Current.Resources["AccentButtonStyle"]};
            var discardAndContinueBtn=new Button{Content="保存せず続ける"};
            var cancelNavBtn=new Button{Content="戻る"};
            AutomationProperties.SetAutomationId(saveAndContinueBtn,"SettingsSaveAndContinue");
            AutomationProperties.SetAutomationId(discardAndContinueBtn,"SettingsDiscardAndContinue");
            AutomationProperties.SetAutomationId(cancelNavBtn,"SettingsCancelNavigation");
            var unsavedActions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8,Children={saveAndContinueBtn,discardAndContinueBtn,cancelNavBtn}};
            var unsavedBar=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Padding=new Thickness(10),Visibility=Visibility.Collapsed,Child=new StackPanel{Spacing=8,Children={unsavedPrompt,unsavedActions}}};
            AutomationProperties.SetAutomationId(unsavedBar,"SettingsUnsavedBar");
            var scroll=new ScrollViewer{Content=panel,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,Padding=new Thickness(0,0,16,0)};
            AutomationProperties.SetAutomationId(scroll,"SettingsScroll");
            var footerStack=new StackPanel{Spacing=8};
            footerStack.Children.Add(unsavedBar);
            footerStack.Children.Add(savedText);
            var content=new Grid{MaxHeight=Math.Max(160,ActualHeight-240),RowSpacing=8};
            content.RowDefinitions.Add(new RowDefinition{Height=new GridLength(1,GridUnitType.Star)});
            content.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
            content.Children.Add(scroll);Grid.SetRow(footerStack,1);content.Children.Add(footerStack);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="設定",PrimaryButtonText="変更を保存",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,Content=content};
            AutomationProperties.SetAutomationId(dialog,"SettingsDialog");
            // Preserve the existing UI Automation identifier on the native footer button.
            var saveStyle=new Style{TargetType=typeof(Button),BasedOn=(Style)Application.Current.Resources["AccentButtonStyle"]};
            saveStyle.Setters.Add(new Setter(AutomationProperties.AutomationIdProperty,"SettingsSave"));
            dialog.PrimaryButtonStyle=saveStyle;
            string? pendingDestination=null;
            bool pendingClose=false, allowCloseWithoutSave=false, populatingSettings=false;
            void UpdateDirtyUI()
            {
                if(populatingSettings)return;
                var dirty=IsDirty();
                savedText.Text=dirty?"未保存の変更":"";
                if(!dirty){unsavedBar.Visibility=Visibility.Collapsed;pendingDestination=null;pendingClose=false;}
            }
            async Task LoadVerificationAsync()
            {
                try
                {
                    var setup=await api.GetAsync("api/library/ai/setup",verificationLifetime.Token);
                    if(verificationLifetime.IsCancellationRequested||disposed)return;
                    savedVerification=setup["verify_ai_runtime"]?.GetValue<bool>()??true;
                    initialVerification=savedVerification.Value;
                    populatingSettings=true;
                    try{verification.IsChecked=savedVerification;}finally{populatingSettings=false;}
                    verification.IsEnabled=true;
                    verificationHint.Text=savedVerification.Value?verificationHelpDefault:verificationHelpOff;
                }
                catch(OperationCanceledException) when(verificationLifetime.IsCancellationRequested){}
                catch(Exception ex)
                {
                    AppLog.Error(ex);
                    if(!verificationLifetime.IsCancellationRequested&&!disposed)
                        verificationHint.Text="バックエンドに接続できないため、現在は変更できません。";
                }
            }
            async Task<bool> SaveSettingsCoreAsync()
            {
                try
                {
                    var enabled=verification.IsChecked==true;
                    var verificationChanged=savedVerification is bool previous&&enabled!=previous;
                    if(verificationChanged)
                    {
                        await api.PostAsync("api/library/ai/runtime-verification",new System.Text.Json.Nodes.JsonObject{["enabled"]=enabled});
                        savedVerification=enabled;
                        initialVerification=enabled;
                    }
                    var selectedTheme=theme.SelectedIndex switch{1=>"light",2=>"dark",_=>"system"};
                    var openExternally=viewer.SelectedIndex==1;
                    ViewerOptions.SavePreferences(wheel.SelectedIndex==1,selectedTheme,ViewerOptions.Value.EnlargeSmallImages,openExternally);
                    initialTheme=theme.SelectedIndex;
                    initialViewer=viewer.SelectedIndex;
                    initialWheel=wheel.SelectedIndex;
                    MainWindow.Current.ApplyTheme(selectedTheme);
                    dialog.RequestedTheme=selectedTheme switch{"light"=>ElementTheme.Light,"dark"=>ElementTheme.Dark,_=>ElementTheme.Default};
                    RefreshThumbnailTooltips();
                    unsavedBar.Visibility=Visibility.Collapsed;
                    savedText.Text=verificationChanged?"変更を保存しました（AI環境の確認設定は次回起動から適用）":"変更を保存しました";
                    return true;
                }
                catch(Exception ex){savedText.Text="保存できません: "+ex.Message;return false;}
            }
            theme.SelectionChanged+=(_,_)=>UpdateDirtyUI();
            viewer.SelectionChanged+=(_,_)=>{externalHint.Visibility=viewer.SelectedIndex==1?Visibility.Visible:Visibility.Collapsed;UpdateDirtyUI();};
            wheel.SelectionChanged+=(_,_)=>UpdateDirtyUI();
            verification.Checked+=(_,_)=>{verificationHint.Text=verificationHelpDefault;UpdateDirtyUI();};
            verification.Unchecked+=(_,_)=>{verificationHint.Text=verificationHelpOff;UpdateDirtyUI();};
            saveAndContinueBtn.Click+=async(_, _)=>
            {
                saveAndContinueBtn.IsEnabled=discardAndContinueBtn.IsEnabled=cancelNavBtn.IsEnabled=false;
                try
                {
                    if(!await SaveSettingsCoreAsync())return;
                    if(pendingDestination is {} next){destination=next;pendingDestination=null;allowCloseWithoutSave=true;dialog.Hide();}
                    else if(pendingClose){pendingClose=false;allowCloseWithoutSave=true;dialog.Hide();}
                }
                finally{saveAndContinueBtn.IsEnabled=discardAndContinueBtn.IsEnabled=cancelNavBtn.IsEnabled=true;}
            };
            discardAndContinueBtn.Click+=(_,_)=>
            {
                allowCloseWithoutSave=true;
                if(pendingDestination is {} next){destination=next;pendingDestination=null;}
                pendingClose=false;
                dialog.Hide();
            };
            cancelNavBtn.Click+=(_,_)=>{pendingDestination=null;pendingClose=false;unsavedBar.Visibility=Visibility.Collapsed;};
            dialog.PrimaryButtonClick+=async (_,args)=>
            {
                args.Cancel=true;var deferral=args.GetDeferral();
                await Task.Yield();dialog.IsPrimaryButtonEnabled=false;
                try{await SaveSettingsCoreAsync();}
                finally{dialog.IsPrimaryButtonEnabled=true;deferral.Complete();}
            };
            var closedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Opened += (_, _) => verificationLoad=LoadVerificationAsync();
            dialog.Closing += (_, args) =>
            {
                if(!allowCloseWithoutSave&&IsDirty()&&destination is null)
                {
                    args.Cancel=true;
                    pendingDestination=null;
                    pendingClose=true;
                    unsavedPrompt.Text="変更が保存されていません。保存してから閉じますか？";
                    saveAndContinueBtn.Content="保存して閉じる";
                    discardAndContinueBtn.Content="保存せず閉じる";
                    unsavedBar.Visibility=Visibility.Visible;
                }
            };
            dialog.Closed += (_, _) => {if(!verificationLifetime.IsCancellationRequested)verificationLifetime.Cancel();closedTcs.TrySetResult(true);};
            void NavigateTool(string target)
            {
                if(IsDirty())
                {
                    pendingClose=false;
                    pendingDestination=target;
                    unsavedPrompt.Text="変更が保存されていません。保存してから続けますか？";
                    saveAndContinueBtn.Content="保存して続ける";
                    discardAndContinueBtn.Content="保存せず続ける";
                    unsavedBar.Visibility=Visibility.Visible;
                }
                else
                {
                    destination=target;
                    allowCloseWithoutSave=true;
                    dialog.Hide();
                }
            }
            var toolsStack=new StackPanel{Spacing=10};
            foreach(var (groupTitle,entries) in new (string,(string Label,string Id,string Target)[])[]{
                ("ライブラリ",[
                    ("登録フォルダ","BtnSettingsOpenFolders","folders"),
                    ("棚一覧","BtnSettingsOpenShelves","shelves"),
                    ("関連語の辞書","BtnRelatedTerms","terms")]),
                ("AI検索",[
                    ("AI検索を設定","BtnAIIndex","ai"),
                    ("自動セットアップ（AI環境）","BtnAIEnvironment","ai-environment")]),
                ("バックアップと管理",[
                    ("バックアップと復元","BtnBackupGuide","backup"),
                    ("診断情報","BtnDiagnostics","diagnostics"),
                    ("AIのダウンロードキャッシュ","BtnRuntimeCache","runtime-cache"),
                    ("すべての閲覧履歴を削除…","BtnClearHistory","history")])})
            {
                toolsStack.Children.Add(new TextBlock{Text=groupTitle,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"],Margin=new Thickness(0,4,0,0)});
                var groupGrid=new Grid{ColumnSpacing=8,RowSpacing=8};
                groupGrid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
                groupGrid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
                for(var r=0;r<(entries.Length+1)/2;r++)groupGrid.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
                for(var i=0;i<entries.Length;i++)
                {
                    var (label,id,target)=entries[i];
                    var button=new Button{Content=label,HorizontalAlignment=HorizontalAlignment.Stretch};
                    AutomationProperties.SetAutomationId(button,id);
                    button.Click+=(_,_)=>NavigateTool(target);
                    Grid.SetRow(button,i/2);Grid.SetColumn(button,i%2);
                    groupGrid.Children.Add(button);
                }
                toolsStack.Children.Add(groupGrid);
            }
            var helpBtn=new Button{Content="使い方を見る",HorizontalAlignment=HorizontalAlignment.Left};
            AutomationProperties.SetAutomationId(helpBtn,"BtnGettingStarted");
            helpBtn.Click+=(_,_)=>NavigateTool("help");
            toolsStack.Children.Add(helpBtn);
            var tools=new ContentControl{Content=toolsStack,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch,IsTabStop=false};
            AutomationProperties.SetAutomationId(tools,"SettingsTools");
            panel.Children.Add(tools);panel.Children.Add(advanced);
            try
            {
                await dialog.ShowAsync();
                await Task.WhenAny(closedTcs.Task, Task.Delay(500));
            }
            finally
            {
                verificationLifetime.Cancel();
                if(verificationLoad is not null)await verificationLoad;
            }
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(destination is not null)
        {
            if(destination=="ai")AI_Click(this,new RoutedEventArgs());
            else if(destination=="help")await OpenGettingStartedGuideAsync(fromSettings:true);
            else if(destination=="terms")RelatedTerms_Click(this,new RoutedEventArgs());
            else if(destination=="history")await DeleteHistoryAsync();
            else if(destination=="backup")await OpenBackupDialogAsync(fromSettings:true);
            else if(destination=="diagnostics")await OpenDiagnosticsDialogAsync(fromSettings:true);
            else if(destination=="ai-environment")await OpenAIAutoEnvironmentDialogAsync(fromSettings:true);
            else if(destination=="runtime-cache")await OpenRuntimeCacheDialogAsync(fromSettings:true);
            else if(destination=="folders")await OpenFolderHubAsync();
            else if(destination=="shelves")await OpenShelfHubAsync();
        }
    }
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
                     "バックアップにはライブラリ情報と、選択した設定・履歴・読書位置・AI検索用データが含まれます。元の画像・動画、モデル、Python環境、サムネイルキャッシュは含みません。",
                TextWrapping=TextWrapping.Wrap
            });
            var offline=new Expander{Header="起動できない場合",HorizontalAlignment=HorizontalAlignment.Stretch,Content=new TextBlock
            {
                Text="アプリを終了してから、復旧ツールで新しい復元先を指定してください。既存のDBや元のメディアへ上書きしないでください。\n\n"+
                     "バックアップ例：\npython tools/backup_library.py backup --catalog <catalog.sqlite> --output <新バックアップ先>\n\n"+
                     "復元例：\npython tools/backup_library.py restore --bundle <バックアップ先> --output <新復元先>\n\n"+
                     "破損したAI検索用データを除いて復元する場合は --without-ai を指定します。CLIを使用できる環境が必要です。",
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
