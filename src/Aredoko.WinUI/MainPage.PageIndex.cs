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
            if(disposed)return;
            var first=new NumberBox{Header="開始ページ",Minimum=1,Maximum=snapshot.PageCount,Value=1,SmallChange=1};
            var count=new NumberBox{Header="ページ数（一度に最大16）",Minimum=1,Maximum=Math.Min(PageImageRequests.MaxPages,snapshot.PageCount),Value=Math.Min(PageImageRequests.MaxPages,snapshot.PageCount),SmallChange=1};
            var start=new Button{Content="選んだページを追加",HorizontalAlignment=HorizontalAlignment.Stretch};
            var cancel=new Button{Content="処理を中断",IsEnabled=false,HorizontalAlignment=HorizontalAlignment.Stretch};
            var progress=new ProgressBar{Minimum=0,Maximum=16,Visibility=Visibility.Collapsed};
            var status=new TextBlock{Text=$"全{snapshot.PageCount:N0}ページ。追加した範囲を「画像の見た目（AI）」で検索できます。",TextWrapping=TextWrapping.Wrap};
            var source=new TextBlock{Text=row.Title,TextWrapping=TextWrapping.Wrap};
            var scopeText=new TextBlock{Text="保存済みのAI対象範囲内の本だけ処理します。",TextWrapping=TextWrapping.Wrap};
            var panel=new StackPanel{Spacing=12};
            foreach(var child in new UIElement[]{source,scopeText,first,count,start,cancel,progress,status})panel.Children.Add(child);
            foreach(var(control,id) in new (DependencyObject,string)[]{(first,"PageAIStart"),(count,"PageAICount"),(start,"PageAIAdd"),(cancel,"PageAICancel"),(status,"PageAIStatus")})AutomationProperties.SetAutomationId(control,id);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="本のページをAI検索に追加",Content=new ScrollViewer{Content=panel,MaxHeight=Math.Max(200,XamlRoot.Size.Height-190)},CloseButtonText="閉じる"};
            AutomationProperties.SetAutomationId(dialog,"PageAIDialog");
            var busy=false;var closeRequested=false;string? job=null;
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
            cancel.Click+=async(_,_)=>{cancel.IsEnabled=false;await CancelOwned();};
            dialog.Closing+=async(_,args)=>
            {
                if(!busy)return;
                args.Cancel=true;closeRequested=true;cancel.IsEnabled=false;await CancelOwned();
            };
            start.Click+=async(_,_)=>
            {
                if(busy)return;
                if(!double.IsFinite(first.Value)||first.Value!=Math.Truncate(first.Value)||!double.IsFinite(count.Value)||count.Value!=Math.Truncate(count.Value)
                    ||first.Value<1||count.Value<1||count.Value>PageImageRequests.MaxPages||first.Value+count.Value-1>snapshot.PageCount)
                {status.Text="有効なページ範囲を指定してください。";return;}
                busy=true;start.IsEnabled=first.IsEnabled=count.IsEnabled=false;progress.Visibility=Visibility.Visible;progress.Value=0;
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
                            "complete"=>$"追加しました: {result["indexed"]}ページ（再利用 {result["reused"]}）。画像の見た目（AI）で検索できます。",
                            "cancelled"=>"中断しました。今回の未完了範囲は保存していません。前回の索引は使えます。",
                            "failed"=>result["error"]!.GetValue<string>(),
                            _=>$"処理中: {result["processed"]}/{result["total"]}ページ"
                        };
                        if(state is not ("running" or "cancelling")){job=null;break;}
                        await Task.Delay(500);result=await api.GetAsync("api/library/ai/status");
                    }
                }
                catch(Exception ex){status.Text=ex.Message;await CancelOwned();}
                finally
                {
                    busy=false;start.IsEnabled=first.IsEnabled=count.IsEnabled=true;cancel.IsEnabled=false;
                    if(closeRequested)dialog.Hide();
                }
            };
            await dialog.ShowAsync();
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();if(PendingSearch&&!disposed)searchTimer.Start();}
    }
}
