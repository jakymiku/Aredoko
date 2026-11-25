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
    public bool SetupRequested {get;private set;}
    public bool Busy=>busy;
    public event Action? CloseReady;
    public event Action? OpenSetupRequested;
    public TagSuggestionsView(TagReviewClient api,int itemId,bool dirty)
    {
        this.api=api;this.itemId=itemId;this.dirty=dirty;InitializeComponent();UiText.Apply(this);UpdateButtons();
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
        var defaultButton=Application.Current.Resources["DefaultButtonStyle"] as Style;
        Generate.Style=Generate.IsEnabled&&Candidates.Items.Count==0?(Style)Application.Current.Resources["AccentButtonStyle"]:defaultButton;
        if(OpenSetup is not null)
        {
            OpenSetup.Visibility=history is {Available:false}?Visibility.Visible:Visibility.Collapsed;
            OpenSetup.IsEnabled=!busy&&!closing;
            OpenSetup.Style=OpenSetup.IsEnabled?(Style)Application.Current.Resources["AccentButtonStyle"]:defaultButton;
        }
        Refresh.IsEnabled=!busy&&!closing;Older.IsEnabled=!busy&&!closing&&history?.NextBefore is not null;
        if(BusyProgress is not null)BusyProgress.Visibility=busy?Visibility.Visible:Visibility.Collapsed;
        var canCancel=busy&&requestId is not null&&!closing;
        Cancel.IsEnabled=canCancel;
        Cancel.Visibility=busy&&requestId is not null?Visibility.Visible:Visibility.Collapsed;
        Batches.IsEnabled=!busy;
        Batches.Visibility=Batches.Items.Count>0?Visibility.Visible:Visibility.Collapsed;
        Candidates.IsEnabled=!busy;
        var pending=!busy&&!closing&&batch is {Stale:false}&&candidate is {State:"pending"};
        Edited.IsEnabled=pending&&!dirty;Accept.IsEnabled=pending&&!dirty&&!string.IsNullOrWhiteSpace(Edited.Text);
        Reject.IsEnabled=pending;
        var pendingCount=!busy&&!closing&&batch is {Stale:false}?batch.Candidates.Count(c=>c.State=="pending"):0;
        if(BatchReviewActions is not null)BatchReviewActions.Visibility=pendingCount>0?Visibility.Visible:Visibility.Collapsed;
        if(AcceptAll is not null)
        {
            AcceptAll.Content=pendingCount>0?AppText.L($"✓ 未承認をすべて承認 ({pendingCount}件)", $"✓ Approve all pending ({pendingCount})"):AppText.L("✓ 未承認をすべて承認", "✓ Approve all pending");
            AcceptAll.IsEnabled=pendingCount>0&&!dirty;
        }
        if(RejectAll is not null)
        {
            RejectAll.Content=pendingCount>0?AppText.L($"× 未承認をすべて却下 ({pendingCount}件)", $"× Reject all pending ({pendingCount})"):AppText.L("× 未承認をすべて却下", "× Reject all pending");
            RejectAll.IsEnabled=pendingCount>0;
        }
    }
    private void Message(string message)=>Status.Text=message+(dirty?AppText.L("\n⚠ 詳細に未保存の編集があります（保存後に承認できます）", "\n⚠ Unsaved edits in details (save before approving)"):"");
    private async Task RunAsync(Func<Task> operation)
    {
        if(busy||disposed)return;busy=true;UpdateButtons();
        try{await operation();}
        catch(OperationCanceledException) when(lifetime.IsCancellationRequested){}
        catch(Exception ex){if(!disposed){Message(ex.Message+AppText.L("\n最新へ戻して状態を確認できます。", "\nClick Refresh to check the latest state."));AppLog.Error(ex);}}
        finally{busy=false;requestId=null;if(!disposed){UpdateButtons();if(closing)CloseReady?.Invoke();}}
    }
    public Task LoadAsync(){Message(AppText.L("状態を確認しています…", "Checking status..."));return RunAsync(()=>LoadCoreAsync(null));}
    private async Task LoadCoreAsync(long? before)
    {
        var loaded=await api.HistoryAsync(itemId,before,lifetime.Token);if(disposed)return;
        ModelDetails.Text="";Metadata.IsExpanded=false;Metadata.Visibility=Visibility.Collapsed;
        history=loaded;batch=null;candidate=null;Evidence.Source=null;Evidence.Visibility=Visibility.Collapsed;populating=true;
        Batches.Items.Clear();Candidates.Items.Clear();
        foreach(var value in loaded.Batches)Batches.Items.Add(new ComboBoxItem{Content=AppText.L($"履歴 #{value.Id} · {value.Candidates.Count}候補", $"Batch #{value.Id} · {value.Candidates.Count} candidates")+(value.Stale?AppText.L(" · 元ファイル変更あり", " · Source changed"):""),Tag=value});
        populating=false;Batches.SelectedIndex=loaded.Batches.Count>0?0:-1;
        if(loaded.Batches.Count==0)
        {
            Provenance.Text=loaded.Available?AppText.L("まだ候補がありません", "No suggestions yet"):AppText.L("タグ付けモデルが未導入です", "Tagging model is not installed");
            Explanation.Text=loaded.Available?AppText.L("上の［✨ 生成］を押すと、この作品のタグ候補を作成します。", "Click [✨ Generate] above to create tag suggestions for this item."):AppText.L("上の［📥 モデルを取得・設定］からモデルを取得するとすぐ使えます。", "Click [📥 Get / Configure Model] above to install a model.");
            Edited.Text="";
        }
        Message(loaded.Available?AppText.L("［✨ 生成］から候補を作成し、根拠を確認して承認・却下できます。", "Click [✨ Generate] to create suggestions, inspect evidence, then approve or reject."):loaded.Reason);
    }
    private void Batch_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(populating||disposed)return;
        batch=(Batches.SelectedItem as ComboBoxItem)?.Tag as TagBatch;candidate=null;Candidates.Items.Clear();Evidence.Source=null;Evidence.Visibility=Visibility.Collapsed;
        Detail.ChangeView(null,0,null,true);
        if(batch is null){UpdateButtons();return;}
        Provenance.Text=$"{batch.Model}\n"+AppText.L($"根拠: {(batch.EvidenceKind=="cover"?"本の先頭ページのみ":"画像")}", $"Evidence: {(batch.EvidenceKind=="cover"?"First page only":"Image")}")+(batch.Stale?AppText.L("\n元ファイルが変わっています。生成し直してください。", "\nSource file changed. Please regenerate."):"");
        ModelDetails.Text=AppText.L($"モデル版: {batch.ModelRevision}\nアダプタ: {batch.Adapter} {batch.AdapterVersion}\n前処理: {batch.Preprocessing}", $"Model revision: {batch.ModelRevision}\nAdapter: {batch.Adapter} {batch.AdapterVersion}\nPreprocessing: {batch.Preprocessing}");
        Metadata.Visibility=Visibility.Visible;Metadata.IsExpanded=false;
        foreach(var value in batch.Candidates)
        {
            var badge=value.State switch{"pending"=>AppText.L("● 未承認", "● Pending"),"accepted"=>AppText.L("✓ 承認済み", "✓ Approved"),_=>AppText.L("× 却下済み", "× Rejected")};
            var row=new ListViewItem{Content=new TextBlock{Text=$"{value.Tag}\n{badge}",TextWrapping=TextWrapping.Wrap},Tag=value};
            AutomationProperties.SetAutomationId(row,$"TagCandidate{value.Id}");AutomationProperties.SetName(row,$"{value.Tag} {value.StateLabel}");Candidates.Items.Add(row);
        }
        Candidates.SelectedIndex=Candidates.Items.Count>0?0:-1;
        if(Candidates.Items.Count==0){Explanation.Text=AppText.L("この履歴に候補はありません", "No suggestions in this batch");Edited.Text="";}
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
        catch(Exception ex){if(!disposed&&!cancellation.IsCancellationRequested&&ReferenceEquals(batch,selected)){Provenance.Text+=AppText.L("\n根拠画像を表示できません。最新へ戻して確認してください。", "\nCould not display evidence image. Refresh to verify.");AppLog.Error(ex);}}
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
        await RunAsync(async()=>{requestId=Guid.NewGuid().ToString("N");UpdateButtons();Message(AppText.L("候補を生成しています… 閉じる操作では生成の終了を待ちます。", "Generating suggestions... Closing will wait for cancellation."));await api.GenerateAsync(itemId,requestId,lifetime.Token);await LoadCoreAsync(null);});
    }
    private async Task ReviewAsync(bool accept)
    {
        if(candidate is not {State:"pending"}||batch is not {Stale:false}||accept&&dirty)return;
        var selected=candidate;var edited=Edited.Text;
        await RunAsync(async()=>{if(accept)ApprovalAttempted=true;await api.ReviewAsync(itemId,selected,accept,edited,lifetime.Token);await LoadCoreAsync(null);});
    }
    private async void Accept_Click(object sender,RoutedEventArgs e)=>await ReviewAsync(true);
    private async void Reject_Click(object sender,RoutedEventArgs e)=>await ReviewAsync(false);
    private async Task ReviewAllPendingAsync(bool accept)
    {
        if(batch is not {Stale:false}||(accept&&dirty))return;
        var pending=batch.Candidates.Where(c=>c.State=="pending").ToArray();
        if(pending.Length==0)return;
        await RunAsync(async()=>{
            var done=0;
            foreach(var item in pending)
            {
                if(lifetime.Token.IsCancellationRequested||disposed)break;
                if(accept)ApprovalAttempted=true;
                await api.ReviewAsync(itemId,item,accept,item.Tag,lifetime.Token);
                done++;
                if(!disposed)Message(accept?AppText.L($"承認中… ({done}/{pending.Length} 件)", $"Approving... ({done}/{pending.Length})"):AppText.L($"却下中… ({done}/{pending.Length} 件)", $"Rejecting... ({done}/{pending.Length})"));
            }
            await LoadCoreAsync(null);
        });
    }
    private async void AcceptAll_Click(object sender,RoutedEventArgs e)=>await ReviewAllPendingAsync(true);
    private async void RejectAll_Click(object sender,RoutedEventArgs e)=>await ReviewAllPendingAsync(false);
    private async Task CancelGenerationAsync()
    {
        var id=requestId;if(id is null||disposed)return;
        Cancel.IsEnabled=false;
        try
        {
            for(var attempt=0;attempt<6&&requestId==id;attempt++)
            {if(await api.CancelAsync(id,lifetime.Token)){if(!disposed)Message(AppText.L("中止を要求しました。処理の終了を待っています。", "Cancellation requested. Waiting for completion..."));break;}await Task.Delay(100,lifetime.Token);}
        }
        catch(OperationCanceledException){}
        catch(Exception ex){if(!disposed){Message(AppText.L("中止を確認できません。処理の終了を待っています。 ", "Could not confirm cancellation. Waiting... ")+ex.Message);AppLog.Error(ex);}}
        finally{if(!disposed)UpdateButtons();}
    }
    private async void Cancel_Click(object sender,RoutedEventArgs e)=>await CancelGenerationAsync();
    private void OpenSetup_Click(object sender,RoutedEventArgs e){if(busy||closing)return;SetupRequested=true;OpenSetupRequested?.Invoke();RequestClose();}
    public void RequestClose(){closing=true;UpdateButtons();if(!busy)CloseReady?.Invoke();else if(requestId is not null)_=CancelGenerationAsync();}
    public void Dispose(){if(disposed)return;disposed=true;lifetime.Cancel();evidenceCancellation?.Cancel();evidenceCancellation?.Dispose();lifetime.Dispose();}
}
