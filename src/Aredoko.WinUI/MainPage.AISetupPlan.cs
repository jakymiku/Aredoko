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
                else if(destination=="existing")await OpenAIEnvironmentDialogAsync();
                else if(destination=="index")await OpenAISettingsAsync();
                else if(destination=="diagnostics")await OpenDiagnosticsDialogAsync();
                else
                {
                    if(destination=="skip")Notice("AIなしで始めます","ファイル名・タグ検索と閲覧を使えます。AIは設定から後で追加できます。");
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
            panel.Children.Add(new TextBlock{Text="使いたい機能を選んでください。AIは任意です。ファイル名・タグ検索と閲覧は、AIを導入しなくても使えます。動画検索は映像、音声・音楽検索は音が対象です。",TextWrapping=TextWrapping.Wrap});
            var summary=new TextBlock{Text="機能を選び、「必要な環境を確認」を押してください。",TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};
            AutomationProperties.SetAutomationId(summary,"AISetupPlanSummary");
            var nextSteps=new TextBlock{TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};AutomationProperties.SetAutomationId(nextSteps,"AISetupNextSteps");
            var recoveryText=new TextBlock{TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};AutomationProperties.SetAutomationId(recoveryText,"AISetupRecoveryText");
            var diagnostics=new Button{Content="診断情報を表示",IsEnabled=false};AutomationProperties.SetAutomationId(diagnostics,"AISetupDiagnostics");
            var recoveryPanel=new StackPanel{Spacing=8};recoveryPanel.Children.Add(recoveryText);recoveryPanel.Children.Add(diagnostics);
            var recovery=new Expander{Header="うまく使えないとき",Content=recoveryPanel,Visibility=Visibility.Collapsed,HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(recovery,"AISetupRecovery");
            var review=new Button{Content="必要な環境を確認"};AutomationProperties.SetAutomationId(review,"ReviewAISetupPlan");
            var download=new Button{Content="モデルの取得候補を見る",IsEnabled=false};AutomationProperties.SetAutomationId(download,"AISetupPlanDownload");
            var existing=new Button{Content="配置済みの環境・モデルを指定",IsEnabled=false};AutomationProperties.SetAutomationId(existing,"AISetupPlanExisting");
            var skip=new Button{Content="今はAIを使わず始める"};AutomationProperties.SetAutomationId(skip,"SkipAISetup");
            var progress=new ProgressBar{IsIndeterminate=true,Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(progress,"AISetupPlanProgress");AutomationProperties.SetName(progress,"AI準備の確認中");
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="使いたいAI機能",PrimaryButtonText="索引・詳細設定へ",CloseButtonText="後で",DefaultButton=ContentDialogButton.None,IsPrimaryButtonEnabled=false};
            AutomationProperties.SetAutomationId(dialog,"AISetupPlanDialog");
            foreach(var (label,index) in new[]{("意味検索",0),("類似画像検索",1),("動画の内容検索",2),("音声・音楽の内容検索",3)})
            {
                var choice=new CheckBox{Content=label,IsChecked=(selected&(1<<index))!=0};
                AutomationProperties.SetAutomationId(choice,"SetupFeature"+AISetupSelection.Features[index]);
                void Changed()
                {
                    selected=choice.IsChecked==true?selected|(1<<index):selected&~(1<<index);
                    version++;request?.Cancel();download.IsEnabled=false;existing.IsEnabled=false;dialog.IsPrimaryButtonEnabled=false;
                    summary.Text="選択を変更しました。「必要な環境を確認」で更新できます。";nextSteps.Text="";
                    recovery.Visibility=Visibility.Collapsed;diagnostics.IsEnabled=false;
                }
                choice.Checked+=(_,_)=>Changed();choice.Unchecked+=(_,_)=>Changed();panel.Children.Add(choice);
            }
            panel.Children.Add(review);panel.Children.Add(progress);panel.Children.Add(summary);
            var actions=new StackPanel{Spacing=8};actions.Children.Add(download);actions.Children.Add(existing);actions.Children.Add(skip);panel.Children.Add(actions);
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
