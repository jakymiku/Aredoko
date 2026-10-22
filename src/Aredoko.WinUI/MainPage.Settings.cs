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
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="設定",PrimaryButtonText="保存",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,Content=panel};
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
                ("AI検索の準備","BtnAIIndex","ai"),
                ("関連語を編集","BtnRelatedTerms","terms"),
                ("閲覧履歴を削除","BtnClearHistory","history"),
                ("バックアップと復旧ガイド","BtnBackupGuide","backup"),
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
            else if(destination=="terms")RelatedTerms_Click(this,new RoutedEventArgs());
            else if(destination=="history")await DeleteHistoryAsync();
            else if(destination=="backup")await OpenBackupGuideDialogAsync();
            else if(destination=="diagnostics")await OpenDiagnosticsDialogAsync();
        }
    }
    private async Task OpenBackupGuideDialogAsync()
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        try
        {
            var panel=new StackPanel{Spacing=12};
            panel.Children.Add(new TextBlock
            {
                Text="【安全な停止時バックアップと復旧の手順】\n" +
                     "Aredokoのデータベースは動作中、排他的ロック（.owner.lock）により破損から保護されています。\n" +
                     "データの整合性を100%保つため、バックアップおよび復旧はアプリを終了した状態でCLIツールを実行します。\n\n" +
                     "■ バックアップコマンド例:\n" +
                     "python tools/backup_library.py backup --catalog <catalog.sqlite> --output <新バックアップ先>\n\n" +
                     "■ 復元コマンド例:\n" +
                     "python tools/backup_library.py restore --bundle <バックアップ先> --output <新復元先>\n\n" +
                     "※ バックアップには手動タグ・棚・履歴・読書位置・ページ本文・AIプロファイルが含まれます。\n" +
                     "※ AIベクトルは同梱または明示省略（--omit-ai / --without-ai）が可能です。",
                TextWrapping=TextWrapping.Wrap
            });
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
