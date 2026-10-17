using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task IndexBookPagesAsync(MediaRow row)
    {
        if(!ready||disposed||saving||dialogOpen||!ArchiveManifest.CanOpen(row)||!await transitions.WaitAsync(0))return;
        dialogOpen=true;searchTimer.Stop();
        try
        {
            if(aiScope is null)throw new InvalidOperationException(aiScopeError);
            var scope=(JsonObject)aiScope.DeepClone();
            var snapshot=await api.PageEvidences.RefreshIndexAsync(row.Id);
            var initial=await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope);
            if(disposed)return;
            var first=new NumberBox{Header="開始ページ",Minimum=1,Maximum=snapshot.PageCount,Value=1,SmallChange=1};
            var count=new NumberBox{Header=new TextBlock{Text="ページ数（最大16）",TextWrapping=TextWrapping.Wrap},Minimum=1,Maximum=Math.Min(PageImageRequests.MaxPages,snapshot.PageCount),Value=Math.Min(PageImageRequests.MaxPages,snapshot.PageCount),SmallChange=1};
            var start=new Button{Content="選んだページを追加",HorizontalAlignment=HorizontalAlignment.Stretch};
            var next=new Button{Content="次の未準備範囲を選ぶ",HorizontalAlignment=HorizontalAlignment.Stretch};
            var cancel=new Button{Content="処理を中断",IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};
            var progress=new ProgressBar{Minimum=0,Maximum=16,Visibility=Visibility.Collapsed};
            var status=new TextBlock{Text="追加した範囲を「画像の見た目（AI）」で検索できます。",TextWrapping=TextWrapping.Wrap};
            var coverageText=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var rangesText=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var ranges=new Expander{Header="準備済みの範囲",HorizontalAlignment=HorizontalAlignment.Stretch,
                HorizontalContentAlignment=HorizontalAlignment.Stretch,Content=new ScrollViewer{Content=FormScrollContent.Wrap(rangesText),MaxHeight=120,HorizontalScrollMode=ScrollMode.Disabled,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled}};
            var source=new TextBlock{Text=row.Title,TextWrapping=TextWrapping.Wrap};
            var fields=new Grid{ColumnSpacing=12};
            fields.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
            fields.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
            Grid.SetColumn(count,1);fields.Children.Add(first);fields.Children.Add(count);
            AutomationProperties.SetName(first,"開始ページ");AutomationProperties.SetName(count,"ページ数（一度に最大16）");
            var panel=new StackPanel{Spacing=12};panel.Children.Add(ranges);panel.Children.Add(fields);
            var heading=new StackPanel{Spacing=8};heading.Children.Add(source);heading.Children.Add(coverageText);
            var actions=new StackPanel{Spacing=8};
            foreach(var child in new UIElement[]{progress,status,next,start,cancel})actions.Children.Add(child);
            foreach(var(control,id) in new (DependencyObject,string)[]{(first,"PageAIStart"),(count,"PageAICount"),(next,"PageAINextRange"),(start,"PageAIAdd"),(cancel,"PageAICancel"),(status,"PageAIStatus"),(coverageText,"PageAICoverage"),(ranges,"PageAIRanges"),(rangesText,"PageAIRangesText")})AutomationProperties.SetAutomationId(control,id);
            var viewport=new ScrollViewer{Content=FormScrollContent.Wrap(panel),Margin=new Thickness(0,12,0,12),HorizontalScrollMode=ScrollMode.Disabled,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            AutomationProperties.SetAutomationId(viewport,"PageAIFieldsScroll");
            // Keep source state, progress and cancellation outside the scrolling
            // range fields, including while the dialog changes height.
            var content=new Grid{Width=Math.Clamp(XamlRoot.Size.Width-112,240,440),Height=Math.Clamp(XamlRoot.Size.Height-240,260,420)};
            content.RowDefinitions.Add(new(){Height=GridLength.Auto});
            content.RowDefinitions.Add(new(){Height=new GridLength(1,GridUnitType.Star)});
            content.RowDefinitions.Add(new(){Height=GridLength.Auto});
            Grid.SetRow(viewport,1);Grid.SetRow(actions,2);
            content.Children.Add(heading);content.Children.Add(viewport);content.Children.Add(actions);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="本のページをAI検索に追加",Content=content,CloseButtonText="閉じる"};
            AutomationProperties.SetAutomationId(dialog,"PageAIDialog");
            var busy=false;var closeRequested=false;string? job=null;PageImageCoverage? coverage=null;
            void SetActions()
            {
                first.IsEnabled=count.IsEnabled=!busy;
                start.IsEnabled=!busy&&coverage?.CanPrepare==true;
                next.IsEnabled=start.IsEnabled&&coverage?.NextRange is not null;
            }
            void SelectNext()
            {
                if(coverage?.NextRange is not PageImageRange range)return;
                first.Value=range.Start+1;count.Value=range.Count;
            }
            void ApplyCoverage(PageImageCoverage value,bool selectNext)
            {
                coverage=value;coverageText.Text=value.Summary;rangesText.Text=value.RangeSummary;
                ToolTipService.SetToolTip(coverageText,"モデル: "+value.Model);
                if(selectNext)SelectNext();
                SetActions();
            }
            async Task CancelOwned()
            {
                if(job is null)return;
                try{await api.PostAsync("api/library/ai/pages/cancel",new JsonObject{{"job_id",job}});}
                catch(Exception ex){status.Text="中断を確認できません。設定の「AI検索の準備」で処理状況を確認してください。";AppLog.Error(ex);}
            }
            first.ValueChanged+=(_,_)=>
            {
                if(double.IsFinite(first.Value))
                {count.Maximum=Math.Min(PageImageRequests.MaxPages,snapshot.PageCount-(int)first.Value+1);if(count.Value>count.Maximum)count.Value=count.Maximum;}
            };
            next.Click+=(_,_)=>SelectNext();
            cancel.Click+=async(_,_)=>{cancel.IsEnabled=false;await CancelOwned();};
            dialog.Closing+=async(_,args)=>
            {
                if(!busy)return;
                args.Cancel=true;closeRequested=true;cancel.IsEnabled=false;await CancelOwned();
            };
            start.Click+=async(_,_)=>
            {
                if(busy||coverage?.CanPrepare!=true)return;
                if(!double.IsFinite(first.Value)||first.Value!=Math.Truncate(first.Value)||!double.IsFinite(count.Value)||count.Value!=Math.Truncate(count.Value)
                    ||first.Value<1||count.Value<1||count.Value>PageImageRequests.MaxPages||first.Value+count.Value-1>snapshot.PageCount)
                {status.Text="有効なページ範囲を指定してください。";return;}
                busy=true;SetActions();progress.Visibility=Visibility.Visible;progress.Value=0;
                try
                {
                    var selected=await api.PageEvidences.ListPagesAsync(row.Id,(int)first.Value-1,(int)count.Value,snapshot.SourceRevision);
                    if(selected.SourceState!="current"||selected.SourceRevision!=snapshot.SourceRevision||selected.Pages.Count!=(int)count.Value)
                        throw new InvalidOperationException("元ファイルが変わりました。閉じて開き直してください。");
                    if(closeRequested)throw new OperationCanceledException("中断しました。");
                    var result=await api.PostAsync("api/library/ai/pages",PageImageRequests.Create(row.Id,selected.Pages.Select(p=>p.PageId).ToArray(),snapshot.SourceRevision,scope));
                    job=result["job_id"]!.GetValue<string>();cancel.IsEnabled=true;progress.Maximum=count.Value;
                    if(closeRequested)await CancelOwned();
                    while(!disposed)
                    {
                        if(result["job_id"]?.GetValue<string>()!=job)throw new InvalidOperationException("処理状況が変わりました。設定の「AI検索の準備」で確認してください。");
                        var state=result["state"]!.GetValue<string>();progress.Value=result["processed"]!.GetValue<int>();
                        status.Text=state switch
                        {
                            "complete"=>$"追加しました: {result["indexed"]}ページ（再利用 {result["reused"]}）。",
                            "cancelled"=>"中断しました。今回の未完了範囲は保存していません。前回の索引は使えます。",
                            "failed"=>result["error"]!.GetValue<string>(),
                            _=>$"処理中: {result["processed"]}/{result["total"]}ページ"
                        };
                        if(state is not ("running" or "cancelling"))
                        {
                            job=null;
                            ApplyCoverage(await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope,initial.Profile),state=="complete");
                            break;
                        }
                        await Task.Delay(500);result=await api.GetAsync("api/library/ai/status");
                    }
                }
                catch(Exception ex)
                {
                    status.Text=ex.Message;coverage=null;coverageText.Text="準備状況を確認できません。閉じて開き直してください。";
                    rangesText.Text="確認できません。";await CancelOwned();
                }
                finally
                {
                    busy=false;SetActions();cancel.IsEnabled=false;
                    if(closeRequested)dialog.Hide();
                }
            };
            ApplyCoverage(initial,true);
            var xamlRoot=XamlRoot;
            Windows.Foundation.TypedEventHandler<XamlRoot,XamlRootChangedEventArgs> fit=(_,_)=>{content.Width=Math.Clamp(xamlRoot.Size.Width-112,240,440);content.Height=Math.Clamp(xamlRoot.Size.Height-240,260,420);};
            xamlRoot.Changed+=fit;
            try{await dialog.ShowAsync();}finally{xamlRoot.Changed-=fit;}
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();if(PendingSearch&&!disposed)searchTimer.Start();}
    }
}
