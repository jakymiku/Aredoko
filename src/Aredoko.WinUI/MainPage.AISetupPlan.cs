using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async void GettingStartedAIPlan_Click(object sender,RoutedEventArgs args)=>await OpenAISetupPlanAsync();
    private bool aiSetupFlowOpen;
    private async Task OpenAISetupPlanAsync()
    {
        if(aiSetupFlowOpen)return;
        aiSetupFlowOpen=true;
        try
        {
            while(!disposed&&ready)
            {
                var destination=await ShowAISetupPlanStepAsync();
                if(disposed)return;
                if(destination=="download")await OpenAIDownloadDialogAsync();
                else if(destination=="download-tagger")await OpenAIDownloadDialogAsync(preferRole:"tagger");
                else if(destination=="automatic")await OpenAIAutoEnvironmentDialogAsync();
                else if(destination=="existing")await OpenAIEnvironmentDialogAsync();
                else if(destination=="index")await OpenAISettingsAsync();
                else if(destination=="diagnostics")await OpenDiagnosticsDialogAsync();
                else
                {
                    if(destination=="skip")Notice(AppText.L("AIなしで始めます", "Starting without AI"),AppText.L("名前・タグ検索と閲覧が使えます（あとで設定できます）", "Name/tag search and browsing are ready to use (you can set up AI anytime)"));
                    return;
                }
            }
        }
        finally{aiSetupFlowOpen=false;}
    }
    private async Task<string?> ShowAISetupPlanStepAsync()
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return null;
        dialogOpen=true;string? destination=null;
        using var lifetime=new CancellationTokenSource();
        CancellationTokenSource? request=null;
        Task? reviewing=null;
        try
        {
            var selected=AISetupSelection.Normalize(ViewerOptions.Value.AISetupFeatures);long version=0;
            var panel=new StackPanel{Spacing=12,MaxWidth=600};
            var summary=new TextBlock{Text=AppText.L("必要な環境を確認しています…", "Checking requirements..."),TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]};
            AutomationProperties.SetAutomationId(summary,"AISetupPlanSummary");
            var nextSteps=new TextBlock{TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true,Foreground=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"]};AutomationProperties.SetAutomationId(nextSteps,"AISetupNextSteps");
            var recoveryText=new TextBlock{TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};AutomationProperties.SetAutomationId(recoveryText,"AISetupRecoveryText");
            var diagnostics=new Button{Content=AppText.L("診断情報", "Diagnostics"),IsEnabled=false};AutomationProperties.SetAutomationId(diagnostics,"AISetupDiagnostics");
            var recoveryPanel=new StackPanel{Spacing=8};recoveryPanel.Children.Add(recoveryText);recoveryPanel.Children.Add(diagnostics);
            var recovery=new Expander{Header=AppText.L("うまく使えないとき", "Troubleshooting"),Content=recoveryPanel,Visibility=Visibility.Collapsed,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(recovery,"AISetupRecovery");
            var review=new Button{Content=AppText.L("⟳ 再確認", "⟳ Re-check"),Padding=new Thickness(10,4,10,4)};AutomationProperties.SetAutomationId(review,"ReviewAISetupPlan");
            var autoReviewTimer=DispatcherQueue.CreateTimer();autoReviewTimer.Interval=TimeSpan.FromMilliseconds(300);autoReviewTimer.IsRepeating=false;
            var download=new Button{Content=AppText.L("モデルをダウンロード", "Download Model"),IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(download,"AISetupPlanDownload");
            var existing=new Button{Content=AppText.L("手元のファイルを使う", "Use Local Files"),IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(existing,"AISetupPlanExisting");
            var automatic=new Button{Content=AppText.L("自動セットアップ", "Auto-Setup"),HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(automatic,"AISetupPlanAutomatic");
            var skip=new Button{Content=AppText.L("あとで（AIなしで使う）", "Later (Use without AI)"),HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(skip,"SkipAISetup");
            var progress=new ProgressBar{IsIndeterminate=true,Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(progress,"AISetupPlanProgress");AutomationProperties.SetName(progress,AppText.L("AI準備の確認中", "Checking AI setup"));
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("AI検索の準備", "Prepare AI Search"),PrimaryButtonText=AppText.L("次へ", "Next"),CloseButtonText=AppText.L("閉じる", "Close"),DefaultButton=ContentDialogButton.None,IsPrimaryButtonEnabled=false};
            dialog.Resources["ContentDialogMaxWidth"]=680d;
            AutomationProperties.SetAutomationId(dialog,"AISetupPlanDialog");
            var choices=new Grid{ColumnSpacing=8,RowSpacing=8};
            choices.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            choices.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            choices.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});choices.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
            foreach(var (label,description,index) in new[]{
                (AppText.L("ファイル名・タグの意味", "Filename & Tag Meaning"),AppText.L("言い換えや曖昧な言葉で探します。", "Search with synonyms and natural-language phrasing."),0),
                (AppText.L("画像の見た目・類似検索", "Visual & Similarity Search"),AppText.L("画像・表紙・ページの情景や、似た画像を探します。", "Search images, covers, and pages by appearance or visual similarity."),1),
                (AppText.L("動画の内容", "Video Content"),AppText.L("映像の場面や、動画内の音声から探します。", "Search video scenes and spoken audio inside videos."),2),
                (AppText.L("音声・音楽の内容", "Audio & Music Content"),AppText.L("音声ファイルの話題や音の特徴から探します。", "Search audio tracks by topic or acoustic characteristics."),3)})
            {
                var content=new StackPanel{Spacing=2};
                content.Children.Add(new TextBlock{Text=label,TextWrapping=TextWrapping.Wrap,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
                content.Children.Add(new TextBlock{Text=description,TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]});
                var choice=new CheckBox{Content=content,IsChecked=(selected&(1<<index))!=0,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch,VerticalAlignment=VerticalAlignment.Center};
                AutomationProperties.SetAutomationId(choice,"SetupFeature"+AISetupSelection.Features[index]);
                AutomationProperties.SetName(choice,label);AutomationProperties.SetHelpText(choice,description);
                void Changed()
                {
                    selected=choice.IsChecked==true?selected|(1<<index):selected&~(1<<index);
                    version++;request?.Cancel();download.IsEnabled=false;existing.IsEnabled=false;dialog.IsPrimaryButtonEnabled=false;
                    summary.Text=AppText.L("構成を確認しています…", "Checking configuration...");nextSteps.Text="";
                    recovery.Visibility=Visibility.Collapsed;diagnostics.IsEnabled=false;
                    autoReviewTimer.Stop();autoReviewTimer.Start();
                }
                choice.Checked+=(_,_)=>Changed();choice.Unchecked+=(_,_)=>Changed();
                var featureBox=new Border
                {
                    Background=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["SubtleFillColorSecondaryBrush"],
                    BorderBrush=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"],
                    BorderThickness=new Thickness(1),
                    CornerRadius=new CornerRadius(6),
                    Padding=new Thickness(10,8,10,8),
                    Child=choice
                };
                Grid.SetRow(featureBox,index/2);Grid.SetColumn(featureBox,index%2);choices.Children.Add(featureBox);
            }
            var planArt=VisualAssets.Sticker(64);
            VisualAssets.State(planArt,"greeting");
            var step1Header=new Grid{ColumnSpacing=10};
            step1Header.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            step1Header.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            step1Header.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            var step1Heading=new TextBlock{Text=AppText.L("① 何で探したいですか？（名前・タグ検索はAIなしでOK）", "1. How do you want to search? (Name/tag search works without AI)"),Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"],TextWrapping=TextWrapping.Wrap,VerticalAlignment=VerticalAlignment.Center};
            Grid.SetColumn(step1Heading,1);
            Grid.SetColumn(review,2);
            step1Header.Children.Add(planArt);step1Header.Children.Add(step1Heading);step1Header.Children.Add(review);
            var step1Card=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=new StackPanel{Spacing=10,Children={step1Header,choices}}};
            panel.Children.Add(step1Card);

            var miniStatusGrid=new Grid{ColumnSpacing=8,Visibility=Visibility.Collapsed};
            miniStatusGrid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            miniStatusGrid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            var runtimeBadgeText=new TextBlock{Text=AppText.L("確認中…", "Checking..."),Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"],TextWrapping=TextWrapping.Wrap};
            var modelBadgeText=new TextBlock{Text=AppText.L("確認中…", "Checking..."),Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"],TextWrapping=TextWrapping.Wrap};
            foreach(var (col,titleText,valueBlock) in new[]{(0,AppText.L("① AI実行環境", "1. AI Runtime"),runtimeBadgeText),(1,AppText.L("② 検索モデル", "2. Search Model"),modelBadgeText)})
            {
                var card=new Border
                {
                    Background=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["SubtleFillColorSecondaryBrush"],
                    BorderBrush=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"],
                    BorderThickness=new Thickness(1),
                    CornerRadius=new CornerRadius(6),
                    Padding=new Thickness(10,6,10,6),
                    Child=new StackPanel
                    {
                        Spacing=2,
                        Children=
                        {
                            new TextBlock{Text=titleText,Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"],Foreground=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["TextFillColorSecondaryBrush"]},
                            valueBlock
                        }
                    }
                };
                Grid.SetColumn(card,col);miniStatusGrid.Children.Add(card);
            }
            var divider=new Border{Height=1,Background=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"],Margin=new Thickness(0,2,0,2)};
            var statusBox=new Border
            {
                Background=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["SubtleFillColorSecondaryBrush"],
                CornerRadius=new CornerRadius(6),
                Padding=new Thickness(12,10,12,10),
                Child=new StackPanel{Spacing=8,Children={summary,divider,nextSteps}}
            };
            var actionsGrid=new Grid{ColumnSpacing=8,RowSpacing=8};
            actionsGrid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            actionsGrid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            actionsGrid.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
            actionsGrid.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
            Grid.SetRow(automatic,0);Grid.SetColumn(automatic,0);actionsGrid.Children.Add(automatic);
            Grid.SetRow(download,0);Grid.SetColumn(download,1);actionsGrid.Children.Add(download);
            Grid.SetRow(existing,1);Grid.SetColumn(existing,0);actionsGrid.Children.Add(existing);
            Grid.SetRow(skip,1);Grid.SetColumn(skip,1);actionsGrid.Children.Add(skip);
            var step2Card=new Border
            {
                Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],
                Child=new StackPanel
                {
                    Spacing=10,
                    Children=
                    {
                        new TextBlock{Text=AppText.L("② 現在の準備状況とセットアップ", "2. Current Status & Setup"),Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]},
                        progress,
                        miniStatusGrid,
                        statusBox,
                        actionsGrid
                    }
                }
            };
            panel.Children.Add(step2Card);
            var taggerBtn=new Button{Content=AppText.L("🏷 タグ付けモデルを取得・設定", "🏷 Get / Configure Tagger Model"),HorizontalAlignment=HorizontalAlignment.Left};
            AutomationProperties.SetAutomationId(taggerBtn,"AISetupPlanTaggerDownload");
            var step3Card=new Border
            {
                Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],
                Child=new StackPanel
                {
                    Spacing=8,
                    Children=
                    {
                        new TextBlock{Text=AppText.L("③ 画像の自動タグ候補（WD Tagger・任意）", "3. Automatic Tag Suggestions (WD Tagger · Optional)"),Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"],TextWrapping=TextWrapping.Wrap},
                        new TextBlock{Text=AppText.L("画像や本の表紙からタグ候補（キャラクター・一般タグ）を自動提案します。基本の実行環境で動作するため、AI検索環境が未導入でもモデル（約468MB）を取得するだけですぐに使えます。", "Suggests character and general tags from images and book covers. Runs on the base runtime, so just downloading the ~468 MB model makes it ready even without full AI search setup."),TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]},
                        taggerBtn
                    }
                }
            };
            panel.Children.Add(step3Card);
            panel.Children.Add(recovery);
            dialog.Content=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),Padding=new Thickness(0,0,16,0),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            async Task ReviewAsync()
            {
                autoReviewTimer.Stop();
                request?.Cancel();
                var expected=++version;request?.Dispose();request=CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                var cancellation=request;
                review.IsEnabled=false;progress.Visibility=Visibility.Visible;
                miniStatusGrid.Visibility=Visibility.Collapsed;divider.Visibility=Visibility.Collapsed;
                download.IsEnabled=false;existing.IsEnabled=false;dialog.IsPrimaryButtonEnabled=false;diagnostics.IsEnabled=false;recovery.Visibility=Visibility.Collapsed;nextSteps.Text="";
                try
                {
                    var selection=selected;
                    var plan=await api.AISetupPlans.CreateAsync(selection,cancellation.Token);
                    AIDownloadJob? downloadJob=null;AIEnvironmentJob? environmentJob=null;IReadOnlyList<AIDownloadCatalog>? catalogs=null;
                    if(!plan.SkipAI)
                    {
                        var acquisition=api.AIDownloads.JobAsync(cancellation.Token);var placement=api.AIEnvironment.JobAsync(cancellation.Token);
                        var catalogTask=api.AIDownloads.CatalogsAsync(cancellation.Token);
                        await Task.WhenAll(acquisition,placement,catalogTask);
                        downloadJob=await acquisition;environmentJob=await placement;catalogs=await catalogTask;
                    }
                    if(lifetime.IsCancellationRequested||expected!=version)return;
                    if(downloadJob?.Published==true&&catalogs is not null&&catalogs.FirstOrDefault(c=>c.Id==downloadJob.CatalogId)?.ModelTarget?.Role=="tagger")
                        downloadJob=null;
                    var runtimeReq=plan.Requirements.FirstOrDefault(r=>r.Id=="embedding-runtime");
                    var modelReq=plan.Requirements.FirstOrDefault(r=>r.Id=="embedding-model");
                    miniStatusGrid.Visibility=plan.SkipAI||runtimeReq is null||modelReq is null?Visibility.Collapsed:Visibility.Visible;
                    if(runtimeReq is not null)runtimeBadgeText.Text=runtimeReq.FilesPresent?AppText.L("✓ 配置済み", "✓ Installed"):AppText.L("⚠ 要導入", "⚠ Needed");
                    if(modelReq is not null)modelBadgeText.Text=modelReq.FilesPresent?AppText.L("✓ 配置済み", "✓ Installed"):AppText.L("⚠ 要導入", "⚠ Needed");
                    divider.Visibility=Visibility.Visible;
                    summary.Text=plan.Summary;
                    nextSteps.Text=AISetupGuidance.Describe(plan,selection,downloadJob,environmentJob);
                    divider.Visibility=string.IsNullOrWhiteSpace(nextSteps.Text)?Visibility.Collapsed:Visibility.Visible;
                    recoveryText.Text=AISetupRecovery.Describe(plan);recovery.Visibility=plan.SkipAI?Visibility.Collapsed:Visibility.Visible;diagnostics.IsEnabled=!plan.SkipAI;
                    automatic.Content=plan.SkipAI?AppText.L("自動セットアップ", "Auto-Setup"):plan.AutomaticSetupSupported?AppText.L("自動セットアップ", "Auto-Setup"):AppText.L("自動セットアップ（このモデルは非対応）", "Auto-Setup (unsupported for this model)");
                    var allPresent=!plan.SkipAI&&plan.Requirements.Count>0&&plan.Requirements.All(row=>row.FilesPresent);
                    var accent=Application.Current.Resources["AccentButtonStyle"] as Style;
                    var defaultButton=Application.Current.Resources["DefaultButtonStyle"] as Style;
                    automatic.Style=!plan.SkipAI&&plan.AutomaticSetupSupported&&!allPresent?accent:defaultButton;
                    existing.IsEnabled=!plan.SkipAI;
                    download.IsEnabled=!plan.ProfileRestartRequired&&!plan.ProfileSelectionInvalid&&plan.Requirements.Any(row=>row.Id=="embedding-model"&&!row.FilesPresent&&row.CatalogIds.Count>0);
                    dialog.PrimaryButtonText=allPresent?AppText.L("AI検索の設定へ →", "Configure AI Search →"):AppText.L("次へ", "Next");
                    dialog.IsPrimaryButtonEnabled=!plan.SkipAI;
                }
                catch(OperationCanceledException)when(cancellation.IsCancellationRequested){}
                catch(Exception ex){if(!lifetime.IsCancellationRequested&&expected==version){miniStatusGrid.Visibility=Visibility.Collapsed;divider.Visibility=Visibility.Collapsed;summary.Text=AppText.L("確認できませんでした。基本機能はそのまま使えます。\n", "Unable to verify status. Standard search remains usable.\n")+ex.Message;}}
                finally{if(!lifetime.IsCancellationRequested&&expected==version){review.IsEnabled=true;progress.Visibility=Visibility.Collapsed;}}
            }
            autoReviewTimer.Tick+=(_,_)=>{if(!lifetime.IsCancellationRequested&&!disposed)reviewing=ReviewAsync();};
            review.Click+=async(_,_)=>{reviewing=ReviewAsync();await reviewing;};
            dialog.Opened+=(_,_)=>{reviewing=ReviewAsync();};
            void MoveTo(string target,int? selection=null)
            {
                try{ViewerOptions.SaveAISetupFeatures(selection??selected);destination=target;dialog.Hide();}
                catch(Exception ex){summary.Text=AppText.L("選択を保存できませんでした。\n", "Could not save selection.\n")+ex.Message;}
            }
            download.Click+=(_,_)=>MoveTo("download");existing.Click+=(_,_)=>MoveTo("existing");
            taggerBtn.Click+=(_,_)=>MoveTo("download-tagger");
            automatic.Click+=(_,_)=>MoveTo("automatic");
            diagnostics.Click+=(_,_)=>MoveTo("diagnostics");
            skip.Click+=(_,_)=>MoveTo("skip",0);
            dialog.PrimaryButtonClick+=(_,args)=>
            {
                try{ViewerOptions.SaveAISetupFeatures(selected);destination="index";}
                catch(Exception ex){args.Cancel=true;summary.Text=AppText.L("選択を保存できませんでした。\n", "Could not save selection.\n")+ex.Message;}
            };
            var closed=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed+=(_,_)=>{autoReviewTimer.Stop();lifetime.Cancel();closed.TrySetResult(true);};
            await dialog.ShowAsync();autoReviewTimer.Stop();await Task.WhenAny(closed.Task,Task.Delay(500));
            if(destination is null&&!disposed)ViewerOptions.SaveAISetupFeatures(selected);
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{lifetime.Cancel();if(reviewing is not null)await reviewing;request?.Dispose();dialogOpen=false;transitions.Release();}
        return destination;
    }
}
