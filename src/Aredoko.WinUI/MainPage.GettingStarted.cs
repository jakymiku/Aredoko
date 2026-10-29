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
            if (GettingStartedStep1Text is not null)
                GettingStartedStep1Text.Text = hasFolder ? $"1. フォルダを追加: 完了（{activeRoots.Length} フォルダ登録済み）" : "1. フォルダを追加: 未登録（次の手順）";
            if (GettingStartedStep2Text is not null)
                GettingStartedStep2Text.Text = hasList ? "2. 一覧を読み込む: 完了" : (hasFolder ? "2. 一覧を読み込む: 未スキャン（次の手順）" : "2. 一覧を読み込む: 未スキャン");
            if (GettingStartedStep3Text is not null)
                GettingStartedStep3Text.Text = aiIndexReady ? "3. 必要ならAIを準備（任意）: 準備完了" : "3. 必要ならAIを準備（任意）: 任意 — ファイル名・タグ検索と閲覧はAIなしで使えます";
            if (GettingStartedFolders is not null)
                GettingStartedFolders.Content = hasFolder ? "登録フォルダをスキャンして一覧を読み込む" : "フォルダを登録する";
        }
        else if (gettingStartedDismissed && rows.Count == 0 && !hasList && view == "all" && string.IsNullOrWhiteSpace(Query.Text) && Kind.SelectedIndex == 0 && selectedSearchRoots is null && selectedShelfIds is null && similarityOrigin is null)
        {
            Empty.Visibility = Visibility.Visible;
            Empty.Text = "フォルダ管理や設定から、フォルダの登録・スキャンをいつでも実行できます。";
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
                        new TextBlock { Text = "アイテム一覧だけ取得（推奨）", Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = "ファイル名・タグ検索と閲覧がすぐ使えます。AI処理は起動しません。", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
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
                        new TextBlock { Text = "一覧取得＋AI索引を作成", Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = "一覧取得の成功後、新規・変更分に現在のモデル・範囲設定でAI索引を作成します（タグ候補の自動承認はしません）。", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
                    }
                }
            };
            AutomationProperties.SetAutomationId(choiceListAndAI, "ScanChoiceListAndAI");
            panel.Children.Add(choiceListAndAI);

            var choiceLater = new RadioButton
            {
                GroupName = "PostRegScanChoice",
                Content = new StackPanel
                {
                    Spacing = 2,
                    Children =
                    {
                        new TextBlock { Text = "後で", Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] },
                        new TextBlock { Text = "登録だけ保持します。「登録フォルダ → 対象フォルダの設定 → スキャン」から実行できます。", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"], Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"], TextWrapping = TextWrapping.Wrap }
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
                                Text = "AI未準備: " + aiReason + " 選択しただけでモデル取得や環境導入は始まりません。",
                                TextWrapping = TextWrapping.Wrap,
                                Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"]
                            },
                            new Button
                            {
                                Content = "AI検索の準備を開く",
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
                Title = "登録したフォルダをスキャンしますか？",
                Content = scroll,
                PrimaryButtonText = "実行",
                CloseButtonText = "後で",
                DefaultButton = ContentDialogButton.Primary
            };
            currentDialog = dialog;
            AutomationProperties.SetAutomationId(dialog, "PostRegistrationScanDialog");

            var result = await dialog.ShowAsync();

            if (openAiSetupRequested)
            {
                ScanStatus.Text = "登録しました。AIの準備後にスキャンを実行してください。";
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
                        var msg = "AIが未準備のためアイテム一覧のみスキャンを開始しました。AI索引は「AI検索の準備」完了後に実行できます。";
                        ScanStatus.Text = msg;
                        Notice("一覧スキャンを開始しました", msg);
                    }
                    else
                    {
                        await StartScanWithModeAsync(targetIds, "list_and_ai");
                    }
                }
                else if (choiceListOnly.IsChecked == true)
                {
                    await StartScanWithModeAsync(targetIds, "list");
                }
                else
                {
                    ScanStatus.Text = "登録しました。「登録フォルダ → 対象フォルダの設定 → スキャン」から実行できます。";
                    Notice("フォルダを登録しました", ScanStatus.Text);
                }
            }
            else
            {
                ScanStatus.Text = "登録しました。「登録フォルダ → 対象フォルダの設定 → スキャン」から実行できます。";
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

    private async Task OpenGettingStartedGuideAsync()
    {
        if (!ready || disposed || dialogOpen || saving || !await transitions.WaitAsync(0)) return;
        dialogOpen = true;bool setupRequested=false,folderRequested=false;
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
            var introduction=new TextBlock{Text="まずはフォルダを登録して、検索と閲覧を始めましょう。AIは後から追加できます。",TextWrapping=TextWrapping.Wrap,VerticalAlignment=VerticalAlignment.Center};
            Grid.SetColumn(introduction,1);welcome.Children.Add(introduction);panel.Children.Add(welcome);
            foreach(var (title,text) in new[]{
                ("1. フォルダを追加", "検索したいフォルダを選び、登録後は「アイテム一覧だけ取得」で始められます。元ファイルは変更しません。"),
                ("2. 検索・閲覧・整理", "ファイル名・タグで検索し、ダブルクリックで開きます。タグや棚の編集は「詳細」から行えます。"),
                ("3. 必要ならAIを準備", "情景や音の内容から探したい場合は、下の「使いたいAI機能から準備」へ。モデル・実行環境・索引が必要です。")})
            {
                var step=new StackPanel{Spacing=4};
                step.Children.Add(new TextBlock{Text=title,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
                step.Children.Add(new TextBlock{Text=text,TextWrapping=TextWrapping.Wrap});panel.Children.Add(step);
            }
            var addFolder=new Button{Content="フォルダの登録へ",HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(addFolder,"GuideAddFolder");panel.Children.Add(addFolder);
            var details=new StackPanel{Spacing=12};
            foreach (var (title, text) in new[]
            {
                ("1. フォルダを登録する", "「登録フォルダ」→「フォルダを追加」から検索したい場所を選びます。サブフォルダを含めるかも選べます。登録成功時に「アイテム一覧だけ取得（推奨）」「一覧取得＋AI索引を作成」「後で」を選択できます。「後で」を選んだ場合も「登録フォルダ → 対象フォルダの設定 → スキャン」からいつでも実行できます。元ファイルは移動・変換しません。"),
                ("2. 検索して開く", "検索欄にファイル名やタグを入力します。画像・本・動画・音声はダブルクリックで開けます。設定で内蔵ビューアとWindowsの既定アプリを選べます。右クリックからエクスプローラーでも開けます。"),
                ("3. AI検索を準備する（任意）", "下の「使いたいAI機能から準備」で用途を選び、必要なモデルと実行環境を確認します。取得前に容量とライセンスを確認でき、AIなしで始めることもできます。実行環境の自動取得は準備中のため、現在は配置済みの環境を指定します。変更後は再起動し、「AI検索の準備」で索引を作ります。動画・音声はそれぞれの内容検索欄から作成してください。WD Taggerの画像タグ候補は任意です。"),
                ("4. 内容から探す・整理する", "準備後は「画像の見た目」などのAI検索方法で、覚えている情景や特徴を入力します。右側の詳細でタグや棚を編集できます。タグ・棚は保存ボタンで保存し、お気に入りはすぐ反映します。AIタグは候補を確認してから承認します。"),
                ("閲覧・データ保護", "一覧ではCtrl+Homeで検索結果の先頭、Ctrl+Endで末尾へ移動できます。画像や本は左右キー・ホイール・マウスの進む／戻るで送れます。ホイール方向やテーマは設定で、小さい画像の拡大・操作バーの常時表示・ページのループ移動はビューアの設定メニューで変更できます。バックアップと復元も設定から実行できます。フォルダ解除や棚の削除で元メディアは削除しません。"),
            })
            {
                details.Children.Add(new TextBlock { Text = title, Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"], TextWrapping = TextWrapping.Wrap });
                details.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true });
            }
            var more=new Expander{Header="詳しい手順・操作とデータ保護",Content=details,HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(more,"GuideDetails");panel.Children.Add(more);
            var scroll = new ScrollViewer { Content = panel, MaxHeight = Math.Max(160, ActualHeight - 240), VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Padding = new Thickness(0, 0, 16, 0) };
            var dialog = new ContentDialog { XamlRoot = XamlRoot, RequestedTheme = ActualTheme, Title = "使い方・初回設定", Content = scroll, PrimaryButtonText="使いたいAI機能から準備", CloseButtonText = "閉じる",DefaultButton=ContentDialogButton.None };
            AutomationProperties.SetAutomationId(dialog, "GettingStartedGuideDialog");
            addFolder.Click+=(_,_)=>{folderRequested=true;dialog.Hide();};
            setupRequested=await dialog.ShowAsync()==ContentDialogResult.Primary;
        }
        catch (Exception error) { Failure(error); }
        finally { dialogOpen = false; transitions.Release(); }
        if(folderRequested&&!disposed)
        {
            await OpenFolderHubAsync();
            if(folderHubOpen)FolderAddPanel.Visibility=Visibility.Visible;
        }
        else if(setupRequested&&!disposed)await OpenAISetupPlanAsync();
    }
}
