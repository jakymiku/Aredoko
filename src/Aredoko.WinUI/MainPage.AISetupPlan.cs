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
            bool refresh=false;
            while(!disposed&&ready)
            {
                var destination=await ShowAISetupPlanStepAsync(refresh);
                if(disposed)return;
                if(destination=="download")await OpenAIDownloadDialogAsync();
                else if(destination=="automatic")await OpenAIAutoEnvironmentDialogAsync();
                else if(destination=="existing")await OpenAIEnvironmentDialogAsync();
                else if(destination=="index")await OpenAISettingsAsync();
                else if(destination=="diagnostics")await OpenDiagnosticsDialogAsync();
                else
                {
                    if(destination=="skip")Notice("AIなしで始めます","名前・タグ検索と閲覧が使えます（あとで設定できます）");
                    return;
                }
                refresh=true;
            }
        }
        finally{aiSetupFlowOpen=false;}
    }
    private async Task<string?> ShowAISetupPlanStepAsync(bool refreshOnOpen)
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return null;
        dialogOpen=true;string? destination=null;
        using var lifetime=new CancellationTokenSource();
        CancellationTokenSource? request=null;
        Task? reviewing=null;
        try
        {
            var selected=AISetupSelection.Normalize(ViewerOptions.Value.AISetupFeatures);long version=0;
            var panel=new StackPanel{Spacing=12};
            panel.Children.Add(new TextBlock{Text="何で探したいですか？（名前・タグ検索はAIなしでOK）",TextWrapping=TextWrapping.Wrap});
            var summary=new TextBlock{Text="使いたい機能を選んで「必要なものを確認」を押してください",TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};
            AutomationProperties.SetAutomationId(summary,"AISetupPlanSummary");
            var nextSteps=new TextBlock{TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};AutomationProperties.SetAutomationId(nextSteps,"AISetupNextSteps");
            var recoveryText=new TextBlock{TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};AutomationProperties.SetAutomationId(recoveryText,"AISetupRecoveryText");
            var diagnostics=new Button{Content="診断情報",IsEnabled=false};AutomationProperties.SetAutomationId(diagnostics,"AISetupDiagnostics");
            var recoveryPanel=new StackPanel{Spacing=8};recoveryPanel.Children.Add(recoveryText);recoveryPanel.Children.Add(diagnostics);
            var recovery=new Expander{Header="うまく使えないとき",Content=recoveryPanel,Visibility=Visibility.Collapsed,HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(recovery,"AISetupRecovery");
            var review=new Button{Content="必要なものを確認"};AutomationProperties.SetAutomationId(review,"ReviewAISetupPlan");
            var download=new Button{Content="モデルをダウンロード",IsEnabled=false};AutomationProperties.SetAutomationId(download,"AISetupPlanDownload");
            var existing=new Button{Content="手元のファイルを使う",IsEnabled=false};AutomationProperties.SetAutomationId(existing,"AISetupPlanExisting");
            var automatic=new Button{Content="自動セットアップ"};AutomationProperties.SetAutomationId(automatic,"AISetupPlanAutomatic");
            var skip=new Button{Content="あとで"};AutomationProperties.SetAutomationId(skip,"SkipAISetup");
            var progress=new ProgressBar{IsIndeterminate=true,Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(progress,"AISetupPlanProgress");AutomationProperties.SetName(progress,"AI準備の確認中");
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AI検索の準備",PrimaryButtonText="次へ",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,IsPrimaryButtonEnabled=false};
            AutomationProperties.SetAutomationId(dialog,"AISetupPlanDialog");
            var choices=new Grid{ColumnSpacing=12,RowSpacing=8};
            choices.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            choices.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            choices.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});choices.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
            foreach(var (label,description,index) in new[]{
                ("ファイル名・タグの意味","言い換えや曖昧な言葉で探します。",0),
                ("画像の見た目・類似検索","画像・表紙・ページの情景や、似た画像を探します。",1),
                ("動画の内容","映像の場面や、動画内の音声から探します。",2),
                ("音声・音楽の内容","音声ファイルの話題や音の特徴から探します。",3)})
            {
                var content=new StackPanel{Spacing=4};
                content.Children.Add(new TextBlock{Text=label,TextWrapping=TextWrapping.Wrap,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
                content.Children.Add(new TextBlock{Text=description,TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]});
                var choice=new CheckBox{Content=content,IsChecked=(selected&(1<<index))!=0,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch,VerticalAlignment=VerticalAlignment.Top};
                AutomationProperties.SetAutomationId(choice,"SetupFeature"+AISetupSelection.Features[index]);
                AutomationProperties.SetName(choice,label);AutomationProperties.SetHelpText(choice,description);
                void Changed()
                {
                    selected=choice.IsChecked==true?selected|(1<<index):selected&~(1<<index);
                    version++;request?.Cancel();download.IsEnabled=false;existing.IsEnabled=false;dialog.IsPrimaryButtonEnabled=false;
                    summary.Text="選択を変更しました。「必要なものを確認」を押すと最新状態を確認できます。";nextSteps.Text="";
                    recovery.Visibility=Visibility.Collapsed;diagnostics.IsEnabled=false;
                }
                choice.Checked+=(_,_)=>Changed();choice.Unchecked+=(_,_)=>Changed();
                Grid.SetRow(choice,index/2);Grid.SetColumn(choice,index%2);choices.Children.Add(choice);
            }
            panel.Children.Add(choices);panel.Children.Add(review);panel.Children.Add(progress);panel.Children.Add(summary);
            var actions=new StackPanel{Spacing=8};actions.Children.Add(automatic);actions.Children.Add(download);actions.Children.Add(existing);actions.Children.Add(skip);panel.Children.Add(actions);
            panel.Children.Add(nextSteps);panel.Children.Add(recovery);
            dialog.Content=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),Padding=new Thickness(0,0,16,0),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            async Task ReviewAsync()
            {
                if(!review.IsEnabled)return;
                var expected=++version;request?.Dispose();request=CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                var cancellation=request;
                review.IsEnabled=false;progress.Visibility=Visibility.Visible;
                download.IsEnabled=false;existing.IsEnabled=false;dialog.IsPrimaryButtonEnabled=false;diagnostics.IsEnabled=false;recovery.Visibility=Visibility.Collapsed;nextSteps.Text="";
                try
                {
                    var selection=selected;
                    var plan=await api.AISetupPlans.CreateAsync(selection,cancellation.Token);
                    AIDownloadJob? downloadJob=null;AIEnvironmentJob? environmentJob=null;
                    if(!plan.SkipAI)
                    {
                        var acquisition=api.AIDownloads.JobAsync(cancellation.Token);var placement=api.AIEnvironment.JobAsync(cancellation.Token);
                        await Task.WhenAll(acquisition,placement);downloadJob=await acquisition;environmentJob=await placement;
                    }
                    if(lifetime.IsCancellationRequested||expected!=version)return;
                    summary.Text=plan.Summary;
                    nextSteps.Text=AISetupGuidance.Describe(plan,selection,downloadJob,environmentJob);
                    recoveryText.Text=AISetupRecovery.Describe(plan);recovery.Visibility=plan.SkipAI?Visibility.Collapsed:Visibility.Visible;diagnostics.IsEnabled=!plan.SkipAI;
                    automatic.Content=plan.SkipAI?"自動セットアップ":plan.AutomaticSetupSupported?"自動セットアップ":"自動セットアップ（このモデルは非対応）";
                    existing.IsEnabled=!plan.SkipAI;
                    download.IsEnabled=!plan.ProfileRestartRequired&&!plan.ProfileSelectionInvalid&&plan.Requirements.Any(row=>row.Id=="embedding-model"&&!row.FilesPresent&&row.CatalogIds.Count>0);
                    dialog.IsPrimaryButtonEnabled=!plan.SkipAI;
                }
                catch(OperationCanceledException)when(cancellation.IsCancellationRequested){}
                catch(Exception ex){if(!lifetime.IsCancellationRequested&&expected==version)summary.Text="確認できませんでした。基本機能はそのまま使えます。\n"+ex.Message;}
                finally{if(!lifetime.IsCancellationRequested){review.IsEnabled=true;progress.Visibility=Visibility.Collapsed;}}
            }
            review.Click+=async(_,_)=>{reviewing=ReviewAsync();await reviewing;};
            dialog.Opened+=(_,_)=>{if(refreshOnOpen)reviewing=ReviewAsync();};
            void MoveTo(string target,int? selection=null)
            {
                try{ViewerOptions.SaveAISetupFeatures(selection??selected);destination=target;dialog.Hide();}
                catch(Exception ex){summary.Text="選択を保存できませんでした。\n"+ex.Message;}
            }
            download.Click+=(_,_)=>MoveTo("download");existing.Click+=(_,_)=>MoveTo("existing");
            automatic.Click+=(_,_)=>MoveTo("automatic");
            diagnostics.Click+=(_,_)=>MoveTo("diagnostics");
            skip.Click+=(_,_)=>MoveTo("skip",0);
            dialog.PrimaryButtonClick+=(_,args)=>
            {
                try{ViewerOptions.SaveAISetupFeatures(selected);destination="index";}
                catch(Exception ex){args.Cancel=true;summary.Text="選択を保存できませんでした。\n"+ex.Message;}
            };
            var closed=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed+=(_,_)=>{lifetime.Cancel();closed.TrySetResult(true);};
            await dialog.ShowAsync();await Task.WhenAny(closed.Task,Task.Delay(500));
            if(destination is null&&!disposed)ViewerOptions.SaveAISetupFeatures(selected);
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{lifetime.Cancel();if(reviewing is not null)await reviewing;request?.Dispose();dialogOpen=false;transitions.Release();}
        return destination;
    }
}
