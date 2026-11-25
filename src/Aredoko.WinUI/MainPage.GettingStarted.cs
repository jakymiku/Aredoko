using Aredoko.Core;
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
                    ? AppText.L("一覧を更新すると名前・タグで探せます。", "Scan your folders to search by filename and tags.")
                    : AppText.L("フォルダを追加するだけで、作品の名前やタグをすぐに探せます。", "Add a folder to start searching by filename and tags right away.");
            if (GettingStartedStep1Text is not null)
                GettingStartedStep1Text.Text = hasFolder ? AppText.L($"完了（{activeRoots.Length} フォルダ）", $"Done ({activeRoots.Length} folder(s))") : AppText.L("探したい場所を登録", "Register folders to search");
            if (GettingStartedStep2Text is not null)
                GettingStartedStep2Text.Text = hasList ? AppText.L("準備完了", "Ready") : hasFolder ? AppText.L("一覧を更新して検索", "Scan list to search") : AppText.L("名前・種類・タグで検索", "Search by name, kind, or tags");
            if (GettingStartedStep3Text is not null)
                GettingStartedStep3Text.Text = aiIndexReady ? AppText.L("準備完了", "Ready") : AppText.L("見た目・意味・音で検索", "Search by visuals, meaning, or audio");
            if (GettingStartedFolders is not null)
                GettingStartedFolders.Content = hasFolder ? AppText.L("登録フォルダを開く", "Open Registered Folders") : AppText.L("フォルダを追加", "Add Folder");
        }
        else if (gettingStartedDismissed && rows.Count == 0 && !hasList && view == "all" && string.IsNullOrWhiteSpace(Query.Text) && Kind.SelectedIndex == 0 && selectedSearchRoots is null && selectedShelfIds is null && similarityOrigin is null)
        {
            Empty.Visibility = Visibility.Visible;
            Empty.Text = AppText.L("左メニューの「登録フォルダ」からいつでも追加・更新できます。", "You can add or scan folders anytime from Registered Folders in the left navigation.");
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
            string aiReason = AppText.L("AIモデルと実行環境の準備が必要です。", "AI model and runtime setup are required.");
            try
            {
                var aiStatus = await api.GetAsync("api/library/ai/status");
                aiAvailable = aiStatus["available"]?.GetValue<bool>() == true;
                aiReason = AppText.TranslateBackend(aiStatus["error"]?.GetValue<string>()) is { Length: > 0 } translated ? translated : aiReason;
                if (aiAvailable && aiStatus["state"]?.GetValue<string>() is "complete" or "partial")
                    aiIndexReady = true;
            }
            catch { }

            var panel = new StackPanel { Spacing = 14 };
            var targetNames = knownRoots.Where(r => targetIds.Contains(r.Id)).Select(r => r.ShortPath).ToArray();
            var targetSummary = targetNames.Length > 0 ? string.Join(AppText.L("、", ", "), targetNames) : AppText.L($"{targetIds.Count} フォルダ", $"{targetIds.Count} folder(s)");
            var targetText = new TextBlock
            {
                Text = AppText.L($"対象: {targetSummary}（{targetIds.Count} フォルダ）", $"Target: {targetSummary} ({targetIds.Count} folder(s))"),
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
                        new TextBlock { Text = AppText.L("ファイル一覧を作る（推奨）", "Fetch item list only (Recommended)"), Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = AppText.L("名前・タグで探せます。AIなしですぐ使えます。", "Search by filename and tags right away without AI."), Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
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
                        new TextBlock { Text = AppText.L("ファイル一覧とAI検索データを作る", "Fetch list & build AI search index"), Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = AppText.L("現在のモデルと対象範囲で、新規・変更分のAI検索データを作ります（タグ候補の自動承認はしません）。", "Builds AI search data for new/changed items using the current model and scope (tags are never auto-approved)."), Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
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
                        new TextBlock { Text = AppText.L("今は登録だけ", "Register only for now"), Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = AppText.L("「登録フォルダ」からあとでファイル一覧を作れます。", "You can scan the item list later from Registered Folders."), Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
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
                                Text = AppText.L("AI未設定：" + aiReason + "（選択しただけでダウンロードや設定変更は始まりません）", "AI not configured: " + aiReason + " (selecting this alone will not start any downloads)"),
                                TextWrapping = TextWrapping.Wrap,
                                Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"]
                            },
                            new Button
                            {
                                Content = AppText.L("AIを設定", "Set up AI"),
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
                Title = AppText.L("登録したフォルダのファイル一覧を作りますか？", "Scan files in registered folder(s)?"),
                Content = scroll,
                PrimaryButtonText = AppText.L("一覧を作る", "Build List"),
                CloseButtonText = AppText.L("今は登録だけ", "Register Only"),
                DefaultButton = ContentDialogButton.Primary
            };
            void UpdatePrimaryText() => dialog.PrimaryButtonText = choiceListAndAI.IsChecked == true ? AppText.L("一覧とAI検索データを作る", "Build List & AI Index") : AppText.L("一覧を作る", "Build List");
            choiceListOnly.Checked += (_, _) => UpdatePrimaryText();
            choiceListAndAI.Checked += (_, _) => UpdatePrimaryText();
            currentDialog = dialog;
            AutomationProperties.SetAutomationId(dialog, "PostRegistrationScanDialog");

            var result = await dialog.ShowAsync();

            if (openAiSetupRequested)
            {
                ScanStatus.Text = AppText.L("フォルダを登録しました。AIを設定した後、「登録フォルダ」から一覧を作成できます。", "Folder registered. After setting up AI, scan items from Registered Folders.");
                Notice(AppText.L("フォルダを登録しました", "Folder registered"), ScanStatus.Text);
                return;
            }

            if (result == ContentDialogResult.Primary)
            {
                if (choiceListAndAI.IsChecked == true)
                {
                    if (!aiAvailable)
                    {
                        await StartScanWithModeAsync(targetIds, "list");
                        var msg = AppText.L("AIが未設定のためファイル一覧だけ作成を開始しました。AI検索データは「設定 → AI検索を設定」の完了後に作成できます。", "Started item list scan only because AI is not configured. Build the AI index after completing Settings → Configure AI Search.");
                        ScanStatus.Text = msg;
                        Notice(AppText.L("ファイル一覧の作成を開始しました", "Item list scan started"), msg);
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
                ScanStatus.Text = AppText.L("フォルダを登録しました。「登録フォルダ」の［一覧を作る］からいつでも実行できます。", "Folder registered. Click Scan List in Registered Folders anytime.");
                Notice(AppText.L("フォルダを登録しました", "Folder registered"), ScanStatus.Text);
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
        dialogOpen = true;bool setupRequested=false,autoSetupRequested=false,folderRequested=false,returnToSettings=false;
        try
        {
            var panel = new StackPanel { Spacing = 14, MaxWidth = 600 };
            var greeting = VisualAssets.Sticker(80);
            VisualAssets.State(greeting, "greeting");
            var welcome = new Grid { ColumnSpacing = 12 };
            welcome.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            welcome.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            welcome.Children.Add(greeting);
            var introStack = new StackPanel { Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
            introStack.Children.Add(new TextBlock
            {
                Text = AppText.L("まずはフォルダを追加して、検索と閲覧を始めましょう。AIは後からいつでも設定できます。", "Start by adding a folder to search and browse right away. You can set up AI anytime."),
                Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"],
                TextWrapping = TextWrapping.Wrap
            });
            introStack.Children.Add(new TextBlock
            {
                Text = AppText.L("🔒 元のファイルやフォルダは一切変更・移動・外部送信しません", "🔒 Original files and folders are never modified, moved, or uploaded"),
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
                (AppText.L("① フォルダを追加", "1. Add Folder"), AppText.L("検索したいフォルダを登録し「ファイル一覧を作る」で準備完了", "Register folders and click Scan List to get started")),
                (AppText.L("② 探して開く・整理", "2. Search, View & Organize"), AppText.L("名前・タグで即検索。Spaceや右側の詳細でタグ付け・棚分け", "Instant filename/tag search. Press Space or open Details to tag and organize")),
                (AppText.L("③ AIで探す（任意）", "3. Search with AI (Optional)"), AppText.L("画像の見た目・言葉の意味・動画の場面・音声から横断検索", "Search across visuals, meaning, video scenes, and audio"))
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
            var addFolder = new Button { Content = hasRegistered ? AppText.L("📁 登録フォルダを開く", "📁 Open Registered Folders") : AppText.L("📁 フォルダを追加", "📁 Add Folder"), HorizontalAlignment = HorizontalAlignment.Stretch, Style = (Style)Application.Current.Resources["AccentButtonStyle"] };
            AutomationProperties.SetAutomationId(addFolder, "GuideAddFolder");
            var aiAutoSetup = new Button { Content = AppText.L("✨ AI自動セットアップ", "✨ AI Auto-Setup"), HorizontalAlignment = HorizontalAlignment.Stretch };
            ToolTipService.SetToolTip(aiAutoSetup, AppText.L("NVIDIA GPU（CUDA）または軽量 CPU 版を自動判定して実行環境と EmbeddingGemma 2 を一括導入", "Auto-detects NVIDIA GPU (CUDA) or Lightweight CPU and sets up the runtime + EmbeddingGemma 2"));
            AutomationProperties.SetAutomationId(aiAutoSetup, "GuideAIAutoSetup");
            Button? backToSettings = fromSettings ? new Button { Content = AppText.L("設定へ戻る", "Back to Settings"), HorizontalAlignment = HorizontalAlignment.Stretch } : null;
            if (backToSettings is not null) AutomationProperties.SetAutomationId(backToSettings, "BtnBackToSettings");

            var quickActions = new Grid { ColumnSpacing = 8 };
            quickActions.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            quickActions.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Grid.SetColumn(aiAutoSetup, 1);
            quickActions.Children.Add(addFolder);
            quickActions.Children.Add(aiAutoSetup);
            if (backToSettings is not null)
            {
                quickActions.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                Grid.SetColumn(backToSettings, 2);
                quickActions.Children.Add(backToSettings);
            }
            panel.Children.Add(quickActions);

            var detailsHeader = new TextBlock
            {
                Text = AppText.L("詳しい使い方・ショートカット", "Detailed Guide & Shortcuts"),
                Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"],
                Margin = new Thickness(0, 4, 0, 0)
            };
            panel.Children.Add(detailsHeader);

            foreach (var (index, title, text) in new[]
            {
                (1, AppText.L("1. フォルダの追加と更新方法", "1. Adding & Updating Folders"), AppText.L("左メニューの「登録フォルダ → ＋ フォルダを追加」（またはウィンドウへドラッグ＆ドロップ）から検索したいフォルダを登録します。登録直後に「ファイル一覧を作る（推奨）」または「一覧＋AI検索データ」を選べます。フォルダ内に新しく追加・変更した作品があるときは「⟳ 更新」で再読み込みできます。", "Open Registered Folders → + Add Folder (or drag & drop onto the window). Right after registering, choose \"Fetch item list only\" or \"Fetch list & AI index\". Click ⟳ Refresh whenever you add or change files.")),
                (2, AppText.L("2. 文字検索・閲覧・タグと棚の整理", "2. Text Search, Viewing & Organizing"), AppText.L("検索欄に名前やタグを入力すると即座に絞り込めます（関連語辞書で表記ゆれ・同義語にも対応）。作品のダブルクリックやEnterで内蔵ビューアが開きます。Spaceキーまたは「詳細」ボタンで右側の詳細ペインを開き、タグの追加（Enter確定）・お気に入り・棚への追加（複数選択時も下のバーから一括操作可能）を行えます。", "Type filenames or tags to filter immediately (supports your synonym dictionary too). Double-click or press Enter to open the built-in viewer. Press Space or click Details to edit tags, favorites, and shelves (or use the bottom bar for bulk edits).")),
                (3, AppText.L("3. AI検索の準備とモデルの選び方（任意）", "3. Preparing AI Search (Optional)"), AppText.L("曖昧な言葉や画像の見た目・動画の場面・音声の内容で探したいときは、上の「✨ AI自動セットアップ」（または「AIで探す方法」／「設定 → AI検索」）から準備できます。\n・「AI自動セットアップ」は NVIDIA GPU（CUDA 版）または非 NVIDIA（軽量 CPU 版）を自動判定し、AI実行環境＋検索モデル（EmbeddingGemma 2）を一括取得します。導入・再起動後に「AI検索を設定」からAI検索データを作成すると使えます。\n・すでに手元に環境やモデルがある場合は「AIで探す方法 → 手元のファイルを使う」から指定できます。", "To search by vague phrasing, image appearance, video scenes, or audio, run ✨ AI Auto-Setup above (or open Prepare AI Search / Settings → AI Search).\n• AI Auto-Setup automatically chooses CUDA (NVIDIA GPU) or Lightweight CPU and sets up the runtime + EmbeddingGemma 2. Restart Aredoko, then build AI indexes.\n• If you already have files locally, select them via \"Use Local Files\".")),
                (4, AppText.L("4. 似た作品の検索・AIタグ候補（WD Tagger）", "4. Similarity Search & AI Tag Suggestions"), AppText.L("作品を右クリック（または詳細ペインの「≈ 似た作品」）から、見た目が似た画像・本・動画や音が似た曲を探せます。\n\n【画像タグ付け（WD Tagger）の始め方】\n「設定 → 🏷 タグ付けモデルを取得」（または詳細ペインの「✨ AI候補 → 📥 モデルを取得・設定」）から wd-swinv2-v3（約468MB）をダウンロードすると、基本の実行環境でそのまま動作するため再起動なしですぐ使えます。詳細ペインの「✨ AI候補」または複数選択の「まとめて整理」からタグ候補を生成・一括承認できます（確定タグは自動上書きされません）。", "Right-click an item (or click ≈ Similar in Details) to find visually or sonically similar works.\n\n[Image Tagging (WD Tagger)]\nDownload wd-swinv2-v3 (~468 MB) from Settings → Get Tagging Model (or from ✨ AI Suggestions). It runs on the base runtime and works immediately without restarting. Existing confirmed tags are never overwritten automatically.")),
                (5, AppText.L("5. ショートカット一覧とバックアップ", "5. Shortcuts & Backups"), AppText.L("・Ctrl+F：検索欄へ移動 / Ctrl+S：タグや棚の変更を保存\n・Space：詳細・プレビュー欄を開閉 / Enter：選択した作品を開く\n・Ctrl+Home / Ctrl+End：一覧の先頭・末尾へ移動\n\nタグ・棚・設定の控えの保存と別フォルダへの安全な復元は「設定 → 管理・診断 → 💾 バックアップと復元」で行えます。", "• Ctrl+F: Focus search / Ctrl+S: Save details\n• Space: Toggle details pane / Enter: Open selected item\n• Ctrl+Home / Ctrl+End: Jump to start or end of list\n\nSave live backups and safely restore to a new location via Settings → Management & Diagnostics → Backup & Restore."))
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
            var dialog = new ContentDialog { XamlRoot = XamlRoot, RequestedTheme = ActualTheme, Title = AppText.L("はじめ方・使い方", "Getting Started / How to Use"), Content = scroll, PrimaryButtonText=AppText.L("AIで探す方法", "AI Search Setup"), CloseButtonText = AppText.L("閉じる", "Close"),DefaultButton=ContentDialogButton.None };
            dialog.Resources["ContentDialogMaxWidth"] = 680d;
            AutomationProperties.SetAutomationId(dialog, "GettingStartedGuideDialog");
            addFolder.Click+=(_,_)=>{folderRequested=true;dialog.Hide();};
            aiAutoSetup.Click+=(_,_)=>{autoSetupRequested=true;dialog.Hide();};
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
        else if(autoSetupRequested&&!disposed)await OpenAIAutoEnvironmentDialogAsync(fromSettings:fromSettings);
        else if(setupRequested&&!disposed)await OpenAISetupPlanAsync();
        else if(returnToSettings&&!disposed)await OpenSettingsAsync();
    }
}
