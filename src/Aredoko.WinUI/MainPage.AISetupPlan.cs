using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async void GettingStartedAIPlan_Click(object sender,RoutedEventArgs args)=>await OpenAISetupPlanAsync();
    private async Task OpenAISetupPlanAsync()
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;string? destination=null;
        using var lifetime=new CancellationTokenSource();
        CancellationTokenSource? request=null;
        try
        {
            var selected=AISetupSelection.Normalize(ViewerOptions.Value.AISetupFeatures);long version=0;
            var panel=new StackPanel{Spacing=12};
            panel.Children.Add(new TextBlock{Text="使いたい機能を選んでください。AIは任意です。ファイル名・タグ検索と閲覧は、AIを導入しなくても使えます。",TextWrapping=TextWrapping.Wrap});
            var summary=new TextBlock{Text="機能を選び、「必要な環境を確認」を押してください。",TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true};
            AutomationProperties.SetAutomationId(summary,"AISetupPlanSummary");
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
                    summary.Text="選択を変更しました。「必要な環境を確認」で更新できます。";
                }
                choice.Checked+=(_,_)=>Changed();choice.Unchecked+=(_,_)=>Changed();panel.Children.Add(choice);
            }
            panel.Children.Add(review);panel.Children.Add(progress);panel.Children.Add(summary);
            var actions=new StackPanel{Spacing=8};actions.Children.Add(download);actions.Children.Add(existing);actions.Children.Add(skip);panel.Children.Add(actions);
            dialog.Content=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),Padding=new Thickness(0,0,16,0),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            review.Click+=async(_,_)=>
            {
                if(!review.IsEnabled)return;
                var expected=++version;request?.Dispose();request=CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                review.IsEnabled=false;progress.Visibility=Visibility.Visible;
                try
                {
                    var plan=await api.AISetupPlans.CreateAsync(selected,request.Token);
                    if(lifetime.IsCancellationRequested||expected!=version)return;
                    summary.Text=plan.Summary;
                    existing.IsEnabled=!plan.SkipAI;
                    download.IsEnabled=plan.Requirements.Any(row=>row.Id=="embedding-model"&&!row.FilesPresent&&row.CatalogIds.Count>0);
                    dialog.IsPrimaryButtonEnabled=!plan.SkipAI;
                }
                catch(OperationCanceledException)when(request.IsCancellationRequested){}
                catch(Exception ex){if(!lifetime.IsCancellationRequested&&expected==version)summary.Text="確認できませんでした。基本機能はそのまま使えます。\n"+ex.Message;}
                finally{if(!lifetime.IsCancellationRequested){review.IsEnabled=true;progress.Visibility=Visibility.Collapsed;}}
            };
            void MoveTo(string target,int? selection=null)
            {
                try{ViewerOptions.SaveAISetupFeatures(selection??selected);destination=target;dialog.Hide();}
                catch(Exception ex){summary.Text="選択を保存できませんでした。\n"+ex.Message;}
            }
            download.Click+=(_,_)=>MoveTo("download");existing.Click+=(_,_)=>MoveTo("existing");
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
        finally{lifetime.Cancel();request?.Dispose();dialogOpen=false;transitions.Release();}
        if(disposed)return;
        if(destination=="download")await OpenAIDownloadDialogAsync();
        else if(destination=="existing")await OpenAIEnvironmentDialogAsync();
        else if(destination=="index")AI_Click(this,new RoutedEventArgs());
        else if(destination=="skip")Notice("AIなしで始めます","ファイル名・タグ検索と閲覧を使えます。AIは設定から後で追加できます。");
    }
}
