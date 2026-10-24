using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Input;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Pickers;

namespace Aredoko_WinUI;

public sealed partial class MainPage : Page
{
    private readonly LibraryApi api = new();
    private readonly RequestVersion searches = new();
    private readonly SemaphoreSlim transitions = new(1,1);
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer searchTimer;
    private readonly ThumbnailService thumbnails;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer itemSizeSaveTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer itemSizeTimer;
    private bool itemSizeReady;
    private int libraryItemScale=100;
    private int itemWheelDelta;
    private XamlRoot? trackedXamlRoot;
    private double lastObservedRasterizationScale = 1.0;
    private readonly Dictionary<ListViewItem, Action> containerRefresh = new();
    private CancellationTokenSource renderCancellation = new();
    private CancellationTokenSource? detailCancellation;
    private ArchiveReaderView? readerView;
    private ImageViewerView? imageViewer;
    private VideoPlayerView? videoPlayer;
    private ViewerWindow? viewerWindow;
    private TagSuggestionsView? tagReview;
    private int? tagReviewSyncItem;
    private readonly ThumbnailClickTracker previewClicks=new();
    [System.Runtime.InteropServices.DllImport("user32.dll")]private static extern uint GetDoubleClickTime();
    [System.Runtime.InteropServices.DllImport("user32.dll")]private static extern int GetSystemMetrics(int index);
    private List<MediaRow> rows=[];
    private MediaRow? active;
    private EditorState saved;
    private bool updatingFavorite;
    private bool ready, populating, saving, dialogOpen, tiles, disposed;
    private int page, lastKind, lastMode;
    private int[]? selectedSearchRoots;
    private int[]? lastRoots;
    private bool lastLiteralOnly;
    private double? lastBoundary;
    private int lastResultGroup;
    private IReadOnlyList<RegisteredRootRow> knownRoots=[];
    private IReadOnlyList<string> knownShelves=[];
    private readonly HashSet<int> checkedFolderIds=[];
    private FolderSettingsDraft? folderDraft;
    private bool folderHubOpen, folderTiles, folderPopulating, folderSettingsActive, pollingScan;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer scanPollTimer;
    private JsonObject? aiScope;
    private string aiScopeError="AI索引の画面で対象を確認・保存してください。";
    private string view="all", lastQuery="";
    private MediaRow? similarityOrigin;
    private CancellationTokenSource? similarityCancellation;
    private bool returningFromSimilarity;
    private SearchBookmark? similarityReturn;
    private sealed record SearchBookmark(string Query,int Kind,int Mode,int[]? Roots,bool LiteralOnly,double? Boundary,int Group,string View,int Page,int Selection,long[]? Shelves);

    public MainPage() {
        InitializeComponent();
        AddHandler(PointerPressedEvent,new PointerEventHandler(PreviewPointerPressed),true);
        AddHandler(PointerPressedEvent,new PointerEventHandler(async(_,args)=>
        {
            var pointer=args.GetCurrentPoint(this).Properties;
            if(!pointer.IsXButton1Pressed&&!pointer.IsXButton2Pressed)return;
            if(dialogOpen||saving||viewerWindow is not null)return;
            args.Handled=true;
            await NavigateHistoryAsync(pointer.IsXButton2Pressed);
        }),true);
        ItemListContainer.AddHandler(PointerWheelChangedEvent,new PointerEventHandler(Library_PointerWheelChanged),true);
        itemSizeSaveTimer=DispatcherQueue.CreateTimer();itemSizeSaveTimer.Interval=TimeSpan.FromMilliseconds(500);
        itemSizeSaveTimer.Tick+=(_,_)=>SaveItemSize();
        itemSizeTimer=DispatcherQueue.CreateTimer();itemSizeTimer.Interval=TimeSpan.FromMilliseconds(80);
        itemSizeTimer.Tick+=(_,_)=>
        {
            itemSizeTimer.Stop();
            if(disposed)return;
            UpdateItemSizes();
        };
        Unloaded+=OnPageUnloaded;
        libraryItemScale=ViewerOptions.Value.LibraryItemScale;ItemSizeSlider.Value=libraryItemScale;
        ItemSizeLabel.Text=$"{libraryItemScale}%";itemSizeReady=true;
        UpdateSearchMethod();
        thumbnails = new ThumbnailService(api);
        searchTimer=DispatcherQueue.CreateTimer(); searchTimer.Interval=TimeSpan.FromMilliseconds(300);
        searchTimer.Tick+=async (_,_)=>{searchTimer.Stop(); if(PendingSearch) await NavigateAsync(0);};
        scanPollTimer=DispatcherQueue.CreateTimer(); scanPollTimer.Interval=TimeSpan.FromSeconds(1);
        scanPollTimer.Tick+=async (_,_)=>await PollScanStateAsync();
    }
    private static bool SameRoots(IReadOnlyList<int>? a,IReadOnlyList<int>? b)=>
        ReferenceEquals(a,b)||(a is not null&&b is not null&&a.SequenceEqual(b));
    private bool PendingSearch => !folderHubOpen&&!shelfHubOpen&&(Query.Text!=lastQuery||Kind.SelectedIndex!=lastKind||SearchMode.SelectedIndex!=lastMode||!SameRoots(selectedSearchRoots,lastRoots)||(AIMatchedOnly.IsChecked==true)!=lastLiteralOnly||BoundaryValue()!=lastBoundary||AIResultGroup.SelectedIndex!=lastResultGroup);
    private EditorState Current()=>new(Tags.Text,editingShelfIds.Length==0?"":ShelfName(editingShelfIds.Min()),Favorite.IsChecked==true,Reviewed.IsChecked==true){ShelfIds=editingShelfIds.ToArray()};
    private bool Dirty=>active is not null && EditorState.IsDirty(saved,Current());
    private bool FolderDirty=>folderSettingsActive && folderDraft is {IsDirty:true};
    private void Notice(string title,string message="",InfoBarSeverity severity=InfoBarSeverity.Informational,string? details=null) {
        Status.Title=title; Status.Message=message; Status.Severity=severity;
        Status.IsOpen=severity is InfoBarSeverity.Warning or InfoBarSeverity.Error;
        StatusExplanation.Text=details??"";
        StatusMore.Visibility=string.IsNullOrWhiteSpace(details)?Visibility.Collapsed:Visibility.Visible;
    }
    private void Failure(Exception ex) {
        Notice("操作を完了できません",ex.Message,InfoBarSeverity.Error);
        AppLog.Error(ex);
    }
    private async void Page_Loaded(object sender,RoutedEventArgs e)
    {
        AttachXamlRoot();
        await InitializeFirstPageAsync();
    }
    private Task? firstPageInitialization;
    // Loaded and the portable owner must await the same in-flight operation.
    internal Task InitializeFirstPageAsync()=>firstPageInitialization??=InitializeFirstPageCoreAsync();
    private async Task InitializeFirstPageCoreAsync() {
        ready=true;
        AttachXamlRoot();
        AppLog.Startup("page_initialization_starting");
        await ConnectAsync();
        UpdateNavigationLayout(ActualWidth);
        AppLog.Startup("page_initialization_completed");
    }
    private bool startupSearchSucceeded;
    private async Task ConnectAsync() {
        try {
            renderCancellation.Cancel();
            AppLog.Startup("session_connecting");await api.ConnectAsync();await RefreshHistoryGenerationAsync();
            AppLog.Startup("session_connected");await LoadAIScopeAsync();
            AppLog.Startup("ai_scope_loaded");await RefreshSearchRootsAsync();
            AppLog.Startup("roots_loaded");await LoadAsync();
            AppLog.Startup(startupSearchSucceeded?"initial_search_completed":"initial_search_failed");
            if(StartupReady.Pending)
            {
                if(!startupSearchSucceeded)await StartupReady.SignalAsync(false);
                else{AppLog.Startup("window_showing");MainWindow.Current.AppWindow.Show();MainWindow.Current.Activate();await StartupReady.FirstFrameAsync();}
            }
        }
        catch(Exception ex) { AppLog.Startup("connection_or_first_frame_failed");AppLog.Error(ex);Notice("バックエンドに接続できません", "Aredokoを閉じ、製品用の起動アイコンから起動し直してください。"+ex.Message,InfoBarSeverity.Error); }
        finally{if(StartupReady.Pending)try{await StartupReady.SignalAsync(false);}catch(Exception ex){AppLog.Error(ex);}}
    }
    private string ResultGroup()=>AIResultGroup.SelectedIndex switch {0=>"leading",1=>"other",_=>"all"};
    private void AIResultGroup_Changed(object sender,SelectionChangedEventArgs e){similarityCancellation?.Cancel();if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private double? BoundaryValue()=>SearchMode.SelectedIndex is 2 or 3 && double.IsFinite(SimilarityBoundary.Value)?SimilarityBoundary.Value:null;
    private void SimilarityBoundary_Changed(NumberBox sender,NumberBoxValueChangedEventArgs args){similarityCancellation?.Cancel();if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private void RestoreSearchRoots(IReadOnlyList<int>? ids)
    {
        selectedSearchRoots=ids is null?null:ids.ToArray();
        SyncSearchRootCombo();
        UpdateActiveSearchScopeBar();
    }
    private void SyncSearchRootCombo()
    {
        var before=populating;populating=true;
        try
        {
            SearchRoot.Items.Clear();
            SearchRoot.Items.Add(new ComboBoxItem {Content="すべてのフォルダ",Tag=0});
            foreach(var row in knownRoots.Where(r=>r.Enabled))
            {
                var option=new ComboBoxItem {Content=row.Path+(row.Online?"":"（未接続）"),Tag=row.Id};
                AutomationProperties.SetAutomationId(option,$"SearchRoot{row.Id}");
                SearchRoot.Items.Add(option);
            }
            if(selectedSearchRoots is null)SearchRoot.SelectedIndex=0;
            else if(selectedSearchRoots.Length==1)
            {
                var single=selectedSearchRoots[0];
                var match=SearchRoot.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Tag is int v&&v==single);
                if(match is null)
                {
                    match=new ComboBoxItem {Content=$"登録が見つからないフォルダ（ID {single}）",Tag=single};
                    SearchRoot.Items.Add(match);
                }
                SearchRoot.SelectedItem=match;
            }
            else
            {
                var multi=new ComboBoxItem {Content=$"選択したフォルダ（{selectedSearchRoots.Length}件）",Tag=-1};
                SearchRoot.Items.Add(multi);
                SearchRoot.SelectedItem=multi;
            }
        }
        finally{populating=before;}
    }
    private void UpdateActiveSearchScopeBar()
    {
        if(ActiveSearchScopeText is null||ResetAllFoldersButton is null)return;
        var isAiOrSimilar=similarityOrigin is not null||(SearchMode.SelectedIndex is >0 and <4&&!string.IsNullOrWhiteSpace(Query.Text));
        var (summary,warning)=FolderScopeDescriber.DescribeSearchScope(knownRoots,selectedSearchRoots,isAiOrSimilar,aiScope);
        ActiveSearchScopeText.Text="検索対象フィルタがオンになっています — "+(warning is null?summary:$"{summary} — {warning}");
        ActiveSearchScopeBar.Visibility=selectedSearchRoots is null?Visibility.Collapsed:Visibility.Visible;
        ResetAllFoldersButton.Visibility=selectedSearchRoots is null?Visibility.Collapsed:Visibility.Visible;
    }
    private async Task RefreshSearchRootsAsync()
    {
        var data=await api.GetAsync("api/library/roots?include_inactive=1");
        knownRoots=RegisteredRootRow.ParseList(data);
        await RefreshShelfDescriptorsAsync();
        var activeIds=knownRoots.Where(r=>r.Enabled).Select(r=>r.Id).ToHashSet();
        checkedFolderIds.RemoveWhere(id=>!activeIds.Contains(id));
        PopulateAddFolderShelves();
        SyncSearchRootCombo();
        UpdateActiveSearchScopeBar();
        if(folderHubOpen)RenderFolderHub();
    }
    private void SearchRoot_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(!ready||populating||SearchRoot.SelectedItem is not ComboBoxItem item||item.Tag is not int tag||tag<0)return;
        selectedSearchRoots=tag==0?null:new[]{tag};
        UpdateActiveSearchScopeBar();
        searchTimer.Stop();searchTimer.Start();
    }
    private async Task LoadAIScopeAsync()
    {
        aiScope=null;
        try {
            var data=await api.GetAsync("api/library/ai/scope");
            if(data["valid"]?.GetValue<bool>()!=true){aiScopeError=data["error"]?.GetValue<string>()??"AI対象を選び直してください。";return;}
            aiScope=(JsonObject)data["scope"]!.DeepClone();
        } catch(Exception ex){aiScopeError="AI対象を取得できません。AI索引の画面で確認してください。"+ex.Message;}
    }
    private async void Reconnect_Click(object sender,RoutedEventArgs e)
    {
        if(!await transitions.WaitAsync(0))return;
        try{if(await ConfirmDiscardAsync())await ConnectAsync();}finally{transitions.Release();}
    }
    private string KindValue()=>Kind.SelectedIndex switch {1=>"book",2=>"image",3=>"video",4=>"audio",5=>"archive",6=>"material",_=>""};
    private async Task LoadAsync(bool reuseSession=false) {
        startupSearchSucceeded=false;UpdateFavoriteRootList();
        var version=searches.Next(); Busy.Visibility=Visibility.Visible;
        GettingStarted.Visibility=Visibility.Collapsed;
        if(rows.Count==0){Empty.Visibility=Visibility.Visible;Empty.Text="検索結果を準備しています…";}
        similarityCancellation?.Cancel();similarityCancellation?.Dispose();similarityCancellation=new();
        CancelSearchButton.Visibility=Visibility.Visible;
        var cancellation=similarityCancellation.Token;var origin=similarityOrigin;
        // Do not allow editing an old record while a different result is loading.
        Editor.IsEnabled=false; Items.IsEnabled=false;
        var query=Query.Text; var kind=KindValue();var selectedKind=Kind.SelectedIndex;var selectedMode=SearchMode.SelectedIndex;var selectedRoots=selectedSearchRoots?.ToArray();var literalOnly=AIMatchedOnly.IsChecked==true;var boundary=BoundaryValue();var resultGroup=AIResultGroup.SelectedIndex;
        try {
            var method=SearchMethod.FromIndex(selectedMode);
            if((origin is not null||method.IsAI&&!string.IsNullOrWhiteSpace(query))&&aiScope is null)throw new InvalidOperationException(aiScopeError);
            var pageSize=method.IsPageText?20:60;
            var conditions=ResultSearchConditions.Create(query,kind,view,method,aiScope,selectedRoots,
                origin?.Id,literalOnly,boundary,ResultGroup(),selectedShelfIds);
            var result=await ReadResultPageAsync(conditions,reuseSession,version,page,pageSize,cancellation);
            if(!searches.IsCurrent(version)||disposed)return;
            resultPageSize=pageSize;
            if(result.Items.Count==0 && page>0)
            {
                page=Math.Max(0,(result.Total-1)/pageSize);
                await LoadAsync(reuseSession: resultSession is not null);return;
            }
            lastQuery=query; lastKind=selectedKind;lastMode=selectedMode;lastRoots=selectedRoots;lastLiteralOnly=literalOnly;lastBoundary=boundary;lastResultGroup=resultGroup;
            SearchOptions.IsExpanded=false;
            var (scopeLabel,scopeWarning)=FolderScopeDescriber.DescribeSearchScope(knownRoots,selectedRoots,origin is not null||(method.IsAI&&query.Length>0),aiScope);
            UpdateActiveSearchScopeBar();
            SearchOptions.Header="AI候補の表示";
            ResetBrowse(checked(page*pageSize),result);rows=result.Items; active=null; if(!folderSettingsActive)Details.IsPaneOpen=false; DetailsButton.IsEnabled=false;detailCancellation?.Cancel(); DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed; Tags.Text="";Shelf.Text="";Favorite.IsChecked=false;Reviewed.IsChecked=false;RenderRows();
            ItemTitle.Text="作品を選んでください"; ItemPath.Text=""; EditStatus.Text="";
            if(!folderHubOpen&&!shelfHubOpen)MainViewTitle.Text=selectedShelfIds is not null?ShelfScopeName():view=="history"?"閲覧履歴":view=="unreviewed"?"ライブラリ（未確認）":"ライブラリ";
            Count.Text=$"{result.Total:N0} 件"; PageNumber.Text=$"{page+1} / {Math.Max(1,(result.Total+pageSize-1)/pageSize)}";
            Previous.IsEnabled=page>0; Next.IsEnabled=(page+1)*pageSize<result.Total;
            Empty.Visibility=rows.Count==0?Visibility.Visible:Visibility.Collapsed;
            Empty.Text=method.IsPageText?(string.IsNullOrWhiteSpace(query)?"探したいページ内の語句を入力して検索してください。":"この範囲に一致するページ本文はありません。")
                :method.IsTagSemantic?(string.IsNullOrWhiteSpace(query)?"未承認タグから探したい内容を入力してください。":"索引済みの未承認タグ候補がありません。設定の「AI検索の準備」で索引を作成してください。")
                :method.IsTagCandidates?"この範囲に一致する未承認のAIタグ候補はありません。作品の詳細「AIタグ候補」から候補を生成・確認できます。"
                :method.IsAI&&query.Length>0?(!string.IsNullOrEmpty(result.SearchStatus)&&result.SearchStatus!="ready"
                    ?AISearchStatus.Guidance(result.SearchStatus,result.SearchCandidateTotal??0,result.IndexedTotal??0,query:query)
                    :result.SearchCandidateTotal>0&&result.IndexedTotal==0?AISearchStatus.Guidance(AISearchStatus.Unindexed,result.SearchCandidateTotal??0,result.IndexedTotal??0)
                    :result.SearchCandidateTotal==0?AISearchStatus.Guidance(AISearchStatus.OutOfScope)
                    :result.SearchStatus=="partially_indexed"&&result.Total==0?AISearchStatus.Guidance(AISearchStatus.PartiallyIndexed,result.SearchCandidateTotal??0,result.IndexedTotal??0)
                    :resultGroup==1&&result.GroupBoundary is null?"参考候補の区切りがありません。「すべてのAI候補」を選ぶか、画像の見た目／ファイル名・タグの意味で区切りを指定してください。"
                    :resultGroup==0&&result.OtherTotal>0?"区切り以上の候補はありません。類似度の区切りを下げるか、参考候補を表示してください。"
                    :AISearchStatus.Guidance(AISearchStatus.Ready,query:query))
                :query.Length>0?"候補がありません。検索条件やAI索引の状態を確認してください。":EmptyScopeGuidance();
            var explanation=
                method.IsPageText ? "抽出・保存済みのページ本文から、同一ページ内で全語一致する作品を検索しています。「本を開く」で先頭の一致ページへ移動できます。"+(scopeWarning is null?"":" "+scopeWarning)
                : method.IsTagSemantic ? "未承認の英語タグ候補を含む索引から、言葉の意味が近い作品を表示しています。確定タグとは混ざりません。類似度は正解率ではありません。承認・却下・再生成の後はAI索引を更新してください。"
                : method.IsTagCandidates ? "最新の生成履歴に未承認の候補がある作品を表示しています。確定タグにはまだ反映されていません。詳細の「AIタグ候補」から根拠を確認して承認・却下できます。"+(scopeWarning is null?"":" "+scopeWarning)
                : method.IsAI && query.Length>0 ? $"AI検索の候補です。{(result.CoverageLimit is int coverage ? $"最大{coverage:N0}件の対象から、" : "")}索引済みの作品を類似順に表示します。ファイル名・タグの一致とAI類似候補を区別しています。類似度・順位統合値は正解率ではありません。{(result.GroupBoundary is double cut?$" 上位候補{result.LeadingTotal:N0}件／参考候補{result.OtherTotal:N0}件（区切り{cut:F3}）。":" 類似度に明確な落差がない場合は自動で区切りません。画像の見た目とファイル名・タグの意味では区切りを手動指定できます。")}"+(scopeWarning is null?"":" "+scopeWarning)
                : method.IsAI ? "探したい内容を文章で入力してください。初回の準備は左下の「設定」→「AI検索の準備」から。"
                : "ファイル名・タグの文字検索。"+Protocol.DescribePartial(result.PartialWords)+Protocol.DescribeExpansions(result.Expansions)+(scopeWarning is null?"":" "+scopeWarning);
            var summary=method.IsPageText?(string.IsNullOrWhiteSpace(query)?"ページ本文に含まれる語句を入力してください。":$"ページ本文一致 {result.Total:N0}件")
                :method.IsTagSemantic?(result.PendingIndexRemaining is >0?$"未承認タグ候補 · 索引の更新が必要: {result.PendingIndexRemaining:N0}件":"未承認タグ候補の意味で検索しています。")
                :method.IsTagCandidates?"未承認の候補です。詳細から確認・承認できます。"
                :method.IsAI?(query.Length==0?"探したい内容を入力してください。"
                    :result.SearchStatus=="unindexed"?$"未索引（対象 {result.SearchCandidateTotal??0:N0}件）"
                    :result.SearchStatus=="out_of_scope"?"対象外（0件）"
                    :$"上位 {result.LeadingTotal:N0}件 · 参考 {result.OtherTotal:N0}件")
                :Protocol.DescribePartial(result.PartialWords)+Protocol.DescribeExpansions(result.Expansions);
            var noticeSeverity=scopeWarning is not null||result.PendingIndexRemaining is >0||(method.IsAI&&query.Length>0&&(result.SearchStatus is "unindexed" or "out_of_scope"||(result.SearchStatus=="partially_indexed"&&result.Total==0)))
                ?InfoBarSeverity.Warning:InfoBarSeverity.Informational;
            Notice(method.IsPageText?"ページ本文":method.IsTagCandidates?"タグ候補":method.IsAI?"AI検索":"検索結果",summary+(scopeWarning is null?"":" "+scopeWarning),noticeSeverity,explanation);
            if(origin is not null)
            {
                var guidance=SimilaritySearch.Guidance(result.SimilarityStatus,origin.Kind);
                Empty.Text=result.SimilarityStatus=="ready"
                    ?(result.SearchCandidateTotal is int cand&&cand>0&&result.IndexedTotal==0?$"この範囲の作品はまだAI索引が作成されていません（対象 {cand:N0}件・未索引）。設定の「AI検索の準備」から索引を作成してください。"
                    :result.SearchCandidateTotal==0?"この範囲（フォルダ・種類）に対象作品がありません。"
                    :"この範囲に索引済みの類似候補はありません。種類・フォルダ・AI対象を確認してください。")
                    :guidance;
                var originTitle=origin.Kind=="video"?"似た動画・素材":origin.Kind=="audio"?"似た音声・曲":"似た画像・表紙";
                var simSummary = result.SimilarityStatus != "ready"
                    ? guidance
                    : result.SearchCandidateTotal is int sc && sc > 0 && result.IndexedTotal == 0
                    ? $"未索引（対象 {sc:N0}件）"
                    : result.SearchCandidateTotal == 0
                    ? "対象外（0件）"
                    : $"{result.Total:N0}件の候補";
                var simSeverity = scopeWarning is not null || result.SimilarityStatus != "ready" || (result.SearchCandidateTotal is int sc2 && (sc2 == 0 || result.IndexedTotal == 0))
                    ? InfoBarSeverity.Warning
                    : InfoBarSeverity.Informational;
                Notice(originTitle,simSummary+(scopeWarning is null?"":" "+scopeWarning),simSeverity,guidance+(result.SearchComplete?" 選択範囲の索引済み作品全体から表示します。":result.CoverageLimit is int similarityLimit?$" 最大{similarityLimit:N0}件の対象から表示します。":""));
            }
            UpdateFavoriteRootList();startupSearchSucceeded=true;RecordNavigationLocation();UpdateGettingStarted();
        } catch(OperationCanceledException) when(cancellation.IsCancellationRequested) { if(searches.IsCurrent(version)&&rows.Count==0){GettingStarted.Visibility=Visibility.Collapsed;Empty.Visibility=Visibility.Visible;Empty.Text="検索を中断しました。もう一度「検索」を押してください。";} Notice("検索中断","検索を中断しました。",InfoBarSeverity.Informational,"ユーザーの操作により検索処理を中断しました。"); }
        catch(Exception ex) { if(searches.IsCurrent(version)){lastQuery=query;lastKind=selectedKind;lastMode=selectedMode;lastRoots=selectedRoots;lastLiteralOnly=literalOnly;lastBoundary=boundary;lastResultGroup=resultGroup;UpdateActiveSearchScopeBar();rows=[];active=null;if(!folderSettingsActive)Details.IsPaneOpen=false;DetailsButton.IsEnabled=false;detailCancellation?.Cancel();DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed;ItemTitle.Text="作品を選んでください";ItemPath.Text="";Tags.Text="";Shelf.Text="";Favorite.IsChecked=false;Reviewed.IsChecked=false;EditStatus.Text="";RenderRows();GettingStarted.Visibility=Visibility.Collapsed;Empty.Visibility=Visibility.Visible;Count.Text="—";PageNumber.Text="—";Previous.IsEnabled=false;Next.IsEnabled=false;Empty.Text=ex is ResultSessionException?"検索結果が更新されたか、有効期限が切れました。同じ条件で「検索」を押してください。":origin is not null?"類似検索を完了できませんでした。「元の検索に戻る」か、AI索引の対象を確認してください。":selectedMode is >0 and <4?(ex.Message.Contains("未導入")||ex.Message.Contains("ai_unavailable")||ex.Message.Contains("モデル設定またはAI索引を開けません")?"AI環境（モデル・Python）が未導入です。ファイル名・タグの文字検索、棚・整理、閲覧はそのまま利用できます。\n「設定」→「AI検索の準備」で導入手順を確認できます。":$"この条件ではAI検索を利用できません。\n{ex.Message}\nファイル名・タグ検索に切り替えるか、AI索引の設定を確認してください。"):"検索を完了できませんでした。検索フォルダや接続状態を確認してください。";Failure(ex);} }
        finally {if(searches.IsCurrent(version)){Busy.Visibility=Visibility.Collapsed;CancelSearchButton.Visibility=Visibility.Collapsed;Items.IsEnabled=true;}}
    }
    private string EmptyScopeGuidance()
    {
        if(Kind.SelectedIndex>0)return "現在の検索範囲・種類に一致する作品はありません。条件を変更してください。";
        if(selectedShelfIds is not null)return "この棚には作品がありません。作品の詳細で所属する棚を選択できます。";
        if(selectedSearchRoots is not null)return "選択したフォルダに表示できる作品がありません。スキャンや接続状態を確認するか、検索範囲を解除してください。";
        if(view=="history")return "閲覧履歴はありません。作品を開くと、ここに表示されます。";
        if(view=="favorites")return "お気に入りはまだありません。作品の右クリックメニューや詳細から登録できます。";
        return knownRoots.Count>0?"作品がありません。登録フォルダのスキャンや接続状態を確認してください。":"フォルダ管理からフォルダを登録し、スキャンしてください。";
    }
    private readonly Dictionary<ListViewItem, Action> containerCleanup = new();

