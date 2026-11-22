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
    private readonly TextBlock currentItem=new(){MaxLines=1,TextTrimming=TextTrimming.CharacterEllipsis,Visibility=Visibility.Collapsed};
    private readonly TextBlock status=new(){TextWrapping=TextWrapping.Wrap};
    private readonly Button start=new(){Content="AI検索データを作成",IsEnabled=false};
    private readonly Button cancel=new(){Content="中止",IsEnabled=false};
    private readonly ProgressBar progress=new(){Visibility=Visibility.Collapsed,IsIndeterminate=true};
    private readonly Image stateArt=VisualAssets.Sticker(64);
    private readonly DispatcherTimer timer=new(){Interval=TimeSpan.FromSeconds(1)};
    private readonly CancellationTokenSource lifetime=new();
    private AudioContentStatus? latest;
    private bool disposed,observing,command;
    private long version;
    private bool VideoAudio=>client.SourceKind=="video";
    private string Subject=>VideoAudio?"動画の音":"音声";
    public Expander Content {get;}

    public AudioPreparationPanel(AudioContentClient client,Func<JsonObject> conditions)
    {
        this.client=client;this.conditions=conditions;
        var panel=new StackPanel{Spacing=8};
        var scopeDesc=new TextBlock{Text=VideoAudio?"現在の範囲の動画（先頭音声）が対象 · 閉じても続行":"現在の範囲の音声が対象 · 閉じても続行",TextWrapping=TextWrapping.Wrap};
        ToolTipService.SetToolTip(scopeDesc,VideoAudio?"作成後は「動画の音（AI）」で探せます（文字起こしは保存しません）。":"作成後は「音声（AI）」で探せます（文字起こしは保存しません）。");
        panel.Children.Add(scopeDesc);
        var stateRow=new Grid{ColumnSpacing=12};
        stateRow.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
        stateRow.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
        var statusStack=new StackPanel{Spacing=6,VerticalAlignment=VerticalAlignment.Center};
        statusStack.Children.Add(currentItem);statusStack.Children.Add(status);statusStack.Children.Add(progress);
        Grid.SetColumn(statusStack,1);
        stateRow.Children.Add(stateArt);stateRow.Children.Add(statusStack);
        panel.Children.Add(stateRow);
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
        actions.Children.Add(start);actions.Children.Add(cancel);panel.Children.Add(actions);
        Content=new Expander{Header=VideoAudio?"動画の音":"音声",Content=panel,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch};
        var automationPrefix=VideoAudio?"VideoAudioContent":"AudioContent";
        AutomationProperties.SetAutomationId(Content,automationPrefix+"Options");
        AutomationProperties.SetAutomationId(status,automationPrefix+"Status");
        AutomationProperties.SetAutomationId(currentItem,automationPrefix+"CurrentItem");
        AutomationProperties.SetAutomationId(progress,automationPrefix+"Progress");
        AutomationProperties.SetName(progress,Subject+"のAI検索データ作成の進捗");
        AutomationProperties.SetAutomationId(start,"Start"+automationPrefix);
        AutomationProperties.SetAutomationId(cancel,"Cancel"+automationPrefix);
        start.Content="AI検索データを作成";
        ToolTipService.SetToolTip(start,$"作成済みの{Subject}は再利用します。残りがある場合はもう一度押すと続きへ進みます");
        ToolTipService.SetToolTip(cancel,$"完了分は保存済みです。処理中の対象のみ次回やり直します");
        Content.Expanding+=async(_,_)=>{if(disposed)return;timer.Start();await RefreshAsync();};
        Content.SizeChanged+=(_,args)=>
        {
            if(!disposed&&Content.IsExpanded&&args.NewSize.Height>args.PreviousSize.Height)Content.StartBringIntoView();
        };
        Content.Collapsed+=(_,_)=>timer.Stop();
        timer.Tick+=Tick;
        start.Click+=async(_,_)=>await CommandAsync(true);
        cancel.Click+=async(_,_)=>await CommandAsync(false);
        status.Text=$"展開すると{Subject}の準備状況を確認できます。";
    }

    private async void Tick(object? sender,object e)=>await RefreshAsync();
    private void Apply(AudioContentStatus value)
    {
        if(disposed)return;
        latest=value;var own=value.SourceKind==client.SourceKind;
        currentItem.Text=own&&value.Busy?value.ItemProgress?.ItemTitle??"":"";
        currentItem.Visibility=string.IsNullOrEmpty(currentItem.Text)?Visibility.Collapsed:Visibility.Visible;
        if(currentItem.Visibility==Visibility.Visible)ToolTipService.SetToolTip(currentItem,currentItem.Text);
        status.Text=!own&&value.Supported&&value.Available
            ?value.Busy?value.Message+"\nこの対象の索引は、現在の準備が終わってから作成できます。":$"{Subject}の索引を作成できます。準備済みの対象は再利用します。"
            :value.Message;
        start.Content=own&&value.RemainingCandidates>0?$"続きから作成（残り {value.RemainingCandidates:N0}件）":"AI検索データを作成";
        start.IsEnabled=!command&&value.Supported&&value.Available&&!value.Busy;
        cancel.IsEnabled=!command&&own&&value.Busy&&value.State!="cancelling";
        progress.Visibility=value.Busy?Visibility.Visible:Visibility.Collapsed;
        var current=own&&value.State=="running"?value.ItemProgress:null;
        progress.IsIndeterminate=!own||value.State!="running"||value.Target==0||current is {TotalMs:null};
        progress.Maximum=current?.TotalMs is int total?total:Math.Max(1,value.Target);
        progress.Value=current is {TotalMs:not null} tracked?tracked.PreparedMs:value.Processed;
        AutomationProperties.SetName(progress,current is null?Subject+"の索引作成の進捗":"現在の"+Subject+"の解析進捗。解析済み時刻で、保存前です。");
        VisualAssets.State(stateArt,!own?null:value.Busy?"indexing":value.State=="failed"?"error":(value.State=="complete"||(value.Target>0&&value.RemainingCandidates==0))?"completed":null);
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
        catch(Exception ex){if(!disposed&&expected==version)status.Text=Subject+"の準備状況を確認できません。"+ex.Message;}
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
        catch(Exception ex){if(!disposed)status.Text=Subject+"の準備を開始・中断できません。"+ex.Message;}
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
