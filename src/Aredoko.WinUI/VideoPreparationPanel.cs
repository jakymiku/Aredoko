using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

// Dialog-owned controls only. Jobs, scopes, persistence and model ownership stay
// in the backend; closing this panel stops observation, not a committed job.
internal sealed class VideoPreparationPanel : IDisposable
{
    private readonly VideoContentClient client;
    private readonly Func<JsonObject> conditions;
    private readonly TextBlock currentItem=new(){MaxLines=1,TextTrimming=TextTrimming.CharacterEllipsis,Visibility=Visibility.Collapsed};
    private readonly TextBlock status=new(){TextWrapping=TextWrapping.Wrap};
    private readonly Button start=new(){Content="AI検索データを作成",IsEnabled=false};
    private readonly Button cancel=new(){Content="中止",IsEnabled=false};
    private readonly ProgressBar progress=new(){Visibility=Visibility.Collapsed,IsIndeterminate=true};
    private readonly DispatcherTimer timer=new(){Interval=TimeSpan.FromSeconds(1)};
    private readonly CancellationTokenSource lifetime=new();
    private VideoContentStatus? latest;
    private bool disposed,observing,command;
    private long version;
    public Expander Content {get;}

    public VideoPreparationPanel(VideoContentClient client,Func<JsonObject> conditions)
    {
        this.client=client;this.conditions=conditions;
        var panel=new StackPanel{Spacing=8};
        var scopeDesc=new TextBlock{Text="現在の範囲の動画が対象 · 閉じても続行",TextWrapping=TextWrapping.Wrap};
        ToolTipService.SetToolTip(scopeDesc,"作成後は「動画の場面（AI）」で探せます（動画内の音は対象外）。");
        panel.Children.Add(scopeDesc);
        panel.Children.Add(currentItem);panel.Children.Add(status);panel.Children.Add(progress);
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
        actions.Children.Add(start);actions.Children.Add(cancel);panel.Children.Add(actions);
        Content=new Expander{Header="動画の場面",Content=panel,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(Content,"VideoContentOptions");
        AutomationProperties.SetAutomationId(status,"VideoContentStatus");
        AutomationProperties.SetAutomationId(currentItem,"VideoContentCurrentItem");
        AutomationProperties.SetAutomationId(progress,"VideoContentProgress");
        AutomationProperties.SetName(progress,"動画のAI検索データ作成の進捗");
        AutomationProperties.SetAutomationId(start,"StartVideoContent");
        AutomationProperties.SetAutomationId(cancel,"CancelVideoContent");
        ToolTipService.SetToolTip(start,"作成済みの動画は再利用します。残りがある場合はもう一度押すと続きへ進みます");
        ToolTipService.SetToolTip(cancel,"完了分は保存済みです。処理中の動画のみ次回やり直します");
        Content.Expanding+=async(_,_)=>{if(disposed)return;timer.Start();await RefreshAsync();};
        Content.SizeChanged+=(_,args)=>
        {
            if(!disposed&&Content.IsExpanded&&args.NewSize.Height>args.PreviousSize.Height)Content.StartBringIntoView();
        };
        Content.Collapsed+=(_,_)=>timer.Stop();
        timer.Tick+=Tick;
        start.Click+=async(_,_)=>await CommandAsync(true);
        cancel.Click+=async(_,_)=>await CommandAsync(false);
        status.Text="展開すると動画の準備状況を確認できます。";
    }

    private async void Tick(object? sender,object e)=>await RefreshAsync();
    private void Apply(VideoContentStatus value)
    {
        if(disposed)return;
        latest=value;status.Text=value.Message;
        currentItem.Text=value.Busy?value.ItemProgress?.ItemTitle??"":"";
        currentItem.Visibility=string.IsNullOrEmpty(currentItem.Text)?Visibility.Collapsed:Visibility.Visible;
        if(currentItem.Visibility==Visibility.Visible)ToolTipService.SetToolTip(currentItem,currentItem.Text);
        start.Content=value.RemainingCandidates>0?$"続きから作成（残り {value.RemainingCandidates:N0}件）":"AI検索データを作成";
        start.IsEnabled=!command&&value.Supported&&value.Available&&!value.Busy;
        cancel.IsEnabled=!command&&value.Busy&&value.State!="cancelling";
        progress.Visibility=value.Busy?Visibility.Visible:Visibility.Collapsed;
        var current=value.State=="running"?value.ItemProgress:null;
        progress.IsIndeterminate=value.State!="running"||value.Target==0||current is {TotalMs:null};
        progress.Maximum=current?.TotalMs is int total?total:Math.Max(1,value.Target);
        progress.Value=current is {TotalMs:not null} tracked?tracked.PreparedMs:value.Processed;
        AutomationProperties.SetName(progress,current is null?"動画の索引作成の進捗":"現在の動画の解析進捗。保存完了前のデータです。");
    }
    private async Task RefreshAsync()
    {
        if(disposed||observing||command)return;
        observing=true;var expected=version;
        try
        {
            var value=await client.StatusAsync(lifetime.Token);
            if(!disposed&&expected==version)Apply(value);
        }
        catch(OperationCanceledException)when(disposed){}
        catch(Exception ex){if(!disposed&&expected==version)status.Text="動画の準備状況を確認できません。"+ex.Message;}
        finally{observing=false;}
    }
    private async Task CommandAsync(bool begin)
    {
        if(disposed||command)return;
        command=true;version++;start.IsEnabled=false;cancel.IsEnabled=false;
        try
        {
            var value=begin?await client.StartAsync(conditions(),lifetime.Token):await client.CancelAsync(lifetime.Token);
            if(!disposed){latest=value;status.Text=value.Message;}
        }
        catch(OperationCanceledException)when(disposed){}
        catch(Exception ex){if(!disposed)status.Text="動画の準備を開始・中断できません。"+ex.Message;}
        finally
        {
            command=false;
            if(!disposed&&latest is not null)
            {
                var message=status.Text;Apply(latest);status.Text=message;
            }
        }
    }
    public void Dispose()
    {
        if(disposed)return;
        disposed=true;version++;timer.Stop();timer.Tick-=Tick;lifetime.Cancel();lifetime.Dispose();
    }
}
