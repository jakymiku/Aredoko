using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

// Dialog-owned controls only. Jobs, scopes, persistence and model ownership stay
// in the backend; closing this panel stops observation, not a committed job.
internal sealed class AudioPreparationPanel : IDisposable
{
    private readonly AudioContentClient client;
    private readonly Func<JsonObject> conditions;
    private readonly TextBlock status=new(){TextWrapping=TextWrapping.Wrap};
    private readonly Button start=new(){Content="音声の索引を作成",IsEnabled=false};
    private readonly Button cancel=new(){Content="中断",IsEnabled=false};
    private readonly ProgressBar progress=new(){Visibility=Visibility.Collapsed,IsIndeterminate=true};
    private readonly DispatcherTimer timer=new(){Interval=TimeSpan.FromSeconds(1)};
    private readonly CancellationTokenSource lifetime=new();
    private AudioContentStatus? latest;
    private bool disposed,observing,command;
    private long version;
    public Expander Content {get;}

    public AudioPreparationPanel(AudioContentClient client,Func<JsonObject> conditions)
    {
        this.client=client;this.conditions=conditions;
        var panel=new StackPanel{Spacing=8};
        panel.Children.Add(new TextBlock{Text="現在の検索フォルダ・棚にある音声が対象です。作成後は検索方法の「音声の内容（AI）」で探せます。文字起こしは保存しません。画面を閉じても準備は続きます。",TextWrapping=TextWrapping.Wrap});
        panel.Children.Add(status);panel.Children.Add(progress);
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
        actions.Children.Add(start);actions.Children.Add(cancel);panel.Children.Add(actions);
        Content=new Expander{Header="音声の内容検索",Content=panel,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        AutomationProperties.SetAutomationId(Content,"AudioContentOptions");
        AutomationProperties.SetAutomationId(status,"AudioContentStatus");
        AutomationProperties.SetAutomationId(progress,"AudioContentProgress");
        AutomationProperties.SetName(progress,"音声の索引作成の進捗");
        AutomationProperties.SetAutomationId(start,"StartAudioContent");
        AutomationProperties.SetAutomationId(cancel,"CancelAudioContent");
        ToolTipService.SetToolTip(start,"準備済みの音声は再利用します。残りがある場合は、もう一度押すと続きへ進みます。");
        ToolTipService.SetToolTip(cancel,"保存済みの音声は残ります。処理中の音声は保存せず、次回は初めから準備します。");
        Content.Expanding+=async(_,_)=>{if(disposed)return;timer.Start();await RefreshAsync();};
        Content.SizeChanged+=(_,args)=>
        {
            if(!disposed&&Content.IsExpanded&&args.NewSize.Height>args.PreviousSize.Height)Content.StartBringIntoView();
        };
        Content.Collapsed+=(_,_)=>timer.Stop();
        timer.Tick+=Tick;
        start.Click+=async(_,_)=>await CommandAsync(true);
        cancel.Click+=async(_,_)=>await CommandAsync(false);
        status.Text="展開すると音声の準備状況を確認できます。";
    }

    private async void Tick(object? sender,object e)=>await RefreshAsync();
    private void Apply(AudioContentStatus value)
    {
        if(disposed)return;
        latest=value;status.Text=value.Message;
        start.Content=value.RemainingCandidates>0?"続きの音声を準備":"音声の索引を作成";
        start.IsEnabled=!command&&value.Supported&&value.Available&&!value.Busy;
        cancel.IsEnabled=!command&&value.Busy&&value.State!="cancelling";
        progress.Visibility=value.Busy?Visibility.Visible:Visibility.Collapsed;
        var current=value.State=="running"?value.ItemProgress:null;
        progress.IsIndeterminate=value.State!="running"||value.Target==0||current is {TotalMs:null};
        progress.Maximum=current?.TotalMs is int total?total:Math.Max(1,value.Target);
        progress.Value=current is {TotalMs:not null} tracked?tracked.PreparedMs:value.Processed;
        AutomationProperties.SetName(progress,current is null?"音声の索引作成の進捗":"現在の音声の解析進捗。総尺確認中の解析済み時刻です。");
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
        catch(Exception ex){if(!disposed&&expected==version)status.Text="音声の準備状況を確認できません。"+ex.Message;}
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
        catch(Exception ex){if(!disposed)status.Text="音声の準備を開始・中断できません。"+ex.Message;}
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