    private static string RowKey(int id) => id.ToString(System.Globalization.CultureInfo.InvariantCulture);
    private MediaRow? RowForKey(object? key) => key is string value &&
        int.TryParse(value, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out var id)
        ? rows.FirstOrDefault(row => row.Id == id) : null;

    private void ReleaseContainer(ListViewItem item)
    {
        containerRefresh.Remove(item);
        if (containerCleanup.Remove(item, out var release)) release();
        if (item.ContentTemplateRoot is Border host) host.Child=null;
        item.ContextFlyout=null; item.Tag=null;
        AutomationProperties.SetAutomationId(item, "");
        AutomationProperties.SetName(item, "");
    }

    private void RenderRows()
    {
        renderCancellation.Cancel(); renderCancellation.Dispose(); renderCancellation = new();
        populating = true;
        try
        {
            foreach (var item in containerCleanup.Keys.ToArray()) ReleaseContainer(item);
            Items.ItemsSource=null;
            Items.ItemsPanel = MediaItemsPanel();
            // Only native strings cross the WinRT collection boundary. MediaRow stays
            // owned by C#; no reflection-based property binding or custom COM model.
            resultKeys.Clear();foreach(var row in rows)resultKeys.Add(RowKey(row.Id));
            Items.ItemsSource=resultKeys;
        }
        finally { populating = false; }
    }

