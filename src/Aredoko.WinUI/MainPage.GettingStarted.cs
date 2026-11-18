using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private void UpdateGettingStarted()
    {
        var activeRoots = knownRoots.Where(r => r.Enabled).ToArray();
        bool hasFolder = activeRoots.Length > 0;
        int scannedItems = activeRoots.Sum(r => r.PresentCount);
        bool hasList = rows.Count > 0 || scannedItems > 0 || activeRoots.Any(r => !string.IsNullOrEmpty(r.LastScannedAt));

        bool show = !gettingStartedDismissed && rows.Count == 0 && !hasList && view == "all" && string.IsNullOrWhiteSpace(Query.Text)
            && Kind.SelectedIndex == 0 && selectedSearchRoots is null && selectedShelfIds is null && similarityOrigin is null;
        GettingStarted.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        if (show)
        {
            Empty.Visibility = Visibility.Collapsed;
            if (GettingStartedSummaryText is not null)
                GettingStartedSummaryText.Text = hasFolder
                    ? "登録したフォルダからファイル一覧を作ると、名前・タグで探せます。"
                    : "探したいフォルダを追加すると、ファイル一覧を作って名前・タグで探せます（AIなしで使えます）。";
            if (GettingStartedStep1Text is not null)
                GettingStartedStep1Text.Text = hasFolder ? $"1. フォルダを追加 — 完了（{activeRoots.Length} フォルダ）" : "1. フォルダを追加 — 探す場所を覚えます";
            if (GettingStartedStep2Text is not null)
                GettingStartedStep2Text.Text = hasList ? "2. ファイル一覧を作る — 完了" : (hasFolder ? "2. ファイル一覧を作る — 下のボタンから作成できます" : "2. ファイル一覧を作る — 作品を見つけて名前・タグで探せます");
            if (GettingStartedStep3Text is not null)
                GettingStartedStep3Text.Text = aiIndexReady ? "3. AIで探す（任意） — 準備済み" : "3. AIで探す（任意） — 情景や音で探したいときに設定します";
            if (GettingStartedFolders is not null)
                GettingStartedFolders.Content = hasFolder ? "ファイル一覧を作る（登録フォルダへ）" : "フォルダを追加";
        }
        else if (gettingStartedDismissed && rows.Count == 0 && !hasList && view == "all" && string.IsNullOrWhiteSpace(Query.Text) && Kind.SelectedIndex == 0 && selectedSearchRoots is null && selectedShelfIds is null && similarityOrigin is null)
        {
            Empty.Visibility = Visibility.Visible;
            Empty.Text = "「登録フォルダ」から、フォルダの追加やファイル一覧の作成をいつでも実行できます。";
        }
    }

    private void GettingStartedDismiss_Click(object sender, RoutedEventArgs args)
    {
        gettingStartedDismissed = true;
        UpdateGettingStarted();
    }

    private async void GettingStartedFolders_Click(object sender, RoutedEventArgs args)
    {
        var activeRoots = knownRoots.Where(r => r.Enabled).ToArray();
        if (activeRoots.Length == 0)
        {
            await OpenFolderHubAsync();
            if (folderHubOpen) FolderAddPanel.Visibility = Visibility.Visible;
        }
        else
        {
            await OpenFolderHubAsync();
            if (folderHubOpen)
            {
                var ids = activeRoots.Select(r => r.Id).ToArray();
                OpenFolderSettingsPanel(ids);
            }
        }
    }

    private async Task PromptPostRegistrationScanAsync(IReadOnlyList<int> targetIds)
    {
        if (targetIds.Count == 0 || !ready || disposed || dialogOpen || saving || !await transitions.WaitAsync(0)) return;
        dialogOpen = true;
        bool openAiSetupRequested = false;
        try
        {
            bool aiAvailable = false;
            string aiReason = "AIモデルと実行環境の準備が必要です。";
            try
            {
                var aiStatus = await api.GetAsync("api/library/ai/status");
                aiAvailable = aiStatus["available"]?.GetValue<bool>() == true;
                aiReason = aiStatus["error"]?.GetValue<string>() ?? aiReason;
                if (aiAvailable && aiStatus["state"]?.GetValue<string>() is "complete" or "partial")
                    aiIndexReady = true;
            }
            catch { }

            var panel = new StackPanel { Spacing = 14 };
            var targetNames = knownRoots.Where(r => targetIds.Contains(r.Id)).Select(r => r.ShortPath).ToArray();
            var targetSummary = targetNames.Length > 0 ? string.Join("、", targetNames) : $"{targetIds.Count} フォルダ";
            var targetText = new TextBlock
            {
                Text = $"対象: {targetSummary}（{targetIds.Count} フォルダ）",
                TextWrapping = TextWrapping.Wrap,
                Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"]
            };
            AutomationProperties.SetAutomationId(targetText, "ScanPromptTargetText");
            panel.Children.Add(targetText);

            var choiceListOnly = new RadioButton
            {
                GroupName = "PostRegScanChoice",
                IsChecked = true,
                Content = new StackPanel
                {
                    Spacing = 2,
                    Children =
                    {
                        new TextBlock { Text = "ファイル一覧を作る（推奨）", Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = "名前・タグで探せます。AIなしですぐ使えます。", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
                    }
                }
            };
            AutomationProperties.SetAutomationId(choiceListOnly, "ScanChoiceListOnly");
            panel.Children.Add(choiceListOnly);

            var choiceListAndAI = new RadioButton
            {
                GroupName = "PostRegScanChoice",
                Content = new StackPanel
                {
                    Spacing = 2,
                    Children =
                    {
                        new TextBlock { Text = "ファイル一覧とAI検索用データを作る", Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = "現在のモデルと対象範囲で、新規・変更分の検索用データを作ります（タグ候補の自動承認はしません）。", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
                    }
                }
            };
            AutomationProperties.SetAutomationId(choiceListAndAI, "ScanChoiceListAndAI");
            panel.Children.Add(choiceListAndAI);

            var choiceLater = new RadioButton
            {
                GroupName = "PostRegScanChoice",
                Visibility = Visibility.Collapsed,
                Content = new StackPanel
                {
                    Spacing = 2,
                    Children =
                    {
                        new TextBlock { Text = "今は登録だけ", Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = "「登録フォルダ」からあとでファイル一覧を作れます。", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
                    }
                }
            };
            AutomationProperties.SetAutomationId(choiceLater, "ScanChoiceLater");
            panel.Children.Add(choiceLater);

            ContentDialog? currentDialog = null;

            if (!aiAvailable)
            {
                var aiWarning = new Border
                {
                    Style = (Style)Application.Current.Resources["AredokoSurfaceStyle"],
                    Margin = new Thickness(0, 4, 0, 0),
                    Child = new StackPanel
                    {
                        Spacing = 6,
                        Margin = new Thickness(10),
                        Children =
                        {
                            new TextBlock
                            {
                                Text = "AI未設定：" + aiReason + "（選択しただけでダウンロードや設定変更は始まりません）",
                                TextWrapping = TextWrapping.Wrap,
                                Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"]
                            },
                            new Button
                            {
                                Content = "AIを設定",
                                HorizontalAlignment = HorizontalAlignment.Left
                            }
                        }
                    }
                };
                var warningText = ((StackPanel)aiWarning.Child).Children[0] as TextBlock;
                if (warningText is not null)
                    AutomationProperties.SetAutomationId(warningText, "ScanChoiceAIUnavailableReason");
                var openAiBtn = ((StackPanel)aiWarning.Child).Children[1] as Button;
                if (openAiBtn is not null)
                {
                    AutomationProperties.SetAutomationId(openAiBtn, "ScanChoiceOpenAISetup");
                    openAiBtn.Click += (_, _) =>
                    {
                        openAiSetupRequested = true;
                        currentDialog?.Hide();
                    };
                }
                panel.Children.Add(aiWarning);
            }

            var scroll = new ScrollViewer
            {
                Content = panel,
                MaxHeight = Math.Max(160, ActualHeight - 240),
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                Padding = new Thickness(0, 0, 16, 0)
            };

            var dialog = new ContentDialog
            {
                XamlRoot = XamlRoot,
                RequestedTheme = ActualTheme,
                Title = "登録したフォルダのファイル一覧を作りますか？",
                Content = scroll,
                PrimaryButtonText = "一覧を作る",
                CloseButtonText = "今は登録だけ",
                DefaultButton = ContentDialogButton.Primary
            };
            void UpdatePrimaryText() => dialog.PrimaryButtonText = choiceListAndAI.IsChecked == true ? "一覧とAI検索用データを作る" : "一覧を作る";
            choiceListOnly.Checked += (_, _) => UpdatePrimaryText();
            choiceListAndAI.Checked += (_, _) => UpdatePrimaryText();
            currentDialog = dialog;
            AutomationProperties.SetAutomationId(dialog, "PostRegistrationScanDialog");

            var result = await dialog.ShowAsync();

            if (openAiSetupRequested)
            {
                ScanStatus.Text = "フォルダを登録しました。AIを設定した後、「登録フォルダ」から一覧を作成できます。";
                Notice("フォルダを登録しました", ScanStatus.Text);
                return;
            }

            if (result == ContentDialogResult.Primary)
            {
                if (choiceListAndAI.IsChecked == true)
                {
                    if (!aiAvailable)
                    {
                        await StartScanWithModeAsync(targetIds, "list");
                        var msg = "AIが未設定のためファイル一覧だけ作成を開始しました。AI検索用データは「設定 → AI検索を設定」の完了後に作成できます。";
                        ScanStatus.Text = msg;
                        Notice("ファイル一覧の作成を開始しました", msg);
                    }
                    else
                    {
                        await StartScanWithModeAsync(targetIds, "list_and_ai");
                    }
                }
                else
                {
                    await StartScanWithModeAsync(targetIds, "list");
                }
            }
            else
            {
                ScanStatus.Text = "フォルダを登録しました。「登録フォルダ」の［一覧を作る］からいつでも実行できます。";
                Notice("フォルダを登録しました", ScanStatus.Text);
            }
        }
        catch (Exception error) { Failure(error); }
        finally
        {
            dialogOpen=false;transitions.Release();
            if(openAiSetupRequested&&!disposed)AI_Click(this,new RoutedEventArgs());
        }
    }

    private async void GettingStartedHelp_Click(object sender, RoutedEventArgs args) => await OpenGettingStartedGuideAsync();

    private async Task OpenGettingStartedGuideAsync(bool fromSettings=false)
    {
        if (!ready || disposed || dialogOpen || saving || !await transitions.WaitAsync(0)) return;
        dialogOpen = true;bool setupRequested=false,folderRequested=false,returnToSettings=false;
        try
        {
            var panel = new StackPanel { Spacing = 16 };
            var greeting = VisualAssets.Sticker(72);
            greeting.Source = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(new Uri("ms-appx:///Assets/Visual/aredoko_mascot_greeting_512.png")) { DecodePixelWidth = 192 };
            greeting.Visibility = Visibility.Visible;
            var welcome=new Grid{ColumnSpacing=12};
            welcome.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            welcome.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            welcome.Children.Add(greeting);
            var introduction=new TextBlock{Text="まずはフォルダを追加して、検索と閲覧を始めましょう。AIは後からいつでも設定できます。",TextWrapping=TextWrapping.Wrap,VerticalAlignment=VerticalAlignment.Center};
            Grid.SetColumn(introduction,1);welcome.Children.Add(introduction);panel.Children.Add(welcome);
            foreach(var (title,text) in new[]{
                ("1. フォルダを追加", "検索したいフォルダを選び、「ファイル一覧を作る」で始められます。元ファイルは変更しません。"),
                ("2. 検索・閲覧・整理", "名前・タグで検索し、ダブルクリックで開きます。右側の詳細でタグ付けや棚分けができます。"),
                ("3. 必要ならAIを設定", "情景や音の内容から探したいときは「AIで探す方法」へ。自動セットアップやダウンロード可能なモデルを選べます。")})
            {
                var step=new StackPanel{Spacing=4};
                step.Children.Add(new TextBlock{Text=title,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
                step.Children.Add(new TextBlock{Text=text,TextWrapping=TextWrapping.Wrap});panel.Children.Add(step);
            }
            var hasRegistered=knownRoots.Any(r=>r.Enabled);
            var addFolder=new Button{Content=hasRegistered?"登録フォルダを開く":"フォルダを追加",HorizontalAlignment=HorizontalAlignment.Stretch,Style=(Style)Application.Current.Resources["AccentButtonStyle"]};
            AutomationProperties.SetAutomationId(addFolder,"GuideAddFolder");panel.Children.Add(addFolder);
            Button? backToSettings=fromSettings?new Button{Content="設定へ戻る",HorizontalAlignment=HorizontalAlignment.Stretch}:null;
            if(backToSettings is not null){AutomationProperties.SetAutomationId(backToSettings,"BtnBackToSettings");panel.Children.Add(backToSettings);}
            var details=new StackPanel{Spacing=12};
            foreach (var (title, text) in new[]
            {
                ("1. フォルダを追加する", "「登録フォルダ」→［フォルダを追加］から検索したい場所を選びます。サブフォルダを含めるかも選べます。登録後は「ファイル一覧を作る（推奨）」「ファイル一覧とAI検索用データを作る」または「今は登録だけ」を選べます。元ファイルは移動・変換しません。"),
                ("2. 検索して開く", "検索欄に名前やタグを入力します。画像・本・動画・音声はダブルクリックで開けます。設定でAredokoとWindowsの既定アプリを選べます。右クリックから保存場所も開けます。"),
                ("3. AIで探す準備をする（任意）", "「AIで探す方法」から用途を選び、必要なものを確認します。EmbeddingGemma 2は「自動セットアップ」で公式パッケージとモデルを取得・確認できます。このほか「ダウンロードできるモデルを選ぶ」「手元のモデルを使う」も選べます。変更後は再起動し、「AI検索を設定」から検索用データを作ります。動画・音声はそれぞれの欄から作成してください。WD TaggerのAIタグ候補は任意です。"),
                ("4. 内容から探す・整理する", "準備後は「画像の見た目（AI）」などの検索方法で、覚えている情景や特徴を入力します。右側の詳細でお気に入りは即反映し、タグ・棚は［変更を保存］で保存します。AIタグ候補は内容を確認してから承認します。"),
                ("閲覧・データ保護", "一覧ではCtrl+Homeで先頭、Ctrl+Endで末尾へ移動できます。画像や本は左右キー・ホイール・マウスの進む／戻るで送れます。ホイール方向や開くアプリは設定で、小さい画像の拡大・操作バーの常時表示・先頭へのループ移動はビューアの設定メニューで変更できます。バックアップと復元も設定から行えます。登録解除や棚の削除で元ファイルは消えません。"),
            })
            {
                details.Children.Add(new TextBlock { Text = title, Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"], TextWrapping = TextWrapping.Wrap });
                details.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true });
            }
            var more=new Expander{Header="詳しい手順・操作とデータ保護",Content=details,HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(more,"GuideDetails");panel.Children.Add(more);
            var scroll = new ScrollViewer { Content = panel, MaxHeight = Math.Max(160, ActualHeight - 240), VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Padding = new Thickness(0, 0, 16, 0) };
            var dialog = new ContentDialog { XamlRoot = XamlRoot, RequestedTheme = ActualTheme, Title = "使い方", Content = scroll, PrimaryButtonText="AIで探す方法", CloseButtonText = "閉じる",DefaultButton=ContentDialogButton.None };
            AutomationProperties.SetAutomationId(dialog, "GettingStartedGuideDialog");
            addFolder.Click+=(_,_)=>{folderRequested=true;dialog.Hide();};
            if(backToSettings is not null)backToSettings.Click+=(_,_)=>{returnToSettings=true;dialog.Hide();};
            var closedTcs=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed+=(_,_)=>closedTcs.TrySetResult(true);
            setupRequested=await dialog.ShowAsync()==ContentDialogResult.Primary;
            await Task.WhenAny(closedTcs.Task,Task.Delay(500));
        }
        catch (Exception error) { Failure(error); }
        finally { dialogOpen = false; transitions.Release(); }
        if(folderRequested&&!disposed)
        {
            await OpenFolderHubAsync();
            if(folderHubOpen)FolderAddPanel.Visibility=Visibility.Visible;
        }
        else if(setupRequested&&!disposed)await OpenAISetupPlanAsync();
        else if(returnToSettings&&!disposed)await OpenSettingsAsync();
    }
}
