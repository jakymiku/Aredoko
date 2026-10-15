using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

public sealed partial class TagSuggestionsView : UserControl, IDisposable
{
    private readonly TagReviewClient api;
    private readonly int itemId;
    private readonly bool dirty;
    private readonly CancellationTokenSource lifetime=new();
    private CancellationTokenSource? evidenceCancellation;
    private TagHistory? history;
    private TagBatch? batch;
    private TagCandidate? candidate;
    private bool busy,closing,disposed,populating;
    private string? requestId;
    public bool ApprovalAttempted {get;private set;}
    public bool Busy=>busy;
    public event Action? CloseReady;
    public TagSuggestionsView(TagReviewClient api,int itemId,bool dirty)
    {
        this.api=api;this.itemId=itemId;this.dirty=dirty;InitializeComponent();UpdateButtons();
    }
    public void Fit(double width,double height)
    {
        Width=Math.Clamp(width-112,260,640);Height=Math.Clamp(height-210,280,580);
        // Keep the ScrollViewer in a continuously measured star column.
        // Moving it through a zero-width column during a live resize can leave
        // its presenter with zero-sized children in the ContentDialog.
        Body.ColumnDefinitions[0].Width=new GridLength(Width<600?Math.Min(152,Width*.32):210);
    }
    private void UpdateButtons()
    {
        if(disposed)return;
        Generate.IsEnabled=!busy&&!closing&&history?.Available==true;
        Refresh.IsEnabled=!busy&&!closing;Older.IsEnabled=!busy&&!closing&&history?.NextBefore is not null;
        Cancel.IsEnabled=busy&&requestId is not null&&!closing;Batches.IsEnabled=!busy;Candidates.IsEnabled=!busy;
        var pending=!busy&&!closing&&batch is {Stale:false}&&candidate is {State:"pending"};
        Edited.IsEnabled=pending&&!dirty;Accept.IsEnabled=pending&&!dirty&&!string.IsNullOrWhiteSpace(Edited.Text);
        Reject.IsEnabled=pending;
    }
    private void Message(string message)=>Status.Text=message+(dirty?"\n未保存の編集があります。承認するには、閉じて詳細の編集を保存してください。":"");
    private async Task RunAsync(Func<Task> operation)
    {
        if(busy||disposed)return;busy=true;UpdateButtons();
        try{await operation();}
        catch(OperationCanceledException) when(lifetime.IsCancellationRequested){}
        catch(Exception ex){if(!disposed){Message(ex.Message+"\n最新へ戻して状態を確認できます。");AppLog.Error(ex);}}
        finally{busy=false;requestId=null;if(!disposed){UpdateButtons();if(closing)CloseReady?.Invoke();}}
    }
    public Task LoadAsync()=>RunAsync(()=>LoadCoreAsync(null));
    private async Task LoadCoreAsync(long? before)
    {
        var loaded=await api.HistoryAsync(itemId,before,lifetime.Token);if(disposed)return;
        history=loaded;batch=null;candidate=null;Evidence.Source=null;Evidence.Visibility=Visibility.Collapsed;populating=true;
        Batches.Items.Clear();Candidates.Items.Clear();
        foreach(var value in loaded.Batches)Batches.Items.Add(new ComboBoxItem{Content=$"履歴 #{value.Id} · {value.Candidates.Count}候補"+(value.Stale?" · 元ファイル変更あり":""),Tag=value});
        populating=false;Batches.SelectedIndex=loaded.Batches.Count>0?0:-1;
        if(loaded.Batches.Count==0){Provenance.Text="まだ候補がありません。";Explanation.Text="画像または本の先頭ページから候補を生成します。";Edited.Text="";}
        Message(loaded.Available?"候補は未確定です。根拠を確認し、必要なら修正して承認してください。":loaded.Reason);
    }
    private void Batch_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(populating||disposed)return;
        batch=(Batches.SelectedItem as ComboBoxItem)?.Tag as TagBatch;candidate=null;Candidates.Items.Clear();Evidence.Source=null;Evidence.Visibility=Visibility.Collapsed;
        Detail.ChangeView(null,0,null,true);
        if(batch is null){UpdateButtons();return;}
        Provenance.Text=$"{batch.Model}\nモデル版: {batch.ModelRevision}\n{batch.Adapter} {batch.AdapterVersion}\n前処理: {batch.Preprocessing}\n根拠: {(batch.EvidenceKind=="cover"?"本の先頭ページのみ":"画像")}"+(batch.Stale?"\n元ファイルが変わっています。生成し直してください。":"");
        foreach(var value in batch.Candidates)
        {
            var row=new ListViewItem{Content=new TextBlock{Text=$"{value.Tag}\n{value.StateLabel}",TextWrapping=TextWrapping.Wrap},Tag=value};
            AutomationProperties.SetAutomationId(row,$"TagCandidate{value.Id}");AutomationProperties.SetName(row,$"{value.Tag} {value.StateLabel}");Candidates.Items.Add(row);
        }
        Candidates.SelectedIndex=Candidates.Items.Count>0?0:-1;
        if(Candidates.Items.Count==0){Explanation.Text="候補はありません。自動承認は行いません。";Edited.Text="";}
        evidenceCancellation?.Cancel();evidenceCancellation?.Dispose();evidenceCancellation=CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        if(!batch.Stale)_=ShowEvidenceAsync(batch,evidenceCancellation.Token);UpdateButtons();
    }
    private async Task ShowEvidenceAsync(TagBatch selected,CancellationToken cancellation)
    {
        try
        {
            var bytes=await api.EvidenceAsync(itemId,selected.Revision,cancellation);
            var png=await ThumbnailCodec.ResizeAsync(bytes,cancellation);
            using var stream=new InMemoryRandomAccessStream();using var writer=new DataWriter(stream);writer.WriteBytes(png);await writer.StoreAsync();writer.DetachStream();stream.Seek(0);
            var image=new BitmapImage();await image.SetSourceAsync(stream);cancellation.ThrowIfCancellationRequested();
            if(!disposed&&ReferenceEquals(batch,selected)){Evidence.Source=image;Evidence.Visibility=Visibility.Visible;}
        }
        catch(OperationCanceledException){}
        catch(Exception ex){if(!disposed&&!cancellation.IsCancellationRequested&&ReferenceEquals(batch,selected)){Provenance.Text+="\n根拠画像を表示できません。最新へ戻して確認してください。";AppLog.Error(ex);}}
    }
    private void Candidate_Changed(object sender,SelectionChangedEventArgs e)
    {
        candidate=(Candidates.SelectedItem as ListViewItem)?.Tag as TagCandidate;
        Edited.Text=candidate?.AcceptedTag??candidate?.Tag??"";Explanation.Text=candidate?.Explanation??"";UpdateButtons();
    }
    private void Edited_Changed(object sender,TextChangedEventArgs e){if(Accept is not null)UpdateButtons();}
    private async void Refresh_Click(object sender,RoutedEventArgs e)=>await LoadAsync();
    private async void Older_Click(object sender,RoutedEventArgs e){if(history?.NextBefore is long before)await RunAsync(()=>LoadCoreAsync(before));}
    private async void Generate_Click(object sender,RoutedEventArgs e)
    {
        if(history?.Available!=true)return;
        await RunAsync(async()=>{requestId=Guid.NewGuid().ToString("N");UpdateButtons();Message("候補を生成しています… 閉じる操作では生成の終了を待ちます。");await api.GenerateAsync(itemId,requestId,lifetime.Token);await LoadCoreAsync(null);});
    }
    private async Task ReviewAsync(bool accept)
    {
        if(candidate is not {State:"pending"}||batch is not {Stale:false}||accept&&dirty)return;
        var selected=candidate;var edited=Edited.Text;
        await RunAsync(async()=>{if(accept)ApprovalAttempted=true;await api.ReviewAsync(itemId,selected,accept,edited,lifetime.Token);await LoadCoreAsync(null);});
    }
    private async void Accept_Click(object sender,RoutedEventArgs e)=>await ReviewAsync(true);
    private async void Reject_Click(object sender,RoutedEventArgs e)=>await ReviewAsync(false);
    private async Task CancelGenerationAsync()
    {
        var id=requestId;if(id is null||disposed)return;
        Cancel.IsEnabled=false;
        try
        {
            for(var attempt=0;attempt<6&&requestId==id;attempt++)
            {if(await api.CancelAsync(id,lifetime.Token)){if(!disposed)Message("中止を要求しました。処理の終了を待っています。");break;}await Task.Delay(100,lifetime.Token);}
        }
        catch(OperationCanceledException){}
        catch(Exception ex){if(!disposed){Message("中止を確認できません。処理の終了を待っています。 "+ex.Message);AppLog.Error(ex);}}
        finally{if(!disposed)UpdateButtons();}
    }
    private async void Cancel_Click(object sender,RoutedEventArgs e)=>await CancelGenerationAsync();
    public void RequestClose(){closing=true;UpdateButtons();if(!busy)CloseReady?.Invoke();else if(requestId is not null)_=CancelGenerationAsync();}
    public void Dispose(){if(disposed)return;disposed=true;lifetime.Cancel();evidenceCancellation?.Cancel();evidenceCancellation?.Dispose();lifetime.Dispose();}
}
