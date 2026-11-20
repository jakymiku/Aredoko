using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task IndexBookAllPagesDirectAsync(MediaRow row)
    {
        if(!ready||disposed||saving||dialogOpen||!ArchiveManifest.CanOpen(row)||!await transitions.WaitAsync(0))return;
        searchTimer?.Stop();
        if(aiScope is null){transitions.Release();Failure(new InvalidOperationException(aiScopeError));return;}
        var proceed=false;
        var autoAll=false;
        try
        {
            dialogOpen=true;
            var scope=(JsonObject)aiScope.DeepClone();
            var snapshot=await api.PageEvidences.RefreshIndexAsync(row.Id);
            var initial=await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope);
            if(disposed)return;
            if(!initial.CanPrepare||initial.RemainingPages==0)
            {
                proceed=true;autoAll=false;
            }
            else if(PageChunkRequests.NeedsLargeBookWarning(snapshot.PageCount))
            {
                var confirm=new ContentDialog
                {
                    XamlRoot=XamlRoot,
                    RequestedTheme=ActualTheme,
                    Title="全ページのAI登録の確認",
                    Content=new TextBlock{Text=PageChunkRequests.LargeBookWarningMessage(row.Title,snapshot.PageCount,initial.RemainingPages),TextWrapping=TextWrapping.Wrap},
                    PrimaryButtonText="全ページを登録する",
                    CloseButtonText="キャンセル",
                    DefaultButton=ContentDialogButton.Primary
                };
                AutomationProperties.SetAutomationId(confirm,"LargeBookAIWarningDialog");
                var choice=await confirm.ShowAsync();
                if(choice==ContentDialogResult.Primary){proceed=true;autoAll=true;}
            }
            else
            {
                proceed=true;autoAll=true;
            }
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();}
        if(proceed&&!disposed)await IndexBookPagesAsync(row,autoStartAll:autoAll);
    }

    private async Task IndexBookPagesAsync(MediaRow row,bool autoStartAll=false)
    {
        if(!ready||disposed||saving||dialogOpen||!ArchiveManifest.CanOpen(row)||!await transitions.WaitAsync(0))return;
        dialogOpen=true;searchTimer?.Stop();
        try
        {
            if(aiScope is null)throw new InvalidOperationException(aiScopeError);
            var scope=(JsonObject)aiScope.DeepClone();
            var snapshot=await api.PageEvidences.RefreshIndexAsync(row.Id);
            var initial=await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope);
            if(disposed)return;
            var mode=new ComboBox{Header="追加する範囲",HorizontalAlignment=HorizontalAlignment.Stretch};
            foreach(var(label,id) in new[]{("ページを指定（最大16）","PageAIManual"),("未準備ページをまとめて（最大128）","PageAIChunked")})
            {var option=new ComboBoxItem{Content=label};AutomationProperties.SetAutomationId(option,id);mode.Items.Add(option);}
            mode.SelectedIndex=0;
            var first=new NumberBox{Header="開始ページ",Minimum=1,Maximum=snapshot.PageCount,Value=1,SmallChange=1};
            var count=new NumberBox{Header=new TextBlock{Text="ページ数（最大16）",TextWrapping=TextWrapping.Wrap},Minimum=1,Maximum=Math.Min(16,snapshot.PageCount),Value=Math.Min(16,snapshot.PageCount),SmallChange=1};
            var limit=new NumberBox{Header="今回追加するページ数の上限",Minimum=1,Maximum=128,Value=64,SmallChange=16};
            var prepare=new Button{Content="件数を確認",HorizontalAlignment=HorizontalAlignment.Stretch};
            var planText=new TextBlock{Text="範囲を確認してから開始してください。",TextWrapping=TextWrapping.Wrap};
            var chunkFields=new StackPanel{Spacing=8,Visibility=Visibility.Collapsed};
            foreach(var element in new UIElement[]{limit,prepare,planText})chunkFields.Children.Add(element);
            var start=new Button{Content="作成",HorizontalAlignment=HorizontalAlignment.Stretch};
            var startAll=new Button{Content="全ページを一括作成",Style=(Style)Application.Current.Resources["AccentButtonStyle"],HorizontalAlignment=HorizontalAlignment.Stretch};
            var next=new Button{Content="次の未作成範囲",HorizontalAlignment=HorizontalAlignment.Stretch};
            var cancel=new Button{Content="中止",IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};
            var largeWarningText=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var largeConfirm=new Button{Content="続行して全ページ作成",Style=(Style)Application.Current.Resources["AccentButtonStyle"],HorizontalAlignment=HorizontalAlignment.Stretch};
            var largeCancel=new Button{Content="キャンセル",HorizontalAlignment=HorizontalAlignment.Stretch};
            var largeWarningActions=new Grid{ColumnSpacing=8};
            largeWarningActions.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
            largeWarningActions.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
            Grid.SetColumn(largeCancel,1);
            largeWarningActions.Children.Add(largeConfirm);largeWarningActions.Children.Add(largeCancel);
            var largeWarningInner=new StackPanel{Spacing=8};
            largeWarningInner.Children.Add(largeWarningText);largeWarningInner.Children.Add(largeWarningActions);
            var largeWarningCard=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=largeWarningInner,Visibility=Visibility.Collapsed};
            var progress=new ProgressBar{Minimum=0,Maximum=16,Visibility=Visibility.Collapsed};
            var status=new TextBlock{Text="追加した範囲を「見た目（AI）」で検索できます",TextWrapping=TextWrapping.Wrap};
            var coverageText=new TextBlock{TextWrapping=TextWrapping.Wrap};var rangesText=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var ranges=new Expander{Header="準備済みの範囲",HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch,
                Content=new ScrollViewer{Content=FormScrollContent.Wrap(rangesText),MaxHeight=120,HorizontalScrollMode=ScrollMode.Disabled,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled}};
            var source=new TextBlock{Text=row.Title,TextWrapping=TextWrapping.Wrap};
            var fields=new Grid{ColumnSpacing=12};
            fields.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});fields.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
            Grid.SetColumn(count,1);fields.Children.Add(first);fields.Children.Add(count);
            AutomationProperties.SetName(first,"開始ページ");AutomationProperties.SetName(count,"ページ数（一度に最大16）");
            var panel=new StackPanel{Spacing=12};foreach(var e in new UIElement[]{mode,ranges,fields,chunkFields})panel.Children.Add(e);
            var heading=new StackPanel{Spacing=8};heading.Children.Add(source);heading.Children.Add(coverageText);
            var actions=new StackPanel{Spacing=8};foreach(var e in new UIElement[]{progress,status,largeWarningCard,next,start,startAll,cancel})actions.Children.Add(e);
            foreach(var(control,id) in new (DependencyObject,string)[]{(mode,"PageAIMode"),(limit,"PageAIChunkLimit"),(prepare,"PageAIChunkPreview"),(planText,"PageAIChunkPlan"),
                (first,"PageAIStart"),(count,"PageAICount"),(next,"PageAINextRange"),(start,"PageAIAdd"),(startAll,"PageAIAddAll"),(largeWarningCard,"PageAILargeWarning"),(largeConfirm,"PageAILargeConfirm"),(largeCancel,"PageAILargeCancel"),(cancel,"PageAICancel"),(status,"PageAIStatus"),(coverageText,"PageAICoverage"),(ranges,"PageAIRanges"),(rangesText,"PageAIRangesText")})AutomationProperties.SetAutomationId(control,id);
            var viewport=new ScrollViewer{Content=FormScrollContent.Wrap(panel),Margin=new Thickness(0,12,0,12),HorizontalScrollMode=ScrollMode.Disabled,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            AutomationProperties.SetAutomationId(viewport,"PageAIFieldsScroll");
            var content=new Grid{Width=Math.Clamp(XamlRoot.Size.Width-112,240,460),Height=Math.Clamp(XamlRoot.Size.Height-200,320,520)};
            content.RowDefinitions.Add(new(){Height=GridLength.Auto});content.RowDefinitions.Add(new(){Height=new GridLength(1,GridUnitType.Star)});content.RowDefinitions.Add(new(){Height=GridLength.Auto});
            Grid.SetRow(viewport,1);Grid.SetRow(actions,2);content.Children.Add(heading);content.Children.Add(viewport);content.Children.Add(actions);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="ページのAI検索データ",Content=content,CloseButtonText="閉じる"};
            AutomationProperties.SetAutomationId(dialog,"PageAIDialog");
            var busy=false;var closeRequested=false;string? job=null;PageImageCoverage? coverage=null;PageChunkPlan? plan=null;PageChunkStatus? chunk=null;
            bool Chunked()=>mode.SelectedIndex==1;
            void SetActions()
            {
                first.IsEnabled=count.IsEnabled=mode.IsEnabled=limit.IsEnabled=!busy;
                prepare.IsEnabled=!busy&&coverage?.CanPrepare==true;
                start.IsEnabled=!busy&&coverage?.CanPrepare==true&&(!Chunked()||plan?.CanStart==true||chunk?.CanResume==true);
                start.Content=Chunked()?(chunk?.CanResume==true?"続きから作成":"作成"):"作成";
                startAll.IsEnabled=!busy&&coverage?.CanPrepare==true&&coverage.RemainingPages>0;
                startAll.Content=coverage is {RemainingPages:>0}?$"全ページを一括作成（残り {coverage.RemainingPages:N0} ページ）":"全ページ登録済み";
                largeConfirm.IsEnabled=largeCancel.IsEnabled=!busy;
                next.Visibility=Chunked()?Visibility.Collapsed:Visibility.Visible;
                next.IsEnabled=!busy&&coverage?.CanPrepare==true&&coverage.NextRange is not null;
            }
            void SelectNext(){if(coverage?.NextRange is PageImageRange r){first.Value=r.Start+1;count.Value=r.Count;}}
            void ApplyCoverage(PageImageCoverage value,bool selectNext)
            {
                coverage=value;coverageText.Text=value.Summary;rangesText.Text=value.RangeSummary;ToolTipService.SetToolTip(coverageText,"モデル: "+value.Model);
                if(selectNext)SelectNext();SetActions();
            }
            void InvalidatePlan()
            {
                plan=null;chunk=null;planText.Text="範囲を確認してから開始してください。";largeWarningCard.Visibility=Visibility.Collapsed;SetActions();
            }
            async Task CancelOwned()
            {
                if(job is null)return;
                try{await api.PostAsync("api/library/ai/pages/cancel",new JsonObject{{"job_id",job}});}
                catch(Exception ex){status.Text="中止を確認できません。設定で状況を確認してください。";AppLog.Error(ex);}
            }
            async Task RunAllPagesAsync()
            {
                if(busy||coverage?.CanPrepare!=true||coverage.RemainingPages==0)return;
                largeWarningCard.Visibility=Visibility.Collapsed;
                busy=true;SetActions();progress.Visibility=Visibility.Visible;progress.Value=0;
                try
                {
                    if(closeRequested)throw new OperationCanceledException("中断しました。");
                    var allStatus=await api.PageEvidences.StartAllPagesAsync(row.Id,snapshot.SourceRevision,scope,initial.Profile);
                    job=allStatus.JobId;cancel.IsEnabled=allStatus.Running;progress.Maximum=Math.Max(1,allStatus.Total);
                    if(closeRequested)await CancelOwned();
                    while(!disposed&&allStatus.Running)
                    {
                        progress.Value=allStatus.Processed;
                        status.Text="処理中: "+allStatus.Summary;
                        await Task.Delay(500);
                        allStatus=await api.PageEvidences.AllPagesStatusAsync(allStatus);
                    }
                    progress.Value=allStatus.Processed;
                    status.Text=allStatus.State switch
                    {
                        "complete"=>"全ページの登録が完了しました。"+allStatus.Summary,
                        "cancelled"=>"中断しました（完了した範囲は保持しています）。"+allStatus.Summary,
                        "failed"=>allStatus.Error,
                        _=>allStatus.Summary
                    };
                    job=null;ApplyCoverage(await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope,initial.Profile),false);
                }
                catch(Exception ex){status.Text=ex.Message;coverage=null;coverageText.Text="準備状況を確認できません。閉じて開き直してください。";rangesText.Text="確認できません。";await CancelOwned();}
                finally{busy=false;SetActions();cancel.IsEnabled=false;if(closeRequested)dialog.Hide();}
            }
            mode.SelectionChanged+=(_,_)=>{fields.Visibility=Chunked()?Visibility.Collapsed:Visibility.Visible;chunkFields.Visibility=Chunked()?Visibility.Visible:Visibility.Collapsed;InvalidatePlan();};
            limit.ValueChanged+=(_,_)=>{if(!busy)InvalidatePlan();};
            first.ValueChanged+=(_,_)=>{if(double.IsFinite(first.Value)){count.Maximum=Math.Min(16,snapshot.PageCount-(int)first.Value+1);if(count.Value>count.Maximum)count.Value=count.Maximum;}};
            next.Click+=(_,_)=>SelectNext();cancel.Click+=async(_,_)=>{cancel.IsEnabled=false;await CancelOwned();};
            largeCancel.Click+=(_,_)=>{largeWarningCard.Visibility=Visibility.Collapsed;};
            largeConfirm.Click+=async(_,_)=>await RunAllPagesAsync();
            startAll.Click+=async(_,_)=>
            {
                if(busy||coverage?.CanPrepare!=true||coverage.RemainingPages==0)return;
                if(PageChunkRequests.NeedsLargeBookWarning(snapshot.PageCount))
                {
                    largeWarningText.Text=PageChunkRequests.LargeBookWarningMessage(row.Title,snapshot.PageCount,coverage.RemainingPages);
                    largeWarningCard.Visibility=Visibility.Visible;
                    return;
                }
                await RunAllPagesAsync();
            };
            dialog.Opened+=(_,_)=>{if(autoStartAll)DispatcherQueue.TryEnqueue(async()=>await RunAllPagesAsync());};
            dialog.Closing+=async(_,args)=>{if(!busy)return;args.Cancel=true;closeRequested=true;cancel.IsEnabled=false;await CancelOwned();};
            prepare.Click+=async(_,_)=>
            {
                if(busy)return;
                if(!double.IsFinite(limit.Value)||limit.Value!=Math.Truncate(limit.Value)||limit.Value is <1 or >128){status.Text="1〜128ページの上限を指定してください。";return;}
                busy=true;InvalidatePlan();
                try
                {
                    plan=await api.PageEvidences.PlanChunksAsync(row.Id,snapshot.SourceRevision,scope,(int)limit.Value,initial.Profile);
                    planText.Text=plan.Summary+(plan.PageIds.Count>0?"\n"+plan.RangeSummary:"");
                    status.Text=plan.CanStart?"表示された範囲を確認して開始してください。16ページずつ保存します。":"追加範囲はありません。準備状況を確認してください。";
                }
                catch(Exception ex){status.Text=ex.Message;plan=null;}
                finally{busy=false;SetActions();if(closeRequested)dialog.Hide();}
            };
            start.Click+=async(_,_)=>
            {
                if(busy||coverage?.CanPrepare!=true||!start.IsEnabled)return;
                if(!Chunked()&&(!double.IsFinite(first.Value)||first.Value!=Math.Truncate(first.Value)||!double.IsFinite(count.Value)||count.Value!=Math.Truncate(count.Value)
                    ||first.Value<1||count.Value<1||count.Value>16||first.Value+count.Value-1>snapshot.PageCount))
                {status.Text="有効なページ範囲を指定してください。";return;}
                busy=true;SetActions();progress.Visibility=Visibility.Visible;progress.Value=0;
                try
                {
                    if(Chunked())
                    {
                        if(closeRequested)throw new OperationCanceledException("中断しました。");
                        chunk=chunk?.CanResume==true?await api.PageEvidences.ResumeChunksAsync(chunk,scope):await api.PageEvidences.StartChunksAsync(plan!);
                        job=chunk.JobId;cancel.IsEnabled=true;progress.Maximum=chunk.Total;
                        if(closeRequested)await CancelOwned();
                        while(!disposed)
                        {
                            progress.Value=chunk.Processed;
                            status.Text=chunk.State switch{"complete"=>"追加しました。"+chunk.Summary,"cancelled"=>"中断しました。"+chunk.Summary,"failed"=>chunk.Error,_=>"処理中: "+chunk.Summary};
                            if(!chunk.Running)break;
                            await Task.Delay(500);chunk=await api.PageEvidences.ChunkStatusAsync(chunk);
                        }
                        plan=null;job=null;ApplyCoverage(await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope,initial.Profile),false);
                    }
                    else
                    {
                        var selected=await api.PageEvidences.ListPagesAsync(row.Id,(int)first.Value-1,(int)count.Value,snapshot.SourceRevision);
                        if(selected.SourceState!="current"||selected.SourceRevision!=snapshot.SourceRevision||selected.Pages.Count!=(int)count.Value)throw new InvalidOperationException("元ファイルが変わりました。閉じて開き直してください。");
                        if(closeRequested)throw new OperationCanceledException("中断しました。");
                        var result=await api.PostAsync("api/library/ai/pages",PageImageRequests.Create(row.Id,selected.Pages.Select(p=>p.PageId).ToArray(),snapshot.SourceRevision,scope));
                        job=result["job_id"]!.GetValue<string>();cancel.IsEnabled=true;progress.Maximum=count.Value;
                        if(closeRequested)await CancelOwned();
                        while(!disposed)
                        {
                            if(result["job_id"]?.GetValue<string>()!=job)throw new InvalidOperationException("処理状況が変わりました。設定の「AI検索の準備」で確認してください。");
                            var state=result["state"]!.GetValue<string>();progress.Value=result["processed"]!.GetValue<int>();
                            status.Text=state switch{"complete"=>$"追加しました: {result["indexed"]}ページ（再利用 {result["reused"]}）","cancelled"=>"中止しました（前回のデータは使えます）","failed"=>result["error"]!.GetValue<string>(),_=>$"処理中: {result["processed"]}/{result["total"]}ページ"};
                            if(state is not ("running" or "cancelling")){job=null;ApplyCoverage(await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope,initial.Profile),state=="complete");break;}
                            await Task.Delay(500);result=await api.GetAsync("api/library/ai/status");
                        }
                    }
                }
                catch(Exception ex){status.Text=ex.Message;coverage=null;coverageText.Text="準備状況を確認できません。閉じて開き直してください。";rangesText.Text="確認できません。";await CancelOwned();}
                finally{busy=false;SetActions();cancel.IsEnabled=false;if(closeRequested)dialog.Hide();}
            };
            ApplyCoverage(initial,true);
            var xamlRoot=XamlRoot;
            Windows.Foundation.TypedEventHandler<XamlRoot,XamlRootChangedEventArgs> fit=(_,_)=>{content.Width=Math.Clamp(xamlRoot.Size.Width-112,240,460);content.Height=Math.Clamp(xamlRoot.Size.Height-200,320,520);};
            xamlRoot.Changed+=fit;try{await dialog.ShowAsync();}finally{xamlRoot.Changed-=fit;}
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();if(PendingAutoSearch&&!disposed)searchTimer.Start();}
    }
}