    private void Items_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
    {
        if (args.ItemContainer is not ListViewItem item) return;
        ReleaseContainer(item);
        if (args.InRecycleQueue || disposed || RowForKey(args.Item) is not MediaRow row) return;
        if (item.ContentTemplateRoot is not Border host) return;
        args.Handled=true;
        var content = new Grid { Padding = new Thickness(8), ColumnSpacing = 12, RowSpacing = 8 };
        var image = new Image { Tag = row.Id, IsDoubleTapEnabled = true, Stretch = Stretch.Uniform };
        AutomationProperties.SetAutomationId(image, $"Preview{row.Id}");
        AutomationProperties.SetName(image, row.Title + "のサムネイル");
        image.DoubleTapped += async (_, args) => { args.Handled=true; await OpenPreviewAsync(row.Id); };
        if(ImageViewerPolicy.CanOpen(row)||ArchiveManifest.CanOpen(row)||VideoPlayerPolicy.CanOpen(row)||AudioPlayerPolicy.CanOpen(row))
            ToolTipService.SetToolTip(image,ImageViewerPolicy.CanOpen(row)?"ダブルクリックで画像を大きく表示":VideoPlayerPolicy.CanOpen(row)?"ダブルクリックで動画を再生":AudioPlayerPolicy.CanOpen(row)?"ダブルクリックで音声を再生":"ダブルクリックで本を開く");
        var text = new StackPanel { Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
        var title=new TextBlock { Text = (row.Favorite ? "★ " : "") + row.Title, TextTrimming = TextTrimming.CharacterEllipsis, Style = (Style)Resources["MediaTitleStyle"] };
        AutomationProperties.SetAutomationId(title,$"ItemTitle{row.Id}");text.Children.Add(title);
        ToolTipService.SetToolTip(title, row.Title);
        var availability = row.Availability == "present" ? "" : AvailabilityLabel(row.Availability);
        var tagSummary = string.Join("、", row.Tags);
        var metadata = tiles ? row.MatchLabel + availability
            : $"{row.MatchLabel}{KindLabel(row.Kind)}{(availability.Length > 0 ? " · " + availability : "")}{(tagSummary.Length > 0 ? " · " + tagSummary : "")}";
        if (!string.IsNullOrWhiteSpace(metadata))
            text.Children.Add(new TextBlock { Text = metadata, TextTrimming = TextTrimming.CharacterEllipsis, Style = (Style)Resources["MediaMetadataStyle"] });
        if(row.AIEvidence.Length>0){var evidence=new TextBlock {Text=row.AIEvidence,TextWrapping=TextWrapping.Wrap,MaxLines=2,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaMetadataStyle"]};AutomationProperties.SetAutomationId(evidence,$"AIEvidence{row.Id}");ToolTipService.SetToolTip(evidence,row.AIEvidence);text.Children.Add(evidence);}
        if(row.Proposal is ProposalMatch proposal){var prop=new TextBlock {Text=proposal.Summary,TextWrapping=TextWrapping.Wrap,MaxLines=2,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaMetadataStyle"]};AutomationProperties.SetAutomationId(prop,$"ProposalEvidence{row.Id}");ToolTipService.SetToolTip(prop,proposal.Summary);text.Children.Add(prop);}
        if(row.AIPage is AIPageMatch aiPage){var pimage=new TextBlock {Text=aiPage.Summary,TextWrapping=TextWrapping.Wrap,MaxLines=2,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaMetadataStyle"]};AutomationProperties.SetAutomationId(pimage,$"AIPageEvidence{row.Id}");ToolTipService.SetToolTip(pimage,aiPage.Summary);text.Children.Add(pimage);}
        if(row.PageText is PageTextMatch pageText){var ptext=new TextBlock {Text=pageText.Summary,TextWrapping=TextWrapping.Wrap,MaxLines=2,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaMetadataStyle"]};AutomationProperties.SetAutomationId(ptext,$"PageTextEvidence{row.Id}");ToolTipService.SetToolTip(ptext,pageText.Summary);text.Children.Add(ptext);}
        if(row.Evidence is {AllDirect:false}){var words=new TextBlock {Text=Protocol.DescribeEvidence(row.Evidence),TextWrapping=TextWrapping.Wrap,MaxLines=2,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaMetadataStyle"]};AutomationProperties.SetAutomationId(words,$"SearchEvidence{row.Id}");text.Children.Add(words);}
        var previewStatus = new TextBlock { Text = row.Availability == "present" && row.Kind is "image" or "book" or "archive" or "video" ? "読込中" : "プレビューなし", Style = (Style)Resources["MediaMetadataStyle"] };
        AutomationProperties.SetAutomationId(previewStatus, $"PreviewStatus{row.Id}");
        text.Children.Add(previewStatus);
        if (tiles)
        {
            content.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            content.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            Grid.SetRow(text, 1);
        }
        else
        {
            content.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            content.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Grid.SetColumn(text, 1);
        }
        content.Children.Add(image); content.Children.Add(text);
        SizeItem(item,image);
        item.Tag=row.Id;AutomationProperties.SetAutomationId(item, $"Item{row.Id}"); AutomationProperties.SetName(item, row.Title);
        item.ContextFlyout=SimilarityMenu(row);
        content.DoubleTapped+=async(_,args)=>{args.Handled=true;await OpenPreviewAsync(row.Id);};
        var renderToken = renderCancellation.Token;
        CancellationTokenSource? visible = null;
        var requestedEdge = 0;
        long thumbnailVersion = 0;
        async Task RefreshThumbnailAsync(bool force = false)
        {
            if (!image.IsLoaded || renderToken.IsCancellationRequested || disposed) return;
            var edge = ThumbnailPolicy.EdgeFor(image.Width, image.Height, XamlRoot?.RasterizationScale ?? 1);
            if (!force && requestedEdge == edge) return;
            requestedEdge = edge;
            var version = ++thumbnailVersion;
            visible?.Cancel(); visible?.Dispose(); visible = CancellationTokenSource.CreateLinkedTokenSource(renderToken);
            var cancellation = visible.Token;
            try
            {
                // Coalesce resize/slider events; keep the last image while a
                // larger derivative is prepared, and reject recycled replies.
                if (!force) await Task.Delay(80, cancellation);
                var bitmap = await thumbnails.GetAsync(row, cancellation, edge);
                if (cancellation.IsCancellationRequested || disposed || version != thumbnailVersion) return;
                image.Source = bitmap;
                previewStatus.Text = bitmap is null ? "プレビューなし" : "";
                previewStatus.Visibility = bitmap is null ? Visibility.Visible : Visibility.Collapsed;
            }
            catch (OperationCanceledException) { }
        }
        image.Loaded += async (_, _) => await RefreshThumbnailAsync(force: true);
        image.SizeChanged += async (_, _) => await RefreshThumbnailAsync();
        image.Unloaded += (_, _) => { ++thumbnailVersion; requestedEdge=0; visible?.Cancel();visible?.Dispose();visible=null;image.Source = null; };
        // Recycled containers must release requests before receiving another row.
        containerCleanup[item] = () =>
        {
            ++thumbnailVersion; requestedEdge=0;
            visible?.Cancel(); visible?.Dispose(); visible=null;
            image.Source=null;
        };
        containerRefresh[item] = () => _ = RefreshThumbnailAsync();
        // Wire loading/cancellation before the live template receives this image.
        host.Child=content;
    }
    private void SizeItem(ListViewItem item,Image image)
    {
        var scale=libraryItemScale/100d;
        var width=LibraryTileLayout.Width(Math.Max(1,(Items.ActualWidth>0?Items.ActualWidth:ItemListContainer.ActualWidth)-16),libraryItemScale);
        item.Width=tiles?width:double.NaN;
        image.Width=tiles?Math.Max(96,width-32):48*scale;
        // Leave room for the filename and metadata even in a short window.
        var height=Math.Max(48,ItemListContainer.ActualHeight-108);
        image.Height=tiles?Math.Min(144*scale,height):64*scale;
    }
    private void AttachXamlRoot()
    {
        if(XamlRoot is null||ReferenceEquals(trackedXamlRoot,XamlRoot))return;
        DetachXamlRoot();
        trackedXamlRoot=XamlRoot;
        lastObservedRasterizationScale=XamlRoot.RasterizationScale;
        trackedXamlRoot.Changed+=OnXamlRootChanged;
    }
    private void DetachXamlRoot()
    {
        if(trackedXamlRoot is not null)
        {
            trackedXamlRoot.Changed-=OnXamlRootChanged;
            trackedXamlRoot=null;
        }
    }
    private void OnXamlRootChanged(XamlRoot sender,XamlRootChangedEventArgs args)
    {
        if(disposed)return;
        var scale=sender.RasterizationScale;
        if(Math.Abs(scale-lastObservedRasterizationScale)>0.001)
        {
            lastObservedRasterizationScale=scale;
            itemSizeTimer.Stop();itemSizeTimer.Start();
        }
    }
    private void OnPageUnloaded(object sender,RoutedEventArgs e)
    {
        DetachXamlRoot();
        itemSizeTimer.Stop();
    }
    private void UpdateItemSizes()=>ReflowBrowse(UpdateItemSizesCore);
    private void UpdateItemSizesCore()
    {
        UpdateShelfItemSizes();
        if(Items.ItemsPanelRoot is ItemsWrapGrid wrap)
            wrap.ItemWidth=tiles?LibraryTileLayout.Width(Math.Max(1,Items.ActualWidth-16),libraryItemScale)+8:double.NaN;
        foreach(var item in containerCleanup.Keys.ToArray())
            if(item.ContentTemplateRoot is Border { Child: Grid content }&&content.Children.FirstOrDefault() is Image image)SizeItem(item,image);
        foreach(var refresh in containerRefresh.Values.ToArray())refresh();
        if(active is not null&&Details.IsPaneOpen&&DetailPreview.Visibility==Visibility.Visible)
            _ = ShowDetailPreviewAsync(active, preserveExisting: true);
    }
    private void ItemListContainer_SizeChanged(object sender,SizeChangedEventArgs args)
    {
        if(itemSizeReady)UpdateItemSizes();
    }
    private void ItemSizeSlider_ValueChanged(object sender,Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs args)
    {
        if(!itemSizeReady)return;
        var scale=ViewerInputSettings.NormalizeScale((int)Math.Round(args.NewValue/20)*20);
        if(libraryItemScale==scale)return;
        libraryItemScale=scale;ItemSizeLabel.Text=$"{scale}%";
        // Resize existing containers: keep selection, dirty edits and decoded thumbnails.
        UpdateItemSizes();itemSizeSaveTimer.Stop();itemSizeSaveTimer.Start();
    }
    private void ResetItemSize_Click(object sender,RoutedEventArgs args)=>ItemSizeSlider.Value=100;
    private void Library_PointerWheelChanged(object sender,PointerRoutedEventArgs args)
    {
        if(!itemSizeReady||dialogOpen||folderHubOpen)return;
        var properties=args.GetCurrentPoint(shelfHubOpen?ShelfList:ItemListContainer).Properties;
        if(properties.IsHorizontalMouseWheel)return;
        if((Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(Windows.System.VirtualKey.Control)&Windows.UI.Core.CoreVirtualKeyStates.Down)==0)
        {itemWheelDelta=0;return;}
        args.Handled=true;itemWheelDelta+=properties.MouseWheelDelta;
        var steps=itemWheelDelta/120;itemWheelDelta%=120;
        if(steps!=0)ItemSizeSlider.Value=Math.Clamp(libraryItemScale+steps*20,60,180);
    }
    private void SaveItemSize()
    {
        itemSizeSaveTimer.Stop();
        if(ViewerOptions.Value.LibraryItemScale==libraryItemScale)return;
        try{ViewerOptions.SaveLibraryItemScale(libraryItemScale);}
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException)
        {if(!disposed)Notice("表示サイズを保存できません",ex.Message,InfoBarSeverity.Warning);AppLog.Error(ex);}
    }
    private static string KindLabel(string kind) => kind switch { "book" => "本", "image" => "画像", "archive" => "ZIP", "video" => "動画", "audio" => "音楽", _ => "素材" };
    private MenuFlyout SimilarityMenu(MediaRow row)
    {
        var menu=new MenuFlyout();
        var favoriteAction=new MenuFlyoutItem{Text=row.Favorite?"お気に入りを解除":"お気に入りに登録"};
        AutomationProperties.SetAutomationId(favoriteAction,"ToggleFavorite"+row.Id);
        favoriteAction.Click+=async(_,_)=>await SetFavoriteAsync(row,!row.Favorite);
        menu.Items.Add(favoriteAction);menu.Items.Add(new MenuFlyoutSeparator());
        if(view=="history")
        {
            var remove=new MenuFlyoutItem{Text="閲覧履歴から削除"};AutomationProperties.SetAutomationId(remove,"RemoveHistory"+row.Id);
            remove.Click+=async(_,_)=>await DeleteHistoryAsync(row.Id);menu.Items.Add(remove);
        }
        if(SimilaritySearch.CanStart(row))
        {
            var search=new MenuFlyoutItem {Text=row.Kind=="video"?"似た動画・素材を探す":row.Kind=="audio"?"似た音声・曲を探す":"似た画像・素材を探す"};AutomationProperties.SetAutomationId(search,"FindSimilar"+row.Id);
            search.Click+=async(_,_)=>await StartSimilarityAsync(row);menu.Items.Add(search);menu.Items.Add(new MenuFlyoutSeparator());
        }
        if(ArchiveManifest.CanOpen(row))
        {
            var pages=new MenuFlyoutItem {Text="本のページをAI検索に追加…"};AutomationProperties.SetAutomationId(pages,"IndexBookPages"+row.Id);
            pages.Click+=async(_,_)=>await IndexBookPagesAsync(row);menu.Items.Add(pages);
            var batch=new MenuFlyoutItem {Text="複数の本をAI検索に追加…"};AutomationProperties.SetAutomationId(batch,"IndexBookBatch"+row.Id);
            batch.Click+=async(_,_)=>await IndexBookBatchAsync(row);menu.Items.Add(batch);
        }
        foreach(var (label,id,explorer) in new[]{("エクスプローラーで表示","ShowInExplorer",true),("既定のアプリで開く","OpenDefault",false)})
        {
            var action=new MenuFlyoutItem{Text=label,IsEnabled=row.Availability=="present"};AutomationProperties.SetAutomationId(action,id+row.Id);
            action.Click+=(_,_)=>OpenInShell(row,explorer);menu.Items.Add(action);
        }
        return menu;
    }
    private void ClearSimilarity()
    {
        similarityOrigin=null;similarityReturn=null;UpdateSearchMethod();
    }
    private async Task StartSimilarityAsync(MediaRow source)
    {
        if(!ready||disposed||saving||dialogOpen||!SimilaritySearch.CanStart(source)||!await transitions.WaitAsync(0))return;
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync())return;
            // Use the context-menu row, never whichever item happens to be selected.
            similarityReturn??=new(lastQuery,lastKind,lastMode,lastRoots?.ToArray(),lastLiteralOnly,lastBoundary,lastResultGroup,view,page,source.Id,selectedShelfIds?.ToArray());
            similarityOrigin=source;if(view=="history")view="all";page=0;UpdateSearchMethod();await LoadAsync();
        }
        finally{transitions.Release();if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void SimilarityBack_Click(object sender,RoutedEventArgs e)
    {
        if(returningFromSimilarity||disposed||dialogOpen||saving||similarityReturn is null)return;
        returningFromSimilarity=true;searchTimer.Stop();
        // A loading transition already passed the discard guard and disabled
        // editing. Do not ask about the old, already discarded draft again.
        var wasLoading=Busy.Visibility==Visibility.Visible;
        if(wasLoading){searches.Next();similarityCancellation?.Cancel();}
        await transitions.WaitAsync();
        try
        {
            if(disposed||(!wasLoading&&!await ConfirmDiscardAsync())||similarityReturn is not SearchBookmark bookmark)return;
            populating=true;
            Query.Text=bookmark.Query;Kind.SelectedIndex=bookmark.Kind;SearchMode.SelectedIndex=bookmark.Mode;
            RestoreSearchRoots(bookmark.Roots);AIMatchedOnly.IsChecked=bookmark.LiteralOnly;
            SimilarityBoundary.Value=bookmark.Boundary??double.NaN;AIResultGroup.SelectedIndex=bookmark.Group;
            SetShelfScope(bookmark.Shelves);view=bookmark.View;page=bookmark.Page;ClearSimilarity();RestoreNavigation();populating=false;
            await LoadAsync();
            await FocusRowAsync(bookmark.Selection);
        }
        finally
        {
            populating=false;returningFromSimilarity=false;
            if(!disposed){Busy.Visibility=Visibility.Collapsed;Items.IsEnabled=true;}
            transitions.Release();
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async Task FocusRowAsync(int itemId)
    {
        var key=Items.Items.OfType<string>().FirstOrDefault(value=>value==RowKey(itemId));
        if(key is null)return;
        for(var attempt=0;attempt<10&&!disposed&&Items.IsEnabled;attempt++)
        {
            Items.UpdateLayout();
            Items.ScrollIntoView(key);
            Items.UpdateLayout();
            if(Items.ContainerFromItem(key) is ListViewItem target&&target.IsLoaded&&target.Focus(FocusState.Keyboard)&&target.FocusState!=FocusState.Unfocused)return;
            await Task.Delay(30);
        }
    }
    private static string AvailabilityLabel(string state) => state switch { "present" => "登録済み", "missing" => "ファイル不明", "unavailable" => "接続・更新を確認", _ => state };
    private int detailPreviewId;
    private int detailRequestedEdge;
    private async Task ShowDetailPreviewAsync(MediaRow row, bool preserveExisting = false)
    {
        var edge = ThumbnailPolicy.EdgeFor(Math.Max(160, Math.Max(DetailPreview.ActualWidth, Editor.ActualWidth)), Math.Max(160, DetailPreview.ActualHeight), XamlRoot?.RasterizationScale ?? 1);
        if (preserveExisting && detailPreviewId == row.Id && detailRequestedEdge == edge && DetailPreview.Source is not null)
            return;
        detailCancellation?.Cancel(); detailCancellation?.Dispose();
        detailCancellation = new CancellationTokenSource(); var cancellation = detailCancellation.Token;
        detailPreviewId = row.Id;
        detailRequestedEdge = edge;
        if (!preserveExisting)
        {
            DetailPreview.Source = null; DetailPreview.Visibility = Visibility.Collapsed;
        }
        try
        {
            var image = await thumbnails.GetAsync(row, cancellation, edge);
            if (cancellation.IsCancellationRequested || active?.Id != row.Id || disposed) return;
            DetailPreview.Source = image; DetailPreview.Visibility = image is null ? Visibility.Collapsed : Visibility.Visible;
        }
        catch (OperationCanceledException) { }
    }
    private async Task NavigateAsync(int nextPage,bool normalSearch=false) {
        if(!ready||saving||!await transitions.WaitAsync(0))return;
        try {
            if(!await ConfirmDiscardAsync()){populating=true;Query.Text=lastQuery;Kind.SelectedIndex=lastKind;SearchMode.SelectedIndex=lastMode;RestoreSearchRoots(lastRoots);AIMatchedOnly.IsChecked=lastLiteralOnly;SimilarityBoundary.Value=lastBoundary??double.NaN;AIResultGroup.SelectedIndex=lastResultGroup;UpdateSearchMethod();populating=false;return;}
            var reuse=!normalSearch&&!PendingSearch&&nextPage!=page;
            if(normalSearch||Query.Text!=lastQuery||SearchMode.SelectedIndex!=lastMode)ClearSimilarity();
            page=nextPage;await LoadAsync(reuseSession: reuse);
        }finally{transitions.Release();if((PendingSearch)&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void Items_Changed(object sender,SelectionChangedEventArgs e) {
        if(populating||!ready)return;
        var index=RowForKey(Items.SelectedItem) is MediaRow selected ? rows.FindIndex(row=>row.Id==selected.Id) : -1;
        if(index<0||index>=rows.Count||active?.Id==rows[index].Id)return;
        if(saving||!await transitions.WaitAsync(0)){RestoreSelection();return;}
        try {
            if(!await ConfirmDiscardAsync()){RestoreSelection();return;}
            ShowItemDetailsPane();
            ApplySelectedRow(rows[index]);
        }finally{transitions.Release();}
    }
    private void ApplySelectedRow(MediaRow row)
    {
        var previous=populating;populating=true;
        try
        {
            active=row; editingShelfIds=active.ShelfIds.ToArray();saved=new(string.Join(", ",active.Tags),active.Shelf,active.Favorite,active.Reviewed){ShelfIds=editingShelfIds.ToArray()};
            Tags.Text=saved.Tags;UpdateShelfEditorLabel();Favorite.IsChecked=saved.Favorite;Reviewed.IsChecked=saved.Reviewed;
            ItemTitle.Text=active.Title;ItemPath.Text=active.LocationLabel;UpdateFileProperties();Editor.IsEnabled=true;DetailsButton.IsEnabled=true;Details.IsPaneOpen=true;
            DetailPreview.ContextFlyout=SimilarityMenu(active);
            UpdateDirty();
            _ = ShowDetailPreviewAsync(active);
        }
        finally{populating=previous;}
    }
    private void RestoreSelection(){populating=true;Items.SelectedItem=active is null?null:Items.Items.OfType<string>().FirstOrDefault(key=>key==RowKey(active.Id));populating=false;}
    private void UpdateDirty()
    {
        if(!ready)return;
        var blocked=active is not null&&tagReviewSyncItem==active.Id;
        Tags.IsEnabled=Shelf.IsEnabled=ChooseShelvesButton.IsEnabled=Favorite.IsEnabled=Reviewed.IsEnabled=!blocked;
        UpdateDetailActions();
        if(blocked)
        {
            EditStatus.Text="承認後のタグを確認できません。AIタグ候補を開き直してください。";
            Save.IsEnabled=false;
            return;
        }
        EditStatus.Text=Dirty?"未保存の変更":"保存済み";
        Save.IsEnabled=active is not null&&Dirty&&!saving;
    }
    private void UpdateDetailActions()
    {
        // Keep unavailable-media actions visible but disabled. Other media's
        // commands do not occupy space or keyboard stops in this editor.
        OpenImage.Visibility=active?.Kind=="image"?Visibility.Visible:Visibility.Collapsed;
        OpenBook.Visibility=active is {Kind: "book" or "archive"}?Visibility.Visible:Visibility.Collapsed;
        OpenVideo.Visibility=active?.Kind=="video"?Visibility.Visible:Visibility.Collapsed;
        OpenAudio.Visibility=active?.Kind=="audio"?Visibility.Visible:Visibility.Collapsed;
        OpenImage.IsEnabled=active is not null&&ImageViewerPolicy.CanOpen(active);
        OpenBook.IsEnabled=active is not null&&ArchiveManifest.CanOpen(active);
        OpenVideo.IsEnabled=active is not null&&VideoPlayerPolicy.CanOpen(active);
        OpenAudio.IsEnabled=active is not null&&AudioPlayerPolicy.CanOpen(active);
        var canReview=active is not null&&TagReviewProtocol.CanOpen(active);
        TagSuggestionsButton.Visibility=canReview?Visibility.Visible:Visibility.Collapsed;
        TagSuggestionsButton.IsEnabled=canReview&&!saving;
        AudioSearchHint.Text=SimilaritySearch.AudioIndexingGuidance;
        AudioSearchHint.Visibility=active?.Kind=="audio"?Visibility.Visible:Visibility.Collapsed;
    }
    private void Editor_Changed(object sender,TextChangedEventArgs e)=>UpdateDirty();
    private async void Favorite_Checked(object sender,RoutedEventArgs args)
    {
        if(!ready||populating||updatingFavorite||active is null||Favorite.IsChecked==saved.Favorite)return;
        await SetFavoriteAsync(active,Favorite.IsChecked==true);
    }
    private async Task SetFavoriteAsync(MediaRow row,bool value)
    {
        if(saving||dialogOpen||tagReviewSyncItem==row.Id||!await transitions.WaitAsync(0))
        {
            if(active?.Id==row.Id){updatingFavorite=true;try{Favorite.IsChecked=saved.Favorite;}finally{updatingFavorite=false;}}
            return;
        }
        saving=true;Favorite.IsEnabled=false;
        try
        {
            // Save only the flag: an unsaved tag/shelf draft must not be committed.
            await api.PostAsync("api/items/update",new JsonObject{{"ids",new JsonArray(row.Id)},{"changes",new JsonObject{{"favorite",value}}}});
            row.Favorite=value;
            if(active?.Id==row.Id)
            {
                saved=saved with {Favorite=value};active.Favorite=value;updatingFavorite=true;
                try{Favorite.IsChecked=value;}finally{updatingFavorite=false;}
            }
            await RefreshResultRowsAfterEditAsync();
        }
        catch(Exception ex)
        {
            if(active?.Id==row.Id){updatingFavorite=true;try{Favorite.IsChecked=saved.Favorite;}finally{updatingFavorite=false;}}
            Failure(ex);
        }
        finally{saving=false;Favorite.IsEnabled=true;UpdateDirty();transitions.Release();}
    }
    private void Editor_Checked(object sender,RoutedEventArgs e)=>UpdateDirty();
    public async Task<bool> ConfirmDiscardAsync() {
        if(saving||dialogOpen)return false;
        RememberCurrentLocation();
        if(!Dirty&&!FolderDirty)return true;
        dialogOpen=true;
        try {
            var content=Dirty?active?.Title:FolderTargetTitle.Text;
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="変更を破棄しますか？",Content=content,PrimaryButtonText="変更を破棄",CloseButtonText="編集を続ける",DefaultButton=ContentDialogButton.Close};
            var accepted=await dialog.ShowAsync()==ContentDialogResult.Primary;
            if(accepted&&Dirty)
            {
                var previous=populating;populating=true;
                try
                {
                    Tags.Text=saved.Tags;editingShelfIds=saved.ShelfIds?.ToArray()??[];UpdateShelfEditorLabel();
                    Favorite.IsChecked=saved.Favorite;Reviewed.IsChecked=saved.Reviewed;
                }
                finally{populating=previous;}
                UpdateDirty();
            }
            if(accepted&&FolderDirty&&folderDraft is not null)
            {
                var ids=folderDraft.TargetIds.ToArray();
                folderDraft=null;
                OpenFolderSettingsPanel(ids);
            }
            return accepted;
        }finally{dialogOpen=false;}
    }
    private async Task SaveAsync() {
        if(active is null||saving||dialogOpen||tagReviewSyncItem==active.Id||!Dirty)return;
        var snapshot=Current();var error=snapshot.Validate();
        if(error is not null){EditStatus.Text=error;return;}
        // Disabling the editor moves WinUI focus elsewhere. Restore only an
        // editor control, and only if the user has not chosen another control
        // while the request was pending. Never take focus from another window.
        var focused=FocusManager.GetFocusedElement(XamlRoot) as Control;
        var restore=focused==Tags||focused==Shelf||focused==ChooseShelvesButton||focused==Favorite||focused==Reviewed||focused==Save;
        var focusState=focused?.FocusState==FocusState.Keyboard?FocusState.Keyboard:FocusState.Programmatic;
        saving=true;Editor.IsEnabled=false;var id=active.Id;
        var displacedFocus=FocusManager.GetFocusedElement(XamlRoot);
        try {
            await api.SaveAsync(id,snapshot);
            saved=snapshot;active.Tags=snapshot.ParsedTags;active.Shelf=snapshot.Shelf;active.ShelfIds=snapshot.ShelfIds?.ToArray()??[];active.Favorite=snapshot.Favorite;active.Reviewed=snapshot.Reviewed;
            EditStatus.Text="保存しました";Notice("保存しました");await RefreshResultRowsAfterEditAsync();
        }catch(Exception ex){Failure(ex);EditStatus.Text="保存できませんでした。変更内容は残っています。";}
        finally
        {
            var unchangedFocus=ReferenceEquals(displacedFocus,FocusManager.GetFocusedElement(XamlRoot));
            saving=false;Editor.IsEnabled=true;Save.IsEnabled=Dirty;
            if(!disposed&&active?.Id==id&&Details.IsPaneOpen&&restore&&unchangedFocus)
            {
                // A successful save disables Save; continue at the tag field.
                var target=focused==Save&&!Save.IsEnabled?Tags:focused;
                target?.Focus(focusState);
            }
            if(PendingSearch){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void Save_Click(object sender,RoutedEventArgs e)=>await SaveAsync();
    private async void SaveShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){e.Handled=true;await SaveAsync();}
    private void SearchShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){e.Handled=true;if(ready&&!dialogOpen)Query.Focus(FocusState.Keyboard);}
    private void Query_Changed(object sender,TextChangedEventArgs e){if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private async void Search_Click(object sender,RoutedEventArgs e){searchTimer.Stop();await NavigateAsync(0,true);}
    private void CancelSearch_Click(object sender,RoutedEventArgs e){searchTimer.Stop();similarityCancellation?.Cancel();}
    private void CancelSearchShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){if(Busy.Visibility==Visibility.Visible||searchTimer.IsRunning){e.Handled=true;searchTimer.Stop();similarityCancellation?.Cancel();}else if(Details.IsPaneOpen&&!folderSettingsActive){e.Handled=true;Details.IsPaneOpen=false;}}
    private void UpdateSearchMethod()
    {
        // SelectionChanged also runs during initialization and dirty-state rollback.
        if(Query is null || SearchMethodHint is null || SimilarityBar is null || SimilarityTitle is null)return;
        var method=SearchMethod.FromIndex(Math.Clamp(SearchMode.SelectedIndex,0,6));
        SearchMode.IsEnabled=view!="history";
        var similar=similarityOrigin is not null;
        SimilarityBar.Visibility=similar?Visibility.Visible:Visibility.Collapsed;
        SimilarityTitle.Text=similar?"類似検索の起点: "+similarityOrigin!.Title:"";
        var ai=method.IsAI&&!similar;
        SearchOptions.Visibility=ai?Visibility.Visible:Visibility.Collapsed;
        var candidates=method.IsTagCandidates&&!similar;
        var pageText=method.IsPageText&&!similar;
        AutomationProperties.SetName(Query,pageText?"ページ本文の検索":candidates?"未承認タグ候補の検索":method.IsAI?"AI検索の文章":"ファイル名・タグ検索");
        SimilarityBoundary.Visibility=!similar&&SearchMode.SelectedIndex is 2 or 3?Visibility.Visible:Visibility.Collapsed;
        AIResultGroup.Visibility=ai?Visibility.Visible:Visibility.Collapsed;
        AIMatchedOnly.Visibility=ai?Visibility.Visible:Visibility.Collapsed;
        Query.PlaceholderText=method.IsTagSemantic?"例：青髪のツインテール（未承認タグの意味）":pageText?"ページ本文に含まれる語句で検索":candidates?"未承認の候補タグ名で絞り込み（空欄で全未承認候補）":method.IsAI?"探したい内容を文章で入力":"ファイル名・タグを検索（Ctrl+F）";
        SearchMethodHint.Text=similar?(similarityOrigin?.Kind=="video"?"動画の代表フレームから似た候補を探しています。検索語の入力や「検索」で通常の検索に戻ります。":similarityOrigin?.Kind=="audio"?"音声・音楽の音響特徴から似た候補を探しています。検索語の入力や「検索」で通常の検索に戻ります。":"画像・表紙から似た候補を探しています。検索語の入力や「検索」で通常の検索に戻ります。"):SearchMode.SelectedIndex switch
        {
            1=>"ファイル名・タグの意味と、画像・表紙の見た目を組み合わせます。",
            2=>"索引済みの画像・表紙・本のページや、動画の代表場面を見た目から探します。",
            3=>"名前やタグの言い換えで探すときに使います。本の本文・音声の文字起こしは対象外です。",
            4=>"未承認のAIタグ候補（最新履歴）だけを検索します。確定タグとは混ざりません。",
            5=>"抽出・保存済みのページ本文（同じページ内の全語一致）を検索します。",
            6=>"英語を含む未承認タグ候補を、日本語の意味で探します。先にAI索引を作成してください。",
            _=>"ファイル名・タグに含まれる文字で探します。"
        };
    }
    private void SearchMode_Changed(object sender,SelectionChangedEventArgs e)
    {
        UpdateSearchMethod();
        similarityCancellation?.Cancel();
        if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}
    }
    private void AIMatchedOnly_Changed(object sender,RoutedEventArgs e){similarityCancellation?.Cancel();if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private void Kind_Changed(object sender,SelectionChangedEventArgs e){similarityCancellation?.Cancel();if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private async void Previous_Click(object sender,RoutedEventArgs e)=>await NavigateAsync(PreviousBrowsePage());
    private async void Next_Click(object sender,RoutedEventArgs e)=>await NavigateAsync(NextBrowsePage());
    private void RestoreNavigation()
    {
        populating=true;
        Nav.SelectedItem=folderHubOpen
            ? FolderNavigation
            : shelfHubOpen||selectedShelfIds is not null
            ? Nav.MenuItems.OfType<NavigationViewItem>().First(x=>x.Tag?.ToString()=="shelf")
            : Nav.MenuItems.OfType<NavigationViewItem>().FirstOrDefault(x=>x.Tag?.ToString()==view) ?? Nav.MenuItems.OfType<NavigationViewItem>().First();
        UnreviewedOnly.IsChecked=view=="unreviewed";
        UnreviewedOnly.IsEnabled=view is "all" or "unreviewed";
        populating=false;
    }
    private async void Nav_SelectionChanged(NavigationView sender,NavigationViewSelectionChangedEventArgs args)
    {
        if(!ready||populating||args.SelectedItem is not NavigationViewItem item)return;
        var next=item.Tag?.ToString()??"";
        if(next=="folders"){await OpenFolderHubAsync();return;}
        if(next=="shelf"){await OpenShelfHubAsync();return;}
        if(next is not ("all" or "favorites" or "unreviewed" or "shelf" or "history"))return;
        if(saving||dialogOpen||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            CloseShelfHubCore();SetShelfScope(null);
            CloseFolderHubCore();
            populating=true;
            if(next=="history"){historyReturnMode=SearchMode.SelectedIndex;SearchMode.SelectedIndex=0;}
            else if(view=="history")SearchMode.SelectedIndex=historyReturnMode;
            populating=false;
            ClearSimilarity();view=next;page=0;RestoreNavigation();UpdateSearchMethod();await LoadAsync();
        }
        finally { transitions.Release();if((PendingSearch)&&!disposed){searchTimer.Stop();searchTimer.Start();} }
    }
    private void Layout_Click(object sender,RoutedEventArgs e){if(extending||saving||dialogOpen)return;tiles=!tiles;LayoutButton.Content=ShelfLayoutButton.Content=tiles?"リスト表示":"グリッド表示";if(shelfHubOpen)RenderShelfLayout();else ReflowBrowse(()=>{RenderRows();RestoreSelection();});}
    private void OpenDetails_Click(object sender,RoutedEventArgs e)
    {
        if(folderHubOpen)
        {
            if(folderSettingsActive)Details.IsPaneOpen=true;
            return;
        }
        if(active is not null){ShowItemDetailsPane();Details.IsPaneOpen=true;}
    }
    private async void PreviewPointerPressed(object sender,PointerRoutedEventArgs e)
    {
        if(disposed||dialogOpen||saving){previewClicks.Reset();return;}
        var point=e.GetCurrentPoint(this);if(!point.Properties.IsLeftButtonPressed){previewClicks.Reset();return;}
        int? sourceId=null;
        for(var source=e.OriginalSource as DependencyObject;source is not null;source=VisualTreeHelper.GetParent(source))
        {
            if(source==DetailPreview){sourceId=active?.Id;break;}
            if(source is Image {Tag:int id}){sourceId=id;break;}
        }
        var scale=Math.Max(.1,XamlRoot.RasterizationScale);
        var target=previewClicks.Register(sourceId,Environment.TickCount64,point.Position.X,point.Position.Y,
            GetDoubleClickTime(),GetSystemMetrics(36)/scale,GetSystemMetrics(37)/scale);
        if(target is int itemId){e.Handled=true;await OpenPreviewAsync(itemId);}
    }
    private async void DetailPreview_DoubleTapped(object sender,DoubleTappedRoutedEventArgs e)
    { if(active is null)return;e.Handled=true;await OpenPreviewAsync(active.Id); }
    private async Task OpenPreviewAsync(int itemId)
    {
        // The first click uses the normal selection/discard guard. Never open
        // a different or stale result if selection is pending or was cancelled.
        if(disposed||saving||dialogOpen||active?.Id!=itemId)return;
        if(ImageViewerPolicy.CanOpen(active))await OpenImageAsync();
        else if(ArchiveManifest.CanOpen(active))await OpenBookAsync();
        else if(VideoPlayerPolicy.CanOpen(active))await OpenVideoAsync();
        else if(AudioPlayerPolicy.CanOpen(active))await OpenAudioAsync();
    }
    private async void OpenImage_Click(object sender,RoutedEventArgs e)=>await OpenImageAsync();
    private async Task OpenImageAsync()
    {
        if(active is null||!ImageViewerPolicy.CanOpen(active)||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;searchTimer.Stop();var itemId=active.Id;var detailsWereOpen=Details.IsPaneOpen;
        var session=resultSession;
        int? lastOpened=null;var lastOrdinal=0;
        try
        {
            if(session is null)throw new InvalidOperationException("同じ条件で検索し直してから画像を開いてください。");
            var selectedIndex=rows.FindIndex(row=>row.Id==itemId);
            if(resultsNeedRefresh||selectedIndex<0)throw new InvalidOperationException("検索結果が変わりました。一覧から作品を選び直してください。");
            var ordinal=checked(browseStart+selectedIndex);
            var sequence=new ImageViewerSequence(active,ordinal,session.Total,session.NeighborAsync);
            var viewer=new ImageViewerView(api,sequence);imageViewer=viewer;
            var window=new ViewerWindow(viewer,"画像ビューア","ImageViewerDialog");viewerWindow=window;
            viewer.ContentOpened+=id=>{lastOpened=id;lastOrdinal=sequence.Position;RecordContentOpened(id);};
            viewer.CloseRequested+=(_,_)=>window.Close();viewer.AttachNavigation(viewer);
            window.Closed+=(_,_)=>viewer.Dispose();
            await window.ShowAsync(viewer.OpenAsync);
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            imageViewer?.Dispose();imageViewer=null;viewerWindow=null;dialogOpen=false;
            try
            {
                if(!disposed&&lastOpened is int target&&session is not null)
                    await RestoreViewerSelectionAsync(target,lastOrdinal,session,detailsWereOpen);
                if(!disposed&&detailsWereOpen&&active?.Id==itemId){Details.IsPaneOpen=true;OpenImage.Focus(FocusState.Programmatic);}
            }
            catch(Exception ex){if(!disposed)Failure(ex);}
            finally{transitions.Release();}
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void OpenBook_Click(object sender,RoutedEventArgs e)=>await OpenBookAsync();
    private async void OpenVideo_Click(object sender,RoutedEventArgs e)=>await OpenVideoAsync();
    private async Task OpenVideoAsync()
    {
        if(active is null||!VideoPlayerPolicy.CanOpen(active)||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;searchTimer.Stop();var itemId=active.Id;var detailsWereOpen=Details.IsPaneOpen;
        try
        {
            var player=new VideoPlayerView(api,active.Id,active.Title,active.VideoMatchMs);videoPlayer=player;
            var window=new ViewerWindow(player,"動画再生","VideoPlayerDialog");viewerWindow=window;
            player.ContentOpened+=RecordContentOpened;
            player.CloseRequested+=(_,_)=>window.Close();player.AttachNavigation(player);
            window.Closed+=(_,_)=>player.Dispose();
            await window.ShowAsync(player.OpenAsync);
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            videoPlayer?.Dispose();videoPlayer=null;viewerWindow=null;dialogOpen=false;
            try{if(!disposed&&detailsWereOpen&&active?.Id==itemId){Details.IsPaneOpen=true;OpenVideo.Focus(FocusState.Programmatic);}}
            finally{transitions.Release();}
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void OpenAudio_Click(object sender,RoutedEventArgs e)=>await OpenAudioAsync();
    private async Task OpenAudioAsync()
    {
        if(active is null||!AudioPlayerPolicy.CanOpen(active)||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;searchTimer.Stop();var itemId=active.Id;var detailsWereOpen=Details.IsPaneOpen;
        try
        {
            var player=new VideoPlayerView(api,active.Id,active.Title,active.AudioMatchMs??active.VideoMatchMs,isAudio:true);videoPlayer=player;
            var window=new ViewerWindow(player,"音声再生","AudioPlayerDialog");viewerWindow=window;
            player.ContentOpened+=RecordContentOpened;
            player.CloseRequested+=(_,_)=>window.Close();player.AttachNavigation(player);
            window.Closed+=(_,_)=>player.Dispose();
            await window.ShowAsync(player.OpenAsync);
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            videoPlayer?.Dispose();videoPlayer=null;viewerWindow=null;dialogOpen=false;
            try{if(!disposed&&detailsWereOpen&&active?.Id==itemId){Details.IsPaneOpen=true;OpenAudio.Focus(FocusState.Programmatic);}}
            finally{transitions.Release();}
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async Task OpenBookAsync()
    {
        if(active is null||!ArchiveManifest.CanOpen(active)||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        // Opening a book neither saves nor discards the current metadata draft.
        dialogOpen=true;searchTimer.Stop();
        var readerItemId=active.Id;var detailsWereOpen=Details.IsPaneOpen;
        try
        {
            var reader=new ArchiveReaderView(api,active.Id,active.Title,active.PageText,active.AIPage);readerView=reader;
            var window=new ViewerWindow(reader,"読書画面","ArchiveReaderDialog");viewerWindow=window;
            window.BeforeCloseAsync=reader.FlushProgressAsync;
            reader.ContentOpened+=RecordContentOpened;
            reader.CloseRequested+=(_,_)=>window.Close();reader.AttachNavigation(reader);
            window.Closed+=(_,_)=>reader.Dispose();
            await window.ShowAsync(reader.OpenAsync);
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            readerView?.Dispose();readerView=null;viewerWindow=null;dialogOpen=false;
            try
            {
                // Switching to the narrow overlay can close the pane while
                // reading. Restore the same item's editor and unsaved draft.
                if(!disposed&&detailsWereOpen&&active?.Id==readerItemId)
                {
                    Details.IsPaneOpen=true;OpenBook.Focus(FocusState.Programmatic);
                }
            }
            finally{transitions.Release();}
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void CloseDetails_Click(object sender,RoutedEventArgs e)=>await CloseDetailsAsync();
    private async void Detail_KeyDown(object sender,KeyRoutedEventArgs e)
    {
        // Only unhandled Escape inside the editor. Popups and ContentDialogs
        // keep their own Escape behavior; background controls are unaffected.
        if(e.Handled || e.Key!=Windows.System.VirtualKey.Escape || dialogOpen || !Details.IsPaneOpen)return;
        e.Handled=true;
        await CloseDetailsAsync();
    }
    private async Task CloseDetailsAsync()
    {
        if(!ready || saving || dialogOpen || !Details.IsPaneOpen || !await transitions.WaitAsync(0))return;
        try
        {
            // Hiding the editor is a layout action. Keep its selected item,
            // draft and saved baseline; navigation/exit retain discard guards.
            Details.IsPaneOpen=false;
            if(folderSettingsActive)FolderList.Focus(FocusState.Keyboard);
            else Items.Focus(FocusState.Keyboard);
        }
        finally{transitions.Release();}
    }
    private async void TagSuggestions_Click(object sender,RoutedEventArgs e)
    {
        if(active is null||!TagReviewProtocol.CanOpen(active)||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        var id=active.Id;var detailsWereOpen=Details.IsPaneOpen;dialogOpen=true;searchTimer.Stop();
        var root=XamlRoot;Windows.Foundation.TypedEventHandler<XamlRoot,XamlRootChangedEventArgs> rootChanged=(_,_)=>tagReview?.Fit(root.Size.Width,root.Size.Height);
        root.Changed+=rootChanged;
        try
        {
            if(tagReviewSyncItem==id)await SyncTagReviewAsync(id);
            tagReview=new TagSuggestionsView(api.TagReviews,id,Dirty){RequestedTheme=ActualTheme};tagReview.Fit(root.Size.Width,root.Size.Height);
            var dialog=new ContentDialog{RequestedTheme=ActualTheme,XamlRoot=XamlRoot,Title="AIタグ候補",Content=tagReview,CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,FullSizeDesired=true};
            dialog.Resources["ContentDialogMaxWidth"]=720d;
            var closeStyle=new Style(typeof(Button));closeStyle.Setters.Add(new Setter(AutomationProperties.AutomationIdProperty,"TagClose"));dialog.CloseButtonStyle=closeStyle;
            tagReview.CloseReady+=()=>dialog.Hide();
            dialog.Closing+=(_,args)=>{if(tagReview?.Busy==true){args.Cancel=true;tagReview.RequestClose();}};
            var shown=dialog.ShowAsync();await tagReview.LoadAsync();await shown;
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally
        {
            root.Changed-=rootChanged;
            var sync=tagReview?.ApprovalAttempted==true;
            tagReview?.Dispose();tagReview=null;
            try{if(sync&&!disposed){tagReviewSyncItem=id;await SyncTagReviewAsync(id);}}
            catch(Exception ex){if(!disposed)Failure(ex);}
            finally{dialogOpen=false;transitions.Release();if(!disposed){if(detailsWereOpen&&active?.Id==id)Details.IsPaneOpen=true;UpdateDirty();if(PendingSearch)searchTimer.Start();}}
        }
    }
    private async Task SyncTagReviewAsync(int id)
    {
        var fresh=await api.TagReviews.ItemAsync(id,CancellationToken.None);
        if(disposed||active?.Id!=id)return;
        active.Tags=fresh.Tags;active.Shelf=fresh.Shelf;active.ShelfIds=fresh.ShelfIds.ToArray();active.Favorite=fresh.Favorite;active.Reviewed=fresh.Reviewed;
        editingShelfIds=fresh.ShelfIds.ToArray();Tags.Text=string.Join(", ",fresh.Tags);UpdateShelfEditorLabel();Favorite.IsChecked=fresh.Favorite;Reviewed.IsChecked=fresh.Reviewed;
        saved=Current();tagReviewSyncItem=null;await RefreshResultRowsAfterEditAsync();
    }
    private void UpdateNavigationLayout(double width)
    {
        if(width<=0)return;
        var expanded=width>=1000;
        Nav.PaneDisplayMode=expanded?NavigationViewPaneDisplayMode.Left:NavigationViewPaneDisplayMode.LeftCompact;
        Nav.IsPaneOpen=expanded;
    }
    private void Page_SizeChanged(object sender,SizeChangedEventArgs e)
    {
        tagReview?.Fit(e.NewSize.Width,e.NewSize.Height);
        if(Details is null || ViewTools is null)return;
        UpdateNavigationLayout(e.NewSize.Width);
        Details.DisplayMode=e.NewSize.Width<1000?SplitViewDisplayMode.Overlay:SplitViewDisplayMode.Inline;
        Details.OpenPaneLength=Math.Min(320,Math.Max(240,e.NewSize.Width-64));
        if(active is null&&!folderSettingsActive)Details.IsPaneOpen=false;
        UpdateDetailLayout();
    }
    private void LibraryLayout_SizeChanged(object sender,SizeChangedEventArgs e)
    {
        if(ViewTools is null)return;
        // Inline details reduce the actual toolbar width independently of the
        // window width; choose wrapping from the content's measured space.
        var narrow=e.NewSize.Width<840;
        Grid.SetRow(ViewTools,narrow?1:0);Grid.SetColumn(ViewTools,narrow?0:1);Grid.SetColumnSpan(ViewTools,narrow?2:1);
        ViewTools.HorizontalAlignment=narrow?HorizontalAlignment.Left:HorizontalAlignment.Right;
        ViewTools.Margin=narrow?new Thickness(0,8,0,0):new Thickness(0);
        UpdateFolderLayout();
        UpdateDetailLayout();
    }

    private void FolderHub_SizeChanged(object sender,SizeChangedEventArgs args)=>UpdateFolderLayout();
    private void UpdateFolderLayout()
    {
        if(FolderSelectionButtons is null||FolderAddScroll is null)return;
        var narrow=LibraryLayout.ActualWidth<840;
        for(var i=0;i<4;i++)FolderSelectionButtons.ColumnDefinitions[i].Width=i<2||!narrow?GridLength.Auto:new GridLength(0);
        var buttons=new[]{SearchSelectedFoldersButton,EditSelectedFoldersButton,UnregisterSelectedFoldersButton,SearchAllFoldersButton};
        for(var i=0;i<buttons.Length;i++){Grid.SetColumn(buttons[i],narrow?i%2:i);Grid.SetRow(buttons[i],narrow?i/2:0);}
        FolderAddScroll.MaxHeight=Math.Max(96,FolderHubView.ActualHeight-FolderHeader.ActualHeight-FolderSelectionPanel.ActualHeight-64);
    }

    private void Details_PaneStateChanged(object sender,object args)=>UpdateDetailLayout();

    private void UpdateDetailLayout()
    {
        if(Details is null||LibraryLayout is null)return;
        var gap=Details.IsPaneOpen&&Details.DisplayMode==SplitViewDisplayMode.Inline?16:0;
        if(LibraryLayout.Margin.Right!=gap)LibraryLayout.Margin=new Thickness(0,0,gap,0);
        // Overlay panes must also occlude the content at their outer edge;
        // antialiasing there otherwise exposes a sliver of the Search button.
        LibraryLayout.Clip=Details.IsPaneOpen&&Details.DisplayMode==SplitViewDisplayMode.Overlay
            ?new RectangleGeometry{Rect=new Windows.Foundation.Rect(0,0,Math.Max(0,LibraryLayout.ActualWidth-Details.OpenPaneLength),LibraryLayout.ActualHeight)}
            :null;
    }

    private void ShowItemDetailsPane()
    {
        folderSettingsActive=false;folderDraft=null;
        DetailPaneTitle.Text="詳細と整理";
        FolderEditorPanel.Visibility=Visibility.Collapsed;
        Editor.Visibility=Visibility.Visible;
    }

    private void CloseFolderHubCore()
    {
        scanPollTimer.Stop();
        folderHubOpen=false;
        MainViewTitle.Text="ライブラリ";
        RootsButton.Content="フォルダ管理";
        FolderHubView.Visibility=Visibility.Collapsed;
        ItemSearchRow.Visibility=Visibility.Visible;
        SearchTools.Visibility=Visibility.Visible;
        ItemListContainer.Visibility=Visibility.Visible;
        ItemPagerRow.Visibility=Visibility.Visible;
        ShowItemDetailsPane();
        Details.IsPaneOpen=active is not null;
    }

    private async void Roots_Click(object sender,RoutedEventArgs e)
    {
        if(folderHubOpen)await ReturnToLibraryAsync(selectedSearchRoots);
        else await OpenFolderHubAsync();
    }

    private async void BackToLibrary_Click(object sender,RoutedEventArgs e)=>await ReturnToLibraryAsync(selectedSearchRoots);

    private async void ResetAllFolders_Click(object sender,RoutedEventArgs e)=>await ReturnToLibraryAsync(null);

    private async void SearchSelectedFolders_Click(object sender,RoutedEventArgs e)
    {
        var activeIds=knownRoots.Where(r=>r.Enabled&&checkedFolderIds.Contains(r.Id)).Select(r=>r.Id).Order().ToArray();
        if(activeIds.Length==0)return;
        await ReturnToLibraryAsync(activeIds);
    }

    private async Task ReturnToLibraryAsync(IReadOnlyList<int>? targetRoots,bool allItems=false)
    {
        if(dialogOpen||saving||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            var changed=!SameRoots(selectedSearchRoots,targetRoots)||selectedShelfIds is not null||allItems;
            if(allItems){view="all";ClearSimilarity();UpdateSearchMethod();}
            SetShelfScope(null);
            RestoreSearchRoots(targetRoots);
            CloseFolderHubCore();
            RestoreNavigation();
            if(changed)page=0;
            await LoadAsync();
        }
        finally{transitions.Release();if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }

    private async Task OpenFolderHubAsync(int? focusRootId=null,bool restoreInactive=false)
    {
        if(dialogOpen||saving||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            CloseShelfHubCore();
            await RefreshSearchRootsAsync();
            if(checkedFolderIds.Count==0&&selectedSearchRoots is not null)
                foreach(var id in selectedSearchRoots.Where(id=>knownRoots.Any(r=>r.Enabled&&r.Id==id)))
                    checkedFolderIds.Add(id);
            folderHubOpen=true;
            await PollScanStateAsync();
            MainViewTitle.Text="登録フォルダ";
            RootsButton.Content="作品一覧へ戻る";
            ItemSearchRow.Visibility=Visibility.Collapsed;
            SearchTools.Visibility=Visibility.Collapsed;
            ItemListContainer.Visibility=Visibility.Collapsed;
            ItemPagerRow.Visibility=Visibility.Collapsed;
            FolderHubView.Visibility=Visibility.Visible;
            RestoreNavigation();
            RenderFolderHub();
            scanPollTimer.Start();
            if(focusRootId is int targetId)
            {
                var row=knownRoots.FirstOrDefault(r=>r.Id==targetId);
                if(row is not null)
                {
                    if(restoreInactive||!row.Enabled)PrefillRestoreRoot(row);
                    else OpenFolderSettingsPanel(new[]{row.Id});
                }
            }
            Notice("登録フォルダ管理","検索するフォルダを選んだり、登録内容を変更できます。");
            RecordNavigationLocation();
        }
        catch(Exception ex){Failure(ex);}
        finally{transitions.Release();}
    }

    private void PopulateAddFolderShelves()
    {
        if(AddRootInitialShelf is null)return;
        var before=folderPopulating;folderPopulating=true;
        try
        {
            var previous=(AddRootInitialShelf.SelectedItem as ComboBoxItem)?.Content?.ToString();
            AddRootInitialShelf.Items.Clear();
            AddRootInitialShelf.Items.Add(new ComboBoxItem {Content="棚なし",Tag="none"});
            AddRootInitialShelf.Items.Add(new ComboBoxItem {Content="新しい棚を作成",Tag="new"});
            foreach(var shelf in knownShelves)AddRootInitialShelf.Items.Add(new ComboBoxItem {Content=shelf,Tag="existing"});
            AddRootInitialShelf.SelectedItem=AddRootInitialShelf.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Content?.ToString()==previous) ?? AddRootInitialShelf.Items[0];
            AddRootNewShelf.IsEnabled=(AddRootInitialShelf.SelectedItem as ComboBoxItem)?.Tag?.ToString()=="new";
        }
        finally{folderPopulating=before;}
    }

    private void AddRootInitialShelf_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(AddRootNewShelf is null)return;
        AddRootNewShelf.IsEnabled=(AddRootInitialShelf.SelectedItem as ComboBoxItem)?.Tag?.ToString()=="new";
    }

    private void ToggleAddFolder_Click(object sender,RoutedEventArgs e)
    {
        FolderAddPanel.Visibility=FolderAddPanel.Visibility==Visibility.Visible?Visibility.Collapsed:Visibility.Visible;
    }

    private async void ChooseFolder_Click(object sender,RoutedEventArgs e)
    {
        try
        {
            var picker=new FolderPicker();picker.FileTypeFilter.Add("*");
            WinRT.Interop.InitializeWithWindow.Initialize(picker,WinRT.Interop.WindowNative.GetWindowHandle(MainWindow.Current));
            var selected=await picker.PickSingleFolderAsync();
            if(selected is not null)RootPath.Text=selected.Path;
        }
        catch(Exception ex){Failure(ex);}
    }

    private string ReadInitialShelf(ComboBox box,TextBox newBox)
    {
        var choice=box.SelectedItem as ComboBoxItem;
        if(choice?.Tag?.ToString()=="new")
            return string.IsNullOrWhiteSpace(newBox.Text)?throw new InvalidOperationException("新しい棚の名前を入力してください。"):newBox.Text.Trim();
        return choice?.Tag?.ToString()=="existing"?choice.Content?.ToString()??"":"";
    }

    private async void AddRoot_Click(object sender,RoutedEventArgs e)
    {
        AddRoot.IsEnabled=false;
        try
        {
            var shelf=ReadInitialShelf(AddRootInitialShelf,AddRootNewShelf);
            var patterns=new JsonArray(AddRootExcludes.Text.Split(',',StringSplitOptions.RemoveEmptyEntries|StringSplitOptions.TrimEntries).Select(s=>(JsonNode?)JsonValue.Create(s)).ToArray());
            var added=await api.PostAsync("api/library/roots",new JsonObject{{"path",RootPath.Text},{"consent",true},{"excludes",patterns},{"default_shelf",shelf},{"folder_books",RootFolderBooks.IsChecked==true},{"recursive",RootRecursive.IsChecked==true}});
            // The server answers {"root_id": n}; reading "id" never reopened the settings panel.
            var newId=(added["root_id"]??added["id"])?.GetValue<int>();
            RootPath.Text="";AddRootExcludes.Text="";AddRootNewShelf.Text="";RootFolderBooks.IsChecked=false;RootRecursive.IsChecked=true;AddRootInitialShelf.SelectedIndex=0;
            await RefreshSearchRootsAsync();
            await LoadAIScopeAsync();
            if(newId is int id&&knownRoots.Any(r=>r.Enabled&&r.Id==id))OpenFolderSettingsPanel(new[]{id});
            ScanStatus.Text="登録しました。スキャンすると一覧に反映されます。";
            Notice("フォルダを登録しました","登録しました。スキャンすると一覧に反映されます。");
        }
        catch(Exception ex){ScanStatus.Text=ex.Message;Failure(ex);}
        finally{AddRoot.IsEnabled=true;}
    }

    private void PrefillRestoreRoot(RegisteredRootRow row)
    {
        FolderAddPanel.Visibility=Visibility.Visible;
        RootPath.Text=row.Path;
        AddRootExcludes.Text=string.Join(", ",row.Exclusions);
        RootFolderBooks.IsChecked=row.FolderBooks;RootRecursive.IsChecked=row.Recursive;
        PopulateAddFolderShelves();
        if(row.DefaultShelf.Length==0)AddRootInitialShelf.SelectedIndex=0;
        else
        {
            var existing=AddRootInitialShelf.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Tag?.ToString()=="existing"&&x.Content?.ToString()==row.DefaultShelf);
            if(existing is not null)AddRootInitialShelf.SelectedItem=existing;
            else{AddRootInitialShelf.SelectedIndex=1;AddRootNewShelf.Text=row.DefaultShelf;AddRootNewShelf.IsEnabled=true;}
        }
        RootPath.Focus(FocusState.Programmatic);
    }

    private void FolderFilter_Changed(object sender,TextChangedEventArgs e){if(ready&&folderHubOpen&&!folderPopulating)RenderFolderHub();}
    private async void FolderStateFilter_Changed(object sender,SelectionChangedEventArgs e){if(ready&&folderHubOpen&&!folderPopulating)await RefreshSearchRootsAsync();}
    private void FolderLayout_Click(object sender,RoutedEventArgs e)
    {
        folderTiles=!folderTiles;
        FolderLayoutButton.Content=folderTiles?"リスト表示":"グリッド表示";
        RenderFolderHub();
    }

    private IReadOnlyList<RegisteredRootRow> FilteredFolders()
    {
        var q=(FolderFilterBox?.Text??"").Trim();
        var state=FolderStateFilter?.SelectedIndex??0;
        return knownRoots.Where(r=>
            (state==3?r.Enabled&&r.Favorite:state==0?r.Enabled:state==2?!r.Enabled:true)&&
            (q.Length==0||r.Name.Contains(q,StringComparison.OrdinalIgnoreCase)||r.Path.Contains(q,StringComparison.OrdinalIgnoreCase)||r.ShortPath.Contains(q,StringComparison.OrdinalIgnoreCase))).ToArray();
    }

    private void RenderFolderHub()
    {
        if(FolderList is null)return;
        folderPopulating=true;
        try
        {
            var visible=FilteredFolders();
            Count.Text=$"{visible.Count:N0} フォルダ";
            FolderList.Items.Clear();
            FolderList.ItemsPanel=(ItemsPanelTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load(folderTiles
                ? "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsWrapGrid Orientation=\"Horizontal\" CacheLength=\"1\"/></ItemsPanelTemplate>"
                : "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsStackPanel CacheLength=\"1\"/></ItemsPanelTemplate>");
            foreach(var row in visible)
            {
                var card=new Grid {Padding=new Thickness(10),ColumnSpacing=12,RowSpacing=8};
                ToolTipService.SetToolTip(card,row.Path);
                var check=new CheckBox
                {
                    IsEnabled=row.Enabled,
                    IsChecked=row.Enabled&&checkedFolderIds.Contains(row.Id),
                    VerticalAlignment=VerticalAlignment.Center,
                    MinWidth=28
                };
                AutomationProperties.SetAutomationId(check,$"ChkFolder{row.Id}");
                AutomationProperties.SetName(check,$"{row.ShortPath}を選択");
                check.Checked+=(_,_)=>{if(folderPopulating)return;if(checkedFolderIds.Count<FolderSearch.MaxRoots)checkedFolderIds.Add(row.Id);else check.IsChecked=false;UpdateFolderSelectionBar();};
                check.Unchecked+=(_,_)=>{if(folderPopulating)return;checkedFolderIds.Remove(row.Id);UpdateFolderSelectionBar();};

                var info=new StackPanel {Spacing=4,VerticalAlignment=VerticalAlignment.Center};
                var titleText=new TextBlock {Text=$"{row.Name}（{row.ShortPath}）",TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaTitleStyle"]};
                AutomationProperties.SetAutomationId(titleText,$"FolderTitle{row.Id}");
                info.Children.Add(titleText);
                var metaText=new TextBlock
                {
                    Text=$"{row.StatusLabel} · {row.ShelfLabel}"+(!row.Recursive?" · 直下のみ":"")+(row.FolderBooks?" · 一冊モード":"")+(row.Exclusions.Count>0?$" · 除外 {row.Exclusions.Count}件":""),
                    TextWrapping=TextWrapping.Wrap,
                    Style=(Style)Resources["MediaMetadataStyle"]
                };
                AutomationProperties.SetAutomationId(metaText,$"FolderMeta{row.Id}");
                info.Children.Add(metaText);
                var pathText=new TextBlock {Text=row.Path,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaMetadataStyle"]};
                info.Children.Add(pathText);

                var actions=new StackPanel {Orientation=Orientation.Horizontal,Spacing=8,VerticalAlignment=VerticalAlignment.Center};
                var favoriteButton=new Button{Content=row.Favorite?"★":"☆"};
                AutomationProperties.SetAutomationId(favoriteButton,$"FavoriteFolder{row.Id}");
                AutomationProperties.SetName(favoriteButton,$"{row.ShortPath}：{(row.Favorite?"お気に入りから外す":"お気に入りに追加")}");
                ToolTipService.SetToolTip(favoriteButton,row.Favorite?"お気に入りから外す":"お気に入りに追加");
                favoriteButton.Click+=async(_,_)=>await SetRootFavoriteAsync(row,!row.Favorite);actions.Children.Add(favoriteButton);
                if(row.Enabled)
                {
                    var openBtn=new Button {Content="フォルダを開く"};
                    AutomationProperties.SetAutomationId(openBtn,$"OpenFolder{row.Id}");
                    AutomationProperties.SetName(openBtn,$"{row.ShortPath}のフォルダを開く");
                    openBtn.Click+=async(_,_)=>await ReturnToLibraryAsync(new[]{row.Id});
                    var configBtn=new Button {Content="設定"};
                    AutomationProperties.SetAutomationId(configBtn,$"ConfigFolder{row.Id}");
                    AutomationProperties.SetName(configBtn,$"{row.ShortPath}の設定");
                    configBtn.Click+=async(_,_)=>await SelectFolderForSettingsAsync(new[]{row.Id},false);
                    actions.Children.Add(openBtn);
                    actions.Children.Add(configBtn);
                }
                else
                {
                    var restoreBtn=new Button {Content="再登録"};
                    AutomationProperties.SetAutomationId(restoreBtn,$"RestoreFolder{row.Id}");
                    AutomationProperties.SetName(restoreBtn,$"{row.ShortPath}を再登録");
                    restoreBtn.Click+=async(_,_)=>await RestoreRootAsync(row);
                    var purgeBtn=new Button {Content="記録を完全削除"};
                    AutomationProperties.SetAutomationId(purgeBtn,$"PurgeFolder{row.Id}");
                    AutomationProperties.SetName(purgeBtn,$"{row.ShortPath}の記録を完全削除");
                    purgeBtn.Click+=async(_,_)=>await PurgeInactiveRootAsync(row);
                    actions.Children.Add(restoreBtn);
                    actions.Children.Add(purgeBtn);
                }

                if(folderTiles)
                {
                    card.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
                    card.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
                    card.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
                    var topRow=new Grid {ColumnSpacing=8};
                    topRow.ColumnDefinitions.Add(new ColumnDefinition {Width=GridLength.Auto});
                    topRow.ColumnDefinitions.Add(new ColumnDefinition {Width=new GridLength(1,GridUnitType.Star)});
                    topRow.Children.Add(check);Grid.SetColumn(info,1);topRow.Children.Add(info);
                    card.Children.Add(topRow);
                    Grid.SetRow(actions,1);card.Children.Add(actions);
                }
                else
                {
                    card.ColumnDefinitions.Add(new ColumnDefinition {Width=GridLength.Auto});
                    card.ColumnDefinitions.Add(new ColumnDefinition {Width=new GridLength(1,GridUnitType.Star)});
                    card.ColumnDefinitions.Add(new ColumnDefinition {Width=GridLength.Auto});
                    card.Children.Add(check);Grid.SetColumn(info,1);card.Children.Add(info);Grid.SetColumn(actions,2);card.Children.Add(actions);
                }

                var item=new ListViewItem
                {
                    Content=card,
                    Style=(Style)Resources["MediaItemCardStyle"],
                    Tag=row.Id,
                    Width=folderTiles?296:double.NaN,
                    HorizontalContentAlignment=HorizontalAlignment.Stretch
                };
                item.Tapped+=async(_,args)=>{if(row.Enabled&&!IsFolderActionSource(args.OriginalSource)){args.Handled=true;await SelectFolderForSettingsAsync(new[]{row.Id},false);}};
                item.DoubleTapped+=async(_,args)=>{if(row.Enabled&&!IsFolderActionSource(args.OriginalSource)){args.Handled=true;await ReturnToLibraryAsync(new[]{row.Id});}};
                AutomationProperties.SetAutomationId(item,$"FolderItem{row.Id}");
                AutomationProperties.SetName(item,$"{row.Name} ({row.ShortPath})");
                var menu=new MenuFlyout();
                var favoriteMenu=new MenuFlyoutItem{Text=row.Favorite?"お気に入りから外す":"お気に入りに追加"};
                AutomationProperties.SetAutomationId(favoriteMenu,$"MenuFavoriteFolder{row.Id}");
                favoriteMenu.Click+=async(_,_)=>await SetRootFavoriteAsync(row,!row.Favorite);menu.Items.Add(favoriteMenu);
                if(row.Enabled)
                {
                    var manageItem=new MenuFlyoutItem {Text="設定・初期棚・スキャン"};
                    AutomationProperties.SetAutomationId(manageItem,$"ManageRoot{row.Id}");
                    manageItem.Click+=async(_,_)=>await SelectFolderForSettingsAsync(new[]{row.Id},false);
                    var browseItem=new MenuFlyoutItem {Text="フォルダを開く"};
                    AutomationProperties.SetAutomationId(browseItem,$"BrowseRoot{row.Id}");
                    browseItem.Click+=async(_,_)=>await ReturnToLibraryAsync(new[]{row.Id});
                    var toggleItem=new MenuFlyoutItem {Text=checkedFolderIds.Contains(row.Id)?"今回の検索対象から外す":"今回の検索対象に含める"};
                    AutomationProperties.SetAutomationId(toggleItem,$"ToggleSearchRoot{row.Id}");
                    toggleItem.Click+=(_,_)=>{if(checkedFolderIds.Contains(row.Id))checkedFolderIds.Remove(row.Id);else if(checkedFolderIds.Count<FolderSearch.MaxRoots)checkedFolderIds.Add(row.Id);RenderFolderHub();};
                    menu.Items.Add(manageItem);menu.Items.Add(browseItem);menu.Items.Add(toggleItem);
                }
                else
                {
                    var restoreItem=new MenuFlyoutItem {Text="再登録"};
                    AutomationProperties.SetAutomationId(restoreItem,$"ManageRoot{row.Id}");
                    restoreItem.Click+=async(_,_)=>await RestoreRootAsync(row);
                    var purgeItem=new MenuFlyoutItem {Text="記録を完全削除"};
                    AutomationProperties.SetAutomationId(purgeItem,$"PurgeRoot{row.Id}");
                    purgeItem.Click+=async(_,_)=>await PurgeInactiveRootAsync(row);
                    menu.Items.Add(restoreItem);menu.Items.Add(purgeItem);
                }
                item.ContextFlyout=menu;
                FolderList.Items.Add(item);
            }
            FolderEmpty.Visibility=visible.Count==0?Visibility.Visible:Visibility.Collapsed;
            UpdateFolderSelectionBar();
        }
        finally{folderPopulating=false;}
    }

    private void UpdateFolderSelectionBar()
    {
        if(FolderSelectionSummary is null||SearchSelectedFoldersButton is null||EditSelectedFoldersButton is null||UnregisterSelectedFoldersButton is null)return;
        var selectedRows=knownRoots.Where(r=>r.Enabled&&checkedFolderIds.Contains(r.Id)).OrderBy(r=>r.Id).ToArray();
        var count=selectedRows.Length;
        if(count==0)
        {
            FolderSelectionSummary.Text="フォルダを選ぶと、まとめて検索や設定ができます。";
            SearchSelectedFoldersButton.Content="選択したフォルダを検索";
            SearchSelectedFoldersButton.IsEnabled=false;
            EditSelectedFoldersButton.IsEnabled=false;
            UnregisterSelectedFoldersButton.IsEnabled=false;
        }
        else
        {
            var names=string.Join("、",selectedRows.Take(3).Select(r=>r.ShortPath))+(count>3?$" ほか{count-3}件":"");
            FolderSelectionSummary.Text=$"選択中: {count} フォルダ（{names}）";
            SearchSelectedFoldersButton.Content=$"選択した {count} フォルダを検索";
            SearchSelectedFoldersButton.IsEnabled=true;
            EditSelectedFoldersButton.IsEnabled=true;
            UnregisterSelectedFoldersButton.IsEnabled=true;
        }
    }

    private async void EditSelectedFolders_Click(object sender,RoutedEventArgs e)
    {
        var ids=knownRoots.Where(r=>r.Enabled&&checkedFolderIds.Contains(r.Id)).Select(r=>r.Id).Order().ToArray();
        if(ids.Length>0)await SelectFolderForSettingsAsync(ids,false);
    }

    private async void UnregisterSelectedFolders_Click(object sender,RoutedEventArgs e)
    {
        var ids=knownRoots.Where(r=>r.Enabled&&checkedFolderIds.Contains(r.Id)).Select(r=>r.Id).Order().ToArray();
        if(ids.Length>0)await SelectFolderForSettingsAsync(ids,true);
    }

    private async Task SelectFolderForSettingsAsync(IReadOnlyList<int> targetIds,bool focusUnregister)
    {
        if(dialogOpen||saving||!await transitions.WaitAsync(0))return;
        try
        {
            if(folderSettingsActive&&folderDraft is not null&&!folderDraft.TargetIds.SequenceEqual(targetIds))
                if(!await ConfirmDiscardAsync())return;
            OpenFolderSettingsPanel(targetIds,focusUnregister);
        }
        finally{transitions.Release();}
    }

    private void OpenFolderSettingsPanel(IReadOnlyList<int> targetIds,bool focusUnregister=false)
    {
        var targets=knownRoots.Where(r=>r.Enabled&&targetIds.Contains(r.Id)).OrderBy(r=>r.Id).ToArray();
        if(targets.Length==0)return;
        folderSettingsActive=true;
        folderDraft=new FolderSettingsDraft(targets);
        folderPopulating=true;
        try
        {
            DetailPaneTitle.Text=folderDraft.IsBatch?$"一括設定（{targets.Length}件）":"フォルダの設定";
            Editor.Visibility=Visibility.Collapsed;
            FolderEditorPanel.Visibility=Visibility.Visible;
            Details.IsPaneOpen=true;
            FolderList.SelectedItem=FolderList.Items.OfType<ListViewItem>().FirstOrDefault(i=>i.Tag is int id&&targetIds.Contains(id));
            DetailsButton.IsEnabled=true;
            FolderTargetTitle.Text=folderDraft.IsBatch
                ? $"選択した {targets.Length} フォルダ: {string.Join("、",targets.Select(r=>r.ShortPath))}"
                : targets[0].ShortPath;
            FolderTargetPath.Text=string.Join("\n",targets.Select(r=>$"{r.Path}（{(r.Online?"接続OK":"未接続")}・{r.PresentCount:N0}件）"));
            CurrentShelfSummary.Text=$"現在の初期棚: {folderDraft.Summary.DisplayText}";
            RootInitialShelf.Items.Clear();
            if(folderDraft.IsBatch)
                RootInitialShelf.Items.Add(new ComboBoxItem {Content=folderDraft.Summary.IsMixed?"複数の設定値（変更しない）":$"変更しない（現在: {folderDraft.Summary.DisplayText}）",Tag="keep"});
            RootInitialShelf.Items.Add(new ComboBoxItem {Content="棚なし",Tag="none"});
            RootInitialShelf.Items.Add(new ComboBoxItem {Content="新しい棚を作成",Tag="new"});
            foreach(var shelf in knownShelves)
                RootInitialShelf.Items.Add(new ComboBoxItem {Content=shelf,Tag="existing"});
            if(folderDraft.IsBatch)
            {
                RootInitialShelf.SelectedIndex=0;
                RootNewShelf.Text="";RootNewShelf.IsEnabled=false;
            }
            else
            {
                var current=targets[0].DefaultShelf;
                if(current.Length==0){RootInitialShelf.SelectedIndex=0;RootNewShelf.Text="";RootNewShelf.IsEnabled=false;}
                else
                {
                    var match=RootInitialShelf.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Tag?.ToString()=="existing"&&x.Content?.ToString()==current);
                    if(match is not null){RootInitialShelf.SelectedItem=match;RootNewShelf.Text="";RootNewShelf.IsEnabled=false;}
                    else{RootInitialShelf.SelectedIndex=1;RootNewShelf.Text=current;RootNewShelf.IsEnabled=true;}
                }
            }
            if(folderDraft.ShelfIdsToSave is {} selectedShelves)ShowRootShelfSelection(selectedShelves);
            FillUnsetShelf.IsChecked=false;
            SingleRootSection.Visibility=folderDraft.IsBatch?Visibility.Collapsed:Visibility.Visible;
            RootExcludes.Text=folderDraft.ExclusionsText;
            SaveRootShelf.Content=folderDraft.IsBatch?$"選択した {targets.Length} フォルダの初期棚を保存":"選択フォルダの初期棚を保存";
            UnregisterTargetText.Text=$"登録解除の対象: {string.Join("、",targets.Select(r=>r.ShortPath))}（{targets.Length} フォルダ）";
            UnregisterConsent.IsChecked=false;
            UnregisterRoot.IsEnabled=false;
            UnregisterRoot.Content=folderDraft.IsBatch?$"選択した {targets.Length} フォルダの登録を解除":"選択フォルダの登録を解除";
            UpdateFolderDraftState();
            if(focusUnregister)UnregisterConsent.Focus(FocusState.Programmatic);
        }
        finally{folderPopulating=false;UpdateFolderDraftState();}
    }

    private void SyncFolderDraftFromControls()
    {
        if(folderPopulating||folderDraft is null)return;
        var choice=RootInitialShelf.SelectedItem as ComboBoxItem;
        var tag=choice?.Tag?.ToString()??"none";
        folderDraft.ShelfMode=tag switch
        {
            "keep" or "multiple"=>BatchShelfMode.KeepExisting,
            "new"=>BatchShelfMode.NewShelf,
            "existing"=>BatchShelfMode.ExistingShelf,
            _=>BatchShelfMode.ClearToNone
        };
        folderDraft.SelectedExistingShelf=tag=="existing"?choice?.Content?.ToString()??"":"";
        folderDraft.NewShelfName=RootNewShelf.Text;
        folderDraft.FillUnset=FillUnsetShelf.IsChecked==true;
        if(!folderDraft.IsBatch)folderDraft.ExclusionsText=RootExcludes.Text;
    }

    private void UpdateFolderDraftState()
    {
        if(folderPopulating||folderDraft is null||FolderEditStatus is null)return;
        SyncFolderDraftFromControls();
        FolderEditStatus.Text=folderDraft.IsDirty?"未保存の設定変更":"設定保存済み";
    }

    private void RootInitialShelf_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(RootNewShelf is null)return;
        var tag=(RootInitialShelf.SelectedItem as ComboBoxItem)?.Tag?.ToString();
        RootNewShelf.IsEnabled=tag=="new";
        if(!folderPopulating&&folderDraft is not null&&tag!="multiple")folderDraft.ClearShelfIdSelection();
        UpdateFolderDraftState();
    }

    private void FolderEditor_Changed(object sender,TextChangedEventArgs e)=>UpdateFolderDraftState();
    private void FolderEditor_Checked(object sender,RoutedEventArgs e)=>UpdateFolderDraftState();
    private void UnregisterConsent_Changed(object sender,RoutedEventArgs e)
    {
        if(UnregisterRoot is not null)UnregisterRoot.IsEnabled=UnregisterConsent.IsChecked==true;
    }

    private async void SaveRootShelf_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||saving||dialogOpen)return;
        SyncFolderDraftFromControls();var draft=folderDraft;
        if(!draft.IsShelfChanged){FolderEditStatus.Text="初期棚の変更はありません。";return;}
        SaveRootShelf.IsEnabled=false;FolderEditorPanel.IsEnabled=false;saving=true;FolderEditStatus.Text="初期棚を保存しています…";
        try
        {
            var ids=draft.ShelfIdsToSave?.ToArray();
            if(ids is null)
            {
                var name=draft.ResolveShelfToSave();if(name is null)return;
                if(name.Length==0)ids=[];
                else
                {
                    var shelf=shelfDescriptors.FirstOrDefault(s=>s.Name==name);
                    if(shelf is null)
                    {
                        var id=await api.Shelves.CreateAsync(name);shelf=new ShelfDescriptor(id,name,0);
                        shelfDescriptors=shelfDescriptors.Append(shelf).ToArray();knownShelves=shelfDescriptors.Select(s=>s.Name).ToArray();
                    }
                    ids=new[]{shelf.Id};
                }
                draft.SelectShelfIds(ids);ShowRootShelfSelection(ids);
            }
            var targets=draft.TargetIds.ToArray();var pendingExcludes=draft.IsExclusionsChanged?draft.ExclusionsText:null;
            var result=await api.SetRootShelvesAsync(targets,ids,draft.FillUnset);
            var primary=ids.Length==0?"":ShelfName(ids.Min());
            knownRoots=knownRoots.Select(root=>targets.Contains(root.Id)?root with{DefaultShelf=primary,ShelfIds=ids.ToArray()}:root).ToArray();
            resultsNeedRefresh=true;OpenFolderSettingsPanel(targets);
            if(pendingExcludes is not null){RootExcludes.Text=pendingExcludes;UpdateFolderDraftState();}
            FolderEditStatus.Text=$"初期棚を保存しました。棚未設定の作品 {result["updated"]?.GetValue<int>()??0:N0} 件に適用しました。"+(pendingExcludes is null?"":"除外ルールは未保存です。");
            ScanStatus.Text=FolderEditStatus.Text;
            try{await RefreshSearchRootsAsync();}
            catch(Exception ex){AppLog.Error(ex);FolderEditStatus.Text="初期棚は保存済みです。一覧を更新できなかったため、再接続してください。";}
        }
        catch(Exception ex){Failure(ex);FolderEditStatus.Text="初期棚を保存できませんでした。選択内容は残っています。";}
        finally{saving=false;SaveRootShelf.IsEnabled=true;FolderEditorPanel.IsEnabled=true;}
    }

    private async void SaveExcludes_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||folderDraft.IsBatch||folderDraft.TargetIds.Count!=1||saving)return;
        SyncFolderDraftFromControls();
        SaveExcludes.IsEnabled=false;saving=true;
        try
        {
            var rootId=folderDraft.TargetIds[0];
            var patterns=new JsonArray(folderDraft.ParseExclusions().Select(s=>(JsonNode?)JsonValue.Create(s)).ToArray());
            await api.PostAsync("api/library/excludes",new JsonObject{{"root_id",rootId},{"patterns",patterns}});
            await RefreshSearchRootsAsync();
            OpenFolderSettingsPanel(new[]{rootId});
            ScanStatus.Text="除外を更新。次回スキャンで反映します。";
            FolderEditStatus.Text="除外ルールを保存しました。";
        }
        catch(Exception ex){ScanStatus.Text=ex.Message;FolderEditStatus.Text=ex.Message;}
        finally{saving=false;SaveExcludes.IsEnabled=true;}
    }

    private async void ScanRoot_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||folderDraft.IsBatch||folderDraft.TargetIds.Count!=1)return;
        try
        {
            var rootId=folderDraft.TargetIds[0];
            await api.PostAsync("api/library/scan",new JsonObject{{"root_id",rootId}});
            ScanStatus.Text="スキャン開始";
            await PollScanStateAsync();
        }
        catch(Exception ex){ScanStatus.Text=ex.Message;}
    }

    private async void CancelScan_Click(object sender,RoutedEventArgs e)
    {
        try
        {
            await api.PostAsync("api/library/cancel",new JsonObject());
            ScanStatus.Text="キャンセル要求済み。前回の索引を保持します。";
            await PollScanStateAsync();
        }
        catch(Exception ex){ScanStatus.Text=ex.Message;}
    }

    private async void UnregisterRoot_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||UnregisterConsent.IsChecked!=true||saving)return;
        UnregisterRoot.IsEnabled=false;saving=true;
        try
        {
            var targets=folderDraft.TargetIds.ToArray();
            var succeeded=new List<int>();
            var failures=new List<string>();
            foreach(var rootId in targets)
            {
                try
                {
                    await api.PostAsync("api/library/roots/unregister",new JsonObject {{"root_id",rootId}});
                    succeeded.Add(rootId);
                    checkedFolderIds.Remove(rootId);
                    folderDraft.RecordSucceeded(rootId);
                }
                catch(Exception ex)
                {
                    var label=knownRoots.FirstOrDefault(r=>r.Id==rootId)?.ShortPath??$"ID {rootId}";
                    failures.Add($"{label}: {ex.Message}");
                }
            }
            if(selectedSearchRoots is not null&&succeeded.Count>0)
            {
                var remainingSearch=selectedSearchRoots.Where(id=>!succeeded.Contains(id)).ToArray();
                if(remainingSearch.Length>0)selectedSearchRoots=remainingSearch;
            }
            await RefreshSearchRootsAsync();
            await LoadAIScopeAsync();
            UnregisterConsent.IsChecked=false;
            if(failures.Count==0)
            {
                folderSettingsActive=false;folderDraft=null;Details.IsPaneOpen=false;
                ShowItemDetailsPane();
                var msg=$"{succeeded.Count}フォルダの登録を解除しました。元ファイルと保存済みのタグ・棚は保持しています。";
                ScanStatus.Text=msg;
                Notice("登録を解除しました",msg);
            }
            else
            {
                var msg=$"{succeeded.Count}件解除、{failures.Count}件失敗（{string.Join(" / ",failures)}）。未完了のフォルダが選択に残っています。";
                FolderEditStatus.Text=msg;
                ScanStatus.Text=msg;
            }
        }
        catch(Exception ex){ScanStatus.Text=ex.Message;UnregisterRoot.IsEnabled=UnregisterConsent.IsChecked==true;}
        finally{saving=false;}
    }

    private async Task PollScanStateAsync()
    {
        if(pollingScan||disposed||!folderHubOpen)return;
        pollingScan=true;
        try
        {
            var state=await api.GetAsync("api/library/scan");
            var phase=state["state"]!.GetValue<string>();
            var running=phase is "running" or "cancelling";
            if(ScanRoot is not null)ScanRoot.IsEnabled=!running;
            if(SaveExcludes is not null)SaveExcludes.IsEnabled=!running;
            if(AddRoot is not null)AddRoot.IsEnabled=!running;
            if(CancelScan is not null)CancelScan.IsEnabled=running;
            if(running||ScanStatus.Text.StartsWith("running")||ScanStatus.Text.StartsWith("スキャン開始"))
            {
                ScanStatus.Text=$"{phase} · {state["discovered"]} 件 {state["error"]}";
                if(!running)await RefreshSearchRootsAsync();
            }
        }
        catch(Exception ex){if(ScanStatus is not null)ScanStatus.Text=ex.Message;}
        finally{pollingScan=false;}
    }

    private async void RelatedTerms_Click(object sender,RoutedEventArgs e)
    {
        // Same transition guard as the other dialogs; unsaved tag drafts stay
        // in the editor because the dictionary never changes item metadata.
        if(dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        var root=XamlRoot;ScrollViewer? editorScroll=null;
        void Fit(XamlRoot sender,XamlRootChangedEventArgs args){if(editorScroll is not null)editorScroll.MaxHeight=Math.Max(160,sender.Size.Height-240);}
        try{
            var editor=new RelatedTermsEditor(api);
            await editor.LoadAsync();
            editorScroll=new ScrollViewer {Content=FormScrollContent.Wrap(editor.Content),MaxHeight=Math.Max(160,root.Size.Height-240),HorizontalScrollMode=ScrollMode.Disabled,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            AutomationProperties.SetAutomationId(editorScroll,"RelatedTermsScroll");
            root.Changed+=Fit;
            var dialog=new ContentDialog {XamlRoot=root,RequestedTheme=ActualTheme,Title="関連語",Content=editorScroll,CloseButtonText="閉じる",DefaultButton=ContentDialogButton.Close};
            AutomationProperties.SetAutomationId(dialog,"RelatedTermsDialog");
            dialog.Closing+=(_,args)=>{if(editor.IsBusy)args.Cancel=true;};
            await dialog.ShowAsync();
        }catch(Exception ex){Failure(ex);}
        finally{
            root.Changed-=Fit;dialogOpen=false;
            // Re-run a literal search so the list reflects the saved dictionary,
            // but never while a tag draft is unsaved (reload would drop it).
            try{if(!disposed&&!Dirty&&lastMode==0&&lastQuery.Length>0)await LoadAsync();}
            finally{transitions.Release();}
        }
    }

    private async void AI_Click(object sender,RoutedEventArgs e)
    {
        if(dialogOpen||saving||!await transitions.WaitAsync(0))return;
        var timer=DispatcherQueue.CreateTimer();timer.Interval=TimeSpan.FromSeconds(1);
        bool reload=false,openEnvironment=false,openDownload=false;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            dialogOpen=true;reload=true;
            var explanation=new TextBlock {Text="AI検索にはモデルと対応する実行環境が必要です。取得・保存先・モデル選択の変更は次回起動で反映します。新しいモデルには対応するAI索引が必要です。",TextWrapping=TextWrapping.Wrap};
            var environmentButton=new Button{Content="配置済みを指定"};AutomationProperties.SetAutomationId(environmentButton,"AIEnvironmentOpen");
            var downloadButton=new Button{Content="モデルをダウンロード",Style=(Style)Resources["AccentButtonStyle"]};AutomationProperties.SetAutomationId(downloadButton,"AIModelDownloadOpen");
            var setupActions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};setupActions.Children.Add(downloadButton);setupActions.Children.Add(environmentButton);
            var modelChoice=new ComboBox {Header="次回起動で使用するAIモデル",HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(modelChoice,"AIProfileChoice");
            var modelWarning=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(modelWarning,"AIProfileWarning");
            var modelApply=new Button {Content="次回起動に設定",IsEnabled=false};
            AutomationProperties.SetAutomationId(modelApply,"AIProfileApply");
            var modelFeedback=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(modelFeedback,"AIProfileFeedback");
            var profileWarnings=new Dictionary<string,string>();
            var profileLabels=new Dictionary<string,string>();
            bool savingProfile=false;
            string savedProfile="default";
            bool fetchingProfiles=false;
            void UpdateProfileWarning()
            {
                if(modelChoice.SelectedItem is not ComboBoxItem selected || selected.Tag is not string id) {
                    modelApply.IsEnabled=false;return;
                }
                modelWarning.Text=profileWarnings.GetValueOrDefault(id,"");
                modelApply.IsEnabled=!fetchingProfiles && !savingProfile && id!=savedProfile && selected.IsEnabled;
            }
            modelChoice.SelectionChanged+=(_,_)=>UpdateProfileWarning();
            async Task RefreshProfiles()
            {
                fetchingProfiles=true;modelApply.IsEnabled=false;
                try
                {
                    var data=await api.GetAsync("api/library/ai/profiles");
                    savedProfile=data["selected"]?.GetValue<string>() ?? "default";
                    profileWarnings.Clear();profileLabels.Clear();modelChoice.Items.Clear();
                    foreach(var entry in data["profiles"]!.AsArray())
                    {
                        if(entry is null)continue;
                        var id=entry["id"]!.GetValue<string>();
                        var label=entry["label"]?.GetValue<string>() ?? id;
                        var valid=entry["valid"]?.GetValue<bool>()==true;
                        var ready=entry["ready"]?.GetValue<bool>()==true;
                        var caps=entry["modalities"] is JsonArray modes && modes.Any(x=>x?.GetValue<string>()=="cover") ? "文字・表紙" : "文字のみ";
                        var item=new ComboBoxItem {Content=$"{label} ({caps}){(ready ? "" : " · 要確認")}",Tag=id,IsEnabled=valid};
                        AutomationProperties.SetAutomationId(item,"AIProfile_"+id.Replace(':','_'));
                        profileLabels[id]=label;
                        profileWarnings[id]=entry["warning"]?.GetValue<string>() ?? "";
                        modelChoice.Items.Add(item);
                        if(id==savedProfile)modelChoice.SelectedItem=item;
                    }
                    if(modelChoice.SelectedItem is null && modelChoice.Items.Count>0)modelChoice.SelectedIndex=0;
                    var active=data["active"]?.GetValue<string>() ?? "default";
                    var overridden=data["command_line_override"]?.GetValue<bool>()==true;
                    var restart=data["restart_required"]?.GetValue<bool>()==true;
                    modelFeedback.Text=(overridden?"起動時に指定したモデルが優先されています。その指定を外して再起動すると、ここで選択したモデルを使用します。":
                        restart?"保存済みです。Aredokoを閉じ、いつもの入口から起動し直してください。":"変更する場合は次回起動に設定を押してください。")
                        +"\n現在起動中: "+(active=="command-line"?"起動引数で指定したモデル":profileLabels.GetValueOrDefault(active,"設定を確認してください"))
                        +(data["error"]?.GetValue<string>() is string err && err.Length>0?"\n"+err:"");
                }
                catch(Exception ex) {modelFeedback.Text="モデル一覧を取得できません: "+ex.Message;}
                finally {fetchingProfiles=false;UpdateProfileWarning();}
            }
            modelApply.Click+=async(_,_)=>{
                if(savingProfile || modelChoice.SelectedItem is not ComboBoxItem item || item.Tag is not string id)return;
                savingProfile=true;modelApply.IsEnabled=false;modelChoice.IsEnabled=false;
                try {
                    await api.PostAsync("api/library/ai/profile",new JsonObject{{"id",id}});
                    await RefreshProfiles();
                } catch(Exception ex) {modelFeedback.Text="設定を保存できません: "+ex.Message;}
                finally {savingProfile=false;modelChoice.IsEnabled=true;UpdateProfileWarning();}
            };
            var status=new TextBlock {TextWrapping=TextWrapping.Wrap};AutomationProperties.SetAutomationId(status,"AIStatus");
            var start=new Button {Content="索引を作成・更新",IsEnabled=false};AutomationProperties.SetAutomationId(start,"StartAIIndex");
            var cancel=new Button {Content="中断",IsEnabled=false};AutomationProperties.SetAutomationId(cancel,"CancelAIIndex");
            var resumeBooks=new Button{Content="前回の本の追加を再開",Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(resumeBooks,"ResumeBookBatch");
            PageBatchStatus? resumableBooks=null;
            var resumeChunks=new Button{Content="前回のページ追加を再開",Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(resumeChunks,"ResumeBookChunks");
            PageChunkStatus? resumableChunks=null;string? ownedPageJob=null;
            var resumeContinuation=new Button{Content="前回の未準備分を再開",Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(resumeContinuation,"ResumeAIContinuation");AutomationProperties.SetName(resumeContinuation,"前回の未準備分を再開");
            IndexContinuationStatus? resumableContinuation=null;string? ownedContinuationJob=null;
            IndexContinuationPlan? continuationPlan=null;bool planningContinuation=false;string? activeProfile=null;
            var planContinuation=new Button{Content="未準備分を計画",IsEnabled=false};AutomationProperties.SetAutomationId(planContinuation,"PlanAIContinuation");AutomationProperties.SetName(planContinuation,"未準備分を計画");
            var startContinuation=new Button{Content="確認した未準備分を作成",Visibility=Visibility.Collapsed,IsEnabled=false};AutomationProperties.SetAutomationId(startContinuation,"StartAIContinuation");AutomationProperties.SetName(startContinuation,"確認した未準備分を作成");
            var continuationText=new TextBlock{TextWrapping=TextWrapping.Wrap,Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(continuationText,"AIContinuationSummary");AutomationProperties.SetName(continuationText,"未準備索引の計画状況");
            void InvalidateContinuationPlan()
            {
                continuationPlan=null;
                continuationText.Text="";
                continuationText.Visibility=Visibility.Collapsed;
                startContinuation.Visibility=Visibility.Collapsed;
            }
            var release=new Button {Content="AIをメモリから解放",IsEnabled=false};
            AutomationProperties.SetAutomationId(release,"AIRelease");
            var releaseResult=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(releaseResult,"AIReleaseResult");
            var idleChoice=new ComboBox {Header="自動解放（検索・索引の終了後）",HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(idleChoice,"AIIdleRelease");
            AutomationProperties.SetName(idleChoice,"自動解放までの時間");
            var pauseChoice=new ComboBox {Header="索引中の待機（新規AI推論後）",HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(pauseChoice,"AIIndexPause");
            AutomationProperties.SetName(pauseChoice,"新規AI推論後の待機時間");
            var saveResource=new Button {Content="リソース設定を保存"};
            AutomationProperties.SetAutomationId(saveResource,"AISaveResource");
            var resourceResult=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(resourceResult,"AIResourceStatus");
            void AddOption(ComboBox control,int value,string label) {
                var option=new ComboBoxItem {Content=label,Tag=value};
                AutomationProperties.SetAutomationId(option,$"{AutomationProperties.GetAutomationId(control)}_{value}");
                control.Items.Add(option);
            }
            foreach(var seconds in new[]{0,60,300,900})
                AddOption(idleChoice,seconds,seconds==0?"使わない":seconds<60?$"{seconds}秒":$"{seconds/60}分");
            foreach(var ms in new[]{0,50,200,500,1000})
                AddOption(pauseChoice,ms,ms==0?"待機なし":$"{ms}ms");
            void SelectOption(ComboBox box,int amount,string suffix) {
                var match=box.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Tag is int value && value==amount);
                if(match is null) {match=new ComboBoxItem {Content=$"{amount}{suffix}（保存済み）",Tag=amount};box.Items.Add(match);}
                box.SelectedItem=match;
            }
            async Task RefreshResource()
            {
                try {
                    var policy=await api.GetAsync("api/library/ai/resource");
                    SelectOption(idleChoice,policy["policy"]?["idle_release_seconds"]?.GetValue<int>() ?? 0,"秒");
                    SelectOption(pauseChoice,policy["policy"]?["index_pause_ms"]?.GetValue<int>() ?? 0,"ms");
                    resourceResult.Text="リソース設定は保存後すぐ適用。GPU使用率やゲームFPSの上限は保証しません。";
                } catch(Exception ex) {resourceResult.Text="リソース設定を取得できません: "+ex.Message;}
            }
            saveResource.Click+=async (_,_)=>{
                if(idleChoice.SelectedItem is not ComboBoxItem idle || idle.Tag is not int idleValue ||
                   pauseChoice.SelectedItem is not ComboBoxItem pause || pause.Tag is not int pauseValue)return;
                saveResource.IsEnabled=false;idleChoice.IsEnabled=false;pauseChoice.IsEnabled=false;
                try {
                    await api.PostAsync("api/library/ai/resource",new JsonObject{{"idle_release_seconds",idleValue},{"index_pause_ms",pauseValue}});
                    resourceResult.Text="保存しました。モデル・索引は変更しません。自動解放は次のアイドル時間から有効です。";
                }catch(Exception ex){resourceResult.Text="設定を保存できません: "+ex.Message;}
                finally{saveResource.IsEnabled=true;idleChoice.IsEnabled=true;pauseChoice.IsEnabled=true;}
            };
            using var scopeEditor=new AIScopeEditor(api,value=>{aiScope=value;aiScopeError="AI索引の画面で対象を選び直して保存してください。";});
            bool availableForIndex=false,indexRunning=false,starting=false;
            void UpdateStart()
            {
                start.IsEnabled=availableForIndex&&!indexRunning&&!starting&&!planningContinuation&&scopeEditor.Ready;
                planContinuation.IsEnabled=availableForIndex&&!indexRunning&&!starting&&!planningContinuation&&scopeEditor.Ready&&aiScope is not null;
                startContinuation.IsEnabled=availableForIndex&&!indexRunning&&!starting&&!planningContinuation&&continuationPlan?.CanStart==true&&continuationPlan?.Profile==activeProfile&&aiScope is not null;
                resumeBooks.IsEnabled=start.IsEnabled&&resumableBooks?.CanResume==true;
                resumeChunks.IsEnabled=start.IsEnabled&&resumableChunks?.CanResume==true&&aiScope is not null&&resumableChunks.MatchesScope(aiScope);
                resumeContinuation.IsEnabled=start.IsEnabled&&resumableContinuation?.CanResume==true&&aiScope is not null&&resumableContinuation.MatchesScope(aiScope);
            }
            scopeEditor.ScopeEdited+=InvalidateContinuationPlan;
            scopeEditor.StateChanged+=UpdateStart;
            bool polling=false;
            bool releasing=false;
            int? indexLimit=null;
            release.Click+=async (_,_)=>{
                releasing=true;release.IsEnabled=false;
                try {
                    var result=await api.PostAsync("api/library/ai/release",new JsonObject());
                    releaseResult.Text=result["released"]?.GetValue<bool>()==true?"解放しました。次の検索でモデルを準備します。":"AIは既にメモリから解放されています。";
                }catch(Exception ex){releaseResult.Text="解放できません: "+ex.Message;}
                finally{releasing=false;await Refresh();}
            };
            async Task Refresh()
            {
                if(polling||disposed)return;polling=true;
                try
                {
                    var data=await api.GetAsync("api/library/ai/status");
                    var available=data["available"]!.GetValue<bool>();
                    var state=data["state"]!.GetValue<string>();
                    var running=state is "running" or "cancelling";
                    indexLimit=data["limit"]?.GetValue<int>();
                    var label=state switch {"idle"=>"未作成","running"=>"作成中","cancelling"=>"中断待ち","complete"=>"準備完了","cancelled"=>"中断済み","interrupted"=>"前回中断","failed"=>"失敗","partial"=>"一部完了",_=>state};
                    var model=data["model"]?.GetValue<string>() ?? "未選択";
                    var capabilities=data["modalities"] is JsonArray modes && modes.Any(x=>x?.GetValue<string>()=="cover") ? "ファイル名・タグ／画像・表紙" : "ファイル名・タグ";
                    status.Text=available ? $"{model} · {capabilities}{(indexLimit is int cap ? $" · 最大{cap:N0}件" : "")}\n索引処理（開始時の対象）: {label} · {data["processed"]}/{data["total"]} {(data["job"]?.GetValue<string>() is "book-pages" or "book-page-batch" or "book-pages-chunked"?"ページ":"件")}\n{data["error"]!.GetValue<string>()}" : "現在のAI検索を利用できません。モデル設定・重み・Python環境を確認してください。文字検索は利用できます。\n"+(data["error"]?.GetValue<string>() ?? "");
                    activeProfile=data["profile"]?.GetValue<string>();
                    if(continuationPlan is not null && continuationPlan.Profile!=activeProfile)InvalidateContinuationPlan();
                    resumableBooks=null;resumeBooks.Visibility=Visibility.Collapsed;
                    resumableChunks=null;resumeChunks.Visibility=Visibility.Collapsed;
                    resumableContinuation=null;resumeContinuation.Visibility=Visibility.Collapsed;
                    ownedPageJob=running&&data["job"]?.GetValue<string>() is "book-pages" or "book-page-batch" or "book-pages-chunked"?data["job_id"]?.GetValue<string>():null;
                    ownedContinuationJob=running&&data["job"]?.GetValue<string>()=="library-continuation-v1"?data["job_id"]?.GetValue<string>():null;
                    if(data["job"]?.GetValue<string>()=="library-continuation-v1")
                    {
                        try
                        {
                            var cont=IndexContinuationStatus.Parse(System.Text.Encoding.UTF8.GetBytes(data.ToJsonString()),data["profile"]?.GetValue<string>() ?? "");
                            status.Text+="\n"+cont.Summary;
                            if(cont.CanResume)
                            {
                                resumableContinuation=cont;resumeContinuation.Visibility=Visibility.Visible;
                                if(aiScope is null||!cont.MatchesScope(aiScope))status.Text+="\n前回と同じ対象範囲を保存すると再開できます。";
                            }
                        }
                        catch(System.IO.InvalidDataException){status.Text+="\n前回の継続索引の情報を復元できません。未準備分を計画し直してください。";}
                    }
                    if(data["job"]?.GetValue<string>()=="book-pages-chunked")
                    {
                        try
                        {
                            var chunk=PageChunkStatus.Parse(System.Text.Encoding.UTF8.GetBytes(data.ToJsonString()),data["profile"]!.GetValue<string>());
                            status.Text+="\n"+chunk.Summary;
                            if(chunk.CanResume)
                            {
                                resumableChunks=chunk;resumeChunks.Visibility=Visibility.Visible;
                                if(aiScope is null||!chunk.MatchesScope(aiScope))status.Text+="\n前回と同じ対象範囲を保存すると再開できます。";
                            }
                        }
                        catch(System.IO.InvalidDataException){status.Text+="\n前回の選択情報を復元できません。本の追加範囲を開き直してください。";}
                    }
                    if(data["job"]?.GetValue<string>()=="book-page-batch")
                    {
                        var batch=PageBatchStatus.Parse(System.Text.Encoding.UTF8.GetBytes(data.ToJsonString()),data["profile"]!.GetValue<string>());
                        status.Text+="\n"+batch.Summary;
                        if(batch.CanResume){resumableBooks=batch;resumeBooks.Visibility=Visibility.Visible;}
                    }
                    availableForIndex=available;indexRunning=running;scopeEditor.SetJobBusy(running);UpdateStart();cancel.IsEnabled=running;
                    var resident=data["resident"]?.GetValue<bool>()==true;
                    release.IsEnabled=available&&!running&&resident&&!releasing;
                    if(available)status.Text+=(resident?"\nAIはメモリ内で待機中。":"\nAIは待機中・次の検索でモデルを準備します。");
                }
                catch(Exception ex){availableForIndex=false;resumableChunks=null;resumableContinuation=null;ownedPageJob=null;ownedContinuationJob=null;status.Text=ex.Message;start.IsEnabled=resumeChunks.IsEnabled=resumeContinuation.IsEnabled=planContinuation.IsEnabled=startContinuation.IsEnabled=cancel.IsEnabled=false;}
                finally{polling=false;}
            }
            start.Click+=async(_,_)=>{
                if(!start.IsEnabled||aiScope is null)return;
                starting=true;UpdateStart();
                try{await api.PostAsync("api/library/ai/index",AIScopeRequests.Scoped(aiScope));await Refresh();}
                catch(Exception ex){status.Text=ex.Message;}
                finally{starting=false;UpdateStart();}
            };
            planContinuation.Click+=async(_,_)=>{
                if(!planContinuation.IsEnabled||aiScope is null||activeProfile is null)return;
                planningContinuation=true;UpdateStart();
                try
                {
                    var plan=await api.Continuation.PlanAsync(aiScope,activeProfile);
                    continuationPlan=plan;
                    continuationText.Text=plan.DetailSummary+(plan.CanStart?"\n"+plan.Summary:"\n追加する未準備アイテムはありません。");
                    continuationText.Visibility=Visibility.Visible;
                    if(plan.CanStart)
                    {
                        startContinuation.Content=$"未準備の{plan.SelectedTotal:N0}件を作成";
                        startContinuation.Visibility=Visibility.Visible;
                    }
                    else
                    {
                        startContinuation.Visibility=Visibility.Collapsed;
                    }
                }
                catch(Exception ex){continuationText.Text="計画を作成できません: "+ex.Message;continuationText.Visibility=Visibility.Visible;InvalidateContinuationPlan();}
                finally{planningContinuation=false;UpdateStart();}
            };
            startContinuation.Click+=async(_,_)=>{
                if(!startContinuation.IsEnabled||continuationPlan is null||aiScope is null)return;
                starting=true;UpdateStart();
                try
                {
                    var started=await api.Continuation.StartAsync(continuationPlan);
                    ownedContinuationJob=started.JobId;
                    InvalidateContinuationPlan();
                    await Refresh();
                }
                catch(Exception ex){status.Text=ex.Message;InvalidateContinuationPlan();}
                finally{starting=false;UpdateStart();}
            };
            resumeBooks.Click+=async(_,_)=>{
                if(!resumeBooks.IsEnabled||resumableBooks is null||aiScope is null)return;
                starting=true;UpdateStart();
                try{await api.PageEvidences.ResumeBatchAsync(resumableBooks.JobId,aiScope,resumableBooks.Profile);await Refresh();}
                catch(Exception ex){status.Text=ex.Message;}
                finally{starting=false;UpdateStart();}
            };
            resumeChunks.Click+=async(_,_)=>{
                if(!resumeChunks.IsEnabled||resumableChunks is null||aiScope is null)return;
                starting=true;UpdateStart();
                try{await api.PageEvidences.ResumeChunksAsync(resumableChunks,aiScope);await Refresh();}
                catch(Exception ex){status.Text=ex.Message;}
                finally{starting=false;UpdateStart();}
            };
            resumeContinuation.Click+=async(_,_)=>{
                if(!resumeContinuation.IsEnabled||resumableContinuation is null||aiScope is null)return;
                starting=true;UpdateStart();
                try
                {
                    var resumed=await api.Continuation.ResumeAsync(resumableContinuation,aiScope);
                    ownedContinuationJob=resumed.JobId;
                    InvalidateContinuationPlan();
                    await Refresh();
                }
                catch(Exception ex){status.Text=ex.Message;}
                finally{starting=false;UpdateStart();}
            };
            cancel.Click+=async(_,_)=>{
                cancel.IsEnabled=false;
                try{
                    var pageJob=ownedPageJob;
                    var contJob=ownedContinuationJob;
                    if(pageJob is not null)
                        await api.PostAsync("api/library/ai/pages/cancel",new JsonObject{{"job_id",pageJob}});
                    else if(contJob is not null)
                        await api.Continuation.CancelAsync(contJob);
                    else
                        await api.PostAsync("api/library/ai/cancel",new JsonObject());
                    await Refresh();
                }
                catch(Exception ex){status.Text=ex.Message;}
                finally{UpdateStart();}};
            timer.Tick+=async(_,_)=>await Refresh();
            var panel=new StackPanel {Spacing=12,MinWidth=320};
            foreach(var element in new UIElement[]{setupActions,explanation,modelChoice,modelWarning,modelApply,modelFeedback,scopeEditor.Content,
                new TextBlock {Text="AIのメモリ・索引負荷",Style=(Style)Application.Current.Resources["SubtitleTextBlockStyle"]},
                release,releaseResult,idleChoice,pauseChoice,saveResource,resourceResult})panel.Children.Add(element);
            var content=new Grid {RowSpacing=12,MaxHeight=Math.Max(160,ActualHeight-240)};
            AutomationProperties.SetAutomationId(content,"AISettingsLayout");
            content.RowDefinitions.Add(new RowDefinition {Height=new GridLength(1,GridUnitType.Star)});
            content.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
            content.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
            var modelOptions=new ScrollViewer {Content=FormScrollContent.Wrap(panel),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            AutomationProperties.SetAutomationId(modelOptions,"AIOptions");
            AutomationProperties.SetName(modelOptions,"モデル・AIリソース設定");
            content.Children.Add(modelOptions);
            var continuationActions=new StackPanel {Orientation=Orientation.Horizontal,Spacing=8};
            continuationActions.Children.Add(planContinuation);continuationActions.Children.Add(startContinuation);
            var indexInfo=new StackPanel {Spacing=8};
            AutomationProperties.SetAutomationId(indexInfo,"AIIndexSummary");
            indexInfo.Children.Add(new TextBlock {Text="現在のAI索引",Style=(Style)Application.Current.Resources["SubtitleTextBlockStyle"]});
            indexInfo.Children.Add(status);
            indexInfo.Children.Add(continuationText);
            indexInfo.Children.Add(continuationActions);
            indexInfo.Children.Add(resumeContinuation);
            indexInfo.Children.Add(resumeBooks);
            indexInfo.Children.Add(resumeChunks);
            Grid.SetRow(indexInfo,1);content.Children.Add(indexInfo);
            var actions=new StackPanel {Orientation=Orientation.Horizontal,Spacing=8};
            actions.Children.Add(start);actions.Children.Add(cancel);Grid.SetRow(actions,2);content.Children.Add(actions);
            await RefreshProfiles();await RefreshResource();await Refresh();timer.Start();
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AI検索の準備",Content=content,CloseButtonText="閉じる"};
            environmentButton.Click+=(_,_)=>{if(scopeEditor.Saving)return;openEnvironment=true;dialog.Hide();};
            downloadButton.Click+=(_,_)=>{if(scopeEditor.Saving)return;openDownload=true;dialog.Hide();};
            dialog.Closing+=(_,args)=>{if(scopeEditor.Saving)args.Cancel=true;};
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{timer.Stop();dialogOpen=false;try{if(reload&&!disposed)await LoadAsync();}finally{transitions.Release();}}
        if(openDownload&&!disposed)await OpenAIDownloadDialogAsync();
        else if(openEnvironment&&!disposed)await OpenAIEnvironmentDialogAsync();
    }

    public Task FlushReaderProgressAsync()=>readerView?.FlushProgressAsync()??Task.CompletedTask;
    public void Stop(){disposed=true;DetachXamlRoot();itemSizeTimer.Stop();containerRefresh.Clear();CloseShelfHubCore();if(resultScroll is not null)resultScroll.ViewChanged-=ResultScroll_Changed;resultWindow?.Dispose();resultWindow=null;SaveItemSize();tagReview?.Dispose();scanPollTimer.Stop();viewerWindow?.Close();similarityCancellation?.Cancel();renderCancellation.Cancel();foreach(var item in containerCleanup.Keys.ToArray())ReleaseContainer(item);detailCancellation?.Cancel();readerView?.Dispose();imageViewer?.Dispose();videoPlayer?.Dispose();searches.Next();searchTimer.Stop();var session=resultSession;resultSession=null;if(session is null)api.Dispose();else _=CloseResultsAndApiAsync(session);}
}

