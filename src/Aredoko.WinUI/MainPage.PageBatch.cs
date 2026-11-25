using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task IndexBookBatchAsync(MediaRow seed)
    {
        if(!ready||disposed||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;searchTimer.Stop();
        try
        {
            if(aiScope is null)throw new InvalidOperationException(aiScopeError);
            var scope=(JsonObject)aiScope.DeepClone();
            var ai=await api.GetAsync("api/library/ai/status");
            var profile=ai["profile"]?.GetValue<string>()??throw new InvalidOperationException(AppText.L("モデル設定を確認してください。", "Check the AI model setting."));
            var choices=new ListView{SelectionMode=ListViewSelectionMode.None,MaxHeight=200,HorizontalContentAlignment=HorizontalAlignment.Stretch};
            var candidates=new[]{seed}.Concat(rowByOrdinal.OrderBy(kv=>kv.Key).Select(kv=>kv.Value).Where(ArchiveManifest.CanOpen)).DistinctBy(r=>r.Id).ToList();
            foreach(var row in candidates)
            {
                var box=new CheckBox{Content=new TextBlock{Text=row.Title,TextWrapping=TextWrapping.Wrap},Tag=row,IsChecked=row.Id==seed.Id,HorizontalAlignment=HorizontalAlignment.Stretch};
                AutomationProperties.SetAutomationId(box,"BatchBook"+row.Id);AutomationProperties.SetName(box,row.Title);
                choices.Items.Add(new ListViewItem{Content=box,Padding=new Thickness(0,0,24,0),HorizontalContentAlignment=HorizontalAlignment.Stretch});
            }
            var limit=new NumberBox{Header=AppText.L("合計ページ上限", "Total page limit"),Minimum=1,Maximum=PageBatchRequests.MaxTotal,Value=64,SmallChange=16};
            var summary=new TextBlock{Text=AppText.L("本を選んで範囲を確認してください", "Select books and check the range"),TextWrapping=TextWrapping.Wrap};
            var details=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var prepare=new Button{Content=AppText.L("範囲を確認", "Check Range"),HorizontalAlignment=HorizontalAlignment.Stretch};
            var start=new Button{Content=AppText.L("作成", "Start"),IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};
            var resume=new Button{Content=AppText.L("再開", "Resume"),Visibility=Visibility.Collapsed,HorizontalAlignment=HorizontalAlignment.Stretch};
            var cancel=new Button{Content=AppText.L("中止", "Cancel"),IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};
            foreach(var(control,id) in new (DependencyObject,string)[]{(choices,"BatchBooks"),(limit,"BatchPageLimit"),(summary,"BatchSummary"),(details,"BatchRanges"),(prepare,"BatchPreview"),(start,"BatchStart"),(resume,"BatchResume"),(cancel,"BatchCancel")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(choices,AppText.L("追加する本を最大8冊選択", "Select up to 8 books to add"));AutomationProperties.SetName(limit,AppText.L("合計ページ数の上限", "Maximum total pages"));
            var fields=new StackPanel{Spacing=12};
            fields.Children.Add(new TextBlock{Text=AppText.L("最大8冊・各16ページまで作成します", "Processes up to 8 books, 16 pages each"),TextWrapping=TextWrapping.Wrap});
            fields.Children.Add(choices);fields.Children.Add(limit);fields.Children.Add(details);
            var viewport=new ScrollViewer{Content=FormScrollContent.Wrap(fields),HorizontalScrollMode=ScrollMode.Disabled,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            var actions=new StackPanel{Spacing=8};foreach(var element in new UIElement[]{summary,prepare,start,resume,cancel})actions.Children.Add(element);
            var content=new Grid{Width=Math.Clamp(XamlRoot.Size.Width-112,240,440),Height=Math.Clamp(XamlRoot.Size.Height-240,280,500),RowSpacing=12};
            content.RowDefinitions.Add(new(){Height=new GridLength(1,GridUnitType.Star)});content.RowDefinitions.Add(new(){Height=GridLength.Auto});
            Grid.SetRow(actions,1);content.Children.Add(viewport);content.Children.Add(actions);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("複数の本をAI検索に追加", "Add Multiple Books to AI Search"),Content=content,CloseButtonText=AppText.L("閉じる", "Close")};
            AutomationProperties.SetAutomationId(dialog,"BookBatchDialog");
            var busy=false;var closing=false;List<BookPageSelection>? plan=null;PageBatchStatus? current=null;
            void Buttons()
            {
                choices.IsEnabled=limit.IsEnabled=prepare.IsEnabled=!busy;
                start.IsEnabled=!busy&&plan is {Count:>0};cancel.IsEnabled=busy&&current?.Running==true;
                resume.Visibility=current?.CanResume==true?Visibility.Visible:Visibility.Collapsed;resume.IsEnabled=!busy;
            }
            void Invalidate()
            {
                if(busy)return;plan=null;current=null;details.Text="";summary.Text=AppText.L("範囲を確認してください。", "Check the range.");Buttons();
            }
            foreach(ListViewItem entry in choices.Items)
            {var box=(CheckBox)entry.Content;box.Checked+=(_,_)=>Invalidate();box.Unchecked+=(_,_)=>Invalidate();}
            limit.ValueChanged+=(_,_)=>Invalidate();
            prepare.Click+=async(_,_)=>
            {
                if(busy)return;
                var selected=choices.Items.Cast<ListViewItem>().Select(x=>(CheckBox)x.Content).Where(x=>x.IsChecked==true).Select(x=>(MediaRow)x.Tag).ToArray();
                if(selected.Length is <1 or >PageBatchRequests.MaxBooks||!double.IsFinite(limit.Value)||limit.Value!=Math.Truncate(limit.Value))
                {summary.Text=AppText.L("1〜8冊と有効なページ上限を指定してください。", "Specify 1-8 books and a valid page limit.");return;}
                busy=true;plan=null;current=null;Buttons();summary.Text=AppText.L("準備状況を確認中…", "Checking status...");
                try
                {
                    var remaining=(int)limit.Value;var proposed=new List<BookPageSelection>();var lines=new List<string>();
                    foreach(var row in selected)
                    {
                        if(remaining==0){lines.Add(row.Title+AppText.L("：今回は合計上限のため対象外", ": Skipped (reached total limit)"));continue;}
                        var snapshot=await api.PageEvidences.RefreshIndexAsync(row.Id);
                        var coverage=await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope,profile);
                        if(!coverage.CanPrepare)throw new InvalidOperationException(row.Title+"："+coverage.Summary);
                        if(coverage.NextRange is not PageImageRange range){lines.Add(row.Title+AppText.L("：準備済み", ": Already prepared"));continue;}
                        var count=Math.Min(remaining,range.Count);
                        var pages=await api.PageEvidences.ListPagesAsync(row.Id,range.Start,count,snapshot.SourceRevision);
                        if(pages.SourceState!="current"||pages.SourceRevision!=snapshot.SourceRevision||pages.Pages.Count!=count)throw new InvalidOperationException(AppText.L("元ファイルが変わりました。もう一度範囲を確認してください。", "Source file changed. Check the range again."));
                        proposed.Add(new(row.Id,snapshot.SourceRevision,pages.Pages.Select(p=>p.PageId).ToArray()));remaining-=count;
                        lines.Add(AppText.L($"{row.Title}：{range.Start+1}〜{range.Start+count}ページ", $"{row.Title}: pp. {range.Start+1}-{range.Start+count}"));
                    }
                    plan=proposed;details.Text=string.Join("\n",lines);
                    summary.Text=plan.Count==0?AppText.L("選んだ本は作成済みです", "Selected books are already indexed"):AppText.L($"{plan.Count}冊・{plan.Sum(b=>b.PageIds.Count)}ページを追加します", $"Will add {plan.Sum(b=>b.PageIds.Count)} pages across {plan.Count} book(s)");
                }
                catch(Exception ex){summary.Text=ex.Message;}
                finally{busy=false;Buttons();if(closing)dialog.Hide();}
            };
            async Task CancelOwned()
            {
                if(current?.Running!=true)return;
                try{await api.PostAsync("api/library/ai/pages/cancel",new JsonObject{{"job_id",current.JobId}});}
                catch(Exception ex){summary.Text=AppText.L("中止を確認できません。AI設定で状態を確認してください。", "Unable to confirm cancellation. Check status in AI Settings.");AppLog.Error(ex);}
            }
            async Task Run(bool retry)
            {
                if(busy||(!retry&&plan is not {Count:>0}))return;
                busy=true;Buttons();
                try
                {
                    current=retry?await api.PageEvidences.ResumeBatchAsync(current!.JobId,scope,profile):await api.PageEvidences.StartBatchAsync(plan!,scope,(int)limit.Value,profile);
                    var job=current.JobId;if(closing)await CancelOwned();
                    while(!disposed)
                    {
                        summary.Text=current.Summary+(current.Running?AppText.L($"\n処理中: {current.Processed}/{current.Total}ページ", $"\nProcessing: {current.Processed}/{current.Total} pages"):current.State=="cancelled"?AppText.L("\n中断しました。完了した本の範囲は保持しています。", "\nCancelled. Completed items were kept."):"\n"+current.Error);
                        cancel.IsEnabled=current.Running;
                        if(!current.Running)
                        {
                            details.Text=string.Join("\n",current.Books.Select(book=>
                                (candidates.FirstOrDefault(r=>r.Id==book.ItemId)?.Title??AppText.L("選択した本", "Selected book"))+"："+
                                (book.State=="complete"?AppText.L($"{book.Indexed}ページ追加済み", $"{book.Indexed} page(s) added"):book.State=="failed"?book.Error:AppText.L("未完了（再開できます）", "Incomplete (resumable)"))));
                            plan=null;break;
                        }
                        await Task.Delay(500);current=await api.PageEvidences.BatchStatusAsync(job,profile);
                    }
                }
                catch(Exception ex){summary.Text=ex.Message;await CancelOwned();plan=null;}
                finally{busy=false;Buttons();if(closing)dialog.Hide();}
            }
            start.Click+=async(_,_)=>await Run(false);resume.Click+=async(_,_)=>await Run(true);
            cancel.Click+=async(_,_)=>{cancel.IsEnabled=false;await CancelOwned();};
            dialog.Closing+=async(_,args)=>{if(!busy)return;args.Cancel=true;closing=true;await CancelOwned();};
            var root=XamlRoot;Windows.Foundation.TypedEventHandler<XamlRoot,XamlRootChangedEventArgs> fit=(_,_)=>
            {content.Width=Math.Clamp(root.Size.Width-112,240,440);content.Height=Math.Clamp(root.Size.Height-240,280,500);};
            root.Changed+=fit;try{await dialog.ShowAsync();}finally{root.Changed-=fit;}
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();if(PendingAutoSearch&&!disposed)searchTimer.Start();}
    }
}
