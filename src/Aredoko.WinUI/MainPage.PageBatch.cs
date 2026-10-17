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
            var profile=ai["profile"]?.GetValue<string>()??throw new InvalidOperationException("モデル設定を確認してください。");
            var choices=new ListView{SelectionMode=ListViewSelectionMode.None,MaxHeight=200,HorizontalContentAlignment=HorizontalAlignment.Stretch};
            var candidates=new[]{seed}.Concat(rows.Where(ArchiveManifest.CanOpen)).DistinctBy(r=>r.Id).ToList();
            foreach(var row in candidates)
            {
                var box=new CheckBox{Content=new TextBlock{Text=row.Title,TextWrapping=TextWrapping.Wrap},Tag=row,IsChecked=row.Id==seed.Id,HorizontalAlignment=HorizontalAlignment.Stretch};
                AutomationProperties.SetAutomationId(box,"BatchBook"+row.Id);AutomationProperties.SetName(box,row.Title);
                choices.Items.Add(new ListViewItem{Content=box,Padding=new Thickness(0,0,24,0),HorizontalContentAlignment=HorizontalAlignment.Stretch});
            }
            var limit=new NumberBox{Header="今回追加する合計ページ数の上限",Minimum=1,Maximum=PageBatchRequests.MaxTotal,Value=64,SmallChange=16};
            var summary=new TextBlock{Text="本を選んで範囲を確認してください。",TextWrapping=TextWrapping.Wrap};
            var details=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var prepare=new Button{Content="範囲を確認",HorizontalAlignment=HorizontalAlignment.Stretch};
            var start=new Button{Content="追加を開始",IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};
            var resume=new Button{Content="同じ範囲を再開",Visibility=Visibility.Collapsed,HorizontalAlignment=HorizontalAlignment.Stretch};
            var cancel=new Button{Content="処理を中断",IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};
            foreach(var(control,id) in new (DependencyObject,string)[]{(choices,"BatchBooks"),(limit,"BatchPageLimit"),(summary,"BatchSummary"),(details,"BatchRanges"),(prepare,"BatchPreview"),(start,"BatchStart"),(resume,"BatchResume"),(cancel,"BatchCancel")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(choices,"追加する本を最大8冊選択");AutomationProperties.SetName(limit,"合計ページ数の上限");
            var fields=new StackPanel{Spacing=12};
            fields.Children.Add(new TextBlock{Text="表示中の検索結果から最大8冊。各本の次の未準備範囲を、1冊最大16ページ追加します。",TextWrapping=TextWrapping.Wrap});
            fields.Children.Add(choices);fields.Children.Add(limit);fields.Children.Add(details);
            var viewport=new ScrollViewer{Content=FormScrollContent.Wrap(fields),HorizontalScrollMode=ScrollMode.Disabled,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            var actions=new StackPanel{Spacing=8};foreach(var element in new UIElement[]{summary,prepare,start,resume,cancel})actions.Children.Add(element);
            var content=new Grid{Width=Math.Clamp(XamlRoot.Size.Width-112,240,440),Height=Math.Clamp(XamlRoot.Size.Height-240,280,500),RowSpacing=12};
            content.RowDefinitions.Add(new(){Height=new GridLength(1,GridUnitType.Star)});content.RowDefinitions.Add(new(){Height=GridLength.Auto});
            Grid.SetRow(actions,1);content.Children.Add(viewport);content.Children.Add(actions);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="複数の本をAI検索に追加",Content=content,CloseButtonText="閉じる"};
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
                if(busy)return;plan=null;current=null;details.Text="";summary.Text="範囲を確認してください。";Buttons();
            }
            foreach(ListViewItem entry in choices.Items)
            {var box=(CheckBox)entry.Content;box.Checked+=(_,_)=>Invalidate();box.Unchecked+=(_,_)=>Invalidate();}
            limit.ValueChanged+=(_,_)=>Invalidate();
            prepare.Click+=async(_,_)=>
            {
                if(busy)return;
                var selected=choices.Items.Cast<ListViewItem>().Select(x=>(CheckBox)x.Content).Where(x=>x.IsChecked==true).Select(x=>(MediaRow)x.Tag).ToArray();
                if(selected.Length is <1 or >PageBatchRequests.MaxBooks||!double.IsFinite(limit.Value)||limit.Value!=Math.Truncate(limit.Value))
                {summary.Text="1〜8冊と有効なページ上限を指定してください。";return;}
                busy=true;plan=null;current=null;Buttons();summary.Text="準備状況を確認中…";
                try
                {
                    var remaining=(int)limit.Value;var proposed=new List<BookPageSelection>();var lines=new List<string>();
                    foreach(var row in selected)
                    {
                        if(remaining==0){lines.Add(row.Title+"：今回は合計上限のため対象外");continue;}
                        var snapshot=await api.PageEvidences.RefreshIndexAsync(row.Id);
                        var coverage=await api.PageEvidences.ImageCoverageAsync(row.Id,snapshot.SourceRevision,scope,profile);
                        if(!coverage.CanPrepare)throw new InvalidOperationException(row.Title+"："+coverage.Summary);
                        if(coverage.NextRange is not PageImageRange range){lines.Add(row.Title+"：準備済み");continue;}
                        var count=Math.Min(remaining,range.Count);
                        var pages=await api.PageEvidences.ListPagesAsync(row.Id,range.Start,count,snapshot.SourceRevision);
                        if(pages.SourceState!="current"||pages.SourceRevision!=snapshot.SourceRevision||pages.Pages.Count!=count)throw new InvalidOperationException("元ファイルが変わりました。もう一度範囲を確認してください。");
                        proposed.Add(new(row.Id,snapshot.SourceRevision,pages.Pages.Select(p=>p.PageId).ToArray()));remaining-=count;
                        lines.Add($"{row.Title}：{range.Start+1}〜{range.Start+count}ページ");
                    }
                    plan=proposed;details.Text=string.Join("\n",lines);
                    summary.Text=plan.Count==0?"選んだ本は準備済みです。":$"今回: {plan.Count}冊・{plan.Sum(b=>b.PageIds.Count)}ページ。まだ追加していません。";
                }
                catch(Exception ex){summary.Text=ex.Message;}
                finally{busy=false;Buttons();if(closing)dialog.Hide();}
            };
            async Task CancelOwned()
            {
                if(current?.Running!=true)return;
                try{await api.PostAsync("api/library/ai/pages/cancel",new JsonObject{{"job_id",current.JobId}});}
                catch(Exception ex){summary.Text="中断を確認できません。AI設定の処理状況を確認してください。";AppLog.Error(ex);}
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
                        summary.Text=current.Summary+(current.Running?$"\n処理中: {current.Processed}/{current.Total}ページ":current.State=="cancelled"?"\n中断しました。完了した本の範囲は保持しています。":"\n"+current.Error);
                        cancel.IsEnabled=current.Running;
                        if(!current.Running)
                        {
                            details.Text=string.Join("\n",current.Books.Select(book=>
                                (candidates.FirstOrDefault(r=>r.Id==book.ItemId)?.Title??"選択した本")+"："+
                                (book.State=="complete"?$"{book.Indexed}ページ追加済み":book.State=="failed"?book.Error:"未完了（再開できます）")));
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
        finally{dialogOpen=false;transitions.Release();if(PendingSearch&&!disposed)searchTimer.Start();}
    }
}
