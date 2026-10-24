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
    }
    private async Task OpenSettingsAsync()
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;string? destination=null;
        try
        {
            var panel=new StackPanel{Spacing=16};
            var theme=new ComboBox{Header="表示テーマ",HorizontalAlignment=HorizontalAlignment.Stretch};
            theme.Items.Add("Windowsの設定に合わせる");theme.Items.Add("ライト");theme.Items.Add("ダーク");
            theme.SelectedIndex=ViewerOptions.Value.Theme switch{"light"=>1,"dark"=>2,_=>0};
            AutomationProperties.SetAutomationId(theme,"SettingsTheme");
            var enlarge=new ToggleSwitch{Header="小さい画像も画面いっぱいに拡大",IsOn=ViewerOptions.Value.EnlargeSmallImages};
            AutomationProperties.SetAutomationId(enlarge,"SettingsEnlargeImages");
            panel.Children.Add(theme);panel.Children.Add(enlarge);
            var wheel=new ComboBox{Header="ホイールで次の画像・ページへ",HorizontalAlignment=HorizontalAlignment.Stretch};
            wheel.Items.Add("下に回す（上で戻る）");wheel.Items.Add("上に回す（下で戻る）");wheel.SelectedIndex=ViewerOptions.Value.WheelUpAdvances?1:0;
            AutomationProperties.SetAutomationId(wheel,"SettingsWheel");
            var hint=new TextBlock{Text="拡大中は画像のスクロールを優先します。マウスの進む・戻るも使えます。",TextWrapping=TextWrapping.Wrap};
            var savedText=new TextBlock{TextWrapping=TextWrapping.Wrap};AutomationProperties.SetAutomationId(savedText,"SettingsStatus");
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="設定",PrimaryButtonText="保存",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,Content=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,Padding=new Thickness(0,0,16,0)}};
            AutomationProperties.SetAutomationId(dialog,"SettingsDialog");
            // Preserve the existing UI Automation identifier on the native footer button.
            var saveStyle=new Style{TargetType=typeof(Button),BasedOn=(Style)Application.Current.Resources["AccentButtonStyle"]};
            saveStyle.Setters.Add(new Setter(AutomationProperties.AutomationIdProperty,"SettingsSave"));
            dialog.PrimaryButtonStyle=saveStyle;
            dialog.PrimaryButtonClick+=(_,args)=>{args.Cancel=true;SavePreferences();};
            void SavePreferences(){try{var selectedTheme=theme.SelectedIndex switch{1=>"light",2=>"dark",_=>"system"};ViewerOptions.SavePreferences(wheel.SelectedIndex==1,selectedTheme,enlarge.IsOn);MainWindow.Current.ApplyTheme(selectedTheme);dialog.RequestedTheme=selectedTheme switch{"light"=>ElementTheme.Light,"dark"=>ElementTheme.Dark,_=>ElementTheme.Default};savedText.Text="保存しました。テーマはすぐ反映し、画像の拡大は次に開くときに適用します。";}catch(Exception ex){savedText.Text="保存できません: "+ex.Message;}}
            panel.Children.Add(wheel);panel.Children.Add(hint);panel.Children.Add(savedText);
            var closedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed += (_, _) => closedTcs.TrySetResult(true);
            foreach(var (label,id,target) in new[]{
                ("使い方・初回設定","BtnGettingStarted","help"),
                ("AI検索の準備","BtnAIIndex","ai"),
                ("関連語を編集","BtnRelatedTerms","terms"),
                ("閲覧履歴を削除","BtnClearHistory","history"),
                ("バックアップと復元","BtnBackupGuide","backup"),
                ("診断情報を表示・コピー","BtnDiagnostics","diagnostics")})
            {
                var button=new Button{Content=label,HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(button,id);
                button.Click+=(_,_)=>{destination=target;dialog.Hide();};panel.Children.Add(button);
            }
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task, Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(destination is not null)
        {
            if(destination=="ai")AI_Click(this,new RoutedEventArgs());
            else if(destination=="help")await OpenGettingStartedGuideAsync();
            else if(destination=="terms")RelatedTerms_Click(this,new RoutedEventArgs());
            else if(destination=="history")await DeleteHistoryAsync();
            else if(destination=="backup")await OpenBackupDialogAsync();
            else if(destination=="diagnostics")await OpenDiagnosticsDialogAsync();
        }
    }
    private async Task OpenRecoveryGuideDialogAsync()
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        try
        {
            var panel=new StackPanel{Spacing=12};
            panel.Children.Add(new TextBlock
            {
                Text="バックアップは「設定」→「バックアップと復元」から作成できます。復元は同じ画面の「バックアップから復元」で行います。\n\n"+
                     "復元内容は新しい保存先で検証します。同意して再起動すると切り替わり、元のライブラリも残ります。自動再起動は、対応した配布版の Aredoko.exe から起動した場合に利用できます。\n\n"+
                     "バックアップにはライブラリ情報と、選択した設定・履歴・読書位置・AI索引が含まれます。元の画像・動画、モデル、Python環境、サムネイルキャッシュは含みません。",
                TextWrapping=TextWrapping.Wrap
            });
            var offline=new Expander{Header="起動できない場合の復旧手順",HorizontalAlignment=HorizontalAlignment.Stretch,Content=new TextBlock
            {
                Text="アプリを終了してから、復旧ツールで新しい復元先を指定してください。既存のDBや元のメディアへ上書きしないでください。\n\n"+
                     "バックアップ例：\npython tools/backup_library.py backup --catalog <catalog.sqlite> --output <新バックアップ先>\n\n"+
                     "復元例：\npython tools/backup_library.py restore --bundle <バックアップ先> --output <新復元先>\n\n"+
                     "破損したAI索引を除いて復元する場合は --without-ai を指定します。CLIを使用できる環境が必要です。",
                TextWrapping=TextWrapping.Wrap
            }};
            AutomationProperties.SetAutomationId(offline,"BackupRecoveryAdvanced");panel.Children.Add(offline);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="バックアップと復旧ガイド",CloseButtonText="閉じる",Content=panel};
            AutomationProperties.SetAutomationId(dialog,"BackupGuideDialog");
            var closeBtn = new Button { Content = "閉じる", HorizontalAlignment = HorizontalAlignment.Right };
            AutomationProperties.SetAutomationId(closeBtn, "BtnCloseBackupGuide");
            closeBtn.Click += (_, _) => dialog.Hide();
            panel.Children.Add(closeBtn);
            var closedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed += (_, _) => closedTcs.TrySetResult(true);
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task, Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();RestoreNavigation();}
    }
    private async Task OpenDiagnosticsDialogAsync()
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        try
        {
            System.Text.Json.Nodes.JsonNode? aiStatus = null;
            try { aiStatus = await api.GetAsync("api/library/ai/status"); } catch { }
            var build=AppBuildIdentity.FromAssembly(typeof(App).Assembly,AppContext.BaseDirectory);
            var report=DiagnosticsReport.Generate(aiStatus,aiScope,knownRoots,knownShelves?.Count??0,0,ActualTheme.ToString(),appVersion:build.Version)
                +"\n"+build.ToDiagnosticText();

            var panel=new StackPanel{Spacing=12};
            var txt = new TextBox
            {
                Text = report,
                IsReadOnly = true,
                AcceptsReturn = true,
                TextWrapping = TextWrapping.Wrap,
                Height = 280,
                FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas, Cascadia Code, monospace")
            };
            AutomationProperties.SetAutomationId(txt, "TxtDiagnostics");
            panel.Children.Add(txt);

            var copyStatus = new TextBlock { TextWrapping = TextWrapping.Wrap, Style = (Style)Resources["MediaMetadataStyle"] };
            AutomationProperties.SetAutomationId(copyStatus, "TxtDiagnosticsStatus");
            var copyBtn = new Button { Content = "クリップボードにコピー", HorizontalAlignment = HorizontalAlignment.Left };
            AutomationProperties.SetAutomationId(copyBtn, "BtnCopyDiagnostics");
            copyBtn.Click += (_, _) =>
            {
                var package = new Windows.ApplicationModel.DataTransfer.DataPackage();
                package.SetText(report);
                Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(package);
                copyStatus.Text = "診断情報をクリップボードにコピーしました。外部への自動送信は行われません。";
            };
            panel.Children.Add(copyBtn);
            panel.Children.Add(copyStatus);

            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="診断情報（匿名化済み）",CloseButtonText="閉じる",Content=panel};
            AutomationProperties.SetAutomationId(dialog,"DiagnosticsDialog");
            var closeDiagBtn = new Button { Content = "閉じる", HorizontalAlignment = HorizontalAlignment.Right };
            AutomationProperties.SetAutomationId(closeDiagBtn, "BtnCloseDiagnostics");
            closeDiagBtn.Click += (_, _) => dialog.Hide();
            panel.Children.Add(closeDiagBtn);
            var closedTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed += (_, _) => closedTcs.TrySetResult(true);
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task, Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();RestoreNavigation();}
    }
}
