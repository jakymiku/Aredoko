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

        bool show = !gettingStartedDismissed && !settingsHubOpen && rows.Count == 0 && !hasList && view == "all" && string.IsNullOrWhiteSpace(Query.Text)
            && Kind.SelectedIndex == 0 && selectedSearchRoots is null && selectedShelfIds is null && similarityOrigin is null;
        GettingStarted.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        if (show)
        {
            Empty.Visibility = Visibility.Collapsed;
            if (GettingStartedSummaryText is not null)
                GettingStartedSummaryText.Text = hasFolder
                    ? "一覧を更新すると名前・タグで探せます。"
                    : "フォルダを追加するだけで、作品の名前やタグをすぐに探せます。";
            if (GettingStartedStep1Text is not null)
                GettingStartedStep1Text.Text = hasFolder ? $"完了（{activeRoots.Length} フォルダ）" : "探したい場所を登録";
            if (GettingStartedStep2Text is not null)
                GettingStartedStep2Text.Text = hasList ? "準備完了" : hasFolder ? "一覧を更新して検索" : "名前・種類・タグで検索";
            if (GettingStartedStep3Text is not null)
                GettingStartedStep3Text.Text = aiIndexReady ? "準備完了" : "見た目・意味・音で検索";
            if (GettingStartedFolders is not null)
                GettingStartedFolders.Content = hasFolder ? "登録フォルダを開く" : "フォルダを追加";
        }
        else if (gettingStartedDismissed && rows.Count == 0 && !hasList && view == "all" && string.IsNullOrWhiteSpace(Query.Text) && Kind.SelectedIndex == 0 && selectedSearchRoots is null && selectedShelfIds is null && similarityOrigin is null)
        {
            Empty.Visibility = Visibility.Visible;
            Empty.Text = "左メニューの「登録フォルダ」からいつでも追加・更新できます。";
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
                IsEnabled = aiAvailable,
                Content = new StackPanel
                {
                    Spacing = 2,
                    Children =
                    {
                        new TextBlock { Text = "ファイル一覧とAI検索データを作る", Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = "現在のモデルと対象範囲で、新規・変更分のAI検索データを作ります（タグ候補の自動承認はしません）。", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
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
            void UpdatePrimaryText() => dialog.PrimaryButtonText = choiceListAndAI.IsChecked == true ? "一覧とAI検索データを作る" : "一覧を作る";
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
                        var msg = "AIが未設定のためファイル一覧だけ作成を開始しました。AI検索データは「設定 → AI検索を設定」の完了後に作成できます。";
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
            var panel = new StackPanel { Spacing = 14, MaxWidth = 600 };
            var greeting = VisualAssets.Sticker(64);
            greeting.Source = new Microsoft.UI.Xaml.Media.Imaging.BitmapImage(new Uri("ms-appx:///Assets/Visual/aredoko_mascot_greeting_512.png")) { DecodePixelWidth = 192 };
            greeting.Visibility = Visibility.Visible;
            var welcome = new Grid { ColumnSpacing = 12 };
            welcome.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            welcome.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            welcome.Children.Add(greeting);
            var introStack = new StackPanel { Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
            introStack.Children.Add(new TextBlock
            {
                Text = "まずはフォルダを追加して、検索と閲覧を始めましょう。AIは後からいつでも設定できます。",
                Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"],
                TextWrapping = TextWrapping.Wrap
            });
            introStack.Children.Add(new TextBlock
            {
                Text = "🔒 元のファイルやフォルダは一切変更・移動・外部送信しません",
                Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"],
                Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"],
                TextWrapping = TextWrapping.Wrap
            });
            Grid.SetColumn(introStack, 1);
            welcome.Children.Add(introStack);
            var welcomeCard = new Border
            {
                Style = (Style)Application.Current.Resources["AredokoSurfaceStyle"],
                Child = welcome
            };
            panel.Children.Add(welcomeCard);

            var overviewGrid = new Grid { ColumnSpacing = 8 };
            overviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            overviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            overviewGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var stepSummaries = new[]
            {
                ("① フォルダを追加", "検索したいフォルダを登録し「ファイル一覧を作る」で準備完了"),
                ("② 探して開く・整理", "名前・タグで即検索。Spaceや右側の詳細でタグ付け・棚分け"),
                ("③ AIで探す（任意）", "画像の見た目・言葉の意味・動画の場面・音声から横断検索")
            };
            for (var i = 0; i < stepSummaries.Length; i++)
            {
                var (stepTitle, stepDesc) = stepSummaries[i];
                var stepCard = new Border
                {
                    Background = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["SubtleFillColorSecondaryBrush"],
                    BorderBrush = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"],
                    BorderThickness = new Thickness(1),
                    CornerRadius = new CornerRadius(6),
                    Padding = new Thickness(10, 8, 10, 8),
                    Child = new StackPanel
                    {
                        Spacing = 4,
                        Children =
                        {
                            new TextBlock { Text = stepTitle, Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"], TextWrapping = TextWrapping.Wrap },
                            new TextBlock { Text = stepDesc, Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
                        }
                    }
                };
                Grid.SetColumn(stepCard, i);
                overviewGrid.Children.Add(stepCard);
            }
            panel.Children.Add(overviewGrid);

            var hasRegistered = knownRoots.Any(r => r.Enabled);
            var addFolder = new Button { Content = hasRegistered ? "📁 登録フォルダを開く" : "📁 フォルダを追加", HorizontalAlignment = HorizontalAlignment.Stretch, Style = (Style)Application.Current.Resources["AccentButtonStyle"] };
            AutomationProperties.SetAutomationId(addFolder, "GuideAddFolder");
            Button? backToSettings = fromSettings ? new Button { Content = "設定へ戻る", HorizontalAlignment = HorizontalAlignment.Stretch } : null;
            if (backToSettings is not null) AutomationProperties.SetAutomationId(backToSettings, "BtnBackToSettings");

            var quickActions = new Grid { ColumnSpacing = 8 };
            quickActions.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            quickActions.Children.Add(addFolder);
            if (backToSettings is not null)
            {
                quickActions.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                Grid.SetColumn(backToSettings, 1);
                quickActions.Children.Add(backToSettings);
            }
            panel.Children.Add(quickActions);

            var detailsHeader = new TextBlock
            {
                Text = "詳しい使い方・ショートカット",
                Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"],
                Margin = new Thickness(0, 4, 0, 0)
            };
            panel.Children.Add(detailsHeader);

            foreach (var (index, title, text) in new[]
            {
                (1, "1. フォルダの追加と更新方法", "左メニューの「登録フォルダ → ＋ フォルダを追加」（またはウィンドウへドラッグ＆ドロップ）から検索したいフォルダを登録します。登録直後に「ファイル一覧を作る（推奨）」または「一覧＋AI検索データ」を選べます。フォルダ内に新しく追加・変更した作品があるときは「⟳ 更新」で再読み込みできます。"),
                (2, "2. 文字検索・閲覧・タグと棚の整理", "検索欄に名前やタグを入力すると即座に絞り込めます（関連語辞書で表記ゆれ・同義語にも対応）。作品のダブルクリックやEnterで内蔵ビューアが開きます。Spaceキーまたは「詳細」ボタンで右側の詳細ペインを開き、タグの追加（Enter確定）・お気に入り・棚への追加（複数選択時も下のバーから一括操作可能）を行えます。"),
                (3, "3. AI検索の準備とモデルの選び方（任意）", "曖昧な言葉や画像の見た目・動画の場面・音声の内容で探したいときは、下の「AIで探す方法」または「設定 → AI検索」から用途をチェックしてセットアップします。\n・「自動セットアップ」でAI実行環境＋検索モデル（EmbeddingGemma 2）を一括導入し、再起動後に「AI検索を設定」からAI検索データを作成すると使えます。\n・すでに手元に環境やモデルがある場合は「手元のファイルを使う」から指定できます。"),
                (4, "4. 似た作品の検索・AIタグ候補（WD Tagger）", "作品を右クリック（または詳細ペインの「≈ 似た作品」）から、見た目が似た画像・本・動画や音が似た曲を探せます。\n\n【画像タグ付け（WD Tagger）の始め方】\n「設定 → 🏷 タグ付けモデルを取得」（または詳細ペインの「✨ AI候補 → 📥 モデルを取得・設定」）から wd-swinv2-v3（約468MB）をダウンロードすると、基本の実行環境でそのまま動作するため再起動なしですぐ使えます。詳細ペインの「✨ AI候補」または複数選択の「まとめて整理」からタグ候補を生成・一括承認できます（確定タグは自動上書きされません）。"),
                (5, "5. ショートカット一覧とバックアップ", "・Ctrl+F：検索欄へ移動 / Ctrl+S：タグや棚の変更を保存\n・Space：詳細・プレビュー欄を開閉 / Enter：選択した作品を開く\n・Ctrl+Home / Ctrl+End：一覧の先頭・末尾へ移動\n\nタグ・棚・設定の控えの保存と別フォルダへの安全な復元は「設定 → 管理・診断 → 💾 バックアップと復元」で行えます。")
            })
            {
                var body = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
                var topicExpander = new Expander
                {
                    Header = title,
                    Content = body,
                    IsExpanded = true,
                    HorizontalAlignment = HorizontalAlignment.Stretch,
                    HorizontalContentAlignment = HorizontalAlignment.Stretch
                };
                AutomationProperties.SetAutomationId(topicExpander, $"GuideTopic{index}");
                panel.Children.Add(topicExpander);
            }
            var scroll = new ScrollViewer { Content = panel, MaxHeight = Math.Max(160, ActualHeight - 240), VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Padding = new Thickness(0, 0, 16, 0) };
            AutomationProperties.SetAutomationId(scroll, "GettingStartedGuideScroll");
            var dialog = new ContentDialog { XamlRoot = XamlRoot, RequestedTheme = ActualTheme, Title = "はじめ方・使い方", Content = scroll, PrimaryButtonText="AIで探す方法", CloseButtonText = "閉じる",DefaultButton=ContentDialogButton.None };
            dialog.Resources["ContentDialogMaxWidth"] = 680d;
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
