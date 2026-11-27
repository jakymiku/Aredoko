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
    private MediaCardResources? cardResources;
    private bool? appliedItemsPanelTiles;
    private long layoutSizeEpoch;
    private MediaCardResources GetCardResources() => cardResources ??= new MediaCardResources(Resources);
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
    private readonly Dictionary<int, MediaRow> rowById = new();
    private double cachedGridCaptionMinHeight = 24;
    private MediaRow? active;
    private EditorState saved;
    private EditorState initialSaved;
    private int? initialSavedItemId;
    private string? detailSaveError;
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
    private bool folderHubOpen, settingsHubOpen, folderTiles, folderPopulating, folderSettingsActive, pollingScan, gettingStartedDismissed, aiIndexReady, scanRootsRefreshed, aiRuntimeChecked, aiRuntimeAvailable;
    private int lastScanAccessDeniedCount;
    private bool lastScanAccessDeniedTruncated;
    private List<(string RootPath, string RelativePath, bool IsDir)> lastScanAccessDeniedEntries=[];
    private bool? lastAutoNavExpanded;
    private string[] draftTags=[];
    private int lastTextSearchMode=0, lastAISearchMode=1;
    private string currentSettingsCategory="all";
    private long? emptyLibraryScanJob;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer scanPollTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer folderFilterTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer runtimeVerifyTimer;
    private readonly CancellationTokenSource runtimeVerifyLifetime=new();
    private bool pollingRuntimeVerify, aiModelResident;
    private long? aiModelLoadingVersion;
    private long? runtimeVerifyClientStartedTick;
    private JsonObject? aiScope;
    private string aiScopeError=AppText.L("AI設定で検索対象を確認・保存してください。","Review and save the search scope in AI settings.");
    private string view="all", lastQuery="";
    private string? selectedTagScope;
    private MediaRow? similarityOrigin;
    private int? similarityOriginPage;
    private int? similarityOriginMs;
    private bool directAudioSimilarity;
    private bool directVideoSimilarity;
    private bool directVideoAudioSimilarity;
    private bool DirectContentSimilarity => directAudioSimilarity||directVideoSimilarity||directVideoAudioSimilarity;
    private CancellationTokenSource? similarityCancellation;
    private CancellationToken? explicitlyCancelledSearch;
    private bool returningFromSimilarity;
    private SearchBookmark? similarityReturn;
    private sealed record SearchBookmark(string Query,int Kind,int Mode,int[]? Roots,bool LiteralOnly,double? Boundary,int Group,string View,int Page,int Selection,long[]? Shelves,string? Tag=null,int? OriginPage=null,int? OriginMs=null);

    public MainPage() {
        InitializeComponent();
        UiText.Apply(this);
        for(var index=0;index<SearchMode.Items.Count;index++)
            if(SearchMode.Items[index] is ComboBoxItem option)
            {
                var hint=SearchModeDescription(index);
                ToolTipService.SetToolTip(option,hint);
                AutomationProperties.SetHelpText(option,hint);
            }
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
        Items.AddHandler(PointerPressedEvent,new PointerEventHandler(LibrarySelectionPointerPressed),true);
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
        tiles=ViewerOptions.Value.LibraryTiles;UpdateLayoutToggleVisuals();
        libraryItemScale=ViewerOptions.Value.LibraryItemScale;ItemSizeSlider.Value=libraryItemScale;
        ItemSizeLabel.Text=$"{libraryItemScale}%";itemSizeReady=true;
        UpdateSearchMethod();
        thumbnails = new ThumbnailService(api);
        searchTimer=DispatcherQueue.CreateTimer(); searchTimer.Interval=TimeSpan.FromMilliseconds(300);
        searchTimer.Tick+=async (_,_)=>{searchTimer.Stop(); if(PendingAutoSearch&&!queryComposing) await NavigateAsync(0);};
        scanPollTimer=DispatcherQueue.CreateTimer(); scanPollTimer.Interval=TimeSpan.FromSeconds(1);
        scanPollTimer.Tick+=async (_,_)=>await PollScanStateAsync();
        folderFilterTimer=DispatcherQueue.CreateTimer(); folderFilterTimer.Interval=TimeSpan.FromMilliseconds(150);
        folderFilterTimer.Tick+=(_,_)=>{folderFilterTimer.Stop();if(!disposed&&ready&&folderHubOpen&&!folderPopulating)RenderFolderHub();};
        runtimeVerifyTimer=DispatcherQueue.CreateTimer(); runtimeVerifyTimer.Interval=TimeSpan.FromSeconds(1);
        runtimeVerifyTimer.Tick+=async (_,_)=>await PollRuntimeVerificationAsync();
    }
    private static string[] ParseTagTokens(string? raw)=>(raw??"").Split([',','、'],StringSplitOptions.RemoveEmptyEntries|StringSplitOptions.TrimEntries).Distinct().ToArray();
    private string[] EffectiveDraftTags()=>draftTags.Concat(ParseTagTokens(Tags?.Text)).Distinct().ToArray();
    private void SyncFavoriteToggle(bool isFavorite)
    {
        if(Favorite is null)return;
        Favorite.IsChecked=isFavorite;
        Favorite.Content=isFavorite?"★":"☆";
        AutomationProperties.SetName(Favorite,isFavorite?AppText.L("お気に入り（登録済み）","Favorite (added)"):AppText.L("お気に入り（未登録）","Favorite (not added)"));
    }
    private static string DetailKindLabel(MediaRow row)=>row.Kind switch
    {
        "book"=>AppText.L("📖 本","📖 Book"),
        "archive"=>AppText.L("🗜 圧縮","🗜 Archive"),
        "video"=>AppText.L("🎬 動画","🎬 Video"),
        "audio"=>AppText.L("🎵 音声","🎵 Audio"),
        "image"=>AppText.L("🖼 画像","🖼 Image"),
        "material" or "asset"=>AppText.L("🧩 素材","🧩 Asset"),
        _=>MediaKindFilter.DisplayName(row)
    };
    private static void PopulateWrappedChips(StackPanel target,double maxRowWidth,IReadOnlyList<FrameworkElement> chips)
    {
        target.Children.Clear();
        if(chips.Count==0)return;
        var chipRow=new StackPanel{Orientation=Orientation.Horizontal,Spacing=6};
        double rowWidth=0;
        foreach(var chip in chips)
        {
            chip.Measure(new Windows.Foundation.Size(double.PositiveInfinity,double.PositiveInfinity));
            var chipWidth=chip.DesiredSize.Width;
            if(chipRow.Children.Count>0&&rowWidth+6+chipWidth>maxRowWidth)
            {
                target.Children.Add(chipRow);
                chipRow=new StackPanel{Orientation=Orientation.Horizontal,Spacing=6};
                rowWidth=0;
            }
            if(chipRow.Children.Count>0)rowWidth+=6;
            chipRow.Children.Add(chip);
            rowWidth+=chipWidth;
        }
        if(chipRow.Children.Count>0)target.Children.Add(chipRow);
    }
    private Style? ThemeStyle(string key)=>(Resources.TryGetValue(key,out var local)?local:Application.Current.Resources.TryGetValue(key,out var app)?app:null) as Style;
    private static bool SameRoots(IReadOnlyList<int>? a,IReadOnlyList<int>? b)=>
        ReferenceEquals(a,b)||(a is not null&&b is not null&&a.SequenceEqual(b));
    private bool PendingSearch => !folderHubOpen&&!shelfHubOpen&&!settingsHubOpen&&(Query.Text!=lastQuery||Kind.SelectedIndex!=lastKind||SearchMode.SelectedIndex!=lastMode||!SameRoots(selectedSearchRoots,lastRoots)||(AIMatchedOnly.IsChecked==true)!=lastLiteralOnly||BoundaryValue()!=lastBoundary||AIResultGroup.SelectedIndex!=lastResultGroup);
    private bool PendingAutoSearch => PendingSearch && SearchMode.SelectedIndex==lastMode && ((similarityOrigin is not null && Query.Text==lastQuery) || !SearchMethod.FromIndex(SearchMode.SelectedIndex).IsAI);
    private EditorState CurrentCommitted()=>new(string.Join(", ",draftTags),editingShelfIds.Length==0?"":ShelfName(editingShelfIds.Min()),Favorite.IsChecked==true,Reviewed.IsChecked==true){ShelfIds=editingShelfIds.ToArray()};
    private EditorState Current()=>new(string.Join(", ",EffectiveDraftTags()),editingShelfIds.Length==0?"":ShelfName(editingShelfIds.Min()),Favorite.IsChecked==true,Reviewed.IsChecked==true){ShelfIds=editingShelfIds.ToArray()};
    private bool Dirty=>active is not null && EditorState.IsDirty(saved,Current());
    private bool HasUncommittedDraft=>active is not null && EditorState.IsDirty(saved,CurrentCommitted());
    private bool CanRevertToInitial=>active is not null && (HasUncommittedDraft || (initialSavedItemId==active.Id && EditorState.IsDirty(initialSaved,saved)));
    private bool FolderDirty=>folderSettingsActive && folderDraft is {IsDirty:true};
    private void Notice(string title,string message="",InfoBarSeverity severity=InfoBarSeverity.Informational,string? details=null) {
        Status.Title=title; Status.Message=message; Status.Severity=severity;
        Status.IsOpen=severity is InfoBarSeverity.Warning or InfoBarSeverity.Error;
        StatusExplanation.Text=details??"";
        StatusMore.Visibility=string.IsNullOrWhiteSpace(details)?Visibility.Collapsed:Visibility.Visible;
    }
    private void Failure(Exception ex) {
        Notice(AppText.L("操作を完了できません","Could not complete action"),AppText.TranslateBackend(ex.Message),InfoBarSeverity.Error);
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
        AttachXamlRoot();
        AppLog.Startup("page_initialization_starting");
        await ConnectAsync();
        // NavigationView can raise its initial selection while authentication is in flight.
        if(disposed)return;
        ready=true;
        UpdateNavigationLayout(ActualWidth);
        AppLog.Startup("page_initialization_completed");
    }
    private bool startupSearchSucceeded;
    private async Task ConnectAsync() {
        try {
            var firstFrameConfirmed=false;
            renderCancellation.Cancel();
            AppLog.Startup("session_connecting");await api.ConnectAsync();thumbnails.ResetSession();await RefreshHistoryGenerationAsync();
            AppLog.Startup("session_connected");await LoadAIScopeAsync();
            _ = StartRuntimeVerifyPollingAsync();
            AppLog.Startup("ai_scope_loaded");await RefreshSearchRootsAsync();
            AppLog.Startup("roots_loaded");
            if(StartupReady.Pending)
            {
                AppLog.Startup("window_showing");MainWindow.Current.AppWindow.Show();MainWindow.Current.Activate();await StartupReady.FirstFrameAsync();firstFrameConfirmed=true;
            }
            if(disposed)return;
            ready=true;UpdateNavigationLayout(ActualWidth);
            await LoadAsync();
            AppLog.Startup(startupSearchSucceeded?"initial_search_completed":"initial_search_failed");
            if(startupSearchSucceeded&&!startupUpdatesRequested&&knownRoots.Any(root=>root.Enabled&&root.StartupScan!="none"))
            {
                // This handshake follows a rendered screen, including direct
                // frontend launches without a portable readiness nonce.
                if(!firstFrameConfirmed)await StartupReady.FirstFrameAsync();
                _=BeginStartupUpdatesAsync();
            }
        }
        catch(Exception ex) { AppLog.Startup("connection_or_first_frame_failed");AppLog.Error(ex);Notice(AppText.L("バックエンドに接続できません","Cannot connect to backend"), AppText.L("Aredokoを閉じ、製品用の起動アイコンから起動し直してください。","Close Aredoko and relaunch it using the app shortcut or Aredoko.exe. ")+AppText.TranslateBackend(ex.Message),InfoBarSeverity.Error); }
        finally{if(StartupReady.Pending)try{await StartupReady.SignalAsync(false);}catch(Exception ex){AppLog.Error(ex);}}
    }
    private string ResultGroup()=>AIResultGroup.SelectedIndex switch {0=>"leading",1=>"other",_=>"all"};
    private void AIResultGroup_Changed(object sender,SelectionChangedEventArgs e){UpdateClearSearchConditionsVisibility();similarityCancellation?.Cancel();searchTimer?.Stop();if(ready&&!populating&&PendingAutoSearch)searchTimer!.Start();}
    private double? BoundaryValue()=>SearchMode.SelectedIndex is 2 or 3 && double.IsFinite(SimilarityBoundary.Value)?SimilarityBoundary.Value:null;
    private void SimilarityBoundary_Changed(NumberBox sender,NumberBoxValueChangedEventArgs args){UpdateClearSearchConditionsVisibility();similarityCancellation?.Cancel();searchTimer?.Stop();if(ready&&!populating&&PendingAutoSearch)searchTimer!.Start();}
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
            SearchRoot.Items.Add(new ComboBoxItem {Content=AppText.L("すべてのフォルダ","All folders"),Tag=0});
            foreach(var row in knownRoots.Where(r=>r.Enabled))
            {
                var option=new ComboBoxItem {Content=row.Path+(row.Online?"":AppText.L("（未接続）"," (Offline)")),Tag=row.Id};
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
                    match=new ComboBoxItem {Content=AppText.L($"登録が見つからないフォルダ（ID {single}）",$"Missing folder registration (ID {single})"),Tag=single};
                    SearchRoot.Items.Add(match);
                }
                SearchRoot.SelectedItem=match;
            }
            else
            {
                var multi=new ComboBoxItem {Content=AppText.L($"選択したフォルダ（{selectedSearchRoots.Length}件）",$"Selected folders ({selectedSearchRoots.Length})"),Tag=-1};
                SearchRoot.Items.Add(multi);
                SearchRoot.SelectedItem=multi;
            }
        }
        finally{populating=before;}
    }
    private void UpdateActiveSearchScopeBar()
    {
        if(ActiveSearchScopeText is null||ResetAllFoldersButton is null)return;
        var isAiOrSimilar=similarityOrigin is not null&&!DirectContentSimilarity||(similarityOrigin is null&&SearchMode.SelectedIndex is >0 and <4&&!string.IsNullOrWhiteSpace(Query.Text));
        var (summary,warning)=FolderScopeDescriber.DescribeSearchScope(knownRoots,selectedSearchRoots,isAiOrSimilar,aiScope);
        ActiveSearchScopeText.Text=$"📁 {summary}"+(warning is null?"":$"\n{warning}");
        ToolTipService.SetToolTip(ActiveSearchScopeText,AppText.L("検索する場所：","Search location: ")+summary+(warning is null?"":$"\n{warning}"));
        ActiveSearchScopeBar.Visibility=selectedSearchRoots is null?Visibility.Collapsed:Visibility.Visible;
        ResetAllFoldersButton.Visibility=selectedSearchRoots is null?Visibility.Collapsed:Visibility.Visible;
        UpdateClearSearchConditionsVisibility();
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
        searchTimer.Stop();
        if(PendingAutoSearch)searchTimer.Start();
    }
    private async Task StartRuntimeVerifyPollingAsync()
    {
        if(disposed)return;
        runtimeVerifyTimer.Start();
        await PollRuntimeVerificationAsync();
    }
    private void SetAiSearchModelLoading(bool loading,long version)
    {
        if(disposed)return;
        if(!loading&&aiModelLoadingVersion!=version)return;
        aiModelLoadingVersion=loading?version:null;
        if(loading)
        {
            if(!aiModelResident&&RuntimeVerifyCard.Visibility==Visibility.Collapsed)
            {
                RuntimeVerifyTitle.Text=AppText.L("AIを起動中…","Starting AI…");
                RuntimeVerifyProgress.IsIndeterminate=true;
                RuntimeVerifyDetail.Text=AppText.L("初回のみ時間がかかります","Only takes longer on first run");
                ToolTipService.SetToolTip(RuntimeVerifyCard,$"{RuntimeVerifyTitle.Text} — {RuntimeVerifyDetail.Text}");
                RuntimeVerifyCard.Visibility=Visibility.Visible;
            }
            if(!runtimeVerifyTimer.IsRunning)runtimeVerifyTimer.Start();
        }
        else
        {
            _ = PollRuntimeVerificationAsync();
        }
    }
    private void UpdateSearchAIUnreadyBar()
    {
        if(SearchAIUnreadyBar is null||SearchMode is null)return;
        var modeIndex=Math.Clamp(SearchMode.SelectedIndex,0,9);
        var isAIMode=modeIndex is not (0 or 4 or 5);
        SearchAIUnreadyBar.Visibility=isAIMode&&similarityOrigin is null&&aiRuntimeChecked&&!aiRuntimeAvailable
            ?Visibility.Visible:Visibility.Collapsed;
    }
    private async void SearchAIUnreadySetup_Click(object sender,RoutedEventArgs e)=>await OpenSettingsAsync("ai");
    private void UpdateNavAIStatus(bool available,bool busy,int? verifyPercent=null)
    {
        if(NavAIStatus is null)return;
        var label=busy?(verifyPercent is int pct?AppText.L($"AI：確認中 {pct}%",$"AI: Checking {pct}%"):AppText.L("AI：確認中","AI: Checking")):available?AppText.L("AI：使用可","AI: Ready"):AppText.L("AI：未設定","AI: Not set up");
        NavAIStatus.Content=label;
        var tip=busy?AppText.L("AI検索の環境・モデルを確認しています（名前・タグ検索はそのまま使えます）","Checking AI environment and model (filename/tag search works normally)."):available?AppText.L("AI検索を使用できます（クリックでAI設定）","AI search is ready (click to open AI settings)"):AppText.L("AI検索は未設定です（クリックして準備）","AI search is not configured (click to set up)");
        ToolTipService.SetToolTip(NavAIStatus,tip);
        AutomationProperties.SetName(NavAIStatus,label);
    }
    private bool ApplyRuntimeVerificationSnapshot(JsonNode data)
    {
        var available=data["available"]?.GetValue<bool>()==true;
        aiRuntimeChecked=true;aiRuntimeAvailable=available;
        UpdateSearchAIUnreadyBar();
        var resident=data["resident"]?.GetValue<bool>()==true;
        aiModelResident=resident;
        var rv=data["runtime_verification"];
        var state=rv?["state"]?.GetValue<string>()??"idle";
        if(available&&state=="verifying")
        {
            runtimeVerifyClientStartedTick??=Environment.TickCount64;
            var clientElapsed=Math.Max(0.0,(Environment.TickCount64-runtimeVerifyClientStartedTick.Value)/1000.0);
            var serverElapsed=rv?["elapsed_seconds"]?.GetValue<double>()??0.0;
            var elapsed=Math.Max(serverElapsed,clientElapsed);
            var slow=rv?["slow"]?.GetValue<bool>()==true||elapsed>=300.0;
            var bytesDone=rv?["bytes_done"]?.GetValue<long>()??0L;
            var bytesTotal=rv?["bytes_total"]?.GetValue<long>()??0L;
            var filesDone=rv?["files_done"]?.GetValue<int>()??0;
            var filesTotal=rv?["files_total"]?.GetValue<int>()??0;
            var percent=bytesTotal>0?Math.Clamp(bytesDone*100.0/bytesTotal,0.0,100.0)
                :filesTotal>0?Math.Clamp(filesDone*100.0/filesTotal,0.0,100.0):0.0;
            UpdateNavAIStatus(available,true,(bytesTotal>0||filesTotal>0)?(int)Math.Round(percent):null);
            var bytesDoneGb=bytesDone/(1024.0*1024.0*1024.0);
            var bytesTotalGb=bytesTotal/(1024.0*1024.0*1024.0);
            RuntimeVerifyProgress.IsIndeterminate=bytesTotal<=0&&filesTotal<=0;
            RuntimeVerifyProgress.Value=percent;
            if(slow)
            {
                RuntimeVerifyTitle.Text=AppText.L("時間がかかっています","Taking longer than usual");
                RuntimeVerifyDetail.Text=bytesTotal>0
                    ?AppText.L($"AIを確認中 {percent:F0}% ({bytesDoneGb:F1} / {bytesTotalGb:F1} GB) — そのままお待ちください",$"Checking AI {percent:F0}% ({bytesDoneGb:F1} / {bytesTotalGb:F1} GB) — please wait")
                    :AppText.L("時間がかかっています。そのままお待ちください","Taking longer than usual. Please wait");
            }
            else
            {
                RuntimeVerifyTitle.Text=AppText.L("AIを確認中","Checking AI");
                RuntimeVerifyDetail.Text=bytesTotal>0
                    ?AppText.L($"{percent:F0}% ({bytesDoneGb:F1} / {bytesTotalGb:F1} GB) · 名前・タグ検索はそのまま使えます",$"{percent:F0}% ({bytesDoneGb:F1} / {bytesTotalGb:F1} GB) · Filename/tag search works normally")
                    :filesTotal>0?AppText.L($"{percent:F0}% ({filesDone:N0} / {filesTotal:N0} ファイル) · 名前・タグ検索はそのまま使えます",$"{percent:F0}% ({filesDone:N0} / {filesTotal:N0} files) · Filename/tag search works normally")
                    :AppText.L("確認しています… · 名前・タグ検索はそのまま使えます","Checking… · Filename/tag search works normally");
            }
            ToolTipService.SetToolTip(RuntimeVerifyCard,$"{RuntimeVerifyTitle.Text} — {RuntimeVerifyDetail.Text}");
            RuntimeVerifyCard.Visibility=Visibility.Visible;
            if(!runtimeVerifyTimer.IsRunning)runtimeVerifyTimer.Start();
            return true;
        }
        runtimeVerifyClientStartedTick=null;
        if(available&&aiModelLoadingVersion is not null&&!resident)
        {
            UpdateNavAIStatus(available,true);
            RuntimeVerifyTitle.Text=AppText.L("AIを起動中…","Starting AI…");
            RuntimeVerifyProgress.IsIndeterminate=true;
            RuntimeVerifyDetail.Text=AppText.L("初回のみ時間がかかります","Only takes longer on first run");
            ToolTipService.SetToolTip(RuntimeVerifyCard,$"{RuntimeVerifyTitle.Text} — {RuntimeVerifyDetail.Text}");
            RuntimeVerifyCard.Visibility=Visibility.Visible;
            if(!runtimeVerifyTimer.IsRunning)runtimeVerifyTimer.Start();
            return false;
        }
        UpdateNavAIStatus(available,false);
        RuntimeVerifyCard.Visibility=Visibility.Collapsed;
        runtimeVerifyTimer.Stop();
        return false;
    }
    private async Task PollRuntimeVerificationAsync()
    {
        if(pollingRuntimeVerify||disposed)return;
        pollingRuntimeVerify=true;
        try
        {
            using var deadline=CancellationTokenSource.CreateLinkedTokenSource(runtimeVerifyLifetime.Token);
            deadline.CancelAfter(TimeSpan.FromSeconds(5));
            var data=await api.GetAsync("api/library/ai/status",deadline.Token);
            if(disposed)return;
            ApplyRuntimeVerificationSnapshot(data);
        }
        catch
        {
            // Best-effort background status check; do not interrupt foreground work.
        }
        finally{pollingRuntimeVerify=false;}
    }
    private async Task WaitForRuntimeVerificationBeforeSearchAsync(long version,CancellationToken cancellation)
    {
        var waitStartedTick=Environment.TickCount64;
        while(!disposed&&searches.IsCurrent(version))
        {
            cancellation.ThrowIfCancellationRequested();
            JsonNode data;
            try
            {
                using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellation,runtimeVerifyLifetime.Token);
                deadline.CancelAfter(TimeSpan.FromSeconds(5));
                data=await api.GetAsync("api/library/ai/status",deadline.Token);
            }
            catch(OperationCanceledException) when(cancellation.IsCancellationRequested||disposed){throw;}
            catch
            {
                return;
            }
            cancellation.ThrowIfCancellationRequested();
            if(!searches.IsCurrent(version)||disposed)throw new OperationCanceledException(cancellation);
            var isVerifying=ApplyRuntimeVerificationSnapshot(data);
            if(!isVerifying)return;
            var rv=data["runtime_verification"];
            var serverElapsed=rv?["elapsed_seconds"]?.GetValue<double>()??0.0;
            var clientElapsed=Math.Max(0.0,(Environment.TickCount64-(runtimeVerifyClientStartedTick??waitStartedTick))/1000.0);
            var elapsed=Math.Max(serverElapsed,clientElapsed);
            var slow=rv?["slow"]?.GetValue<bool>()==true||elapsed>=300.0;
            var bytesDone=rv?["bytes_done"]?.GetValue<long>()??0L;
            var bytesTotal=rv?["bytes_total"]?.GetValue<long>()??0L;
            var percent=bytesTotal>0?Math.Clamp(bytesDone*100.0/bytesTotal,0.0,100.0):0.0;
            Count.Text=slow?AppText.L("時間がかかっています","Taking longer than usual"):bytesTotal>0?AppText.L($"AIを確認中 {percent:F0}%",$"Checking AI {percent:F0}%"):AppText.L("AIを確認中…","Checking AI…");
            if(rows.Count==0)
            {
                Empty.Visibility=Visibility.Visible;
                Empty.Text=slow
                    ?AppText.L("AIの確認に時間がかかっています。完了後に検索します。","AI verification is taking longer than usual. Search will run once ready.")
                    :AppText.L($"AIの確認後に検索します（{percent:F0}%）",$"Search will run after checking AI ({percent:F0}%)");
            }
            if(slow)
            {
                Notice(AppText.L("時間がかかっています","Taking longer than usual"),AppText.L("AIの確認完了後に自動で検索を開始します。","Search will start automatically once AI verification completes."),InfoBarSeverity.Warning);
            }
            await Task.Delay(500,cancellation);
        }
    }
    private async Task LoadAIScopeAsync()
    {
        aiScope=null;
        try {
            var data=await api.GetAsync("api/library/ai/scope");
            if(data["valid"]?.GetValue<bool>()!=true){aiScopeError=AppText.TranslateBackend(data["error"]?.GetValue<string>())??AppText.L("AI対象を選び直してください。","Please re-select your AI search scope.");return;}
            aiScope=(JsonObject)data["scope"]!.DeepClone();
        } catch(Exception ex){aiScopeError=AppText.L("AI対象を取得できません。AI検索設定で確認してください。","Could not load AI scope. Check AI Search Settings. ")+AppText.TranslateBackend(ex.Message);}
    }
    private async void Reconnect_Click(object sender,RoutedEventArgs e)
    {
        CloseBrowseMenus();
        if(!await transitions.WaitAsync(0))return;
        try{if(await ConfirmDiscardAsync())await ConnectAsync();}finally{transitions.Release();}
    }
    private string KindValue()=>MediaKindFilter.FromIndex(Kind.SelectedIndex);
    private void UpdateLibraryHeading()
    {
        if(folderHubOpen||shelfHubOpen||settingsHubOpen)return;
        MainViewTitle.Text=selectedShelfIds is not null?ShelfScopeName():view switch
        {
            "favorites"=>AppText.L("お気に入り","Favorites"),
            "history"=>AppText.L("閲覧履歴","History"),
            "unreviewed"=>AppText.L("未確認の作品","Unreviewed"),
            _=>AppText.L("すべての作品","All Items")
        };
        ToolTipService.SetToolTip(MainViewTitle,selectedShelfIds is not null?ShelfScopeName(summarize:false):MainViewTitle.Text);
    }
    private async Task LoadAsync(bool reuseSession=false) {
        CloseBrowseMenus();EmptyAIRecovery.Visibility=Visibility.Collapsed;EmptyPrepareAIButton.Visibility=Visibility.Visible;EmptyResetConditionsButton.Visibility=Visibility.Collapsed;EmptyOpenFoldersButton.Visibility=Visibility.Collapsed;
        // The accepted destination owns the heading even while its request is
        // pending or fails. Never label old, disabled rows as the new results.
        UpdateLibraryHeading();Count.Text=AppText.L("検索中…","Searching…");
        startupSearchSucceeded=false;UpdateFavoriteRootList();
        var version=searches.Next(); Busy.Visibility=Visibility.Visible;
        GettingStarted.Visibility=Visibility.Collapsed;
        if(rows.Count==0){VisualAssets.State(EmptyArt,"searching");Empty.Visibility=Visibility.Visible;Empty.Text=AppText.L("検索中…","Searching…");}
        similarityCancellation?.Cancel();similarityCancellation?.Dispose();similarityCancellation=new();explicitlyCancelledSearch=null;
        CancelSearchButton.Visibility=Visibility.Visible;
        var cancellation=similarityCancellation.Token;var origin=similarityOrigin;
        // Do not allow editing an old record while a different result is loading.
        Editor.IsEnabled=false; Items.IsEnabled=false;
        var query=Query.Text; var kind=KindValue();var selectedKind=Kind.SelectedIndex;var selectedMode=SearchMode.SelectedIndex;var selectedRoots=selectedSearchRoots?.ToArray();var literalOnly=AIMatchedOnly.IsChecked==true;var boundary=BoundaryValue();var resultGroup=AIResultGroup.SelectedIndex;
        try {
            var method=SearchMethod.FromIndex(selectedMode);
            if((origin is not null&&!DirectContentSimilarity||origin is null&&method.IsAI&&!method.IsDirectContent&&!string.IsNullOrWhiteSpace(query))&&aiScope is null)throw new InvalidOperationException(aiScopeError);
            var pageSize=method.IsPageText?20:60;
            var conditions=ResultSearchConditions.Create(query,kind,view,method,aiScope,selectedRoots,
                origin?.Id,literalOnly,boundary,ResultGroup(),selectedShelfIds,directAudioSimilarity,directVideoSimilarity,directVideoAudioSimilarity,selectedTagScope,similarityOriginPage,similarityOriginMs);
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
            var (scopeLabel,scopeWarning)=FolderScopeDescriber.DescribeSearchScope(knownRoots,selectedRoots,origin is not null&&!DirectContentSimilarity||(origin is null&&method.IsAI&&!method.IsDirectContent&&query.Length>0),aiScope);
            UpdateActiveSearchScopeBar();
            SearchOptions.Header=AppText.L("AI検索結果の絞り込み","Filter AI Search Results");
            ResetBrowse(checked(page*pageSize),result);rows=result.Items;SyncRowsState();BindLibrarySelection();active=null;initialSavedItemId=null; if(!folderSettingsActive&&librarySelection.Count==0){Details.IsPaneOpen=false;DetailKindBadge.Visibility=Visibility.Collapsed;} DetailsButton.IsEnabled=false;detailCancellation?.Cancel(); DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed; draftTags=[];Tags.Text="";editingShelfIds=[];UpdateShelfEditorLabel();SyncFavoriteToggle(false);Reviewed.IsChecked=false;RenderRows();UpdateBrowseTagsFlyout();
            ItemTitle.Text=AppText.L("作品を選んでください","Select an item"); ItemPath.Text=""; EditStatus.Text=""; UpdateDetailSaveBar();
            UpdateLibraryHeading();
            if(settingsHubOpen)settingsReturnCount=AppText.L($"{result.Total:N0} 件",$"{result.Total:N0} items");
            else Count.Text=AppText.L($"{result.Total:N0} 件",$"{result.Total:N0} items");
            var slotTotal=virtualTotal<=MaxVirtualSlots?virtualTotal:rows.Count;
            UpdateBrowseFooter(FormatLoadedPageRange(browseStart,slotTotal,virtualTotal),browseStart>0,browseStart+slotTotal<virtualTotal);
            VisualAssets.State(EmptyArt,!HasActiveSearchConditions()&&knownRoots.Count==0&&view=="all"&&selectedShelfIds is null&&selectedTagScope is null&&selectedSearchRoots is null?"greeting":"no_results");Empty.Visibility=virtualTotal==0?Visibility.Visible:Visibility.Collapsed;
            EmptyResetConditionsButton.Visibility=virtualTotal==0&&HasActiveSearchConditions()?Visibility.Visible:Visibility.Collapsed;
            EmptyOpenFoldersButton.Visibility=virtualTotal==0&&!HasActiveSearchConditions()&&view=="all"&&selectedShelfIds is null&&selectedTagScope is null&&selectedSearchRoots is null&&GettingStarted.Visibility!=Visibility.Visible?Visibility.Visible:Visibility.Collapsed;
            Empty.Text=method.IsPageText?(string.IsNullOrWhiteSpace(query)?AppText.L("ページ内の文字を入力してください","Enter text to search inside book pages"):AppText.L("一致するページ本文はありません","No matching page text found"))
                :method.IsTagSemantic?(string.IsNullOrWhiteSpace(query)?AppText.L("AIタグ候補から探す言葉を入力してください","Enter words to search AI tag suggestions"):AppText.L("AIタグ候補のAI検索データがありません","No AI search index for AI tag suggestions"))
                :method.IsTagCandidates?AppText.L("該当するAIタグ候補はありません","No matching AI tag suggestions")
                :method.IsVideoAudioContent?(string.IsNullOrWhiteSpace(query)?AppText.L("探したい音の特徴を入力してください","Describe the sounds you are looking for"):AppText.L("動画の音のAI検索データがありません","No AI search index for video audio"))
                :method.IsVideoContent?(string.IsNullOrWhiteSpace(query)?AppText.L("探したい動画の場面を入力してください","Describe the video scenes you are looking for"):AppText.L("動画の映像のAI検索データがありません","No AI search index for video frames"))
                :method.IsAI&&query.Length>0?(!string.IsNullOrEmpty(result.SearchStatus)&&result.SearchStatus!="ready"
                    ?AISearchStatus.Guidance(result.SearchStatus,result.SearchCandidateTotal??0,result.IndexedTotal??0,query:query)
                    :result.SearchCandidateTotal>0&&result.IndexedTotal==0?AISearchStatus.Guidance(AISearchStatus.Unindexed,result.SearchCandidateTotal??0,result.IndexedTotal??0)
                    :result.SearchCandidateTotal==0?AISearchStatus.Guidance(AISearchStatus.OutOfScope)
                    :result.SearchStatus=="partially_indexed"&&result.Total==0?AISearchStatus.Guidance(AISearchStatus.PartiallyIndexed,result.SearchCandidateTotal??0,result.IndexedTotal??0)
                    :resultGroup==1&&result.GroupBoundary is null?AppText.L("参考候補はありません","No additional suggestions")
                    :resultGroup==0&&result.OtherTotal>0?AppText.L("しきい値以上の候補はありません","No top suggestions above threshold")
                    :AISearchStatus.Guidance(AISearchStatus.Ready,query:query))
                :query.Length>0?AppText.L("一致する作品はありません","No matching items"):EmptyScopeGuidance();
            var explanation=
                method.IsPageText ? AppText.L("抽出・保存済みのページ本文が検索対象です（同じページ内に検索語がすべて含まれる本を表示しています）。「本を開く」で先頭の一致ページへ移動できます。","Searches extracted and saved page text (shows books where a single page contains all search terms). Choose \"Open book\" to jump to the first matching page.")+(scopeWarning is null?"":" "+scopeWarning)
                : method.IsTagSemantic ? AppText.L("AIタグ候補（英語を含む）から意味が近い作品を表示しています。確定タグとは混ざりません。類似度は正解率ではありません。承認・却下・再生成の後はAI検索データを更新してください。","Shows items whose AI tag suggestions (including English) are semantically close. Kept separate from confirmed tags. Similarity scores are not accuracy. Rebuild the AI index after approving, rejecting, or regenerating.")
                : method.IsTagCandidates ? AppText.L("最新の生成履歴に未承認のAIタグ候補がある作品を表示しています。確定タグにはまだ反映されていません。詳細の「AIタグ候補」から根拠を確認して承認・却下できます。","Shows items with pending AI tag suggestions from the latest generation. Not yet applied to confirmed tags. Open \"AI Tag Suggestions\" in Details to review evidence, approve, or reject.")+(scopeWarning is null?"":" "+scopeWarning)
                : method.IsVideoAudioContent ? AppText.L("AI検索データがある動画内の音を、内容や音の特徴から探します。一致区間の開始から動画を再生できます。先頭の音声トラックが対象です。文字起こしは生成しません。","Searches indexed video audio by content or sound characteristics and lets you play from matching segments. Uses the first audio track; no transcripts are generated.")
                : method.IsVideoContent ? AppText.L("AI検索データがある動画を、場面や動きの内容から探します。一致区間の開始から再生できます。動画内の音は対象外です。","Searches indexed videos by visual scenes and motion, and lets you play from matching segments. Audio is not included.")
                : method.IsAudioContent ? AppText.L("AI検索データがある音声・音楽を、内容や音の特徴から探します。一致した時刻から再生できます。文字起こしは生成しません。","Searches indexed audio and music by content or sound characteristics and lets you play from matching timestamps. No transcripts are generated.")
                : method.IsAI && query.Length>0 ? AppText.L($"AI検索の候補です。{(result.CoverageLimit is int coverage ? $"最大{coverage:N0}件の対象から、" : "")}AI検索データがある作品を類似順に表示します。名前・タグの一致とAI類似候補を区別しています。類似度・一致率は正解率ではありません。{(result.GroupBoundary is double cut?$" 上位候補{result.LeadingTotal:N0}件／参考候補{result.OtherTotal:N0}件（区切り{cut:F3}）。":" 類似度に明確な落差がない場合は自動で区切りません。見た目と言葉の意味では区切りを手動指定できます。")}",$"AI search candidates{(result.CoverageLimit is int coverage2 ? $" (up to {coverage2:N0} items)" : "")}, ordered by similarity among indexed items. Filename/tag matches are distinguished from AI candidates; similarity scores are not accuracy.{(result.GroupBoundary is double cut2?$" Top {result.LeadingTotal:N0} / More {result.OtherTotal:N0} (cutoff {cut2:F3}).":" Without a clear similarity drop, results are not split automatically. You can set a manual cutoff in Visual & Text Meaning mode.")}")+(scopeWarning is null?"":" "+scopeWarning)
                : method.IsAI ? AppText.L("探したい内容を文章で入力してください。初回の設定は左下の「設定」→「AI検索」から行えます。","Describe what you're looking for. Set up AI Search anytime under Settings -> AI Search.")
                : AppText.L("名前・タグの文字検索。","Text search in names & tags. ")+Protocol.DescribePartial(result.PartialWords)+Protocol.DescribeExpansions(result.Expansions)+(scopeWarning is null?"":" "+scopeWarning);
            var summary=method.IsPageText?(string.IsNullOrWhiteSpace(query)?AppText.L("ページ内の文字を入力してください","Enter text to search pages"):AppText.L($"ページ内一致 {result.Total:N0}冊",$"{result.Total:N0} matching books"))
                :method.IsTagSemantic?(result.PendingIndexRemaining is >0?AppText.L($"AIタグ候補 · 要更新 {result.PendingIndexRemaining:N0}件",$"AI Tag Suggestions · {result.PendingIndexRemaining:N0} pending update"):AppText.L("AIタグ候補（AI）","AI Tag Suggestions (AI)"))
                :method.IsTagCandidates?AppText.L($"AIタグ候補あり {result.Total:N0}件",$"{result.Total:N0} items with suggestions")
                :method.IsVideoAudioContent?(string.IsNullOrWhiteSpace(query)?AppText.L("探したい音の特徴を入力してください","Describe video sounds to search"):AppText.L($"動画の音 {result.Total:N0}件 · 準備済み {result.IndexedTotal??0:N0}件",$"Video audio {result.Total:N0} · {result.IndexedTotal??0:N0} indexed"))
                :method.IsVideoContent?(string.IsNullOrWhiteSpace(query)?AppText.L("探したい動画の場面を入力してください","Describe video scenes to search"):AppText.L($"動画の場面 {result.Total:N0}件 · 準備済み {result.IndexedTotal??0:N0}件",$"Video scenes {result.Total:N0} · {result.IndexedTotal??0:N0} indexed"))
                :method.IsAI?(query.Length==0?AppText.L("探したい内容を入力してください","Enter a description to search")
                    :result.SearchStatus=="unindexed"?AppText.L($"未作成（対象 {result.SearchCandidateTotal??0:N0}件）",$"Not indexed ({result.SearchCandidateTotal??0:N0} eligible)")
                    :result.SearchStatus=="out_of_scope"?AppText.L("対象外（0件）","Out of scope (0)")
                    :AppText.L($"AI候補 {result.Total:N0}件（上位 {result.LeadingTotal:N0} · 参考 {result.OtherTotal:N0}）",$"AI suggestions {result.Total:N0} (Top {result.LeadingTotal:N0} · More {result.OtherTotal:N0})"))
                :Protocol.DescribePartial(result.PartialWords)+Protocol.DescribeExpansions(result.Expansions);
            var noticeSeverity=scopeWarning is not null||result.PendingIndexRemaining is >0||(method.IsAI&&query.Length>0&&(result.SearchStatus is "unindexed" or "out_of_scope"||(result.SearchStatus=="partially_indexed"&&result.Total==0)))
                ?InfoBarSeverity.Warning:InfoBarSeverity.Informational;
            Notice(method.IsPageText?AppText.L("ページ内一致","Page Text Matches"):method.IsTagCandidates?AppText.L("AIタグ候補","AI Tag Suggestions"):method.IsAI?AppText.L("AI検索","AI Search"):AppText.L("検索結果","Search Results"),summary+(scopeWarning is null?"":" "+scopeWarning),noticeSeverity,explanation);
            if(origin is not null)
            {
                var guidance=SimilaritySearch.Guidance(result.SimilarityStatus,origin.Kind,directAudioSimilarity,directVideoSimilarity,directVideoAudioSimilarity);
                Empty.Text=result.SimilarityStatus=="ready"
                    ?(result.SearchCandidateTotal is int cand&&cand>0&&result.IndexedTotal==0?AppText.L($"AI検索データが未作成です（対象 {cand:N0}件）",$"AI search data has not been created yet ({cand:N0} eligible)")
                    :result.SearchCandidateTotal==0?AppText.L("条件に合う作品はありません","No matching items")
                    :AppText.L("似た候補はありません","No similar suggestions found"))
                    :guidance;
                var originTitle=origin.Kind=="video"?(directVideoAudioSimilarity?AppText.L("音が似た動画","Videos with similar audio"):directVideoSimilarity?AppText.L("場面が似た動画","Videos with similar scenes"):AppText.L("似た動画","Similar videos")):origin.Kind=="audio"?AppText.L("似た音声・曲","Similar audio / music"):AppText.L("似た画像・表紙","Similar images / covers");
                var simSummary = result.SimilarityStatus != "ready"
                    ? guidance
                    : result.SearchCandidateTotal is int sc && sc > 0 && result.IndexedTotal == 0
                    ? AppText.L($"未作成（対象 {sc:N0}件）",$"Not indexed ({sc:N0} eligible)")
                    : result.SearchCandidateTotal == 0
                    ? AppText.L("対象外（0件）","Out of scope (0)")
                    : AppText.L($"{result.Total:N0}件の候補",$"{result.Total:N0} candidates");
                var simSeverity = scopeWarning is not null || result.SimilarityStatus != "ready" || (result.SearchCandidateTotal is int sc2 && (sc2 == 0 || result.IndexedTotal == 0))
                    ? InfoBarSeverity.Warning
                    : InfoBarSeverity.Informational;
                Notice(originTitle,simSummary+(scopeWarning is null?"":" "+scopeWarning),simSeverity,guidance+(result.SearchComplete?AppText.L(" 選択範囲の準備済み作品全体から表示します。"," Showing results across all indexed items in the selected scope."):result.CoverageLimit is int similarityLimit?AppText.L($" 最大{similarityLimit:N0}件の対象から表示します。",$" Showing up to {similarityLimit:N0} eligible items."):""));
            }
            RestoreSelection();ApplyLibrarySelection();
            UpdateFavoriteRootList();startupSearchSucceeded=true;RecordNavigationLocation();UpdateGettingStarted();
        }
        catch(OperationCanceledException) when(cancellation.IsCancellationRequested)
        {
            if(searches.IsCurrent(version)&&!disposed)
            {
                // Treat the cancelled inputs as attempted. Otherwise PendingSearch
                // immediately schedules the identical request again. Later input
                // changes still differ from these captured values and can search.
                if(explicitlyCancelledSearch!=cancellation)
                {
                    lastQuery=query;lastKind=selectedKind;lastMode=selectedMode;lastRoots=selectedRoots;
                    lastLiteralOnly=literalOnly;lastBoundary=boundary;lastResultGroup=resultGroup;
                }
                if(resultSession is null)
                {
                    resultWindow?.Dispose();resultWindow=null;rows=[];SyncRowsState();active=null;initialSavedItemId=null;BindLibrarySelection();
                    if(!folderSettingsActive){Details.IsPaneOpen=false;DetailKindBadge.Visibility=Visibility.Collapsed;}
                    detailCancellation?.Cancel();DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed;
                    ItemTitle.Text=AppText.L("作品を選んでください","Select an item");ItemPath.Text="";draftTags=[];Tags.Text="";editingShelfIds=[];UpdateShelfEditorLabel();SyncFavoriteToggle(false);Reviewed.IsChecked=false;EditStatus.Text="";UpdateDetailSaveBar();
                    RenderRows();Count.Text=AppText.L("中止しました","Canceled");UpdateBrowseFooter("—",false,false);
                }
                else
                {
                    // A cancelled range read may retain the same valid frozen
                    // result. Restore paging to the rows that remain on screen.
                    page=Math.Max(0,browseStart/resultPageSize);
                    Editor.IsEnabled=active is not null;UpdateDirty();
                    Count.Text=AppText.L($"{resultSession.Total:N0} 件（移動を中止）",$"{resultSession.Total:N0} items (navigation canceled)");
                    var canceledSlotTotal=virtualTotal<=MaxVirtualSlots?virtualTotal:rows.Count;
                    UpdateBrowseFooter(FormatLoadedPageRange(browseStart,canceledSlotTotal,resultSession.Total),browseStart>0,browseStart+canceledSlotTotal<resultSession.Total);
                }
                if(rows.Count==0)
                {
                    GettingStarted.Visibility=Visibility.Collapsed;Empty.Visibility=Visibility.Visible;
                    VisualAssets.State(EmptyArt,"no_results");Empty.Text=AppText.L("検索を中止しました","Search canceled");
                }
                Notice(AppText.L("検索中止","Search Canceled"),AppText.L("検索を中止しました。","Search canceled."),InfoBarSeverity.Informational,AppText.L("ユーザーの操作により検索処理を中止しました。","The search was canceled by the user."));
            }
        }
        catch(Exception ex)
        {
            if(searches.IsCurrent(version))
            {
                var aiIndexingActive=ex is ResultSessionException{AIIndexing:true};
                var isAiMode=origin is not null||SearchMethod.FromIndex(selectedMode).IsAI;
                if(!aiIndexingActive&&ex is ResultSessionException rse&&rse.Status==System.Net.HttpStatusCode.Conflict&&isAiMode&&!disposed)
                {
                    try
                    {
                        using var checkCts=new CancellationTokenSource(TimeSpan.FromMilliseconds(1500));
                        var statusData=await api.GetAsync("api/library/ai/status",checkCts.Token);
                        aiIndexingActive=statusData["state"]?.GetValue<string>() is "running" or "cancelling";
                    }
                    catch{}
                }
                if(!searches.IsCurrent(version)||disposed)return;
                var missingAI=!aiIndexingActive&&origin is null&&ex is not ResultSessionException&&(selectedMode is >0 and <4 or 7 or 8 or 9)&&
                    (ex.Message.Contains("未導入")||ex.Message.Contains("ai_unavailable")||ex.Message.Contains("モデル設定またはAI索引を開けません")||ex.Message.Contains("not installed",StringComparison.OrdinalIgnoreCase));
                lastQuery=query;lastKind=selectedKind;lastMode=selectedMode;lastRoots=selectedRoots;
                lastLiteralOnly=literalOnly;lastBoundary=boundary;lastResultGroup=resultGroup;UpdateActiveSearchScopeBar();
                rows=[];SyncRowsState();active=null;initialSavedItemId=null;if(!folderSettingsActive){Details.IsPaneOpen=false;DetailKindBadge.Visibility=Visibility.Collapsed;}DetailsButton.IsEnabled=false;
                detailCancellation?.Cancel();DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed;
                ItemTitle.Text=AppText.L("作品を選んでください","Select an item");ItemPath.Text="";draftTags=[];Tags.Text="";editingShelfIds=[];UpdateShelfEditorLabel();
                SyncFavoriteToggle(false);Reviewed.IsChecked=false;EditStatus.Text="";UpdateDetailSaveBar();RenderRows();
                GettingStarted.Visibility=Visibility.Collapsed;VisualAssets.State(EmptyArt,aiIndexingActive?"indexing":missingAI?"no_results":"error");
                Empty.Visibility=Visibility.Visible;Count.Text="—";UpdateBrowseFooter("—",false,false);
                Empty.Text=aiIndexingActive?AppText.L("AI検索データの作成中のため結果が更新されました。完了まで少し待つか、名前・タグ検索をご利用ください。","Search results changed while AI indexing is in progress. Please wait for indexing to finish or use Name & Tag search.")
                    :ex is ResultSessionException?AppText.L("結果の有効期限が切れました。再検索してください","Search results expired. Please search again.")
                    :origin is not null?AppText.L("類似検索に失敗しました","Similarity search failed")
                    :missingAI?AppText.L("AIが未設定です（名前・タグ検索は使えます）","AI is not configured (filename/tag search works normally)")
                    :selectedMode is >0 and <4 or 7 or 8 or 9?AppText.L($"この条件ではAI検索できません（{AppText.TranslateBackend(ex.Message)}）",$"AI search cannot run with these settings ({AppText.TranslateBackend(ex.Message)})")
                    :AppText.L("検索できませんでした","Search failed");
                EmptyPrepareAIButton.Visibility=missingAI?Visibility.Visible:Visibility.Collapsed;
                EmptyAIRecovery.Visibility=missingAI||aiIndexingActive?Visibility.Visible:Visibility.Collapsed;
                EmptyResetConditionsButton.Visibility=!missingAI&&!aiIndexingActive&&HasActiveSearchConditions()?Visibility.Visible:Visibility.Collapsed;
                if(aiIndexingActive){Notice(AppText.L("AI検索データを作成中","Building AI search index"),AppText.L("完了まで少し待つか、「名前・タグ」検索をご利用ください。","Please wait for indexing to finish or switch to Name & Tag search."),InfoBarSeverity.Warning);AppLog.Error(ex);}
                else if(missingAI){Notice(AppText.L("AIの準備が必要です","AI setup required"));AppLog.Error(ex);}
                else Failure(ex);
            }
        }
        finally {if(searches.IsCurrent(version)){Busy.Visibility=Visibility.Collapsed;CancelSearchButton.Visibility=Visibility.Collapsed;Items.IsEnabled=true;}}
    }
    private void UpdateBrowseFooter(string pageText,bool canPrev,bool canNext)
    {
        PageNumber.Text=pageText;
        Previous.IsEnabled=canPrev;
        Next.IsEnabled=canNext;
        if(FooterPrevButton is not null)FooterPrevButton.IsEnabled=canPrev;
        if(FooterNextButton is not null)FooterNextButton.IsEnabled=canNext;
        if(FooterPagerButtons is not null)FooterPagerButtons.Visibility=canPrev||canNext?Visibility.Visible:Visibility.Collapsed;
    }
    internal static string FormatLoadedPageRange(int start,int count,int total)=>count==0?AppText.L("0 件","0 items"):start==0&&count>=total?AppText.L($"全 {total:N0} 件",$"{total:N0} total"):AppText.L($"{start+1:N0}–{start+count:N0} 件 / 全 {total:N0} 件",$"{start+1:N0}–{start+count:N0} / {total:N0}");
    private string EmptyScopeGuidance()
    {
        if(selectedTagScope is not null)return AppText.L($"タグ「{selectedTagScope}」の作品はありません",$"No items with tag \"{selectedTagScope}\"");
        if(Kind.SelectedIndex>0)return AppText.L("条件に合う作品はありません","No items match the current filters");
        if(selectedShelfIds is not null)return AppText.L("この棚に作品はありません","No items in this shelf");
        if(selectedSearchRoots is not null)return AppText.L("このフォルダに作品がありません","No items in this folder");
        if(view=="history")return AppText.L("閲覧履歴はまだありません","No browsing history yet");
        if(view=="favorites")return AppText.L("お気に入りはまだありません（★ で追加できます）","No favorites yet (click ★ to add one)");
        return knownRoots.Count>0?AppText.L("作品がありません（登録フォルダの一覧を更新してください）","No items found (try refreshing your registered folders)"):AppText.L("まだ作品がありません","No items yet");
    }
    private MediaRow? RowForKey(object? key)
    {
        if (TryParseOrdinalKey(key, out var ord) && rowByOrdinal.TryGetValue(ord, out var byOrd))
            return byOrd;
        return key is string value
            && int.TryParse(value, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out var id)
            && rowById.TryGetValue(id, out var row) ? row : null;
    }

    private void SyncRowsState(bool updateCaptionHeight = true)
    {
        if (rows.Count == 0) ClearVirtualBlocks();
        else foreach (var row in rows) rowById[row.Id] = row;
        if (updateCaptionHeight) cachedGridCaptionMinHeight = ComputeGridCaptionMinHeight();
    }

    private double ComputeLibraryTileWidth()
    {
        var availW = Items.ActualWidth > 0 ? Items.ActualWidth : ItemListContainer.ActualWidth;
        if (resultScroll is { ViewportWidth: > 0 } && resultScroll.ViewportWidth < availW)
            availW = resultScroll.ViewportWidth;
        return Math.Floor(LibraryTileLayout.Width(Math.Max(1, availW - 16), libraryItemScale));
    }

    private void SyncItemsWrapGridSize()
    {
        if (Items.ItemsPanelRoot is not ItemsWrapGrid wrap) return;
        if (!tiles)
        {
            wrap.ItemWidth = double.NaN;
            wrap.ItemHeight = double.NaN;
            return;
        }
        var availW = Items.ActualWidth > 0 ? Items.ActualWidth : ItemListContainer.ActualWidth;
        if (availW <= 16 || ItemListContainer.ActualHeight <= 48) return;
        var scale = libraryItemScale / 100d;
        var tileW = ComputeLibraryTileWidth();
        var imgHeight = Math.Min(160 * scale, Math.Max(48, ItemListContainer.ActualHeight - 108));
        var captionHeight = cachedGridCaptionMinHeight > 0 ? cachedGridCaptionMinHeight : 24;
        wrap.ItemWidth = tileW + 8;
        wrap.ItemHeight = Math.Ceiling(imgHeight + 24 + captionHeight) + 10;
    }

    private void ItemContainer_ContextRequested(UIElement sender, ContextRequestedEventArgs args)
    {
        if (args.Handled || disposed || sender is not ListViewItem item || item.Tag is not int id || !rowById.TryGetValue(id, out var row)) return;
        var menu = SimilarityMenu(row);
        if (args.TryGetPosition(item, out var position)) menu.ShowAt(item, position);
        else menu.ShowAt(item);
        args.Handled = true;
    }

    private void ReleaseContainer(ListViewItem item, bool detachVisualTree = false)
    {
        realizedItems.Remove(item);
        if (item.ContentTemplateRoot is Border host && host.Tag is MediaCardSlot slot)
        {
            if (slot.CurrentOrdinal >= 0
                && pendingOrdinalContainers.TryGetValue(slot.CurrentOrdinal, out var tracked)
                && ReferenceEquals(tracked, item))
                pendingOrdinalContainers.Remove(slot.CurrentOrdinal);
            if (detachVisualTree)
            {
                item.ContextRequested -= ItemContainer_ContextRequested;
                slot.ResetForRecycle();
                slot.DetachContainer();
                host.Tag = null;
                host.Child = null;
            }
            else
            {
                slot.ResetForRecycle();
            }
        }
        else if (detachVisualTree)
        {
            item.ContextRequested -= ItemContainer_ContextRequested;
            if (item.ContentTemplateRoot is Border clearHost) clearHost.Child = null;
        }
        item.ContextFlyout = null; item.Tag = null;
        AutomationProperties.SetAutomationId(item, "");
        AutomationProperties.SetName(item, "");
    }

    private int CurrentThumbnailEdge()
    {
        var scale = libraryItemScale / 100d;
        var tileWidth = ComputeLibraryTileWidth();
        var imgW = tiles ? Math.Max(64, tileWidth - 20) : 72 * scale;
        var maxH = Math.Max(48, ItemListContainer.ActualHeight - 108);
        var imgH = tiles ? Math.Min(160 * scale, maxH) : 54 * scale;
        return ThumbnailPolicy.EdgeFor(imgW, imgH, XamlRoot?.RasterizationScale ?? 1);
    }

    private void RenderRows()
    {
        ResetFastScroll();
        renderCancellation.Cancel(); renderCancellation.Dispose(); renderCancellation = new();
        SyncRowsState();
        populating = true;
        var detachTrees = appliedItemsPanelTiles != tiles;
        try
        {
            foreach (var item in realizedItems.ToArray()) ReleaseContainer(item, detachVisualTree: detachTrees);
            Items.ItemsSource = null;
            if (detachTrees)
            {
                Items.ItemsPanel = MediaItemsPanel();
                appliedItemsPanelTiles = tiles;
            }
            // Only ordinal strings cross the WinRT collection boundary. MediaRow stays
            // owned by C#; pooled MediaCardSlot containers avoid allocations on scroll.
            resultKeys.Clear();
            var slotCount = virtualTotal <= MaxVirtualSlots ? virtualTotal : rows.Count;
            for (var i = 0; i < slotCount; i++) resultKeys.Add(OrdinalKey(browseStart + i));
            Items.ItemsSource = resultKeys;
            SyncItemsWrapGridSize();
        }
        finally { populating = false; }
        if (rows.Count > 0)
            _ = thumbnails.PrefetchRowsAsync(rows.ToArray(), CurrentThumbnailEdge(), renderCancellation.Token);
        if (resultSession is { } session && virtualTotal <= MaxVirtualSlots && virtualTotal > rows.Count)
        {
            if (rows.Count < Math.Min(VirtualBlockSize, virtualTotal))
                _ = EnsureVirtualBlockAsync(0, session, virtualGeneration, warmNext: false);
            if (virtualTotal > VirtualBlockSize)
                _ = EnsureVirtualBlockAsync(1, session, virtualGeneration, warmNext: false);
        }
    }

    private static string ThumbnailOpenTooltip(MediaRow row)=>ViewerOptions.Value.OpenExternally
        ?AppText.L("ダブルクリックでWindowsの既定アプリで開く","Double-click to open with Windows default app")
        :ImageViewerPolicy.CanOpen(row)?AppText.L("ダブルクリックで画像を開く","Double-click to open image")
        :VideoPlayerPolicy.CanOpen(row)?AppText.L("ダブルクリックで動画を再生","Double-click to play video")
        :AudioPlayerPolicy.CanOpen(row)?AppText.L("ダブルクリックで音声を再生","Double-click to play audio")
        :AppText.L("ダブルクリックで本を開く","Double-click to open book");
    private void RefreshThumbnailTooltips()
    {
        foreach (var item in realizedItems)
            if (item.ContentTemplateRoot is Border { Tag: MediaCardSlot slot })
                slot.RefreshOpenTooltip();
    }
    private string FormatRowMetadata(MediaRow row, bool summarizeShelves = true)
    {
        var availability=row.Availability=="present"?"":AvailabilityLabel(row.Availability);
        var shelves=row.ShelfIds.Length>0?row.ShelfIds.Select(ShelfName).Where(name=>!string.IsNullOrWhiteSpace(name)).ToArray():string.IsNullOrWhiteSpace(row.Shelf)?[]:new[]{row.Shelf};
        if(!summarizeShelves)
        {
            var fullShelves=ShelfProtocol.SummarizeNames(shelves,maxVisible:0);
            var fullTags=string.Join(AppText.L("、",", "),row.Tags);
            return $"{row.MatchLabel}{MediaKindFilter.DisplayName(row)}{(availability.Length>0?" · "+availability:"")}{(fullShelves.Length>0?AppText.L(" · 棚:"," · Shelf:")+fullShelves:"")}{(fullTags.Length>0?" · "+fullTags:"")}";
        }
        var parts=new List<string>();
        if(availability.Length>0)parts.Add(availability);
        return row.MatchLabel+string.Join(" · ",parts);
    }
    private Border CreateCardBadge(string text, double maxWidth, string? automationId = null)
    {
        var tb = new TextBlock
        {
            Text = text,
            MaxWidth = maxWidth,
            MaxLines = 1,
            TextWrapping = TextWrapping.NoWrap,
            TextTrimming = TextTrimming.CharacterEllipsis,
            Style = (Style)Resources["MediaMetadataStyle"],
        };
        if (automationId is not null) AutomationProperties.SetAutomationId(tb, automationId);
        return new()
        {
            Style = (Style)Resources["CardBadgeBorderStyle"],
            Child = tb,
        };
    }
    private string FormatListFolderLabel(MediaRow row)
    {
        var root = knownRoots.FirstOrDefault(r => r.Id == row.RootId);
        var rootName = root is null ? "" : (!string.IsNullOrWhiteSpace(root.Name) ? root.Name : root.ShortPath);
        var loc = row.Location.Replace('\\', '/');
        if (row.IsFolderBook)
        {
            var rel = loc == "./" ? rootName : loc.TrimEnd('/');
            return string.IsNullOrWhiteSpace(rel) ? "" : AppText.L($"📁 {rel}（一冊）",$"📁 {rel} (Book)");
        }
        var slash = loc.LastIndexOf('/');
        var sub = slash > 0 ? loc[..slash] : "";
        if (!string.IsNullOrWhiteSpace(rootName) && !string.IsNullOrWhiteSpace(sub)) return $"📁 {rootName}/{sub}";
        if (!string.IsNullOrWhiteSpace(sub)) return $"📁 {sub}";
        if (!string.IsNullOrWhiteSpace(rootName)) return $"📁 {rootName}";
        return "";
    }
    private static string FormatListFileDetails(MediaRow row)
    {
        var parts = new List<string>(3);
        if (!row.IsFolderBook && row.Modified > 0)
        {
            try
            {
                parts.Add(DateTimeOffset.FromUnixTimeMilliseconds(row.Modified / 1000000).ToLocalTime().ToString("yyyy/MM/dd HH:mm"));
            }
            catch (ArgumentOutOfRangeException) { }
        }
        if (row.Size > 0)
        {
            var sizeText = row.Size >= 1024L * 1024 * 1024 ? $"{row.Size / (1024d * 1024 * 1024):N2} GB"
                : row.Size >= 1024L * 1024 ? $"{row.Size / (1024d * 1024):N1} MB"
                : $"{Math.Max(1, Math.Round(row.Size / 1024d)):N0} KB";
            parts.Add(sizeText);
        }
        if (!row.IsFolderBook)
        {
            var ext = System.IO.Path.GetExtension(row.Location).TrimStart('.').ToUpperInvariant();
            if (!string.IsNullOrEmpty(ext)) parts.Add(ext);
        }
        return string.Join(" · ", parts);
    }
    private MediaCardSlot EnsureSlot(ListViewItem item, Border host)
    {
        if (host.Tag is MediaCardSlot existing)
        {
            if (existing.IsTiles == tiles)
            {
                existing.AttachContainer(item);
                return existing;
            }
            existing.ResetForRecycle();
            existing.DetachContainer();
            host.Tag = null;
            host.Child = null;
        }
        var slot = new MediaCardSlot(
            isTiles: tiles,
            resources: GetCardResources(),
            pointerPressedHandler: new PointerEventHandler(LibrarySelectionPointerPressed),
            onOpenPreview: OpenPreviewAsync,
            onToggleFavorite: row => SetFavoriteAsync(row, !row.Favorite),
            onOpenDetails: OpenRowDetailsAsync,
            onOpenQuick: OpenRowPreviewQuickAsync,
            formatShortMetadata: row => FormatRowMetadata(row, summarizeShelves: true),
            formatFullMetadata: row => FormatRowMetadata(row, summarizeShelves: false),
            formatFolderLabel: FormatListFolderLabel,
            shelfName: ShelfName,
            kindIndex: () => Kind.SelectedIndex,
            canOpenMedia: static row => ImageViewerPolicy.CanOpen(row) || ArchiveManifest.CanOpen(row) || VideoPlayerPolicy.CanOpen(row) || AudioPlayerPolicy.CanOpen(row),
            openTooltip: ThumbnailOpenTooltip);
        slot.RefreshThumbnail = () => _ = RefreshSlotThumbnailAsync(slot, force: false);
        slot.PreviewImage.Loaded += (_, _) => _ = RefreshSlotThumbnailAsync(slot, force: false);
        slot.PreviewImage.SizeChanged += (_, _) =>
        {
            slot.ConstrainCaption();
            _ = RefreshSlotThumbnailAsync(slot, force: false);
        };
        slot.PreviewImage.Unloaded += (_, _) => slot.UnloadImage();
        slot.AttachContainer(item);
        item.Margin = tiles ? new Thickness(0, 0, 10, 10) : new Thickness(0, 0, 8, 6);
        item.ContextRequested -= ItemContainer_ContextRequested;
        item.ContextRequested += ItemContainer_ContextRequested;
        host.Tag = slot;
        host.Child = slot.Root;
        return slot;
    }

    private void SizeCardSlot(ListViewItem item, MediaCardSlot slot)
    {
        var scale = libraryItemScale / 100d;
        var width = ComputeLibraryTileWidth();
        var cardWidth = tiles ? Math.Max(1, width - 2) : double.NaN;
        var imgWidth = tiles ? Math.Max(64, width - 20) : 72 * scale;
        var height = Math.Max(48, ItemListContainer.ActualHeight - 108);
        var imgHeight = tiles ? Math.Min(160 * scale, height) : 54 * scale;
        slot.Root.MinHeight = tiles ? 0 : Math.Max(66, 54 * scale + 12);
        slot.ApplySizing(cardWidth, imgWidth, imgHeight, GridCaptionMinHeight(), layoutSizeEpoch);
    }

    private void BindSlotWithRow(ListViewItem item, MediaCardSlot slot, MediaRow row, int ordinal, bool scheduleThumbnail)
    {
        pendingOrdinalContainers.Remove(ordinal);
        if (slot.AppliedLayoutEpoch != layoutSizeEpoch) SizeCardSlot(item, slot);
        slot.BindRow(row, ordinal, MediaKindFilter.DisplayName(row), DetailKindLabel(row), tiles ? "" : FormatListFileDetails(row));
        item.Tag = row.Id;
        AutomationProperties.SetAutomationId(item, $"Item{row.Id}");
        AutomationProperties.SetName(item, row.Title);
        UpdateSelectionFrame(item);
        if (tiles && Items.ItemsPanelRoot is ItemsWrapGrid wrap && (double.IsNaN(wrap.ItemWidth) || double.IsNaN(wrap.ItemHeight)))
            SyncItemsWrapGridSize();
        var initialEdge = ThumbnailPolicy.EdgeFor(slot.PreviewImage.Width, slot.PreviewImage.Height, XamlRoot?.RasterizationScale ?? 1);
        if (thumbnails.TryGetCached(row, initialEdge) is BitmapImage cachedBitmap)
        {
            slot.RequestedEdge = initialEdge;
            ++slot.ThumbVersion;
            slot.VisibleCts?.Cancel(); slot.VisibleCts?.Dispose(); slot.VisibleCts = null;
            if (!ReferenceEquals(slot.PreviewImage.Source, cachedBitmap)) slot.PreviewImage.Source = cachedBitmap;
            slot.Placeholder.Visibility = Visibility.Collapsed;
            slot.PreviewStatus.Text = "";
            slot.PreviewStatus.Visibility = Visibility.Collapsed;
        }
        else if (scheduleThumbnail)
        {
            _ = RefreshSlotThumbnailAsync(slot, force: false);
        }
    }

    private void HydratePendingOrdinalContainer(ListViewItem item, MediaRow row, int ordinal)
    {
        pendingOrdinalContainers.Remove(ordinal);
        if (disposed || item.ContentTemplateRoot is not Border { Tag: MediaCardSlot slot } || slot.CurrentOrdinal != ordinal)
            return;
        BindSlotWithRow(item, slot, row, ordinal, scheduleThumbnail: true);
    }

    private async Task RefreshSlotThumbnailAsync(MediaCardSlot slot, bool force = false)
    {
        var row = slot.CurrentRow;
        var renderToken = renderCancellation.Token;
        if (row is null || !slot.PreviewImage.IsLoaded || renderToken.IsCancellationRequested || disposed) return;
        var edge = ThumbnailPolicy.EdgeFor(slot.PreviewImage.Width, slot.PreviewImage.Height, XamlRoot?.RasterizationScale ?? 1);
        if (!force && slot.RequestedEdge == edge) return;
        if (thumbnails.TryGetCached(row, edge) is BitmapImage instantBitmap)
        {
            slot.RequestedEdge = edge;
            ++slot.ThumbVersion;
            slot.VisibleCts?.Cancel(); slot.VisibleCts?.Dispose(); slot.VisibleCts = null;
            if (!ReferenceEquals(slot.PreviewImage.Source, instantBitmap)) slot.PreviewImage.Source = instantBitmap;
            slot.Placeholder.Visibility = Visibility.Collapsed;
            slot.PreviewStatus.Text = "";
            slot.PreviewStatus.Visibility = Visibility.Collapsed;
            return;
        }
        if (fastScrolling) return;
        slot.RequestedEdge = edge;
        var version = ++slot.ThumbVersion;
        slot.VisibleCts?.Cancel(); slot.VisibleCts?.Dispose();
        slot.VisibleCts = CancellationTokenSource.CreateLinkedTokenSource(renderToken);
        var cancellation = slot.VisibleCts.Token;
        try
        {
            if (!force && slot.PreviewImage.Source is not null) await Task.Delay(80, cancellation);
            var bitmap = await thumbnails.GetAsync(row, cancellation, edge);
            if (cancellation.IsCancellationRequested || disposed || version != slot.ThumbVersion) return;
            slot.PreviewImage.Source = bitmap;
            slot.Placeholder.Visibility = bitmap is null ? Visibility.Visible : Visibility.Collapsed;
            slot.PreviewStatus.Text = "";
            slot.PreviewStatus.Visibility = Visibility.Collapsed;
        }
        catch (OperationCanceledException) { }
    }

    private void Items_ContainerContentChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
    {
        if (args.ItemContainer is not ListViewItem item) return;
        if (args.InRecycleQueue || disposed || item.ContentTemplateRoot is not Border host || !TryParseOrdinalKey(args.Item, out var ordinal))
        {
            ReleaseContainer(item);
            return;
        }
        args.Handled = true;
        var slot = EnsureSlot(item, host);
        if (slot.CurrentOrdinal >= 0 && slot.CurrentOrdinal != ordinal
            && pendingOrdinalContainers.TryGetValue(slot.CurrentOrdinal, out var prev)
            && ReferenceEquals(prev, item))
            pendingOrdinalContainers.Remove(slot.CurrentOrdinal);
        slot.ResetForRecycle();
        realizedItems.Add(item);
        if (slot.AppliedLayoutEpoch != layoutSizeEpoch) SizeCardSlot(item, slot);
        if (RowForKey(args.Item) is MediaRow row)
        {
            BindSlotWithRow(item, slot, row, ordinal, scheduleThumbnail: false);
            if (slot.PreviewImage.Source is null && !fastScrolling)
                args.RegisterUpdateCallback(Items_ContainerContentChanging_Phase1);
        }
        else
        {
            slot.BindSkeleton(ordinal);
            item.Tag = null;
            AutomationProperties.SetAutomationId(item, "");
            AutomationProperties.SetName(item, "");
            UpdateSelectionFrame(item);
            pendingOrdinalContainers[ordinal] = item;
            if (resultSession is { } session)
                _ = EnsureVirtualBlockAsync(ordinal / VirtualBlockSize, session, virtualGeneration, warmNext: !fastScrolling);
        }
    }

    private void Items_ContainerContentChanging_Phase1(ListViewBase sender, ContainerContentChangingEventArgs args)
    {
        if (args.InRecycleQueue || disposed || args.ItemContainer is not ListViewItem item) return;
        if (item.ContentTemplateRoot is Border { Tag: MediaCardSlot { CurrentRow: not null } slot })
            _ = RefreshSlotThumbnailAsync(slot, force: false);
    }
    private static double EstimateTilePillHeight(string icon, string summary)
    {
        var (primary, score, secondary) = Protocol.FormatTileEvidence(icon, summary);
        return score is not null || secondary is not null || primary.Length > 18 ? 44 : 28;
    }

    private double ComputeGridCaptionMinHeight()
    {
        if (!tiles) return 0;
        var maxHeight = 24.0;
        var nonDefaultImageCheck = Kind.SelectedIndex is not (0 or 1);
        foreach (var r in rows)
        {
            var h = 22.0;
            if (r.ShelfIds.Length > 0 || !string.IsNullOrWhiteSpace(r.Shelf) || r.Tags.Length > 0 || (r.Kind == "image" && nonDefaultImageCheck))
                h += 26;
            if (r.Availability != "present" || r.MatchLabel.Length > 0)
                h += 20;
            if (r.AIEvidence.Length > 0)
                h += EstimateTilePillHeight(r.Kind == "video" ? "🎬" : r.Kind == "audio" ? "🎵" : "✨", r.AIEvidence);
            if (r.Proposal is ProposalMatch proposal)
                h += EstimateTilePillHeight("🎬", proposal.Summary);
            if (r.AIPage is AIPageMatch aiPage)
                h += EstimateTilePillHeight("📄", aiPage.Summary);
            if (r.PageText is PageTextMatch pageText)
                h += EstimateTilePillHeight("📄", pageText.Summary);
            if (r.Evidence is { AllDirect: false })
                h += EstimateTilePillHeight("💬", Protocol.DescribeEvidence(r.Evidence));
            if (h > maxHeight) maxHeight = h;
        }
        if (similarityOrigin is not null || SearchMethod.FromIndex(SearchMode.SelectedIndex).IsAI)
        {
            if (maxHeight < 72.0) maxHeight = 72.0;
        }
        return maxHeight;
    }
    private double GridCaptionMinHeight()=>tiles?cachedGridCaptionMinHeight:0;
    private static void ConstrainCardCaption(Grid content,StackPanel text)
    {
        if(content.ColumnDefinitions.Count>=4&&content.Children.OfType<StackPanel>().FirstOrDefault(sp=>Equals(sp.Tag,"ItemListMeta")) is {} listMeta)
        {
            var cw=content.ActualWidth;
            var narrow=cw>0&&cw<560;
            listMeta.Visibility=narrow?Visibility.Collapsed:Visibility.Visible;
            if(cw>0)listMeta.MaxWidth=Math.Clamp(cw*0.28,160,280);
        }
        var available=content.ColumnDefinitions.Count>1?content.ColumnDefinitions[1].ActualWidth
            :content.ActualWidth-content.Padding.Left-content.Padding.Right;
        if(double.IsFinite(available)&&available>0)text.MaxWidth=Math.Max(1,available);
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
        smoothWheelScroller.Stop();
    }
    private void UpdateItemSizes()=>ReflowBrowse(UpdateItemSizesCore);
    private void UpdateItemSizesCore()
    {
        UpdateShelfItemSizes();
        cachedGridCaptionMinHeight = ComputeGridCaptionMinHeight();
        ++layoutSizeEpoch;
        SyncItemsWrapGridSize();
        foreach (var item in realizedItems.ToArray())
        {
            if (item.ContentTemplateRoot is Border { Tag: MediaCardSlot slot })
            {
                SizeCardSlot(item, slot);
                slot.RefreshThumbnail?.Invoke();
            }
        }
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
    private void SmallItemSize_Click(object sender,RoutedEventArgs args)=>ItemSizeSlider.Value=60;
    private void ResetItemSize_Click(object sender,RoutedEventArgs args)=>ItemSizeSlider.Value=100;
    private void LargeItemSize_Click(object sender,RoutedEventArgs args)=>ItemSizeSlider.Value=180;
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
        {if(!disposed)Notice(AppText.L("表示サイズを保存できません","Could not save display size"),AppText.TranslateBackend(ex.Message),InfoBarSeverity.Warning);AppLog.Error(ex);}
    }
    private MenuFlyout SimilarityMenu(MediaRow row)
    {
        if(librarySelection.Count>1&&librarySelection.Contains(row.Id))return SelectionMenu();
        var menu=new MenuFlyout();
        var detailsAction=new MenuFlyoutItem{Text=AppText.L("詳細を開く","Open details")};
        AutomationProperties.SetAutomationId(detailsAction,"OpenDetails"+row.Id);
        detailsAction.Click+=async(_,_)=>await OpenRowDetailsAsync(row);
        menu.Items.Add(detailsAction);
        var favoriteAction=new MenuFlyoutItem{Text=row.Favorite?AppText.L("☆ お気に入りを解除","☆ Remove from favorites"):AppText.L("★ お気に入りに追加","★ Add to favorites")};
        AutomationProperties.SetAutomationId(favoriteAction,"ToggleFavorite"+row.Id);
        favoriteAction.Click+=async(_,_)=>await SetFavoriteAsync(row,!row.Favorite);
        menu.Items.Add(favoriteAction);
        var editShelvesAction=new MenuFlyoutItem{Text=AppText.L("📚 棚に追加・変更…","📚 Add / change shelves…")};
        AutomationProperties.SetAutomationId(editShelvesAction,"EditItemShelves"+row.Id);
        editShelvesAction.Click+=async(_,_)=>await ChooseRowShelvesAsync(row);
        menu.Items.Add(editShelvesAction);
        if(row.ShelfIds.Length>0)
        {
            var shelfIds=row.ShelfIds.ToArray();
            var openShelvesAction=new MenuFlyoutItem{Text=shelfIds.Length==1?AppText.L($"📚 棚「{ShelfName(shelfIds[0])}」を開く",$"📚 Open shelf \"{ShelfName(shelfIds[0])}\""):AppText.L($"📚 所属する棚を開く（{shelfIds.Length:N0} 棚）",$"📚 Open shelves ({shelfIds.Length:N0})")};
            AutomationProperties.SetAutomationId(openShelvesAction,"OpenItemShelves"+row.Id);
            ToolTipService.SetToolTip(openShelvesAction,string.Join(AppText.L("、",", "),shelfIds.Select(ShelfName)));
            openShelvesAction.Click+=async(_,_)=>await OpenShelfScopeAsync(shelfIds);
            menu.Items.Add(openShelvesAction);
        }
        if(row.Tags.Length>0)
        {
            var itemTags=row.Tags.ToArray();
            if(itemTags.Length==1)
            {
                var tag=itemTags[0];
                var searchTagAction=new MenuFlyoutItem{Text=AppText.L($"# タグ「{tag}」で絞り込む",$"# Filter by tag \"{tag}\"")};
                AutomationProperties.SetAutomationId(searchTagAction,$"FilterByItemTag{row.Id}_0");
                searchTagAction.Click+=async(_,_)=>await FilterByTagAsync(tag);
                menu.Items.Add(searchTagAction);
            }
            else
            {
                var tagMenu=new MenuFlyoutSubItem{Text=AppText.L($"# タグで絞り込む（{itemTags.Length:N0} 件）",$"# Filter by tag ({itemTags.Length:N0})")};
                AutomationProperties.SetAutomationId(tagMenu,$"FilterByItemTags{row.Id}");
                ToolTipService.SetToolTip(tagMenu,string.Join(AppText.L("、",", "),itemTags));
                for(var i=0;i<itemTags.Length;i++)
                {
                    var tag=itemTags[i];
                    var tagItem=new MenuFlyoutItem{Text=$"#{tag}"};
                    AutomationProperties.SetAutomationId(tagItem,$"FilterByItemTag{row.Id}_{i}");
                    tagItem.Click+=async(_,_)=>await FilterByTagAsync(tag);
                    tagMenu.Items.Add(tagItem);
                }
                menu.Items.Add(tagMenu);
            }
        }
        if(librarySelection.Anchor is {} anchor&&anchor.Id!=row.Id&&SelectionPosition(row.Id) is {} targetPos)
        {
            var spanCount=Math.Abs((long)targetPos.Ordinal-anchor.Ordinal)+1;
            var overLimit=spanCount>LibrarySelection.Maximum;
            var rangeItem=new MenuFlyoutItem
            {
                Text=overLimit
                    ? AppText.L($"ここまで範囲選択（{spanCount:N0} 件・上限 {LibrarySelection.Maximum} 件）",$"Select range to here ({spanCount:N0}, max {LibrarySelection.Maximum})")
                    : AppText.L($"ここまで範囲選択（{spanCount:N0} 件）",$"Select range to here ({spanCount:N0})"),
                IsEnabled=!overLimit&&!saving&&!dialogOpen&&!preparingSelection&&resultSession is not null&&resultWindow is not null
            };
            AutomationProperties.SetAutomationId(rangeItem,"SelectRangeTo"+row.Id);
            rangeItem.Click+=async(_,_)=>await SelectLibraryRangeAsync(targetPos,false);
            menu.Items.Add(rangeItem);
        }
        menu.Items.Add(new MenuFlyoutSeparator());
        var addedSearchSection=false;
        if(view=="history")
        {
            var remove=new MenuFlyoutItem{Text=AppText.L("閲覧履歴から削除…","Remove from history…")};AutomationProperties.SetAutomationId(remove,"RemoveHistory"+row.Id);
            remove.Click+=async(_,_)=>await DeleteHistoryAsync(row.Id);menu.Items.Add(remove);
            addedSearchSection=true;
        }
        if(SimilaritySearch.CanStart(row))
        {
            AddSimilarityMenuItems(menu.Items,row,forDetail:false);
            addedSearchSection=true;
        }
        if(TagReviewProtocol.CanOpen(row))
        {
            var tagSuggestions=new MenuFlyoutItem{Text=AppText.L("✨ AIタグ候補を作成・確認…","✨ Create / review AI tag suggestions…")};
            AutomationProperties.SetAutomationId(tagSuggestions,"TagSuggestions"+row.Id);
            ToolTipService.SetToolTip(tagSuggestions,AppText.L("WD Tagger でこの作品のタグ候補を生成・承認します。","Generate and review tag suggestions for this item with WD Tagger."));
            tagSuggestions.Click+=async(_,_)=>await OpenTagSuggestionsAsync(row);
            menu.Items.Add(tagSuggestions);
            addedSearchSection=true;
        }
        if(ArchiveManifest.CanOpen(row))
        {
            var pages=new MenuFlyoutItem {Text=AppText.L("ページをAI検索データに追加…","Add pages to AI search index…")};AutomationProperties.SetAutomationId(pages,"IndexBookPages"+row.Id);
            pages.Click+=async(_,_)=>await IndexBookPagesAsync(row);menu.Items.Add(pages);
            var allPages=new MenuFlyoutItem {Text=AppText.L("全ページを一括でAI検索データに追加","Add all pages to AI search index")};AutomationProperties.SetAutomationId(allPages,"IndexBookAllPages"+row.Id);
            allPages.Click+=async(_,_)=>await IndexBookAllPagesDirectAsync(row);menu.Items.Add(allPages);
            var batch=new MenuFlyoutItem {Text=AppText.L("複数の本をAI検索データに追加…","Add multiple books to AI search index…")};AutomationProperties.SetAutomationId(batch,"IndexBookBatch"+row.Id);
            batch.Click+=async(_,_)=>await IndexBookBatchAsync(row);menu.Items.Add(batch);
            addedSearchSection=true;
        }
        if(addedSearchSection)menu.Items.Add(new MenuFlyoutSeparator());
        foreach(var (label,id,explorer) in new[]{(AppText.L("エクスプローラーで開く","Show in Explorer"),"ShowInExplorer",true),(AppText.L("既定のアプリで開く","Open in default app"),"OpenDefault",false)})
        {
            var action=new MenuFlyoutItem{Text=label,IsEnabled=row.Availability=="present"};AutomationProperties.SetAutomationId(action,id+row.Id);
            action.Click+=(_,_)=>OpenInShell(row,explorer);menu.Items.Add(action);
        }
        var copyPath=new MenuFlyoutItem{Text=AppText.L("パスをコピー","Copy path"),IsEnabled=row.Availability=="present"};
        AutomationProperties.SetAutomationId(copyPath,"CopyFilePath"+row.Id);
        copyPath.Click+=(_,_)=>CopyFilePath(row);menu.Items.Add(copyPath);
        return menu;
    }
    private void AddSimilarityMenuItems(IList<MenuFlyoutItemBase> target,MediaRow row,bool forDetail)
    {
        var suffix=forDetail?"":row.Id.ToString();
        var prefix=forDetail?"DetailFindSimilar":"FindSimilar";
        var visualId=forDetail
            ? (row.Kind=="video"?"DetailFindSimilarVideoVisual":row.Kind=="audio"?"DetailFindSimilarAudioVisual":"DetailFindSimilarVisual")
            : ("FindSimilar"+suffix);
        var visualText=row.Kind=="audio"?AppText.L("音の響きが似た曲を探す","Find songs with similar acoustics"):AppText.L("見た目が似た画像・動画を探す","Find visually similar images & videos");
        var visual=new MenuFlyoutItem{Text=visualText};
        AutomationProperties.SetAutomationId(visual,visualId);
        if(row.Kind=="video")ToolTipService.SetToolTip(visual,AppText.L("動画の代表場面から、見た目が似た画像・本・動画を探します（種類フィルタで絞込可）。","Finds images, books, and videos that look similar to this video's key frame (supports type filtering)."));
        else if(row.Kind=="audio")ToolTipService.SetToolTip(visual,AppText.L("AI検索データを使わず、音の響き・音響特徴から似た候補を探します。","Finds similar audio using acoustic features without an AI search index."));
        else ToolTipService.SetToolTip(visual,AppText.L("画像・表紙の見た目から、似た画像・本・動画の場面を探します（種類フィルタで絞込可）。","Finds visually similar images, book covers, and video scenes (supports type filtering)."));
        visual.Click+=async(_,_)=>await StartSimilarityAsync(row);
        if(row.Kind=="video")
        {
            target.Add(visual);
            var content=new MenuFlyoutItem{Text=AppText.L("場面・動きが似た動画を探す（動画専用）","Find videos with similar scenes & motion (videos only)")};
            AutomationProperties.SetAutomationId(content,prefix+"VideoContent"+suffix);
            ToolTipService.SetToolTip(content,AppText.L("作成済みの動画AI検索データから似た場面・動きを探します。","Finds videos with similar scenes and motion from the video AI index."));
            content.Click+=async(_,_)=>await StartSimilarityAsync(row,directVideo:true);
            target.Add(content);
            var audioContent=new MenuFlyoutItem{Text=AppText.L("音が似た動画を探す（動画専用）","Find videos with similar audio (videos only)")};
            AutomationProperties.SetAutomationId(audioContent,prefix+"VideoAudio"+suffix);
            ToolTipService.SetToolTip(audioContent,AppText.L("動画内音声のAI検索データを使います（映像の類似検索とは別です）。","Uses the video-audio AI index (separate from visual similarity)."));
            audioContent.Click+=async(_,_)=>await StartSimilarityAsync(row,directVideoAudio:true);
            target.Add(audioContent);
            return;
        }
        if(row.Kind=="audio")
        {
            var content=new MenuFlyoutItem{Text=AppText.L("似た曲・音声を探す","Find similar audio & music")};
            AutomationProperties.SetAutomationId(content,prefix+"AudioContent"+suffix);
            ToolTipService.SetToolTip(content,AppText.L("音声のAI検索データを使い、内容が似た曲・音声を探します。","Uses the audio AI index to find similar songs and audio."));
            content.Click+=async(_,_)=>await StartSimilarityAsync(row,directAudio:true);
            target.Add(content);
        }
        target.Add(visual);
    }
    private void ClearSimilarity()
    {
        similarityOrigin=null;similarityOriginPage=null;similarityOriginMs=null;directAudioSimilarity=false;directVideoSimilarity=false;directVideoAudioSimilarity=false;similarityReturn=null;UpdateSearchMethod();
    }
    private async Task StartSimilarityAsync(MediaRow source,bool directAudio=false,bool directVideo=false,bool directVideoAudio=false,int? originPage=null,int? originMs=null)
    {
        if(!ready||disposed||saving||dialogOpen||!SimilaritySearch.CanStart(source)||!await transitions.WaitAsync(0))return;
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync())return;
            // Use the context-menu row, never whichever item happens to be selected.
            similarityReturn??=new(lastQuery,lastKind,lastMode,lastRoots?.ToArray(),lastLiteralOnly,lastBoundary,lastResultGroup,view,page,source.Id,selectedShelfIds?.ToArray(),selectedTagScope,similarityOriginPage,similarityOriginMs);
            similarityOrigin=source;similarityOriginPage=originPage;similarityOriginMs=originMs;directAudioSimilarity=directAudio&&source.Kind=="audio";directVideoSimilarity=directVideo&&source.Kind=="video";directVideoAudioSimilarity=directVideoAudio&&source.Kind=="video";
            if(DirectContentSimilarity){populating=true;try{Kind.SelectedIndex=directVideoSimilarity||directVideoAudioSimilarity?3:4;SearchMode.SelectedIndex=directVideoAudioSimilarity?9:directVideoSimilarity?8:7;}finally{populating=false;}}
            if(view=="history")view="all";page=0;UpdateSearchMethod();await LoadAsync();
        }
        finally{transitions.Release();if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
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
            SetShelfScope(bookmark.Shelves);SetTagScope(bookmark.Tag);view=bookmark.View;page=bookmark.Page;ClearSimilarity();RestoreNavigation();populating=false;
            await LoadAsync();
            await FocusRowAsync(bookmark.Selection);
        }
        finally
        {
            populating=false;returningFromSimilarity=false;
            if(!disposed){Busy.Visibility=Visibility.Collapsed;Items.IsEnabled=true;}
            transitions.Release();
            if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async Task FocusRowAsync(int itemId)
    {
        smoothWheelScroller.Stop();
        var key = KeyForItem(itemId);
        if(key is null)return;
        for(var attempt=0;attempt<10&&!disposed&&Items.IsEnabled;attempt++)
        {
            Items.UpdateLayout();
            Items.ScrollIntoView(key);
            Items.UpdateLayout();
            if(Items.ContainerFromItem(key) is ListViewItem target&&target.IsLoaded)
            {
                UpdateSelectionFrame(target);
                if(target.Focus(FocusState.Keyboard)&&target.FocusState!=FocusState.Unfocused)return;
            }
            await Task.Delay(30);
        }
        if(Items.ContainerFromItem(key) is ListViewItem realized)UpdateSelectionFrame(realized);
    }
    private static string AvailabilityLabel(string state) => state switch { "present" => AppText.L("登録済み", "Available"), "missing" => AppText.L("ファイル不明", "File missing"), "unavailable" => AppText.L("接続・更新を確認", "Check connection/refresh"), _ => state };
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
        }finally{transitions.Release();if((PendingAutoSearch)&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void Items_Changed(object sender,SelectionChangedEventArgs e)=>await ChangeLibrarySelectionAsync();
    private void UpdateSelectionFrame(ListViewItem item)
    {
        var selected=item.IsSelected||(item.Tag is int id&&librarySelection.Contains(id));
        var target=selected?GetCardResources().MediaItemSelectedCard:GetCardResources().MediaItemCard;
        if(target is not null&&!ReferenceEquals(item.Style,target))item.Style=target;
    }
    private int? detailScrollItemId;
    private bool detailScrollResetPending, revertStatusActive;
    private void ApplySelectedRow(MediaRow row)
    {
        var previous=populating;populating=true;
        try
        {
            revertStatusActive=false;
            detailSaveError=null;
            if(detailScrollItemId!=row.Id)
            {
                detailScrollItemId=row.Id;
                detailScrollResetPending=true;
            }
            active=row; editingShelfIds=active.ShelfIds.ToArray();draftTags=active.Tags.ToArray();saved=new(string.Join(", ",draftTags),active.Shelf,active.Favorite,active.Reviewed){ShelfIds=editingShelfIds.ToArray()};
            if(initialSavedItemId!=row.Id)
            {
                initialSavedItemId=row.Id;
                initialSaved=saved;
            }
            Tags.Text="";UpdateShelfEditorLabel();SyncFavoriteToggle(saved.Favorite);
            DetailKindBadgeText.Text=DetailKindLabel(active);
            DetailKindBadge.Visibility=Visibility.Visible;
            Reviewed.IsChecked=saved.Reviewed;
            ItemTitle.Text=active.Title;ItemPath.Text=active.DetailLocationLabel;
            ItemPath.Visibility=string.IsNullOrEmpty(ItemPath.Text)?Visibility.Collapsed:Visibility.Visible;
            ToolTipService.SetToolTip(ItemTitle,active.Title);ToolTipService.SetToolTip(ItemPath,active.LocationLabel);
            UpdateFileProperties();Editor.IsEnabled=true;DetailsButton.IsEnabled=true;
            ApplyPendingDetailScrollReset();
            DetailPreview.ContextFlyout=SimilarityMenu(active);
            UpdateDirty();
            if(Details.IsPaneOpen)_ = ShowDetailPreviewAsync(active);
        }
        finally{populating=previous;}
    }
    private void ApplyPendingDetailScrollReset()
    {
        if(!detailScrollResetPending||active?.Id!=detailScrollItemId||!Details.IsPaneOpen||
           Editor.Visibility!=Visibility.Visible||!DetailScroll.IsLoaded||DetailScroll.ViewportHeight<=0)return;
        if(DetailScroll.VerticalOffset<=0||DetailScroll.ChangeView(null,0,null,true))detailScrollResetPending=false;
    }
    private void DetailScroll_Loaded(object sender,RoutedEventArgs e)=>ApplyPendingDetailScrollReset();
    private void DetailScroll_SizeChanged(object sender,SizeChangedEventArgs e)=>ApplyPendingDetailScrollReset();
    private void RestoreSelection()
    {
        var previous=populating;populating=true;
        try
        {
            if(librarySelection.Count==0&&active is not null&&SelectionPosition(active.Id) is {} position)librarySelection.Single(position);
            Items.SelectedItems.Clear();
            foreach(var id in librarySelection.Ids)
            {
                if(ordinalById.TryGetValue(id,out var ord))
                {
                    var idx=ord-browseStart;
                    if(idx>=0&&idx<resultKeys.Count)Items.SelectedItems.Add(resultKeys[idx]);
                }
            }
        }
        finally{populating=previous;}
        UpdateLibrarySelectionTools();
    }
    private void UpdateDetailSaveBar(bool blocked=false)
    {
        if(DetailSaveBar is null||DetailSaveButtons is null)return;
        var showButtons=active is not null&&CanRevertToInitial&&!saving&&!blocked;
        DetailSaveButtons.Visibility=showButtons?Visibility.Visible:Visibility.Collapsed;
        DetailSaveBar.Visibility=active is not null&&(showButtons||saving||blocked||!string.IsNullOrEmpty(EditStatus.Text))
            ?Visibility.Visible:Visibility.Collapsed;
    }
    private void UpdateDirty()
    {
        if(!ready)return;
        var blocked=active is not null&&tagReviewSyncItem==active.Id;
        Tags.IsEnabled=Shelf.IsEnabled=ChooseShelvesButton.IsEnabled=Favorite.IsEnabled=Reviewed.IsEnabled=!blocked;
        if(CommitTagInputButton is not null)CommitTagInputButton.IsEnabled=!blocked&&active is not null&&!saving&&!string.IsNullOrWhiteSpace(Tags.Text);
        UpdateDetailActions();
        if(blocked)
        {
            revertStatusActive=false;
            detailSaveError=null;
            EditStatus.Text=AppText.L("タグを確認できません。AI候補を開き直してください","Could not verify tags. Reopen AI Suggestions.");
            Save.Visibility=Visibility.Collapsed;
            Save.IsEnabled=false;
            RevertEditsButton.Visibility=Visibility.Collapsed;
            RevertEditsButton.IsEnabled=false;
            UpdateDetailSaveBar(blocked:true);
            return;
        }
        var canRevert=CanRevertToInitial&&!saving;
        if(canRevert)revertStatusActive=false;
        EditStatus.Text=detailSaveError is not null?detailSaveError
            :saving?AppText.L("保存しています…","Saving…")
            :canRevert?(resultsNeedRefresh?AppText.L("保存しました（再検索してください）","Saved (refresh search)"):AppText.L("✓ 変更は自動保存されました","✓ Changes saved automatically"))
            :revertStatusActive?AppText.L("変更を元に戻しました","Changes reverted")
            :"";
        Save.Visibility=Visibility.Collapsed;
        Save.IsEnabled=false;
        RevertEditsButton.Visibility=canRevert?Visibility.Visible:Visibility.Collapsed;
        RevertEditsButton.IsEnabled=canRevert;
        UpdateDetailSaveBar(blocked:false);
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
        DetailAvailabilityHint.Text=active is null?"":active.Availability!="present"
            ?active.Availability=="missing"
                ?AppText.L("⚠ 元ファイルが見つかりません（タグ・棚は保持）","⚠ Source file not found (tags & shelves kept)")
                :AppText.L("⚠ 元ファイルにアクセスできません（タグ・棚は保持）","⚠ Cannot access source file (tags & shelves kept)")
            :active.Kind is "image" or "book" or "archive" or "video" or "audio"&&
                !OpenImage.IsEnabled&&!OpenBook.IsEnabled&&!OpenVideo.IsEnabled&&!OpenAudio.IsEnabled
                ?AppText.L("アプリ内では開けない形式です（ファイル情報から場所を開けます）","This format cannot be opened in-app (you can reveal it from File Info)"):"";
        DetailAvailabilityHint.Visibility=DetailAvailabilityHint.Text.Length>0?Visibility.Visible:Visibility.Collapsed;
        // Describe the same match passed to the reader/player. The viewer still
        // checks the current source revision or available playback duration.
        DetailOpenHint.Text="";
        if(active is {Kind: "book" or "archive"} book)
        {
            var matchPage=book.AIPage?.Page??book.PageText?.Pages.FirstOrDefault()?.Page;
            var matchState=book.AIPage?.SourceState??book.PageText?.SourceState;
            if(matchPage is int page)
                DetailOpenHint.Text=matchState=="current"
                    ?AppText.L($"{page+1:N0} ページ目を開きます",$"Opens at page {page+1:N0}")
                    :AppText.L("読書位置を復元して開きます","Opens at saved reading position");
        }
        else if(active is {Kind: "video" or "audio"} media)
        {
            var matchMs=media.Kind=="video"?VideoPlayerPolicy.MatchStartMs(media):media.AudioMatchMs??media.VideoMatchMs;
            if(matchMs is int ms)
                DetailOpenHint.Text=AppText.L($"{VideoPlayerPolicy.FormatTime(TimeSpan.FromMilliseconds(ms))} から再生します",$"Plays from {VideoPlayerPolicy.FormatTime(TimeSpan.FromMilliseconds(ms))}");
        }
        DetailOpenHint.Visibility=DetailOpenHint.Text.Length>0?Visibility.Visible:Visibility.Collapsed;
        var evidence=new List<string>();
        if(active?.AIEvidence is {Length:>0} aiEvidence)evidence.Add(aiEvidence);
        if(active?.AIPage is {} pageEvidence)evidence.Add(pageEvidence.Summary);
        if(active?.PageText is {} textEvidence)evidence.Add(textEvidence.Summary);
        if(active?.Proposal is {} proposalEvidence)evidence.Add(proposalEvidence.Summary);
        if(active?.Evidence is {} wordEvidence)evidence.Add(Protocol.DescribeEvidence(wordEvidence,wordsPerPart:int.MaxValue));
        DetailEvidenceText.Text=string.Join("\n\n",evidence.Where(value=>value.Length>0));
        DetailEvidence.Visibility=DetailEvidenceText.Text.Length>0?Visibility.Visible:Visibility.Collapsed;
        var canReview=active is not null&&TagReviewProtocol.CanOpen(active);
        TagSuggestionsButton.Visibility=canReview?Visibility.Visible:Visibility.Collapsed;
        TagSuggestionsButton.IsEnabled=canReview&&!saving;
        AudioSearchHint.Text=SimilaritySearch.AudioIndexingGuidance;
        AudioSearchHint.Visibility=active?.Kind=="audio"?Visibility.Visible:Visibility.Collapsed;
        var hasActiveShelves=active is {ShelfIds.Length:>1};
        OpenActiveShelvesButton.Visibility=hasActiveShelves?Visibility.Visible:Visibility.Collapsed;
        OpenActiveShelvesButton.IsEnabled=hasActiveShelves&&!saving&&tagReviewSyncItem!=active!.Id;
        ToolTipService.SetToolTip(OpenActiveShelvesButton,hasActiveShelves?AppText.L($"所属する棚をすべて開く（{string.Join("、",active!.ShelfIds.Select(ShelfName))}）",$"Open all assigned shelves ({string.Join(", ",active!.ShelfIds.Select(ShelfName))})"):AppText.L("この作品の所属する棚を表示","Show shelves assigned to this item"));
        var canFindSimilar=active is not null&&SimilaritySearch.CanStart(active);
        DetailFindSimilarButton.Visibility=canFindSimilar?Visibility.Visible:Visibility.Collapsed;
        DetailFindSimilarButton.IsEnabled=canFindSimilar&&!saving&&tagReviewSyncItem!=active?.Id;
        if(canFindSimilar&&active is {} simRow)
        {
            if(simRow.Kind is "video" or "audio")
            {
                DetailFindSimilarButton.Content=simRow.Kind=="video"?AppText.L("≈ 似た作品…","≈ Similar items…"):AppText.L("≈ 似た音声…","≈ Similar audio…");
                var simFlyout=new MenuFlyout();
                AddSimilarityMenuItems(simFlyout.Items,simRow,forDetail:true);
                DetailFindSimilarButton.Flyout=simFlyout;
            }
            else
            {
                DetailFindSimilarButton.Content=AppText.L("≈ 似た作品","≈ Find similar");
                DetailFindSimilarButton.Flyout=null;
            }
        }
        else DetailFindSimilarButton.Flyout=null;
        FilterByActiveTagButton.Visibility=Visibility.Collapsed;
        FilterByActiveTagButton.IsEnabled=false;
        FilterByActiveTagButton.Flyout=null;

        ActiveTagChipsPanel.Children.Clear();
        var visibleDraftTags=active is null?[]:draftTags;
        var hasDraftTags=visibleDraftTags.Length>0;
        ActiveTagChipsScroll.Visibility=hasDraftTags?Visibility.Visible:Visibility.Collapsed;
        AutomationProperties.SetName(ActiveTagChipsPanel,hasDraftTags?string.Join(", ",visibleDraftTags):AppText.L("タグなし","No tags"));
        if(hasDraftTags)
        {
            var canEditDraft=active is not null&&!saving&&tagReviewSyncItem!=active.Id;
            var maxRowWidth=ActiveTagChipsScroll.ActualWidth>60
                ? ActiveTagChipsScroll.ActualWidth-4
                : Math.Max(180,Details.OpenPaneLength-56);
            var chipElements=new List<FrameworkElement>(visibleDraftTags.Length);
            for(var i=0;i<visibleDraftTags.Length;i++)
            {
                var index=i;
                var tag=visibleDraftTags[index];
                var chipLabel=new TextBlock{Text="#"+tag,MaxWidth=140,TextTrimming=TextTrimming.CharacterEllipsis,VerticalAlignment=VerticalAlignment.Center,Style=(Style)Resources["MediaMetadataStyle"]};
                var tagBtn=new Button
                {
                    Content=chipLabel,
                    Padding=new Thickness(6,2,4,2),
                    MinWidth=0,
                    MinHeight=0,
                    Background=new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                    BorderThickness=new Thickness(0)
                };
                ToolTipService.SetToolTip(tagBtn,AppText.L($"「{tag}」で一覧を絞り込む",$"Filter list by \"{tag}\""));
                AutomationProperties.SetAutomationId(tagBtn,$"DraftTagChip{index}");
                AutomationProperties.SetName(tagBtn,AppText.L($"タグ「{tag}」で絞り込む",$"Filter by tag \"{tag}\""));
                tagBtn.Click+=async(_,_)=>await FilterByTagAsync(tag);
                var removeBtn=new Button
                {
                    Content="×",
                    Padding=new Thickness(4,1,4,1),
                    MinWidth=0,
                    MinHeight=0,
                    Background=new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                    BorderThickness=new Thickness(0),
                    IsEnabled=canEditDraft
                };
                ToolTipService.SetToolTip(removeBtn,AppText.L($"タグ「{tag}」を外す",$"Remove tag \"{tag}\""));
                AutomationProperties.SetAutomationId(removeBtn,$"RemoveDraftTag{index}");
                AutomationProperties.SetName(removeBtn,AppText.L($"タグ「{tag}」を外す",$"Remove tag \"{tag}\""));
                removeBtn.Click+=async(_,_)=>
                {
                    if(active is null||saving||dialogOpen||tagReviewSyncItem==active.Id)return;
                    detailSaveError=null;
                    draftTags=draftTags.Where(existing=>existing!=tag).ToArray();
                    UpdateDirty();
                    Tags.Focus(FocusState.Programmatic);
                    await SaveAsync(commitPendingTagBox:false);
                };
                var chipInner=new StackPanel{Orientation=Orientation.Horizontal,Spacing=2};
                chipInner.Children.Add(tagBtn);
                chipInner.Children.Add(removeBtn);
                chipElements.Add(new Border{Style=(Style)Resources["CardBadgeBorderStyle"],Padding=new Thickness(2),Child=chipInner});
            }
            PopulateWrappedChips(ActiveTagChipsPanel,maxRowWidth,chipElements);
        }

        var effectiveTags=active is null?[]:EffectiveDraftTags();
        var candidateTags=active is null?[]:rows.SelectMany(row=>row.Tags).Where(t=>!string.IsNullOrWhiteSpace(t)).Distinct().Where(t=>!effectiveTags.Contains(t)).Take(25).ToArray();
        var canSuggest=active is not null&&candidateTags.Length>0;
        SuggestExistingTagsButton.Visibility=canSuggest?Visibility.Visible:Visibility.Collapsed;
        SuggestExistingTagsButton.IsEnabled=canSuggest&&!saving&&tagReviewSyncItem!=active!.Id&&effectiveTags.Length<30;
        if(canSuggest)
        {
            var suggestFlyout=new MenuFlyout();
            for(var i=0;i<candidateTags.Length;i++)
            {
                var candidateTag=candidateTags[i];
                var suggestItem=new MenuFlyoutItem{Text=$"＋ {candidateTag}"};
                AutomationProperties.SetAutomationId(suggestItem,$"SuggestTag{i}");
                suggestItem.Click+=async(_,_)=>
                {
                    if(active is null||saving||dialogOpen||tagReviewSyncItem==active.Id)return;
                    detailSaveError=null;
                    draftTags=draftTags.Append(candidateTag).Distinct().ToArray();
                    UpdateDirty();
                    Tags.Focus(FocusState.Programmatic);
                    await SaveAsync(commitPendingTagBox:false);
                };
                suggestFlyout.Items.Add(suggestItem);
            }
            SuggestExistingTagsButton.Flyout=suggestFlyout;
        }
        else SuggestExistingTagsButton.Flyout=null;
    }
    private bool CommitTagInput()
    {
        if(!ready||disposed||saving||dialogOpen||active is null||tagReviewSyncItem==active.Id)return false;
        var added=ParseTagTokens(Tags.Text);
        var changed=false;
        if(added.Length>0)
        {
            var next=draftTags.Concat(added).Distinct().ToArray();
            changed=!next.SequenceEqual(draftTags);
            draftTags=next;
        }
        var previous=populating;populating=true;
        try{Tags.Text="";Tags.SelectionStart=0;}
        finally{populating=previous;}
        if(changed)detailSaveError=null;
        UpdateDirty();
        Tags.Focus(FocusState.Programmatic);
        return changed;
    }
    private async void CommitTagInput_Click(object sender,RoutedEventArgs e)
    {
        if(CommitTagInput())await SaveAsync(commitPendingTagBox:false);
    }
    private async void Tags_KeyDown(object sender,KeyRoutedEventArgs e)
    {
        if(IsUnmodifiedEnter(e)&&ready&&!disposed&&!saving&&!dialogOpen)
        {
            e.Handled=true;
            if(CommitTagInput())await SaveAsync(commitPendingTagBox:false);
            return;
        }
        if(e.Key==Windows.System.VirtualKey.Enter&&SelectionKey(Windows.System.VirtualKey.Control)&&!SelectionKey(Windows.System.VirtualKey.Shift)&&!SelectionKey(Windows.System.VirtualKey.Menu)
           &&ready&&!disposed&&!saving&&!dialogOpen&&Dirty&&tagReviewSyncItem!=active?.Id)
        {
            e.Handled=true;
            await SaveAsync();
        }
    }
    private void Editor_Changed(object sender,TextChangedEventArgs e)
    {
        if(!populating)detailSaveError=null;
        UpdateDirty();
    }
    private async void Favorite_Checked(object sender,RoutedEventArgs args)
    {
        if(!ready||populating||updatingFavorite||active is null||Favorite.IsChecked==saved.Favorite)return;
        await SetFavoriteAsync(active,Favorite.IsChecked==true);
    }
    private async Task SetFavoriteAsync(MediaRow row,bool value)
    {
        if(saving||dialogOpen||tagReviewSyncItem==row.Id||!await transitions.WaitAsync(0))
        {
            if(active?.Id==row.Id){updatingFavorite=true;try{SyncFavoriteToggle(saved.Favorite);}finally{updatingFavorite=false;}}
            return;
        }
        saving=true;Favorite.IsEnabled=false;
        try
        {
            // Save only the flag: an unsaved tag/shelf draft must not be committed.
            bool kept=false;
            if(resultSession is {} session&&!resultsNeedRefresh)kept=await session.EditFavoriteAsync(row.Id,value,CancellationToken.None);
            else await api.PostAsync("api/items/update",new JsonObject{{"ids",new JsonArray(row.Id)},{"changes",new JsonObject{{"favorite",value}}}});
            ApplyFavoriteValue(row,value);
            if(!kept)await RefreshResultRowsAfterEditAsync(favoriteOnly:true);
        }
        catch(Exception ex)
        {
            if(active?.Id==row.Id){updatingFavorite=true;try{SyncFavoriteToggle(saved.Favorite);}finally{updatingFavorite=false;}}
            Failure(ex);
        }
        finally{saving=false;Favorite.IsEnabled=true;UpdateDirty();transitions.Release();}
    }
    private void ApplyFavoriteValue(MediaRow row,bool value)
    {
        row.Favorite=value;
        if(rowById.TryGetValue(row.Id,out var cachedRow))cachedRow.Favorite=value;
        if(rows.FirstOrDefault(item=>item.Id==row.Id) is {} visibleRow)visibleRow.Favorite=value;
        if(active?.Id==row.Id)
        {
            saved=saved with {Favorite=value};
            if(initialSavedItemId==row.Id)initialSaved=initialSaved with {Favorite=value};
            active.Favorite=value;updatingFavorite=true;
            try
            {
                SyncFavoriteToggle(value);
            }
            finally{updatingFavorite=false;}
        }
        RefreshFavoriteCard(row);
    }
    private void RefreshFavoriteCard(MediaRow row)
    {
        foreach(var item in realizedItems.ToArray())
        {
            if(item.ContentTemplateRoot is Border{Tag:MediaCardSlot slot}&&slot.CurrentRow?.Id==row.Id)
            {
                slot.CurrentRow.Favorite=row.Favorite;
                slot.ApplyFavoriteVisuals(slot.CurrentRow,MediaKindFilter.DisplayName(slot.CurrentRow));
            }
        }
        if(active?.Id==row.Id)DetailPreview.ContextFlyout=SimilarityMenu(active);
    }
    private async void Editor_Checked(object sender,RoutedEventArgs e)
    {
        if(!ready||populating||disposed||saving||dialogOpen||active is null||tagReviewSyncItem==active.Id)return;
        detailSaveError=null;
        UpdateDirty();
        await SaveAsync(commitPendingTagBox:false);
    }
    public async Task<bool> ConfirmDiscardAsync() {
        if(saving||dialogOpen)return false;
        RememberCurrentLocation();
        if(!FolderDirty)
        {
            if(active is not null&&!string.IsNullOrEmpty(Tags.Text))
            {
                var previous=populating;populating=true;
                try{Tags.Text="";}finally{populating=previous;}
                UpdateDirty();
            }
            return true;
        }
        var detailsWereOpen=Details.IsPaneOpen;
        dialogOpen=true;
        try {
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("変更を破棄しますか？","Discard changes?"),Content=FolderTargetTitle.Text,PrimaryButtonText=AppText.L("変更を破棄","Discard"),CloseButtonText=AppText.L("編集を続ける","Continue editing"),DefaultButton=ContentDialogButton.Close};
            var accepted=await dialog.ShowAsync()==ContentDialogResult.Primary;
            if(accepted&&FolderDirty&&folderDraft is not null)
            {
                var ids=folderDraft.TargetIds.ToArray();
                folderDraft=null;
                OpenFolderSettingsPanel(ids);
            }
            return accepted;
        }
        finally
        {
            dialogOpen=false;
            if(!disposed&&detailsWereOpen&&(active is not null||librarySelection.Count>0||folderSettingsActive))Details.IsPaneOpen=true;
        }
    }
    private async Task SaveAsync(bool commitPendingTagBox=true,bool isRevert=false) {
        if(commitPendingTagBox)CommitTagInput();
        var snapshot=commitPendingTagBox?Current():CurrentCommitted();
        if(active is null||saving||dialogOpen||tagReviewSyncItem==active.Id||!EditorState.IsDirty(saved,snapshot))return;
        var error=snapshot.Validate();
        if(error is not null){detailSaveError=error;UpdateDirty();return;}
        // Disabling the editor moves WinUI focus elsewhere. Restore only an
        // editor control, and only if the user has not chosen another control
        // while the request was pending. Never take focus from another window.
        var focused=FocusManager.GetFocusedElement(XamlRoot) as Control;
        var restore=focused==Tags||focused==CommitTagInputButton||focused==SuggestExistingTagsButton||focused==Shelf||focused==ChooseShelvesButton||focused==OpenActiveShelvesButton||focused==Favorite||focused==Reviewed||focused==Save||focused==RevertEditsButton||focused==FilterByActiveTagButton||focused==DetailFindSimilarButton;
        var focusState=focused?.FocusState==FocusState.Keyboard?FocusState.Keyboard:FocusState.Programmatic;
        detailSaveError=null;
        saving=true;Editor.IsEnabled=false;var id=active.Id;
        var displacedFocus=FocusManager.GetFocusedElement(XamlRoot);
        UpdateDirty();
        try {
            await api.SaveAsync(id,snapshot);
            saved=snapshot;active.Tags=snapshot.ParsedTags;active.Shelf=snapshot.Shelf;active.ShelfIds=snapshot.ShelfIds?.ToArray()??[];active.Favorite=snapshot.Favorite;active.Reviewed=snapshot.Reviewed;
            draftTags=snapshot.ParsedTags;
            if(commitPendingTagBox||isRevert)
            {
                var beforePopulating=populating;populating=true;
                try{Tags.Text="";}finally{populating=beforePopulating;}
            }
            EditStatus.Text=isRevert?AppText.L("元に戻しました（一覧を更新中…）","Reverted (refreshing list…)"):AppText.L("保存しました（一覧を更新中…）","Saved (refreshing list…)");UpdateDetailSaveBar();await RefreshResultRowsAfterEditAsync();
            if(isRevert)revertStatusActive=true;
            if(!resultsNeedRefresh)Notice(isRevert?AppText.L("変更を元に戻しました","Changes reverted"):AppText.L("保存しました","Saved"));
        }catch(Exception ex){Failure(ex);detailSaveError=AppText.L("保存できませんでした（編集内容は残っています）","Could not save (your edits remain)");}
        finally
        {
            var unchangedFocus=ReferenceEquals(displacedFocus,FocusManager.GetFocusedElement(XamlRoot));
            saving=false;Editor.IsEnabled=true;
            UpdateDirty();
            if(active is not null)DetailPreview.ContextFlyout=SimilarityMenu(active);
            if(!disposed&&active?.Id==id&&Details.IsPaneOpen&&restore&&unchangedFocus)
            {
                // A successful save disables Save; continue at the tag field.
                var target=(focused==Save&&!Save.IsEnabled)||(focused==RevertEditsButton&&!RevertEditsButton.IsEnabled)||(focused==CommitTagInputButton&&!CommitTagInputButton.IsEnabled)||(focused==FilterByActiveTagButton&&!FilterByActiveTagButton.IsEnabled)||(focused==DetailFindSimilarButton&&!DetailFindSimilarButton.IsEnabled)?Tags:focused;
                target?.Focus(focusState);
            }
            if(PendingAutoSearch){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void Save_Click(object sender,RoutedEventArgs e)=>await SaveAsync();
    private async void RevertEdits_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||populating||saving||dialogOpen||active is null||tagReviewSyncItem==active.Id||!CanRevertToInitial)return;
        var itemId=active.Id;
        var baseline=initialSavedItemId==itemId?initialSaved:saved;
        detailSaveError=null;
        var previous=populating;populating=true;
        try
        {
            draftTags=baseline.ParsedTags;Tags.Text="";editingShelfIds=baseline.ShelfIds?.ToArray()??[];UpdateShelfEditorLabel();
            Reviewed.IsChecked=baseline.Reviewed;
        }
        finally{populating=previous;}
        if(EditorState.IsDirty(saved,CurrentCommitted()))
        {
            await SaveAsync(commitPendingTagBox:false,isRevert:true);
        }
        else
        {
            revertStatusActive=true;
            UpdateDirty();
            Notice(AppText.L("変更を元に戻しました","Changes reverted"));
        }
        if(!disposed&&active?.Id==itemId&&Details.IsPaneOpen)Tags.Focus(FocusState.Programmatic);
    }
    private async void DetailFindSimilar_Click(object sender,RoutedEventArgs e)
    {
        if(active is not null&&DetailFindSimilarButton.Flyout is null)await StartSimilarityAsync(active);
    }
    private void SetTagScope(string? tag)
    {
        selectedTagScope=ResultSearchConditions.NormalizeTag(tag);
        UpdateTagScopeLabel();
        UpdateBrowseTagsFlyout();
        UpdateClearSearchConditionsVisibility();
    }
    private void UpdateBrowseTagsFlyout()
    {
        if(BrowseTagsButton is null)return;
        var rankedTags=rows
            .SelectMany(row=>row.Tags.Distinct())
            .GroupBy(tag=>tag)
            .Select(group=>(Tag:group.Key,Count:group.Count()))
            .OrderByDescending(entry=>entry.Count)
            .ThenBy(entry=>entry.Tag,StringComparer.CurrentCultureIgnoreCase)
            .Take(30)
            .ToArray();
        var visible=rankedTags.Length>0||selectedTagScope is not null;
        BrowseTagsButton.Visibility=visible?Visibility.Visible:Visibility.Collapsed;
        BrowseTagsButton.IsEnabled=visible&&!saving;
        if(!visible)
        {
            BrowseTagsButton.Flyout=null;
            return;
        }
        var flyout=new MenuFlyout();
        if(selectedTagScope is not null)
        {
            var clearItem=new MenuFlyoutItem{Text=AppText.L("タグの絞り込みを解除","Clear tag filter")};
            AutomationProperties.SetAutomationId(clearItem,"BrowseTagClear");
            clearItem.Click+=(s,e)=>ClearTagScope_Click(s,e);
            flyout.Items.Add(clearItem);
            if(rankedTags.Length>0)flyout.Items.Add(new MenuFlyoutSeparator());
        }
        if(rankedTags.Length>0)
        {
            var headerItem=new MenuFlyoutItem{Text=AppText.L("よく使われるタグ","Popular tags"),IsEnabled=false};
            AutomationProperties.SetAutomationId(headerItem,"BrowseTagsHeader");
            flyout.Items.Add(headerItem);
        }
        for(var i=0;i<rankedTags.Length;i++)
        {
            var (tag,count)=rankedTags[i];
            var tagItem=new MenuFlyoutItem{Text=AppText.L($"#{tag}（{count:N0} 件）",$"#{tag} ({count:N0})")};
            AutomationProperties.SetAutomationId(tagItem,$"BrowseTagItem{i}");
            tagItem.Click+=async(_,_)=>await FilterByTagAsync(tag);
            flyout.Items.Add(tagItem);
        }
        BrowseTagsButton.Flyout=flyout;
    }
    private void UpdateTagScopeLabel()
    {
        if(TagScopeBar is null||TagScopeText is null)return;
        TagScopeBar.Visibility=selectedTagScope is null?Visibility.Collapsed:Visibility.Visible;
        TagScopeText.Text=selectedTagScope is null?"":AppText.L($"タグ：{selectedTagScope}",$"Tag: {selectedTagScope}");
        ToolTipService.SetToolTip(TagScopeText,selectedTagScope is null?"":AppText.L($"確定タグで絞り込み中：{selectedTagScope}",$"Filtering by tag: {selectedTagScope}"));
    }
    private async void ClearTagScope_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||disposed||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync())return;
            SetTagScope(null);
            page=0;
            RestoreNavigation();
            await LoadAsync();
        }
        finally{transitions.Release();if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async Task FilterByTagAsync(string tag)
    {
        if(!ready||disposed||saving||dialogOpen||string.IsNullOrWhiteSpace(tag)||!await transitions.WaitAsync(0))return;
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync())return;
            similarityCancellation?.Cancel();
            populating=true;
            try
            {
                queryComposing=false;
                CloseSettingsHubCore();
                CloseShelfHubCore();
                CloseFolderHubCore();
                SetTagScope(tag);
                UpdateSearchMethod();
                RestoreNavigation();
            }
            finally{populating=false;}
            UpdateClearSearchConditionsVisibility();
            page=0;
            await LoadAsync();
        }
        finally{transitions.Release();if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void SaveShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){e.Handled=true;await SaveAsync();}
    private void SearchShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){e.Handled=true;if(ready&&!dialogOpen)Query.Focus(FocusState.Keyboard);}
    private bool queryComposing;
    private void Query_CompositionStarted(TextBox sender,TextCompositionStartedEventArgs args){queryComposing=true;searchTimer?.Stop();}
    private void Query_CompositionEnded(TextBox sender,TextCompositionEndedEventArgs args)
    {
        queryComposing=false;
        searchTimer?.Stop();
        if(ready&&!populating&&!disposed&&PendingAutoSearch)searchTimer!.Start();
    }
    private void Query_Changed(object sender,TextChangedEventArgs e){UpdateClearSearchConditionsVisibility();searchTimer?.Stop();if(ready&&!populating&&!queryComposing&&PendingAutoSearch)searchTimer!.Start();}
    private bool HasActiveSearchConditions()
        =>!string.IsNullOrEmpty(Query?.Text)
        ||(Kind?.SelectedIndex??0)>0
        ||(SearchMode?.SelectedIndex??0)>0
        ||similarityOrigin is not null
        ||selectedShelfIds is not null
        ||selectedTagScope is not null
        ||selectedSearchRoots is not null
        ||AIMatchedOnly?.IsChecked==true
        ||UnreviewedOnly?.IsChecked==true
        ||view=="unreviewed"
        ||(SimilarityBoundary is not null&&double.IsFinite(SimilarityBoundary.Value))
        ||(AIResultGroup?.SelectedIndex??0)>0;
    private void UpdateClearSearchConditionsVisibility()
    {
        if(ClearSearchConditionsButton is null)return;
        var next=HasActiveSearchConditions()?Visibility.Visible:Visibility.Collapsed;
        if(ClearSearchConditionsButton.Visibility!=next)
        {
            ClearSearchConditionsButton.Visibility=next;
            UpdateSearchToolbarLayout();
        }
    }
    private async void ClearSearchConditions_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||disposed||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync())return;
            similarityCancellation?.Cancel();
            populating=true;
            try
            {
                queryComposing=false;
                Query.Text="";
                Kind.SelectedIndex=0;
                SearchMode.SelectedIndex=0;
                AIMatchedOnly.IsChecked=false;
                UnreviewedOnly.IsChecked=false;
                if(view=="unreviewed")view="all";
                SimilarityBoundary.Value=double.NaN;
                AIResultGroup.SelectedIndex=0;
                CloseSettingsHubCore();
                CloseShelfHubCore();
                CloseFolderHubCore();
                SetShelfScope(null);
                SetTagScope(null);
                RestoreSearchRoots(null);
                ClearSimilarity();
                UpdateSearchMethod();
                RestoreNavigation();
            }
            finally{populating=false;}
            UpdateClearSearchConditionsVisibility();
            page=0;
            await LoadAsync();
        }
        finally{transitions.Release();if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private void Query_KeyDown(object sender,KeyRoutedEventArgs e)
    {
        if(!IsUnmodifiedEnter(e)||queryComposing||!ready||disposed||saving||dialogOpen||populating)return;
        e.Handled=true;
        Search_Click(sender,new RoutedEventArgs());
    }
    private async void Search_Click(object sender,RoutedEventArgs e){searchTimer.Stop();await NavigateAsync(0,true);}
    private async void EmptyLiteralSearch_Click(object sender,RoutedEventArgs e)
    {
        searchTimer.Stop();
        populating=true;SearchMode.SelectedIndex=0;populating=false;
        await NavigateAsync(0,true);
    }
    private void CancelSearch_Click(object sender,RoutedEventArgs e)
    {
        searchTimer.Stop();
        if(similarityCancellation is null)return;
        // Stop both the running request and any input already queued before
        // this click. Input changed after the click remains a new search.
        explicitlyCancelledSearch=similarityCancellation.Token;
        lastQuery=Query.Text;lastKind=Kind.SelectedIndex;lastMode=SearchMode.SelectedIndex;
        lastRoots=selectedSearchRoots?.ToArray();lastLiteralOnly=AIMatchedOnly.IsChecked==true;
        lastBoundary=BoundaryValue();lastResultGroup=AIResultGroup.SelectedIndex;
        similarityCancellation.Cancel();
    }
    private void CancelSearchShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){if(Busy.Visibility==Visibility.Visible||searchTimer.IsRunning){e.Handled=true;searchTimer.Stop();similarityCancellation?.Cancel();}else if(Details.IsPaneOpen&&!folderSettingsActive){e.Handled=true;Details.IsPaneOpen=false;}}
    private void SearchCategoryText_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||populating)return;
        if(SearchMode.SelectedIndex is not (0 or 4 or 5))
            SearchMode.SelectedIndex=lastTextSearchMode is 0 or 4 or 5?lastTextSearchMode:0;
    }
    private void SearchCategoryAI_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||populating)return;
        if(SearchMode.SelectedIndex is 0 or 4 or 5)
            SearchMode.SelectedIndex=lastAISearchMode is not (0 or 4 or 5)?lastAISearchMode:1;
    }
    private void UpdateSearchMethod()
    {
        // SelectionChanged also runs during initialization and dirty-state rollback.
        if(Query is null || Kind is null || SearchMethodHint is null || SimilarityBar is null || SimilarityTitle is null)return;
        var modeIndex=Math.Clamp(SearchMode.SelectedIndex,0,9);
        var method=SearchMethod.FromIndex(modeIndex);
        var isAIMode=modeIndex is not (0 or 4 or 5);
        if(isAIMode)lastAISearchMode=modeIndex;
        else lastTextSearchMode=modeIndex;
        var selected=ThemeStyle("SelectedSegmentButtonStyle");
        var unselected=ThemeStyle("UnselectedSegmentButtonStyle");
        if(SearchCategoryTextButton is not null)SearchCategoryTextButton.Style=isAIMode?unselected:selected;
        if(SearchCategoryAIButton is not null)SearchCategoryAIButton.Style=isAIMode?selected:unselected;
        if(SearchCategorySegment is not null)SearchCategorySegment.Style=ThemeStyle(isAIMode?"AISearchSegmentBorderStyle":"SearchSegmentBorderStyle");
        Query.Style=isAIMode?ThemeStyle("AIHeroQueryTextBoxStyle"):null;
        for(var i=0;i<SearchMode.Items.Count;i++)
            if(SearchMode.Items[i] is ComboBoxItem option)
                option.Visibility=(i is not (0 or 4 or 5))==isAIMode?Visibility.Visible:Visibility.Collapsed;
        SearchMode.IsEnabled=view!="history";
        var similar=similarityOrigin is not null;
        SimilarityBar.Visibility=similar?Visibility.Visible:Visibility.Collapsed;
        if(similar)
        {
            var simBasis=directVideoAudioSimilarity?AppText.L("動画内の音","video audio")
                :directVideoSimilarity?AppText.L("動画の映像","video visuals")
                :directAudioSimilarity?AppText.L("音声・音楽","audio/music")
                :similarityOriginMs is not null?AppText.L("動画のこの場面（複合）","this video moment (combined)")
                :similarityOrigin?.Kind=="video"?AppText.L("動画の代表場面（複合）","video key frame (combined)")
                :similarityOrigin?.Kind=="audio"?AppText.L("音の響き・音響特徴","acoustic features")
                :AppText.L("見た目（画像・本・動画の複合）","visual similarity (images/books/videos)");
            SimilarityTitle.Text=similarityOriginPage is int p
                ? AppText.L($"≈ 『{similarityOrigin!.Title}（{p+1}ページ目）』に似た作品（{simBasis}）",$"≈ Similar to \"{similarityOrigin!.Title} (page {p+1})\" ({simBasis})")
                : similarityOriginMs is int ms
                ? AppText.L($"≈ 『{similarityOrigin!.Title}（{VideoPlayerPolicy.FormatTime(TimeSpan.FromMilliseconds(ms))}）』に似た作品（{simBasis}）",$"≈ Similar to \"{similarityOrigin!.Title} ({VideoPlayerPolicy.FormatTime(TimeSpan.FromMilliseconds(ms))})\" ({simBasis})")
                : AppText.L($"≈ 『{similarityOrigin!.Title}』に似た作品（{simBasis}）",$"≈ Similar to \"{similarityOrigin!.Title}\" ({simBasis})");
        }
        else SimilarityTitle.Text="";
        UpdateSearchAIUnreadyBar();
        var ai=method.IsAI&&!method.IsDirectContent&&!similar;
        Kind.IsEnabled=!method.IsDirectContent&&!DirectContentSimilarity;
        SearchOptions.Visibility=ai?Visibility.Visible:Visibility.Collapsed;
        var candidates=method.IsTagCandidates&&!similar;
        var pageText=method.IsPageText&&!similar;
        AutomationProperties.SetName(Query,pageText?AppText.L("ページ内の文字を検索","Search text inside pages"):candidates?AppText.L("未承認タグの文字を検索","Search AI tag suggestions text"):method.IsAI?AppText.L("AI検索の文章","AI search description"):AppText.L("名前・タグ検索","Filename & tag search"));
        SimilarityBoundary.Visibility=!similar&&SearchMode.SelectedIndex is 2 or 3?Visibility.Visible:Visibility.Collapsed;
        AIResultGroup.Visibility=ai?Visibility.Visible:Visibility.Collapsed;
        AIMatchedOnly.Visibility=ai?Visibility.Visible:Visibility.Collapsed;
        Query.PlaceholderText=method.IsTagSemantic?AppText.L("例：青髪のツインテール（AIタグ候補の意味）","e.g. blue twin-tail hair (AI tag suggestion meaning)"):pageText?AppText.L("ページ内の文字を入力","Enter text inside pages"):candidates?AppText.L("AIタグ候補の文字を入力（空欄で全件）","Enter AI tag suggestion text (blank for all)"):method.IsAI?AppText.L("覚えている内容を文章で（例：夕焼けの海）","Describe what you remember (e.g. ocean at sunset)"):AppText.L("名前・タグで検索（Ctrl+F）","Search filenames & tags (Ctrl+F)");
        SearchMethodHint.Text=similar?(directVideoAudioSimilarity?AppText.L("保存済みの動画内音声から、音の特徴が似た動画を探しています。一致区間から再生できます。検索語の入力や「検索」で通常の検索に戻ります。","Finding videos with similar indexed audio. Play starts from the matching segment. Enter a query or click Search to return."):directVideoSimilarity?AppText.L("作成済みの動画データから内容が似た候補を探しています。動画内の音は対象外です。検索語の入力や「検索」で通常の検索に戻ります。","Finding videos with similar indexed visual scenes (audio not included). Enter a query or click Search to return."):directAudioSimilarity?AppText.L("作成済みの音声の内容・特徴から似た候補を探しています。検索語の入力や「検索」で通常の検索に戻ります。","Finding similar audio from indexed content. Enter a query or click Search to return."):similarityOriginMs is not null?AppText.L("指定した再生時刻の場面から、画像・本・動画の視覚的に似た候補を探しています。種類の絞り込みも適用できます。","Finding visually similar images, books, and videos from this video moment. Type filters apply."):similarityOrigin?.Kind=="video"?AppText.L("動画の代表場面から、画像・本・動画の似た候補を探しています。種類の絞り込みも適用できます。","Finding visually similar images, books, and videos from this video's key frame. Type filters apply."):similarityOrigin?.Kind=="audio"?AppText.L("音声・音楽の音響特徴から似た候補を探しています。検索語の入力や「検索」で通常の検索に戻ります。","Finding similar songs/audio by acoustic features. Enter a query or click Search to return."):AppText.L("画像・表紙の見た目から、画像・本・動画の似た候補を探しています。種類の絞り込みも適用できます。","Finding visually similar images, books, and videos from this image or cover. Type filters apply.")):SearchModeDescription(SearchMode.SelectedIndex);
        ToolTipService.SetToolTip(SearchMode,SearchMethodHint.Text);
        AutomationProperties.SetHelpText(SearchMode,SearchMethodHint.Text);
        UpdateClearSearchConditionsVisibility();
    }
    private async void EmptyOpenFolders_Click(object sender,RoutedEventArgs e)=>await OpenFolderHubAsync();
    private static string SearchModeDescription(int index)=>index switch
        {
            1=>AppText.L("名前・タグの意味と、画像・表紙の見た目を組み合わせます（AI）。","Combines filename/tag meaning with visual similarity of images and covers (AI)."),
            2=>AppText.L("AI検索データがある画像・表紙・本のページや、動画の代表場面を見た目から探します（AI）。","Searches indexed images, book covers/pages, and video key frames visually (AI)."),
            3=>AppText.L("名前やタグの意味・言い換えで探します。本の本文・音声の文字起こしは対象外です（AI）。","Searches by meaning and paraphrases of filenames and tags. Book body text and audio transcripts are not included (AI)."),
            4=>AppText.L("未承認のAIタグ候補（最新履歴）だけを文字で検索します。確定タグとは混ざりません。","Text search over pending AI tag suggestions (latest run only), kept separate from confirmed tags."),
            5=>AppText.L("抽出済みのページ本文が検索対象です（同じページ内で検索語がすべて含まれる本を探します）。","Searches extracted page text (finds books where all search terms appear on the same page)."),
            6=>AppText.L("英語を含む未承認タグ候補を、日本語の意味で探します。先にAI検索データを作成してください（AI）。","Searches pending AI tag suggestions (including English tags) by semantic meaning. Build the AI index first (AI)."),
            9=>AppText.L("動画内の音や会話の特徴を文章で探します。「設定 → AI検索を設定 → 動画内の音」でAI検索データを作成してください（先頭トラック対象・文字起こしなし）。","Searches sounds or speech characteristics inside videos. Build the index under Settings -> Configure AI Search -> Video audio (first audio track, no transcripts)."),
            8=>AppText.L("動画の場面や動きを文章で探します。「設定 → AI検索を設定 → 動画の映像」でAI検索データを作成してください（音は対象外）。","Searches video scenes and motion by description. Build the index under Settings -> Configure AI Search -> Video visuals (no audio)."),
            7=>AppText.L("音声や音楽の内容・特徴を文章で探します。「設定 → AI検索を設定 → 音声・音楽」でAI検索データを作成してください（文字起こしなし）。","Searches audio and music content by description. Build the index under Settings -> Configure AI Search -> Audio & music (no transcripts)."),
            _=>AppText.L("名前・タグに含まれる文字で探します。","Searches text in filenames and confirmed tags.")
        };
    private void SearchMode_Changed(object sender,SelectionChangedEventArgs e)
    {
        if((SearchMode.SelectedIndex is 7 or 8 or 9)&&ready&&!populating)
        {
            populating=true;Kind.SelectedIndex=(SearchMode.SelectedIndex is 8 or 9)?3:4;populating=false;
        }
        UpdateSearchMethod();
        similarityCancellation?.Cancel();
        searchTimer?.Stop();
    }
    private void AIMatchedOnly_Changed(object sender,RoutedEventArgs e){UpdateClearSearchConditionsVisibility();similarityCancellation?.Cancel();searchTimer?.Stop();if(ready&&!populating&&PendingAutoSearch)searchTimer!.Start();}
    private void Kind_Changed(object sender,SelectionChangedEventArgs e){UpdateClearSearchConditionsVisibility();similarityCancellation?.Cancel();searchTimer?.Stop();if(ready&&!populating&&PendingAutoSearch)searchTimer!.Start();}
    private void CloseBrowseMenus(){ItemSizeFlyout.Hide();BrowseActionsFlyout.Hide();}
    private void BrowseActions_Click(object sender,RoutedEventArgs e)=>ItemSizeFlyout.Hide();
    private async void Previous_Click(object sender,RoutedEventArgs e){CloseBrowseMenus();await NavigateAsync(PreviousBrowsePage());}
    private async void Next_Click(object sender,RoutedEventArgs e){CloseBrowseMenus();await NavigateAsync(NextBrowsePage());}
    private void RestoreNavigation()
    {
        populating=true;
        Nav.SelectedItem=settingsHubOpen
            ? (currentSettingsCategory=="ai"?NavAIStatus:SettingsNavItem)
            : folderHubOpen
            ? FolderNavigation
            : shelfHubOpen||selectedShelfIds is not null
            ? Nav.MenuItems.OfType<NavigationViewItem>().First(x=>x.Tag?.ToString()=="shelf")
            : Nav.MenuItems.OfType<NavigationViewItem>().FirstOrDefault(x=>x.Tag?.ToString()==view) ?? Nav.MenuItems.OfType<NavigationViewItem>().First();
        UnreviewedOnly.IsChecked=view=="unreviewed";
        UnreviewedOnly.IsEnabled=view is "all" or "unreviewed";
        populating=false;
        UpdateClearSearchConditionsVisibility();
    }
    private async void Nav_SelectionChanged(NavigationView sender,NavigationViewSelectionChangedEventArgs args)
    {
        if(!ready||populating||args.SelectedItem is not NavigationViewItem item)return;
        CloseBrowseMenus();
        var next=item.Tag?.ToString()??"";
        if(next=="settings"){await OpenSettingsAsync("all");return;}
        if(next=="ai"){await OpenSettingsAsync("ai");return;}
        if(next=="folders"){await OpenFolderHubAsync();return;}
        if(next=="shelf"){await OpenShelfHubAsync();return;}
        if(next is not ("all" or "favorites" or "unreviewed" or "shelf" or "history"))return;
        if(saving||dialogOpen||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            var sameLibraryReturn=(settingsHubOpen||folderHubOpen||shelfHubOpen)&&next==view&&selectedShelfIds is null&&similarityOrigin is null;
            CloseSettingsHubCore();CloseShelfHubCore();
            CloseFolderHubCore();
            if(sameLibraryReturn)
            {
                RestoreNavigation();UpdateSearchMethod();
                if(CanRestoreLoadedResultSession(page,out var pageInLoadedWindow)&&pageInLoadedWindow)
                {
                    RestoreLoadedLibraryView();
                    RecordNavigationLocation();
                    return;
                }
            }
            SetShelfScope(null);
            populating=true;
            if(next=="history"){historyReturnMode=SearchMode.SelectedIndex;SearchMode.SelectedIndex=0;}
            else if(view=="history")SearchMode.SelectedIndex=historyReturnMode;
            populating=false;
            ClearSimilarity();view=next;page=0;RestoreNavigation();UpdateSearchMethod();await LoadAsync();
        }
        finally { transitions.Release();if((PendingAutoSearch)&&!disposed){searchTimer.Stop();searchTimer.Start();} }
    }
    private void UpdateLayoutToggleVisuals()
    {
        var selected=ThemeStyle("SelectedSegmentButtonStyle");
        var unselected=ThemeStyle("UnselectedSegmentButtonStyle");
        if(LayoutButton is not null)LayoutButton.Style=tiles?unselected:selected;
        if(LayoutGridButton is not null)LayoutGridButton.Style=tiles?selected:unselected;
        if(ShelfLayoutButton is not null)ShelfLayoutButton.Style=tiles?unselected:selected;
        if(ShelfLayoutGridButton is not null)ShelfLayoutGridButton.Style=tiles?selected:unselected;
        if(FolderLayoutButton is not null)FolderLayoutButton.Style=folderTiles?unselected:selected;
        if(FolderLayoutGridButton is not null)FolderLayoutGridButton.Style=folderTiles?selected:unselected;
    }
    private void SetLibraryTiles(bool nextTiles)
    {
        if(tiles==nextTiles||extending||saving||dialogOpen)return;
        try{ViewerOptions.SaveLibraryView(nextTiles);}
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException)
        {Notice(AppText.L("表示方法を保存できません","Could not save view layout"),AppText.TranslateBackend(ex.Message),InfoBarSeverity.Warning);AppLog.Error(ex);return;}
        CloseBrowseMenus();tiles=nextTiles;UpdateLayoutToggleVisuals();
        if(shelfHubOpen)RenderShelfLayout();else ReflowBrowse(()=>{RenderRows();RestoreSelection();});
    }
    private void LayoutList_Click(object sender,RoutedEventArgs e)=>SetLibraryTiles(false);
    private void LayoutGrid_Click(object sender,RoutedEventArgs e)=>SetLibraryTiles(true);
    private void Layout_Click(object sender,RoutedEventArgs e)=>SetLibraryTiles(!tiles);
    private void OpenDetails_Click(object sender,RoutedEventArgs e)
    {
        if(folderHubOpen)
        {
            if(folderSettingsActive)Details.IsPaneOpen=true;
            return;
        }
        if(librarySelection.Count>1||librarySelection.Count==1&&active is null){ShowSelectionSummary();Details.IsPaneOpen=true;}
        else if(active is not null){ShowItemDetailsPane();Details.IsPaneOpen=true;_ = ShowDetailPreviewAsync(active);}
    }
    private async Task OpenRowDetailsAsync(MediaRow row)
    {
        if(disposed||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try
        {
            if(active?.Id!=row.Id)
            {
                if(!await ConfirmDiscardAsync())return;
                if(SelectionPosition(row.Id) is {} position)librarySelection.Single(position);
                ShowItemDetailsPane();ApplySelectedRow(row);RestoreSelection();
            }
            ShowItemDetailsPane();Details.IsPaneOpen=true;
            await ShowDetailPreviewAsync(row);
        }
        finally{transitions.Release();}
    }
    private async Task OpenRowPreviewQuickAsync(MediaRow row)
    {
        if(disposed||saving||dialogOpen)return;
        if(active?.Id==row.Id&&librarySelection.Count==1)
        {
            await OpenPreviewAsync(row.Id);
            return;
        }
        if(!await transitions.WaitAsync(0))return;
        var transitioned=false;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            if(SelectionPosition(row.Id) is {} position)librarySelection.Single(position);
            ShowItemDetailsPane();
            ApplySelectedRow(row);
            RestoreSelection();
            transitioned=active?.Id==row.Id;
        }
        finally{transitions.Release();}
        if(transitioned&&!disposed)await OpenPreviewAsync(row.Id);
    }
    private async void PreviewPointerPressed(object sender,PointerRoutedEventArgs e)
    {
        if(e.Handled||disposed||dialogOpen||saving||SelectionKey(Windows.System.VirtualKey.Control)||SelectionKey(Windows.System.VirtualKey.Shift)){previewClicks.Reset();return;}
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
    private async void Items_PreviewKeyDown(object sender,KeyRoutedEventArgs e)
    {
        if(!e.Handled&&e.Key is Windows.System.VirtualKey.Up or Windows.System.VirtualKey.Down
            or Windows.System.VirtualKey.PageUp or Windows.System.VirtualKey.PageDown
            or Windows.System.VirtualKey.Home or Windows.System.VirtualKey.End)
            smoothWheelScroller.Stop();
        if(e.Handled||e.OriginalSource is not ListViewItem { IsSelected:true, Tag:int itemId }
            ||!ready||disposed||saving||dialogOpen||librarySelection.Count!=1||active?.Id!=itemId)return;
        if(IsUnmodifiedEnter(e))
        {
            e.Handled=true;
            if(!e.KeyStatus.WasKeyDown)await OpenPreviewAsync(itemId);
            return;
        }
        if(e.Key==Windows.System.VirtualKey.Space
            &&!SelectionKey(Windows.System.VirtualKey.Control)
            &&!SelectionKey(Windows.System.VirtualKey.Shift)
            &&!SelectionKey(Windows.System.VirtualKey.Menu)
            &&!SelectionKey(Windows.System.VirtualKey.LeftWindows)
            &&!SelectionKey(Windows.System.VirtualKey.RightWindows))
        {
            e.Handled=true;
            if(e.KeyStatus.WasKeyDown)return;
            if(Details.IsPaneOpen)
            {
                if(!await ConfirmDiscardAsync())return;
                Details.IsPaneOpen=false;
            }
            else if(active is {} current)
            {
                ShowItemDetailsPane();
                Details.IsPaneOpen=true;
                await ShowDetailPreviewAsync(current);
            }
        }
    }
    private async Task OpenPreviewAsync(int itemId)
    {
        if(librarySelection.Count!=1||SelectionKey(Windows.System.VirtualKey.Control)||SelectionKey(Windows.System.VirtualKey.Shift))return;
        // The first click uses the normal selection/discard guard. Never open
        // a different or stale result if selection is pending or was cancelled.
        if(disposed||saving||dialogOpen||active?.Id!=itemId)return;
        if(ViewerOptions.Value.OpenExternally&&!await OpenPreferredExternalAsync(active))return;
        if(disposed||saving||dialogOpen||active?.Id!=itemId)return;
        if(ImageViewerPolicy.CanOpen(active))await OpenImageAsync();
        else if(ArchiveManifest.CanOpen(active))await OpenBookAsync();
        else if(VideoPlayerPolicy.CanOpen(active))await OpenVideoAsync(autoPlay:true);
        else if(AudioPlayerPolicy.CanOpen(active))await OpenAudioAsync(autoPlay:true);
    }
    private async void OpenImage_Click(object sender,RoutedEventArgs e)=>await OpenImageAsync();
    private static ResultSession? ViewerFavoriteSession(ResultSession? session)
        => session is { FavoritePatchSupported: true } ? session : null;
    private Task OpenImageAsync()=>active is {} row&&ImageViewerPolicy.CanOpen(row)?OpenVisualSessionAsync(row):Task.CompletedTask;
    private Task OpenBookAsync()=>active is {} row&&ArchiveManifest.CanOpen(row)?OpenVisualSessionAsync(row):Task.CompletedTask;
    private async Task OpenVisualSessionAsync(MediaRow initialRow)
    {
        if((!ImageViewerPolicy.CanOpen(initialRow)&&!ArchiveManifest.CanOpen(initialRow))||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        // Opening a visual viewer neither saves nor discards the current metadata draft.
        dialogOpen=true;searchTimer.Stop();
        var itemId=initialRow.Id;
        var initialIsImage=ImageViewerPolicy.CanOpen(initialRow);
        var detailsWereOpen=Details.IsPaneOpen;
        var session=resultSession;
        int? lastOpened=null;var lastOrdinal=0;var viewerResultsChanged=false;
        var editDetails=false;
        (MediaRow Row,int? OriginPage)? pendingSimilarity=null;
        try
        {
            var hasItem=ordinalById.TryGetValue(itemId,out var ordinal);
            if(!hasItem)
            {
                var fallbackIndex=rows.FindIndex(row=>row.Id==itemId);
                hasItem=fallbackIndex>=0;
                ordinal=hasItem?checked(browseStart+fallbackIndex):0;
            }
            if(initialIsImage)
            {
                if(session is null)throw new InvalidOperationException(AppText.L("同じ条件で検索し直してから画像を開いてください。","Run the same search again before opening images."));
                if(resultsNeedRefresh||!hasItem)throw new InvalidOperationException(AppText.L("検索結果が変わりました。一覧から作品を選び直してください。","Search results changed. Please choose the item again from the list."));
            }
            var canCrossNavigate=session is not null&&!resultsNeedRefresh&&hasItem;
            var favorites=canCrossNavigate?ViewerFavoriteSession(session):null;
            lastOpened=initialRow.Id;lastOrdinal=ordinal;
            var currentRowsById=new Dictionary<int,MediaRow>();
            foreach(var row in rowById.Values)currentRowsById[row.Id]=row;
            currentRowsById[initialRow.Id]=initialRow;
            Func<int,int,CancellationToken,Task<ResultNeighbor?>>? visualNeighborFn=canCrossNavigate&&session is not null
                ? async(id,dir,ct)=>
                {
                    var neighbor=await session.NeighborAsync(id,dir,ct,includeBooks:true);
                    if(neighbor is not null)currentRowsById[neighbor.Item.Id]=neighbor.Item;
                    return neighbor;
                }
                : null;
            ViewerWindow? window=null;
            var swapping=false;
            var currentRow=initialRow;
            var currentOrdinal=ordinal;
            Func<int,CancellationToken,Task<ResultNeighbor?>>? visualAtOrdinalFn=canCrossNavigate&&session is not null
                ? async(targetOrdinal,ct)=>
                {
                    var pageData=await session.RangeAsync(targetOrdinal,1,ct);
                    if(pageData.Items.Count!=1)return null;
                    var item=pageData.Items[0];
                    currentRowsById[item.Id]=item;
                    if(ImageViewerPolicy.CanOpen(item)||ArchiveManifest.CanOpen(item))
                        return new ResultNeighbor(targetOrdinal,item);
                    var dir=targetOrdinal>=currentOrdinal?1:-1;
                    var neighbor=await session.NeighborAsync(item.Id,dir,ct,includeBooks:true);
                    if(neighbor is not null)currentRowsById[neighbor.Item.Id]=neighbor.Item;
                    return neighbor;
                }
                : null;

            void TrackFavorite(int id,bool value,bool kept)
            {
                var targetRow=rowById.GetValueOrDefault(id)??(currentRowsById.TryGetValue(id,out var cached)?cached:active?.Id==id?active:null);
                if(targetRow is not null)ApplyFavoriteValue(targetRow,value);
                if(currentRowsById.TryGetValue(id,out var tracked))ApplyFavoriteValue(tracked,value);
                viewerResultsChanged|=!kept;
            }
            ImageViewerView CreateImageView(MediaRow row,int pos,int total)
            {
                var seq=new ImageViewerSequence(row,pos,total,session!.NeighborAsync);
                var viewer=new ImageViewerView(api,seq,favorites,visualNeighborFn,visualAtOrdinalFn);
                imageViewer=viewer;
                viewer.FavoriteChanged+=TrackFavorite;
                viewer.CurrentItemChanged+=(id,pos)=>{
                    lastOpened=id;lastOrdinal=pos;currentOrdinal=pos;
                    if(currentRowsById.TryGetValue(id,out var hit))currentRow=hit;
                };
                viewer.ContentOpened+=id=>{
                    lastOpened=id;lastOrdinal=seq.Position;currentOrdinal=seq.Position;
                    if(currentRowsById.TryGetValue(id,out var hit))currentRow=hit;
                    RecordContentOpened(id);
                };
                viewer.EditDetailsRequested+=()=>{editDetails=true;window?.Close();};
                viewer.ToggleMaximizeRequested+=()=>window?.ToggleMaximize();
                viewer.FindSimilarRequested+=originId=>{
                    var targetRow=currentRowsById.GetValueOrDefault(originId)??currentRow;
                    pendingSimilarity=(targetRow,null);
                    window?.Close();
                };
                viewer.NavigateToItemRequested+=async(neighbor,_)=>await SwapToNeighborAsync(neighbor,direction:1);
                viewer.CloseRequested+=(_,_)=>window?.Close();
                viewer.AttachNavigation(viewer);
                return viewer;
            }
            ArchiveReaderView CreateBookView(MediaRow row,int pos,bool openAtEnd)
            {
                var reader=new ArchiveReaderView(api,row.Id,row.Title,row.PageText,row.AIPage,favorites,pos,
                    openAtEnd:openAtEnd,
                    canNavigatePrevious:visualNeighborFn is not null&&pos>0,
                    canNavigateNext:visualNeighborFn is not null&&session is not null&&pos+1<session.Total);
                readerView=reader;
                reader.FavoriteChanged+=TrackFavorite;
                reader.ContentOpened+=id=>{
                    lastOpened=id;lastOrdinal=pos;currentOrdinal=pos;
                    if(currentRowsById.TryGetValue(id,out var hit))currentRow=hit;
                    RecordContentOpened(id);
                };
                reader.EditDetailsRequested+=()=>{editDetails=true;window?.Close();};
                reader.ToggleMaximizeRequested+=()=>window?.ToggleMaximize();
                reader.FindSimilarPageRequested+=(originId,pageIndex)=>{
                    var targetRow=currentRowsById.GetValueOrDefault(originId)??row;
                    pendingSimilarity=(targetRow,pageIndex);
                    window?.Close();
                };
                reader.NavigateOutRequested+=async direction=>{
                    if(swapping||visualNeighborFn is null||window is null||disposed)return;
                    try
                    {
                        var neighbor=await visualNeighborFn(row.Id,direction,CancellationToken.None);
                        if(disposed)return;
                        if(neighbor is null)
                        {
                            reader.ShowBoundaryNotice(direction<0?AppText.L("前の画像・本はありません","No previous image or book"):AppText.L("次の画像・本はありません","No next image or book"));
                            return;
                        }
                        await SwapToNeighborAsync(neighbor,direction);
                    }
                    catch(Exception ex) when(!disposed)
                    {
                        AppLog.Error(ex);
                        reader.ShowBoundaryNotice(ex is ResultSessionException
                            ?AppText.L("結果の有効期限が切れました。閉じて再検索してください","Search results expired. Close and search again.")
                            :AppText.L("次の作品を取得できません。接続を確認して再試行してください","Could not load the next item. Check connection and try again."));
                    }
                };
                reader.CloseRequested+=(_,_)=>window?.Close();
                reader.AttachNavigation(reader);
                return reader;
            }
            async Task SwapToNeighborAsync(ResultNeighbor neighbor,int direction)
            {
                if(swapping||window is null||disposed)return;
                swapping=true;
                try
                {
                    currentRowsById[neighbor.Item.Id]=neighbor.Item;
                    if(readerView is {} oldReader){await oldReader.FlushProgressAsync();readerView=null;oldReader.Dispose();}
                    if(imageViewer is {} oldImage){await oldImage.FlushFavoriteAsync();imageViewer=null;oldImage.Dispose();}
                    if(disposed)return;
                    currentRow=neighbor.Item;currentOrdinal=neighbor.Ordinal;
                    lastOpened=neighbor.Item.Id;lastOrdinal=neighbor.Ordinal;
                    if(ImageViewerPolicy.CanOpen(neighbor.Item))
                    {
                        var nextViewer=CreateImageView(neighbor.Item,neighbor.Ordinal,session!.Total);
                        window.BeforeCloseAsync=nextViewer.FlushFavoriteAsync;
                        window.SwapContent(nextViewer,AppText.L("画像ビューア","Image Viewer"),"ImageViewerDialog");
                        nextViewer.FocusViewport();
                        _=nextViewer.OpenAsync();
                    }
                    else if(ArchiveManifest.CanOpen(neighbor.Item))
                    {
                        var nextReader=CreateBookView(neighbor.Item,neighbor.Ordinal,openAtEnd:direction<0);
                        window.BeforeCloseAsync=nextReader.FlushProgressAsync;
                        window.SwapContent(nextReader,AppText.L("読書画面","Reader"),"ArchiveReaderDialog");
                        nextReader.FocusViewport();
                        _=nextReader.OpenAsync();
                    }
                }
                finally{swapping=false;}
            }

            if(initialIsImage)
            {
                var viewer=CreateImageView(initialRow,ordinal,session!.Total);
                window=new ViewerWindow(viewer,AppText.L("画像ビューア","Image Viewer"),"ImageViewerDialog");
                viewerWindow=window;
                window.BeforeCloseAsync=viewer.FlushFavoriteAsync;
                window.Closed+=(_,_)=>{imageViewer?.Dispose();imageViewer=null;readerView?.Dispose();readerView=null;};
                await window.ShowAsync(viewer.OpenAsync);
            }
            else
            {
                var reader=CreateBookView(initialRow,ordinal,openAtEnd:false);
                window=new ViewerWindow(reader,AppText.L("読書画面","Reader"),"ArchiveReaderDialog");
                viewerWindow=window;
                window.BeforeCloseAsync=reader.FlushProgressAsync;
                window.Closed+=(_,_)=>{imageViewer?.Dispose();imageViewer=null;readerView?.Dispose();readerView=null;};
                await window.ShowAsync(reader.OpenAsync);
            }
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            imageViewer?.Dispose();imageViewer=null;readerView?.Dispose();readerView=null;viewerWindow=null;dialogOpen=false;
            try
            {
                if(!disposed&&viewerResultsChanged)
                {
                    await RefreshResultRowsAfterEditAsync(favoriteOnly:true);session=resultSession;
                    if(lastOpened is int changed&&session is not null)
                    {
                        var position=(await session.LocateAsync([changed],CancellationToken.None)).FirstOrDefault();
                        if(position is not null)lastOrdinal=position.Ordinal;else lastOpened=null;
                    }
                }
                if(!disposed&&lastOpened is int target&&session is not null&&(initialIsImage||target!=itemId))
                    await RestoreViewerSelectionAsync(target,lastOrdinal,session,detailsWereOpen);
                if(!disposed&&pendingSimilarity is null&&editDetails&&(initialIsImage
                    ?(session is not null&&ReferenceEquals(resultSession,session)&&!PendingSearch&&active is {} currentImg&&currentImg.Id==lastOpened)
                    :(active is {} currentBook&&currentBook.Id==itemId)))
                    await OpenDetailsAfterViewerAsync(active!);
                else if(!disposed&&pendingSimilarity is null&&detailsWereOpen&&active?.Id==itemId)
                {
                    Details.IsPaneOpen=true;(initialIsImage?OpenImage:OpenBook).Focus(FocusState.Programmatic);
                }
            }
            catch(Exception ex){if(!disposed)Failure(ex);}
            finally{transitions.Release();}
            if(!disposed&&pendingSimilarity is {} req)
                await StartSimilarityAsync(req.Row,originPage:req.OriginPage);
            else if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void OpenBook_Click(object sender,RoutedEventArgs e)=>await OpenBookAsync();
    private async void OpenVideo_Click(object sender,RoutedEventArgs e)=>await OpenVideoAsync();
    private Task OpenVideoAsync(bool autoPlay=false)=>OpenPlayerAsync(isAudio:false,autoPlay:autoPlay);
    private async void OpenAudio_Click(object sender,RoutedEventArgs e)=>await OpenAudioAsync();
    private Task OpenAudioAsync(bool autoPlay=false)=>OpenPlayerAsync(isAudio:true,autoPlay:autoPlay);

    private async Task OpenPlayerAsync(bool isAudio,bool autoPlay=false)
    {
        if(active is not {} playerRow || !(isAudio ? AudioPlayerPolicy.CanOpen(playerRow) : VideoPlayerPolicy.CanOpen(playerRow))
            || saving || dialogOpen || !await transitions.WaitAsync(0))return;

        dialogOpen=true;
        searchTimer.Stop();
        var itemId=playerRow.Id;
        var detailsWereOpen=Details.IsPaneOpen;
        var viewerResultsChanged=false;
        var editDetails=false;
        (MediaRow Row,int OriginMs)? pendingFrameSimilarity=null;
        try
        {
            var hasItem=ordinalById.TryGetValue(itemId,out var ordinal);
            if(!hasItem)
            {
                var fallbackIndex=rows.FindIndex(row=>row.Id==itemId);
                hasItem=fallbackIndex>=0;
                ordinal=hasItem?checked(browseStart+fallbackIndex):0;
            }
            var favorites=!resultsNeedRefresh&&hasItem?ViewerFavoriteSession(resultSession):null;
            var start=isAudio ? playerRow.AudioMatchMs??playerRow.VideoMatchMs : VideoPlayerPolicy.MatchStartMs(playerRow);
            var player=new VideoPlayerView(api,itemId,playerRow.Title,start,isAudio,favorites,Math.Max(0,ordinal),autoPlay:autoPlay);
            videoPlayer=player;
            var window=new ViewerWindow(player,isAudio?AppText.L("音声再生","Audio Player"):AppText.L("動画再生","Video Player"),isAudio?"AudioPlayerDialog":"VideoPlayerDialog");
            viewerWindow=window;
            window.BeforeCloseAsync=player.FlushFavoriteAsync;
            player.FavoriteChanged+=(id,value,kept)=>
            {
                if(id==itemId)ApplyFavoriteValue(playerRow,value);
                viewerResultsChanged|=!kept;
            };
            player.ContentOpened+=RecordContentOpened;
            player.EditDetailsRequested+=()=>{editDetails=true;window.Close();};
            player.OpenExternalRequested+=()=>{window.Close();OpenInShell(playerRow,false);};
            player.ToggleMaximizeRequested+=()=>window.ToggleMaximize();
            player.FindSimilarFrameRequested+=(_,ms)=>{pendingFrameSimilarity=(playerRow,ms);window.Close();};
            player.CloseRequested+=(_,_)=>window.Close();
            player.AttachNavigation(player);
            window.Closed+=(_,_)=>player.Dispose();
            await window.ShowAsync(player.OpenAsync);
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            videoPlayer?.Dispose();videoPlayer=null;viewerWindow=null;dialogOpen=false;
            try
            {
                if(!disposed&&viewerResultsChanged)await RefreshResultRowsAfterEditAsync(favoriteOnly:true);
                if(!disposed&&pendingFrameSimilarity is null&&active is {} current&&current.Id==itemId)
                {
                    if(editDetails)
                        await OpenDetailsAfterViewerAsync(current);
                    else if(detailsWereOpen)
                    {
                        Details.IsPaneOpen=true;
                        (isAudio?OpenAudio:OpenVideo).Focus(FocusState.Programmatic);
                    }
                }
            }
            catch(Exception ex){if(!disposed)Failure(ex);}
            finally{transitions.Release();}
            if(!disposed&&pendingFrameSimilarity is {} req)
                await StartSimilarityAsync(req.Row,originMs:req.OriginMs);
            else if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async Task OpenDetailsAfterViewerAsync(MediaRow row)
    {
        ShowItemDetailsPane();
        Details.IsPaneOpen=true;
        await ShowDetailPreviewAsync(row,preserveExisting:true);
        if(!disposed&&active?.Id==row.Id)Tags.Focus(FocusState.Programmatic);
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
        if(active is not null)await OpenTagSuggestionsAsync(active);
    }
    private async Task OpenTagSuggestionsAsync(MediaRow targetRow)
    {
        if(!TagReviewProtocol.CanOpen(targetRow)||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        var id=targetRow.Id;var isDirty=active?.Id==id&&Dirty;var detailsWereOpen=Details.IsPaneOpen;dialogOpen=true;searchTimer.Stop();
        var openTaggerDownload=false;
        var root=XamlRoot;Windows.Foundation.TypedEventHandler<XamlRoot,XamlRootChangedEventArgs> rootChanged=(_,_)=>tagReview?.Fit(root.Size.Width,root.Size.Height);
        root.Changed+=rootChanged;
        try
        {
            if(tagReviewSyncItem==id)await SyncTagReviewAsync(id);
            tagReview=new TagSuggestionsView(api.TagReviews,id,isDirty){RequestedTheme=ActualTheme};tagReview.Fit(root.Size.Width,root.Size.Height);
            tagReview.OpenSetupRequested+=()=>openTaggerDownload=true;
            var dialog=new ContentDialog{RequestedTheme=ActualTheme,XamlRoot=XamlRoot,Title=AppText.L("AIタグ候補","AI Tag Suggestions"),Content=tagReview,CloseButtonText=AppText.L("閉じる","Close"),DefaultButton=ContentDialogButton.None,FullSizeDesired=true};
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
            finally{dialogOpen=false;transitions.Release();if(!disposed){if(detailsWereOpen&&!openTaggerDownload&&active?.Id==id)Details.IsPaneOpen=true;UpdateDirty();if(PendingAutoSearch&&!openTaggerDownload)searchTimer.Start();}}
        }
        if(openTaggerDownload&&!disposed)await OpenAIDownloadDialogAsync(preferRole:"tagger");
    }
    private async Task SyncTagReviewAsync(int id)
    {
        var fresh=await api.TagReviews.ItemAsync(id,CancellationToken.None);
        if(disposed)return;
        if(active?.Id==id)
        {
            active.Tags=fresh.Tags;active.Shelf=fresh.Shelf;active.ShelfIds=fresh.ShelfIds.ToArray();active.Favorite=fresh.Favorite;active.Reviewed=fresh.Reviewed;
            editingShelfIds=fresh.ShelfIds.ToArray();draftTags=fresh.Tags.ToArray();Tags.Text="";UpdateShelfEditorLabel();SyncFavoriteToggle(fresh.Favorite);Reviewed.IsChecked=fresh.Reviewed;
            saved=Current();
            if(initialSavedItemId==id)initialSaved=saved;
        }
        else if(rowById.TryGetValue(id,out var listed))
        {
            listed.Tags=fresh.Tags;listed.Shelf=fresh.Shelf;listed.ShelfIds=fresh.ShelfIds.ToArray();listed.Favorite=fresh.Favorite;listed.Reviewed=fresh.Reviewed;
        }
        if(rows.FirstOrDefault(row=>row.Id==id) is {} bufferListed&&!ReferenceEquals(bufferListed,active)&&(!rowById.TryGetValue(id,out var cachedListed)||!ReferenceEquals(bufferListed,cachedListed)))
        {
            bufferListed.Tags=fresh.Tags;bufferListed.Shelf=fresh.Shelf;bufferListed.ShelfIds=fresh.ShelfIds.ToArray();bufferListed.Favorite=fresh.Favorite;bufferListed.Reviewed=fresh.Reviewed;
        }
        tagReviewSyncItem=null;await RefreshResultRowsAfterEditAsync();
    }
    private void UpdateNavigationLayout(double width)
    {
        if(width<=0)return;
        var expanded=width>=(Details.IsPaneOpen?1080:1000);
        var displayMode=width>=720?NavigationViewPaneDisplayMode.Left:NavigationViewPaneDisplayMode.LeftCompact;
        if(Nav.PaneDisplayMode!=displayMode)Nav.PaneDisplayMode=displayMode;
        if(lastAutoNavExpanded!=expanded)
        {
            lastAutoNavExpanded=expanded;
            Nav.IsPaneOpen=expanded;
        }
        Details.DisplayMode=width<720?SplitViewDisplayMode.Overlay:SplitViewDisplayMode.Inline;
        Details.OpenPaneLength=width>=1080?340:width>=880?300:Math.Clamp(width-580,260,300);
    }
    private void Page_SizeChanged(object sender,SizeChangedEventArgs e)
    {
        tagReview?.Fit(e.NewSize.Width,e.NewSize.Height);
        if(Details is null || ViewTools is null)return;
        UpdateNavigationLayout(e.NewSize.Width);
        if(active is null&&librarySelection.Count==0&&!folderSettingsActive)Details.IsPaneOpen=false;
        UpdateDetailLayout();
    }
    private void LibraryLayout_SizeChanged(object sender,SizeChangedEventArgs e)
    {
        UpdateSearchToolbarLayout();
        UpdateFolderLayout();
        UpdateDetailLayout();
    }
    private void SearchToolbarPart_SizeChanged(object sender,SizeChangedEventArgs e)=>UpdateSearchToolbarLayout();
    private void UpdateSearchToolbarLayout()
    {
        if(ViewTools is null||SearchFilterTools is null||SearchCategorySegment is null||LibraryLayout is null||SearchTools is null)return;
        // Inline details and long search labels change the usable width.
        // Keep the hero command bar grouped and wrap only the filter cluster.
        var queryWidth=SearchCategorySegment.DesiredSize.Width+220+SearchButton.DesiredSize.Width+(CancelSearchButton.Visibility==Visibility.Visible?CancelSearchButton.DesiredSize.Width+8:0)+32;
        var filterWrap=LibraryLayout.ActualWidth<queryWidth+SearchFilterTools.DesiredSize.Width;
        Grid.SetRow(SearchFilterTools,filterWrap?1:0);Grid.SetColumn(SearchFilterTools,filterWrap?0:4);Grid.SetColumnSpan(SearchFilterTools,filterWrap?5:1);
        SearchFilterTools.Margin=filterWrap?new Thickness(0,8,0,0):new Thickness(0);
        // The star column clips HeadingTools.DesiredSize; its horizontal
        // children still expose the natural width needed for the full title.
        var headingWidth=NavigationBackButton.DesiredSize.Width+NavigationForwardButton.DesiredSize.Width+MainViewTitle.DesiredSize.Width+2*HeadingTools.Spacing;
        var headerWrap=LibraryLayout.ActualWidth<headingWidth+HeaderCommands.DesiredSize.Width+LibraryHeader.ColumnSpacing;
        Grid.SetRow(HeaderCommands,headerWrap?1:0);Grid.SetColumn(HeaderCommands,headerWrap?0:1);Grid.SetColumnSpan(HeaderCommands,headerWrap?2:1);
        HeaderCommands.Margin=headerWrap?new Thickness(0,8,0,0):new Thickness(0);
    }

    private double ComputeFolderTileWidth()
    {
        var avail = FolderList is { ActualWidth: > 0 } ? FolderList.ActualWidth
            : FolderHubView is { ActualWidth: > 0 } ? Math.Min(880, FolderHubView.ActualWidth) : 880;
        return Math.Clamp(Math.Floor((avail - 28) / 2.0), 340, 424);
    }

    private void FolderHub_SizeChanged(object sender,SizeChangedEventArgs args)=>UpdateFolderLayout();
    private void UpdateFolderLayout()
    {
        if(FolderSelectionButtons is null||FolderAddScroll is null)return;
        var narrow=LibraryLayout.ActualWidth<840;
        for(var i=0;i<4;i++)FolderSelectionButtons.ColumnDefinitions[i].Width=i<2||!narrow?GridLength.Auto:new GridLength(0);
        var buttons=new[]{SearchSelectedFoldersButton,EditSelectedFoldersButton,UnregisterSelectedFoldersButton,SearchAllFoldersButton};
        for(var i=0;i<buttons.Length;i++){Grid.SetColumn(buttons[i],narrow?i%2:i);Grid.SetRow(buttons[i],narrow?i/2:0);}
        FolderAddScroll.MaxHeight=Math.Max(96,FolderHubView.ActualHeight-FolderHeader.ActualHeight-(FolderAIStatusBar?.ActualHeight??0)-FolderSelectionPanel.ActualHeight-124);
        if(folderTiles&&FolderList is not null)
        {
            var tileW=ComputeFolderTileWidth();
            foreach(var item in FolderList.Items.OfType<ListViewItem>())item.Width=tileW;
        }
    }

    private void Details_PaneStateChanged(object sender,object args)
    {
        UpdateNavigationLayout(ActualWidth);
        UpdateDetailLayout();
        ApplyPendingDetailScrollReset();
    }

    private void UpdateDetailLayout()
    {
        if(Details is null||LibraryLayout is null)return;
        var compact=ActualWidth<1100||ActualHeight<820;
        if(DetailPreview is not null)DetailPreview.Height=ActualHeight<760?140:compact?172:200;
        var inlineOpen=Details.IsPaneOpen&&Details.DisplayMode==SplitViewDisplayMode.Inline;
        if(MainContentSurface is not null)
        {
            MainContentSurface.CornerRadius=inlineOpen?new CornerRadius(8,8,0,0):new CornerRadius(8,0,0,0);
            MainContentSurface.BorderThickness=inlineOpen?new Thickness(1,1,1,0):new Thickness(1,1,0,0);
            // Overlay panes must also occlude the content at their outer edge;
            // antialiasing there otherwise exposes a sliver of the Search button.
            MainContentSurface.Clip=Details.IsPaneOpen&&Details.DisplayMode==SplitViewDisplayMode.Overlay
                ?new RectangleGeometry{Rect=new Windows.Foundation.Rect(0,0,Math.Max(0,MainContentSurface.ActualWidth-Details.OpenPaneLength),MainContentSurface.ActualHeight)}
                :null;
        }
    }

    private void ShowItemDetailsPane()
    {
        SelectionSummaryScroll.Visibility=Visibility.Collapsed;
        folderSettingsActive=false;folderDraft=null;
        DetailPaneTitle.Text=AppText.L("詳細と整理","Details & Organization");
        DetailPaneTitle.Visibility=Visibility.Collapsed;
        FolderEditorPanel.Visibility=Visibility.Collapsed;
        Editor.Visibility=Visibility.Visible;
    }

    private void CloseFolderHubCore()
    {
        folderFilterTimer.Stop();
        folderAiPollTimer?.Stop();
        folderAiLoadLifetime?.Cancel();
        folderAiLoadLifetime?.Dispose();
        folderAiLoadLifetime=null;
        if(emptyLibraryScanJob is null)scanPollTimer.Stop();
        folderHubOpen=false;
        ToolTipService.SetToolTip(Count,null);
        UpdateLibraryHeading();
        FolderHubView.Visibility=Visibility.Collapsed;
        ItemSearchRow.Visibility=Visibility.Visible;
        SearchTools.Visibility=Visibility.Visible;
        ItemListContainer.Visibility=Visibility.Visible;
        ItemPagerRow.Visibility=Visibility.Visible;
        ShowItemDetailsPane();
        if(active is null&&librarySelection.Count==0)Details.IsPaneOpen=false;
    }

    private async void Roots_Click(object sender,RoutedEventArgs e)
    {
        if(folderHubOpen)await ReturnToLibraryAsync(selectedSearchRoots);
        else await OpenFolderHubAsync();
    }


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
            var changed=!SameRoots(selectedSearchRoots,targetRoots)||selectedShelfIds is not null||(allItems&&(view!="all"||similarityOrigin is not null));
            if(allItems){view="all";ClearSimilarity();UpdateSearchMethod();}
            SetShelfScope(null);
            RestoreSearchRoots(targetRoots);
            CloseFolderHubCore();
            RestoreNavigation();
            if(!changed&&CanRestoreLoadedResultSession(page,out var pageInLoadedWindow)&&pageInLoadedWindow)
            {
                RestoreLoadedLibraryView();
                RecordNavigationLocation();
                return;
            }
            if(changed)page=0;
            await LoadAsync(reuseSession:!changed&&CanRestoreLoadedResultSession(page,out _));
        }
        finally{transitions.Release();if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }

    private async Task OpenFolderHubAsync(int? focusRootId=null,bool restoreInactive=false)
    {
        if(dialogOpen||saving||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        searchTimer.Stop();
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            CloseBrowseMenus();CloseSettingsHubCore();CloseShelfHubCore();
            await RefreshSearchRootsAsync();
            if(checkedFolderIds.Count==0&&selectedSearchRoots is not null)
                foreach(var id in selectedSearchRoots.Where(id=>knownRoots.Any(r=>r.Enabled&&r.Id==id)))
                    checkedFolderIds.Add(id);
            folderHubOpen=true;
            await PollScanStateAsync();
            MainViewTitle.Text=AppText.L("登録フォルダ","Registered Folders");
            ItemSearchRow.Visibility=Visibility.Collapsed;
            SearchTools.Visibility=Visibility.Collapsed;
            ItemListContainer.Visibility=Visibility.Collapsed;
            ItemPagerRow.Visibility=Visibility.Collapsed;
            FolderHubView.Visibility=Visibility.Visible;
            UpdateLayoutToggleVisuals();
            RestoreNavigation();
            RenderFolderHub();
            scanPollTimer.Start();
            _ = RefreshFolderAIStatusAsync(fetchCoverage:true);
            if(focusRootId is int targetId)
            {
                var row=knownRoots.FirstOrDefault(r=>r.Id==targetId);
                if(row is not null)
                {
                    if(restoreInactive||!row.Enabled)PrefillRestoreRoot(row);
                    else OpenFolderSettingsPanel(new[]{row.Id});
                }
            }
            Notice(AppText.L("登録フォルダ","Registered Folders"),AppText.L("検索するフォルダを選んだり、ファイル一覧の更新や設定を行えます。","Select folders to search, refresh file lists, or adjust folder settings."));
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
            AddRootInitialShelf.Items.Add(new ComboBoxItem {Content=AppText.L("棚なし","No shelf"),Tag="none"});
            AddRootInitialShelf.Items.Add(new ComboBoxItem {Content=AppText.L("新しい棚を作成","Create new shelf"),Tag="new"});
            foreach(var shelf in knownShelves)AddRootInitialShelf.Items.Add(new ComboBoxItem {Content=shelf,Tag="existing"});
            AddRootInitialShelf.SelectedItem=AddRootInitialShelf.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Content?.ToString()==previous) ?? AddRootInitialShelf.Items[0];
            AddRootNewShelf.IsEnabled=(AddRootInitialShelf.SelectedItem as ComboBoxItem)?.Tag?.ToString()=="new";
            AddRootNewShelf.Visibility=AddRootNewShelf.IsEnabled?Visibility.Visible:Visibility.Collapsed;
        }
        finally{folderPopulating=before;}
    }

    private void AddRootInitialShelf_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(AddRootNewShelf is null)return;
        AddRootNewShelf.IsEnabled=(AddRootInitialShelf.SelectedItem as ComboBoxItem)?.Tag?.ToString()=="new";
        AddRootNewShelf.Visibility=AddRootNewShelf.IsEnabled?Visibility.Visible:Visibility.Collapsed;
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
            return string.IsNullOrWhiteSpace(newBox.Text)?throw new InvalidOperationException(AppText.L("新しい棚の名前を入力してください。","Enter a name for the new shelf.")):newBox.Text.Trim();
        return choice?.Tag?.ToString()=="existing"?choice.Content?.ToString()??"":"";
    }

    private async void AddRoot_Click(object sender,RoutedEventArgs e)
    {
        AddRoot.IsEnabled=false;FolderRegistrationEditor.IsEnabled=false;AddRoot.Content=AppText.L("追加しています…","Adding…");
        var addedIds = new List<int>();
        var errors = new List<string>();
        var failedPaths = new List<string>();
        try
        {
            var rawPaths = RootPath.Text.Split(new[]{';','\r','\n'}, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                                       .Where(p => !string.IsNullOrWhiteSpace(p)).Distinct().ToArray();
            if(rawPaths.Length == 0)
                throw new InvalidOperationException(AppText.L("追加するフォルダを選択するか、パスを入力してください。","Select a folder to add or enter a folder path."));

            var shelf=ReadInitialShelf(AddRootInitialShelf,AddRootNewShelf);
            var patterns=AddRootExcludes.Text.Split(',',StringSplitOptions.RemoveEmptyEntries|StringSplitOptions.TrimEntries);
            var recursive = RootRecursive.IsChecked == true;
            var folderBooks = RootFolderBooks.IsChecked == true;

            foreach(var path in rawPaths)
            {
                try
                {
                    var added = await api.PostAsync("api/library/roots", new JsonObject
                    {
                        {"path", path},
                        {"consent", true},
                        {"excludes", new JsonArray(patterns.Select(pattern=>(JsonNode?)JsonValue.Create(pattern)).ToArray())},
                        {"default_shelf", shelf},
                        {"folder_books", folderBooks},
                        {"recursive", recursive}
                    });
                    var newId = (added["root_id"] ?? added["id"])?.GetValue<int>();
                    if(newId is int id) addedIds.Add(id);
                }
                catch(Exception ex)
                {
                    errors.Add($"{path}: {AppText.TranslateBackend(ex.Message)}");
                    failedPaths.Add(path);
                }
            }

            if(addedIds.Count == 0)
            {
                var msg = errors.Count > 0 ? string.Join(" / ", errors) : AppText.L("フォルダを登録できませんでした。","Could not register folder.");
                throw new InvalidOperationException(msg);
            }

            if(errors.Count==0)
            {
                RootPath.Text=""; AddRootExcludes.Text=""; AddRootNewShelf.Text=""; RootFolderBooks.IsChecked=false; RootRecursive.IsChecked=true; AddRootInitialShelf.SelectedIndex=0;
                FolderAddPanel.Visibility=Visibility.Collapsed;
            }
            else RootPath.Text=string.Join("; ",failedPaths);
            resultsNeedRefresh=true;
            thumbnails.ResetSession();
            await RefreshSearchRootsAsync();
            await LoadAIScopeAsync();
            _ = RefreshFolderAIStatusAsync(fetchCoverage:true);

            OpenFolderSettingsPanel(addedIds);
            await PromptPostRegistrationScanAsync(addedIds);
            if(errors.Count>0)
                Notice(AppText.L("一部のフォルダを追加できませんでした","Some folders could not be added"),AppText.L($"{addedIds.Count}件追加・{failedPaths.Count}件失敗",$"{addedIds.Count} added, {failedPaths.Count} failed"),InfoBarSeverity.Warning,string.Join("\n",errors));
        }
        catch(Exception ex)
        {
            ScanStatus.Text=AppText.TranslateBackend(ex.Message);
            if(addedIds.Count==0)Failure(ex);
            else
            {
                AppLog.Error(ex);
                Notice(AppText.L("追加後の処理に失敗しました","Post-registration step failed"),AppText.L($"{addedIds.Count}件追加済み・{failedPaths.Count}件失敗",$"{addedIds.Count} added, {failedPaths.Count} failed"),InfoBarSeverity.Warning,$"{string.Join(" / ",errors)}\n{AppText.TranslateBackend(ex.Message)}");
            }
        }
        finally{AddRoot.IsEnabled=true;FolderRegistrationEditor.IsEnabled=true;AddRoot.Content=AppText.L("追加","Add");}
    }

    private void PrefillRestoreRoot(RegisteredRootRow row)
    {
        FolderAddPanel.Visibility=Visibility.Visible;
        FolderRegistrationOptions.IsExpanded=true;
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

    private void FolderFilter_Changed(object sender,TextChangedEventArgs e){if(ready&&folderHubOpen&&!folderPopulating){folderFilterTimer.Stop();folderFilterTimer.Start();}}
    private void FolderStateFilter_Changed(object sender,SelectionChangedEventArgs e){if(ready&&folderHubOpen&&!folderPopulating){folderFilterTimer.Stop();RenderFolderHub();}}
    private void ClearFolderFilters_Click(object sender,RoutedEventArgs e)
    {
        folderFilterTimer.Stop();
        var previous=folderPopulating;folderPopulating=true;
        try{FolderFilterBox.Text="";FolderStateFilter.SelectedIndex=0;}
        finally{folderPopulating=previous;}
        if(ready&&folderHubOpen&&!folderPopulating)RenderFolderHub();
    }
    private void SelectVisibleFolders_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||!folderHubOpen||saving||dialogOpen||folderPopulating)return;
        var ids=FilteredFolders().Where(root=>root.Enabled).Select(root=>root.Id).ToArray();
        if(checkedFolderIds.Count+ids.Count(id=>!checkedFolderIds.Contains(id))>FolderSearch.MaxRoots)
        {
            Notice(AppText.L("選択上限を超えています","Selection limit reached"),AppText.L($"選択できるのは最大 {FolderSearch.MaxRoots} 件です",$"You can select up to {FolderSearch.MaxRoots} folders"),InfoBarSeverity.Warning);
            return;
        }
        checkedFolderIds.UnionWith(ids);RenderFolderHub();
    }
    private void DeselectVisibleFolders_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||!folderHubOpen||saving||dialogOpen||folderPopulating)return;
        checkedFolderIds.ExceptWith(FilteredFolders().Where(root=>root.Enabled).Select(root=>root.Id));
        RenderFolderHub();
    }
    private void ClearAllFolderSelections_Click(object sender,RoutedEventArgs e)
    {
        if(!ready||!folderHubOpen||saving||dialogOpen||folderPopulating)return;
        checkedFolderIds.Clear();RenderFolderHub();
    }
    private void SetFolderTiles(bool nextTiles)
    {
        if(folderTiles==nextTiles)return;
        folderTiles=nextTiles;
        UpdateLayoutToggleVisuals();
        RenderFolderHub();
    }
    private void FolderLayoutList_Click(object sender,RoutedEventArgs e)=>SetFolderTiles(false);
    private void FolderLayoutGrid_Click(object sender,RoutedEventArgs e)=>SetFolderTiles(true);
    private void FolderLayout_Click(object sender,RoutedEventArgs e)=>SetFolderTiles(!folderTiles);

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
            Count.Text=AppText.L($"{visible.Count:N0} / {knownRoots.Count:N0} フォルダ",$"{visible.Count:N0} / {knownRoots.Count:N0} folders");
            ToolTipService.SetToolTip(Count,AppText.L("表示中 / 登録履歴の合計フォルダ数","Shown / total folders in history"));
            var hasNameFilter=!string.IsNullOrWhiteSpace(FolderFilterBox.Text);
            var state=FolderStateFilter.SelectedIndex;
            ClearFolderFilters.Visibility=FolderFilterBox.Text.Length>0||state!=0?Visibility.Visible:Visibility.Collapsed;
            if(knownRoots.Count==0)
            {
                VisualAssets.State(FolderEmptyArt,"greeting");
                FolderEmptyTitle.Text=AppText.L("まだ登録フォルダがありません","No registered folders yet");
                FolderEmpty.Text=AppText.L("ここにフォルダをドロップ、または［＋ フォルダを追加］から登録できます（元のファイルは移動・変更しません）。","Drop folders here or click \"+ Add Folder\" to register them (original files are never moved or modified).");
                FolderEmptyAddButton.Visibility=Visibility.Visible;
                FolderEmptyClearFiltersButton.Visibility=Visibility.Collapsed;
            }
            else if(!hasNameFilter&&state==0&&!knownRoots.Any(root=>root.Enabled))
            {
                VisualAssets.State(FolderEmptyArt,"no_results");
                FolderEmptyTitle.Text=AppText.L("登録中のフォルダはありません","No active folders");
                FolderEmpty.Text=AppText.L("解除済みのフォルダは上の表示状態を「すべて」に切り替えると確認できます。","Switch the filter above to \"All\" to view unregistered folders.");
                FolderEmptyAddButton.Visibility=Visibility.Visible;
                FolderEmptyClearFiltersButton.Visibility=Visibility.Collapsed;
            }
            else
            {
                VisualAssets.State(FolderEmptyArt,"no_results");
                FolderEmptyTitle.Text=AppText.L("該当するフォルダはありません","No matching folders");
                FolderEmpty.Text=AppText.L("絞り込み条件に一致するフォルダはありません。","No folders match the current filters.");
                FolderEmptyAddButton.Visibility=Visibility.Collapsed;
                FolderEmptyClearFiltersButton.Visibility=Visibility.Visible;
            }
            FolderList.Items.Clear();
            FolderList.ItemsPanel=(ItemsPanelTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load(folderTiles
                ? "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsWrapGrid Orientation=\"Horizontal\" CacheLength=\"3.0\"/></ItemsPanelTemplate>"
                : "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsStackPanel CacheLength=\"3.0\"/></ItemsPanelTemplate>");
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
                AutomationProperties.SetName(check,AppText.L($"{row.ShortPath}を選択",$"Select {row.ShortPath}"));
                check.Checked+=(_,_)=>{if(folderPopulating)return;if(checkedFolderIds.Count<FolderSearch.MaxRoots)checkedFolderIds.Add(row.Id);else check.IsChecked=false;UpdateFolderSelectionBar();};
                check.Unchecked+=(_,_)=>{if(folderPopulating)return;checkedFolderIds.Remove(row.Id);UpdateFolderSelectionBar();};

                var info=new StackPanel {Spacing=4,VerticalAlignment=VerticalAlignment.Center};
                var titleText=new TextBlock {Text=row.Name,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaTitleStyle"]};
                AutomationProperties.SetAutomationId(titleText,$"FolderTitle{row.Id}");
                ToolTipService.SetToolTip(titleText,row.Path);
                info.Children.Add(titleText);
                var badgeRow=new StackPanel{Orientation=Orientation.Horizontal,Spacing=4};
                var fullMetaText=$"{row.StatusLabel} · {row.ShelfLabel}"+(!row.Recursive?AppText.L(" · 直下のみ"," · Top level only"):"")+(row.FolderBooks?AppText.L(" · 一冊モード"," · Folder-as-book"):"")+(row.Exclusions.Count>0?AppText.L($" · 除外 {row.Exclusions.Count}件",$" · {row.Exclusions.Count} exclusions"):"");
                AutomationProperties.SetAutomationId(badgeRow,$"FolderMeta{row.Id}");
                AutomationProperties.SetName(badgeRow,fullMetaText);
                badgeRow.Children.Add(CreateCardBadge(row.StatusLabel,140));
                if(!string.IsNullOrEmpty(row.DefaultShelf)||row.ShelfIds is {Count:>0})
                    badgeRow.Children.Add(CreateCardBadge("📚 "+row.ShelfLabel,140));
                if(!row.Recursive)badgeRow.Children.Add(CreateCardBadge(AppText.L("直下のみ","Top level only"),100));
                if(row.FolderBooks)badgeRow.Children.Add(CreateCardBadge(AppText.L("一冊モード","Folder-as-book"),100));
                if(row.Exclusions.Count>0)badgeRow.Children.Add(CreateCardBadge(AppText.L($"除外 {row.Exclusions.Count}件",$"{row.Exclusions.Count} excluded"),100));
                ToolTipService.SetToolTip(badgeRow,fullMetaText);
                info.Children.Add(badgeRow);
                var pathText=new TextBlock {Text=row.Path,TextTrimming=TextTrimming.CharacterEllipsis,Style=(Style)Resources["MediaMetadataStyle"]};
                info.Children.Add(pathText);

                var actions=new StackPanel {Orientation=Orientation.Horizontal,Spacing=6,VerticalAlignment=VerticalAlignment.Center};
                var actionPad=folderTiles?new Thickness(10,5,10,5):new Thickness(11,5,11,6);
                var favoriteButton=new Button{Content=row.Favorite?"★":"☆",Padding=actionPad};
                AutomationProperties.SetAutomationId(favoriteButton,$"FavoriteFolder{row.Id}");
                AutomationProperties.SetName(favoriteButton,$"{row.ShortPath}：{(row.Favorite?AppText.L("お気に入りから外す","Remove from favorites"):AppText.L("お気に入りに追加","Add to favorites"))}");
                ToolTipService.SetToolTip(favoriteButton,row.Favorite?AppText.L("お気に入りから外す","Remove from favorites"):AppText.L("お気に入りに追加","Add to favorites"));
                favoriteButton.Click+=async(_,_)=>await SetRootFavoriteAsync(row,!row.Favorite);actions.Children.Add(favoriteButton);
                if(row.Enabled)
                {
                    var openBtn=new Button {Content=AppText.L("作品を見る","Browse items"),Padding=actionPad};
                    AutomationProperties.SetAutomationId(openBtn,$"OpenFolder{row.Id}");
                    AutomationProperties.SetName(openBtn,AppText.L($"{row.ShortPath}の作品を見る",$"Browse items in {row.ShortPath}"));
                    openBtn.Click+=async(_,_)=>await ReturnToLibraryAsync(new[]{row.Id});
                    var quickScanBtn=new Button {Content=AppText.L("⟳ 更新","⟳ Refresh"),Padding=actionPad};
                    AutomationProperties.SetAutomationId(quickScanBtn,$"QuickScanFolder{row.Id}");
                    AutomationProperties.SetName(quickScanBtn,AppText.L($"{row.ShortPath}のファイル一覧を更新",$"Refresh file list for {row.ShortPath}"));
                    ToolTipService.SetToolTip(quickScanBtn,AppText.L("このフォルダのファイル一覧を更新","Refresh the file list for this folder"));
                    quickScanBtn.Click+=async(_,_)=>await StartScanWithModeAsync(new[]{row.Id},"list");
                    var configBtn=new Button {Content=AppText.L("設定","Settings"),Padding=actionPad};
                    AutomationProperties.SetAutomationId(configBtn,$"ConfigFolder{row.Id}");
                    AutomationProperties.SetName(configBtn,AppText.L($"{row.ShortPath}の設定",$"Settings for {row.ShortPath}"));
                    configBtn.Click+=async(_,_)=>await SelectFolderForSettingsAsync(new[]{row.Id},false);
                    actions.Children.Add(openBtn);
                    actions.Children.Add(quickScanBtn);
                    actions.Children.Add(configBtn);
                }
                else
                {
                    var restoreBtn=new Button {Content=AppText.L("再登録","Re-register"),Padding=actionPad};
                    AutomationProperties.SetAutomationId(restoreBtn,$"RestoreFolder{row.Id}");
                    AutomationProperties.SetName(restoreBtn,AppText.L($"{row.ShortPath}を再登録",$"Re-register {row.ShortPath}"));
                    restoreBtn.Click+=async(_,_)=>await RestoreRootAsync(row);
                    var purgeBtn=new Button {Content=AppText.L("記録を完全削除","Delete records"),Padding=actionPad};
                    AutomationProperties.SetAutomationId(purgeBtn,$"PurgeFolder{row.Id}");
                    AutomationProperties.SetName(purgeBtn,AppText.L($"{row.ShortPath}の記録を完全削除",$"Permanently delete records for {row.ShortPath}"));
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
                    Width=folderTiles?ComputeFolderTileWidth():double.NaN,
                    Margin=folderTiles?new Thickness(0,0,8,8):new Thickness(0,0,0,6),
                    HorizontalContentAlignment=HorizontalAlignment.Stretch
                };
                item.Tapped+=async(_,args)=>{if(row.Enabled&&!IsFolderActionSource(args.OriginalSource)){args.Handled=true;await SelectFolderForSettingsAsync(new[]{row.Id},false);}};
                item.DoubleTapped+=async(_,args)=>{if(row.Enabled&&!IsFolderActionSource(args.OriginalSource)){args.Handled=true;await ReturnToLibraryAsync(new[]{row.Id});}};
                AutomationProperties.SetAutomationId(item,$"FolderItem{row.Id}");
                AutomationProperties.SetName(item,$"{row.Name} ({row.ShortPath})");
                var menu=new MenuFlyout();
                var favoriteMenu=new MenuFlyoutItem{Text=row.Favorite?AppText.L("お気に入りから外す","Remove from favorites"):AppText.L("お気に入りに追加","Add to favorites")};
                AutomationProperties.SetAutomationId(favoriteMenu,$"MenuFavoriteFolder{row.Id}");
                favoriteMenu.Click+=async(_,_)=>await SetRootFavoriteAsync(row,!row.Favorite);menu.Items.Add(favoriteMenu);
                if(row.Enabled)
                {
                    var manageItem=new MenuFlyoutItem {Text=AppText.L("フォルダの設定","Folder settings")};
                    AutomationProperties.SetAutomationId(manageItem,$"ManageRoot{row.Id}");
                    manageItem.Click+=async(_,_)=>await SelectFolderForSettingsAsync(new[]{row.Id},false);
                    var browseItem=new MenuFlyoutItem {Text=AppText.L("このフォルダの作品を見る","Browse items in this folder")};
                    AutomationProperties.SetAutomationId(browseItem,$"BrowseRoot{row.Id}");
                    browseItem.Click+=async(_,_)=>await ReturnToLibraryAsync(new[]{row.Id});
                    var toggleItem=new MenuFlyoutItem {Text=checkedFolderIds.Contains(row.Id)?AppText.L("選択から外す","Deselect"):AppText.L("選択に含める","Select")};
                    AutomationProperties.SetAutomationId(toggleItem,$"ToggleSearchRoot{row.Id}");
                    toggleItem.Click+=(_,_)=>{if(checkedFolderIds.Contains(row.Id))checkedFolderIds.Remove(row.Id);else if(checkedFolderIds.Count<FolderSearch.MaxRoots)checkedFolderIds.Add(row.Id);RenderFolderHub();};
                    menu.Items.Add(manageItem);menu.Items.Add(browseItem);menu.Items.Add(toggleItem);
                }
                else
                {
                    var restoreItem=new MenuFlyoutItem {Text=AppText.L("再登録","Re-register")};
                    AutomationProperties.SetAutomationId(restoreItem,$"ManageRoot{row.Id}");
                    restoreItem.Click+=async(_,_)=>await RestoreRootAsync(row);
                    var purgeItem=new MenuFlyoutItem {Text=AppText.L("記録を完全削除","Delete records")};
                    AutomationProperties.SetAutomationId(purgeItem,$"PurgeRoot{row.Id}");
                    purgeItem.Click+=async(_,_)=>await PurgeInactiveRootAsync(row);
                    menu.Items.Add(restoreItem);menu.Items.Add(purgeItem);
                }
                item.ContextFlyout=menu;
                FolderList.Items.Add(item);
            }
            FolderEmptyState.Visibility=FolderEmpty.Visibility=visible.Count==0?Visibility.Visible:Visibility.Collapsed;
            UpdateFolderSelectionBar();
        }
        finally{folderPopulating=false;}
    }

    private void UpdateFolderSelectionBar()
    {
        if(FolderSelectionPanel is null||FolderSelectionSummary is null||SearchSelectedFoldersButton is null||EditSelectedFoldersButton is null||UnregisterSelectedFoldersButton is null)return;
        var selectedRows=knownRoots.Where(r=>r.Enabled&&checkedFolderIds.Contains(r.Id)).OrderBy(r=>r.Id).ToArray();
        var count=selectedRows.Length;
        FolderSelectionPanel.Visibility=count>0?Visibility.Visible:Visibility.Collapsed;
        if(count==0)
        {
            FolderSelectionSummary.Text="";
            SearchSelectedFoldersButton.IsEnabled=false;
            EditSelectedFoldersButton.IsEnabled=false;
            UnregisterSelectedFoldersButton.IsEnabled=false;
        }
        else
        {
            var names=string.Join(AppText.L("、",", "),selectedRows.Take(3).Select(r=>r.ShortPath))+(count>3?AppText.L($" ほか{count-3}件",$" and {count-3} more"):"");
            FolderSelectionSummary.Text=AppText.L($"{count}フォルダ選択中（{names}）",$"{count} folders selected ({names})");
            SearchSelectedFoldersButton.Content=AppText.L($"🔍 {count}フォルダを検索",$"🔍 Search {count} folders");
            SearchSelectedFoldersButton.IsEnabled=true;
            EditSelectedFoldersButton.IsEnabled=true;
            UnregisterSelectedFoldersButton.IsEnabled=true;
        }
        UpdateFolderLayout();
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
            if(folderSettingsActive&&folderDraft is not null&&folderDraft.TargetIds.SequenceEqual(targetIds.Order()))
            {
                Details.IsPaneOpen=true;
                if(focusUnregister){RootRemovalSection.IsExpanded=true;UnregisterConsent.Focus(FocusState.Programmatic);}
                return;
            }
            if(Dirty||(folderSettingsActive&&folderDraft is not null&&!folderDraft.TargetIds.SequenceEqual(targetIds)))
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
            DetailKindBadge.Visibility=Visibility.Collapsed;
            DetailPaneTitle.Visibility=Visibility.Visible;
            DetailPaneTitle.Text=folderDraft.IsBatch?AppText.L($"一括設定（{targets.Length}件）",$"Batch settings ({targets.Length})"):AppText.L("フォルダの設定","Folder settings");
            SelectionSummaryScroll.Visibility=Visibility.Collapsed;
            Editor.Visibility=Visibility.Collapsed;
            FolderEditorPanel.Visibility=Visibility.Visible;
            Details.IsPaneOpen=true;
            FolderList.SelectedItem=FolderList.Items.OfType<ListViewItem>().FirstOrDefault(i=>i.Tag is int id&&targetIds.Contains(id));
            DetailsButton.IsEnabled=true;
            FolderTargetTitle.Text=folderDraft.IsBatch
                ? AppText.L($"選択した {targets.Length} フォルダ: {string.Join("、",targets.Select(r=>r.ShortPath))}",$"{targets.Length} selected folders: {string.Join(", ",targets.Select(r=>r.ShortPath))}")
                : targets[0].ShortPath;
            FolderTargetPath.Text=string.Join("\n",targets.Select(r=>AppText.L($"{r.Path}（{(r.Online?"接続OK":"未接続")}・{r.PresentCount:N0}件）",$"{r.Path} ({(r.Online?"Connected":"Offline")} · {r.PresentCount:N0} items)")));
            CurrentShelfSummary.Text=AppText.L($"現在: {folderDraft.Summary.DisplayText}",$"Current: {folderDraft.Summary.DisplayText}");
            RootInitialShelf.Items.Clear();
            if(folderDraft.IsBatch)
                RootInitialShelf.Items.Add(new ComboBoxItem {Content=folderDraft.Summary.IsMixed?AppText.L("複数の設定値（変更しない）","Mixed values (keep unchanged)"):AppText.L($"変更しない（現在: {folderDraft.Summary.DisplayText}）",$"Keep unchanged (current: {folderDraft.Summary.DisplayText})"),Tag="keep"});
            RootInitialShelf.Items.Add(new ComboBoxItem {Content=AppText.L("棚なし","No shelf"),Tag="none"});
            RootInitialShelf.Items.Add(new ComboBoxItem {Content=AppText.L("新しい棚を作成","Create new shelf"),Tag="new"});
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
            RootShelfSettings.IsExpanded=folderDraft.IsBatch;
            RootRemovalSection.IsExpanded=focusUnregister;
            RootExcludes.Text=folderDraft.ExclusionsText;
            RootStartupScan.SelectedIndex=targets.All(root=>root.StartupScan==targets[0].StartupScan)
                ? targets[0].StartupScan switch{"list"=>1,"list_and_ai"=>2,_=>0} : -1;
            SaveRootShelf.Content=folderDraft.IsBatch?AppText.L($"保存（{targets.Length}フォルダ）",$"Save ({targets.Length} folders)"):AppText.L("保存","Save");
            UnregisterTargetText.Text=AppText.L($"{string.Join("、",targets.Select(r=>r.ShortPath))}（{targets.Length} フォルダ・{targets.Sum(r=>r.PresentCount):N0} 件）\n元ファイルは残り、再登録でタグと棚が戻ります。",
                $"{string.Join(", ",targets.Select(r=>r.ShortPath))} ({targets.Length} folders · {targets.Sum(r=>r.PresentCount):N0} items)\nOriginal files remain, and tags/shelves restore if re-registered.");
            UnregisterConsent.IsChecked=false;
            UnregisterRoot.IsEnabled=true;
            UnregisterRoot.Content=folderDraft.IsBatch?AppText.L($"登録を解除（{targets.Length}フォルダ）",$"Unregister ({targets.Length} folders)"):AppText.L("登録を解除","Unregister");
            UpdateScanRootButtonLabel();
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
        FolderEditStatus.Text=folderDraft.IsDirty?AppText.L("未保存の設定変更","Unsaved setting changes"):AppText.L("設定保存済み","Settings saved");
    }

    private void RootInitialShelf_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(RootNewShelf is null)return;
        var tag=(RootInitialShelf.SelectedItem as ComboBoxItem)?.Tag?.ToString();
        RootNewShelf.IsEnabled=tag=="new";
        RootNewShelf.Visibility=RootNewShelf.IsEnabled?Visibility.Visible:Visibility.Collapsed;
        if(!folderPopulating&&folderDraft is not null&&tag!="multiple")folderDraft.ClearShelfIdSelection();
        UpdateFolderDraftState();
    }

    private void FolderEditor_Changed(object sender,TextChangedEventArgs e)=>UpdateFolderDraftState();
    private void FolderEditor_Checked(object sender,RoutedEventArgs e)=>UpdateFolderDraftState();
    private void UnregisterConsent_Changed(object sender,RoutedEventArgs e)
    {
        if(UnregisterRoot is not null)UnregisterRoot.IsEnabled=!saving;
    }

    private async void SaveRootShelf_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||saving||dialogOpen)return;
        SyncFolderDraftFromControls();var draft=folderDraft;
        if(!draft.IsShelfChanged){FolderEditStatus.Text=AppText.L("変更はありません","No changes");return;}
        SaveRootShelf.IsEnabled=false;FolderEditorPanel.IsEnabled=false;saving=true;FolderEditStatus.Text=AppText.L("保存しています…","Saving…");
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
            var shelfExpanded=RootShelfSettings.IsExpanded;
            resultsNeedRefresh=true;OpenFolderSettingsPanel(targets);
            RootShelfSettings.IsExpanded=shelfExpanded;
            if(pendingExcludes is not null){RootExcludes.Text=pendingExcludes;UpdateFolderDraftState();}
            FolderEditStatus.Text=AppText.L($"保存しました（棚なし {result["updated"]?.GetValue<int>()??0:N0}件に適用）",$"Saved (applied to {result["updated"]?.GetValue<int>()??0:N0} unshelved items)")+(pendingExcludes is null?"":AppText.L(" · 除外は未保存"," · Exclusions unsaved"));
            ScanStatus.Text=FolderEditStatus.Text;
            try{await RefreshSearchRootsAsync();}
            catch(Exception ex){AppLog.Error(ex);FolderEditStatus.Text=AppText.L("保存しました（一覧の更新に失敗）","Saved (failed to refresh list)");}
        }
        catch(Exception ex){Failure(ex);FolderEditStatus.Text=AppText.L("保存できませんでした（選択内容は残っています）","Could not save (selection remains)");}
        finally{saving=false;SaveRootShelf.IsEnabled=true;FolderEditorPanel.IsEnabled=true;}
    }

    private async void SaveExcludes_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||folderDraft.IsBatch||folderDraft.TargetIds.Count!=1||saving||dialogOpen)return;
        SyncFolderDraftFromControls();
        var draft=folderDraft;var rootId=draft.TargetIds[0];var savedText=draft.ExclusionsText;
        var exclusions=draft.ParseExclusions();
        SaveExcludes.IsEnabled=false;FolderEditorPanel.IsEnabled=false;saving=true;
        try
        {
            var patterns=new JsonArray(exclusions.Select(s=>(JsonNode?)JsonValue.Create(s)).ToArray());
            await api.PostAsync("api/library/excludes",new JsonObject{{"root_id",rootId},{"patterns",patterns}});
            draft.MarkExclusionsSaved(savedText);
            resultsNeedRefresh=true;
            knownRoots=knownRoots.Select(root=>root.Id==rootId?root with{Exclusions=exclusions}:root).ToArray();
            ScanStatus.Text=AppText.L("次回の一覧更新で反映されます","Will take effect on the next refresh");
            FolderEditStatus.Text=AppText.L("除外を保存しました","Saved exclusions")+(draft.IsShelfChanged?AppText.L(" · 自動棚は未保存"," · Default shelf unsaved"):"");
            thumbnails.ResetSession();
            try{await RefreshSearchRootsAsync();}
            catch(Exception ex){AppLog.Error(ex);FolderEditStatus.Text=AppText.L("保存しました（一覧の更新に失敗）","Saved (failed to refresh list)")+(draft.IsShelfChanged?AppText.L(" · 自動棚は未保存"," · Default shelf unsaved"):"");}
        }
        catch(Exception ex){ScanStatus.Text=AppText.TranslateBackend(ex.Message);FolderEditStatus.Text=AppText.TranslateBackend(ex.Message);}
        finally{saving=false;SaveExcludes.IsEnabled=true;FolderEditorPanel.IsEnabled=true;}
    }

    private async Task StartScanWithModeAsync(IReadOnlyList<int> targetIds, string mode)
    {
        if(targetIds.Count==0)return;
        try
        {
            var body=new JsonObject{{"mode",mode}};
            if(targetIds.Count==1)
                body["root_id"]=targetIds[0];
            else
                body["root_ids"]=new JsonArray(targetIds.Select(id=>(JsonNode?)JsonValue.Create(id)).ToArray());
            var started=await api.PostAsync("api/library/scan",body);
            resultsNeedRefresh=true;
            if(disposed)return;
            if(rows.Count==0&&!knownRoots.Any(root=>root.Enabled&&root.PresentCount>0))
            {
                emptyLibraryScanJob=started["job_id"]?.GetValue<long>();
                if(emptyLibraryScanJob is not null&&!scanPollTimer.IsRunning)scanPollTimer.Start();
            }
            scanRootsRefreshed=false;
            ScanStatus.Text=mode=="list_and_ai"?AppText.L("更新開始（一覧＋AI検索データ）","Refresh started (file list + AI search index)"):AppText.L("更新開始（一覧のみ）","Refresh started (file list only)");
            await PollScanStateAsync();
        }
        catch(Exception ex){ScanStatus.Text=AppText.TranslateBackend(ex.Message);Failure(ex);}
    }

    private void ScanModeChoice_Changed(object sender,SelectionChangedEventArgs e)
    {
        if(!folderPopulating)UpdateScanRootButtonLabel();
    }

    private void UpdateScanRootButtonLabel()
    {
        if(ScanRoot is null||folderDraft is null)return;
        var targets=knownRoots.Where(r=>r.Enabled&&folderDraft.TargetIds.Contains(r.Id)).ToArray();
        bool firstScan=targets.Length>0&&targets.All(r=>string.IsNullOrEmpty(r.LastScannedAt)&&r.PresentCount==0);
        bool withAI=ScanModeChoice?.SelectedIndex==1;
        ScanRoot.Content=firstScan
            ?(withAI?AppText.L("一覧とAIデータを作成","Create file list & AI index"):AppText.L("ファイル一覧を作成","Create file list"))
            :(withAI?AppText.L("一覧とAIデータを更新","Update file list & AI index"):AppText.L("ファイル一覧を更新","Refresh file list"));
    }

    private async void ScanRoot_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||folderDraft.TargetIds.Count==0)return;
        var mode=(ScanModeChoice?.SelectedIndex==1)?"list_and_ai":"list";
        await StartScanWithModeAsync(folderDraft.TargetIds,mode);
    }

    private async void CancelScan_Click(object sender,RoutedEventArgs e)
    {
        try
        {
            await api.PostAsync("api/library/cancel",new JsonObject());
            ScanStatus.Text=AppText.L("中止しています…（前回のデータは残ります）","Canceling… (previous data stays intact)");
            await PollScanStateAsync();
        }
        catch(Exception ex){ScanStatus.Text=AppText.TranslateBackend(ex.Message);}
    }

    private async void UnregisterRoot_Click(object sender,RoutedEventArgs e)
    {
        if(folderDraft is null||saving||dialogOpen)return;
        if(UnregisterConsent.IsChecked!=true)
        {
            if(!await transitions.WaitAsync(0))return;
            var confirmed=false;
            dialogOpen=true;
            try
            {
                var confirmDialog=new ContentDialog
                {
                    XamlRoot=XamlRoot,
                    RequestedTheme=ActualTheme,
                    Title=AppText.L("フォルダの登録を解除","Unregister folder"),
                    Content=AppText.L($"対象: {folderDraft.TargetIds.Count} フォルダ\n元のファイル・タグ・棚は残ります（再登録で復元できます）。",$"Selected: {folderDraft.TargetIds.Count} folders\nOriginal files, tags, and shelves remain (restored if re-registered)."),
                    PrimaryButtonText=AppText.L("登録を解除","Unregister"),
                    CloseButtonText=AppText.L("キャンセル","Cancel"),
                    DefaultButton=ContentDialogButton.Close
                };
                confirmed=await confirmDialog.ShowAsync()==ContentDialogResult.Primary;
            }
            finally{dialogOpen=false;transitions.Release();}
            if(!confirmed||disposed||folderDraft is null)return;
        }
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
                    failures.Add($"{label}: {AppText.TranslateBackend(ex.Message)}");
                }
            }
            if(selectedSearchRoots is not null&&succeeded.Count>0)
            {
                var remainingSearch=selectedSearchRoots.Where(id=>!succeeded.Contains(id)).ToArray();
                if(remainingSearch.Length>0)selectedSearchRoots=remainingSearch;
            }
            resultsNeedRefresh=true;
            thumbnails.ResetSession();
            await RefreshSearchRootsAsync();
            await LoadAIScopeAsync();
            _ = RefreshFolderAIStatusAsync(fetchCoverage:true);
            UnregisterConsent.IsChecked=false;
            if(failures.Count==0)
            {
                folderSettingsActive=false;folderDraft=null;Details.IsPaneOpen=false;
                ShowItemDetailsPane();
                var msg=AppText.L($"{succeeded.Count}フォルダの登録を解除しました（元ファイル・タグ・棚は保持）",$"Unregistered {succeeded.Count} folder(s) (files, tags, and shelves preserved)");
                ScanStatus.Text=msg;
                Notice(AppText.L("登録を解除しました","Unregistered"),msg);
            }
            else
            {
                var msg=AppText.L($"{succeeded.Count}件解除、{failures.Count}件失敗（{string.Join(" / ",failures)}）。未完了のフォルダが選択に残っています。",$"Unregistered {succeeded.Count}, failed {failures.Count} ({string.Join(" / ",failures)}). Remaining folders stay selected.");
                FolderEditStatus.Text=msg;
                ScanStatus.Text=msg;
            }
        }
        catch(Exception ex){ScanStatus.Text=ex.Message;UnregisterRoot.IsEnabled=true;}
        finally{saving=false;if(UnregisterRoot is not null)UnregisterRoot.IsEnabled=true;}
    }

    private bool CanRefreshEmptyLibraryAfterScan()=>!disposed&&!folderHubOpen&&!shelfHubOpen&&!settingsHubOpen&&rows.Count==0&&active is null
        &&view=="all"&&similarityOrigin is null&&selectedSearchRoots is null&&selectedShelfIds is null
        &&Kind.SelectedIndex==0&&SearchMode.SelectedIndex==0&&string.IsNullOrWhiteSpace(Query.Text);

    private async Task PollScanStateAsync()
    {
        if(pollingScan||disposed||(!folderHubOpen&&emptyLibraryScanJob is null))return;
        pollingScan=true;
        try
        {
            var state=await api.GetAsync("api/library/scan");
            if(disposed)return;
            var phase=state["state"]?.GetValue<string>() ?? "idle";
            var mode=state["mode"]?.GetValue<string>() ?? "list";
            var stage=state["stage"]?.GetValue<string>() ?? phase;
            var aiState=state["ai_state"]?.GetValue<string>() ?? "none";
            var aiError=state["ai_error"]?.GetValue<string>() ?? "";
            var aiProcessed=state["ai_processed"]?.GetValue<int>() ?? 0;
            var aiTotal=state["ai_total"]?.GetValue<int>() ?? 0;
            var discovered=state["discovered"]?.GetValue<int>() ?? 0;
            var scanError=state["error"]?.GetValue<string>() ?? "";
            var deniedCount=state["skipped_access_denied"]?.GetValue<int>() ?? 0;
            var deniedTruncated=state["access_denied_truncated"]?.GetValue<bool>()==true;
            var deniedEntries=new List<(string RootPath,string RelativePath,bool IsDir)>();
            if(state["access_denied_entries"] is JsonArray deniedArray)
            {
                foreach(var item in deniedArray)
                {
                    if(item is not JsonObject obj)continue;
                    var rp=obj["root_path"]?.GetValue<string>() ?? "";
                    var rel=obj["relative_path"]?.GetValue<string>() ?? "";
                    if(string.IsNullOrWhiteSpace(rel))continue;
                    deniedEntries.Add((rp,rel,obj["is_dir"]?.GetValue<bool>()==true));
                }
            }
            lastScanAccessDeniedCount=deniedCount;
            lastScanAccessDeniedTruncated=deniedTruncated;
            lastScanAccessDeniedEntries=deniedEntries;

            bool listRunning = phase is "running" or "cancelling";
            bool aiRunning = mode == "list_and_ai" && (stage == "ai" || aiState is "running" or "cancelling");
            bool anyRunning = listRunning || aiRunning;

            if(emptyLibraryScanJob is long job&&state["id"]?.GetValue<long>() is long observedJob
                &&(observedJob>job||observedJob==job&&!listRunning))
            {
                if(observedJob==job&&phase=="complete"&&CanRefreshEmptyLibraryAfterScan())
                {
                    // The folder-to-library transition may still be reading an empty snapshot.
                    if(dialogOpen||saving||!await transitions.WaitAsync(0))return;
                    emptyLibraryScanJob=null;
                    try
                    {
                        thumbnails.ResetSession();
                        await RefreshSearchRootsAsync();
                        if(CanRefreshEmptyLibraryAfterScan())await LoadAsync();
                    }
                    finally{transitions.Release();if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}}
                }
                else emptyLibraryScanJob=null;
            }
            if(!folderHubOpen)
            {
                if(emptyLibraryScanJob is null)scanPollTimer.Stop();
                return;
            }

            if(ScanRoot is not null)ScanRoot.IsEnabled=!anyRunning;
            if(SaveExcludes is not null)SaveExcludes.IsEnabled=!anyRunning;
            if(AddRoot is not null)AddRoot.IsEnabled=!anyRunning;
            if(CancelScan is not null)CancelScan.IsEnabled=anyRunning;
            if(ShowScanAccessDeniedButton is not null)
            {
                ShowScanAccessDeniedButton.Visibility=!listRunning&&lastScanAccessDeniedCount>0?Visibility.Visible:Visibility.Collapsed;
                ShowScanAccessDeniedButton.Content=AppText.L($"アクセス拒否ログを表示（{lastScanAccessDeniedCount:N0}件）",$"View access-denied log ({lastScanAccessDeniedCount:N0})");
            }

            if(!listRunning && !scanRootsRefreshed)
            {
                scanRootsRefreshed = true;
                resultsNeedRefresh = true;
                thumbnails.ResetSession();
                await RefreshSearchRootsAsync();
                _ = RefreshFolderAIStatusAsync(fetchCoverage:true);
                UpdateGettingStarted();
                if(phase=="complete"&&lastScanAccessDeniedCount>0)
                    Notice(
                        AppText.L("アクセス拒否された項目をスキップしました","Skipped access-denied items"),
                        AppText.L($"アクセス権限がない {lastScanAccessDeniedCount:N0} 件のフォルダ・ファイルをスキップして更新を完了しました。「アクセス拒否ログを表示」から詳細を確認できます。",
                            $"Completed refresh after skipping {lastScanAccessDeniedCount:N0} access-denied item(s). Select \"View access-denied log\" for details."),
                        InfoBarSeverity.Warning);
            }
            if(listRunning)
            {
                scanRootsRefreshed = false;
            }

            var deniedSuffix=lastScanAccessDeniedCount>0
                ?AppText.L($" · アクセス拒否 {lastScanAccessDeniedCount:N0}件スキップ",$" · {lastScanAccessDeniedCount:N0} access-denied skipped")
                :"";
            if(listRunning)
            {
                var prefix = phase == "cancelling" ? AppText.L("更新を中止中","Canceling refresh") : AppText.L("一覧を更新中","Refreshing list");
                ScanStatus.Text = AppText.L($"{prefix} · {discovered} 件",$"{prefix} · {discovered} items");
            }
            else if(aiRunning)
            {
                var prefix = aiState == "cancelling" ? AppText.L("AIデータ作成を中止中","Canceling AI indexing") : AppText.L("AIデータ作成中","Building AI index");
                ScanStatus.Text = AppText.L($"{prefix} · {aiProcessed}/{aiTotal} 件",$"{prefix} · {aiProcessed}/{aiTotal} items");
                _ = RefreshFolderAIStatusAsync(fetchCoverage:false);
            }
            else if(phase == "failed")
            {
                ScanStatus.Text = AppText.L($"更新失敗 · {AppText.TranslateBackend(scanError)}",$"Refresh failed · {AppText.TranslateBackend(scanError)}");
            }
            else if(!string.IsNullOrEmpty(aiError) || aiState == "failed")
            {
                ScanStatus.Text = AppText.L($"一覧更新完了 · AI未完了: {AppText.TranslateBackend(aiError)}",$"List refreshed · AI incomplete: {AppText.TranslateBackend(aiError)}")+deniedSuffix;
            }
            else if(phase == "complete")
            {
                if(mode == "list_and_ai")
                {
                    if(aiState == "skipped")
                        ScanStatus.Text = AppText.L($"一覧を更新しました（{discovered}件）· AIは未実行",$"List refreshed ({discovered} items) · AI skipped")+deniedSuffix;
                    else if(aiState == "cancelled")
                        ScanStatus.Text = AppText.L($"一覧を更新しました（{discovered}件）· AI中止",$"List refreshed ({discovered} items) · AI canceled")+deniedSuffix;
                    else
                        ScanStatus.Text = AppText.L($"一覧・AI検索データ完了（{discovered}件）",$"List & AI index complete ({discovered} items)")+deniedSuffix;
                }
                else
                {
                    ScanStatus.Text = AppText.L($"一覧を更新しました（{discovered}件）",$"List refreshed ({discovered} items)")+deniedSuffix;
                }
            }
            else if(!string.IsNullOrEmpty(scanError))
            {
                ScanStatus.Text = AppText.TranslateBackend(scanError);
            }
        }
        catch(Exception ex)
        {
            if(folderHubOpen)ScanStatus.Text=ex.Message;
            else
            {
                emptyLibraryScanJob=null;scanPollTimer.Stop();
                AppLog.Error(ex);
            }
        }
        finally{pollingScan=false;}
    }

    private async void ShowScanAccessDenied_Click(object sender,RoutedEventArgs e)=>await OpenScanAccessDeniedDialogAsync();

    private string FormatAccessDeniedLogLine(string rootPath,string relativePath,bool isDir)
    {
        var prefix=isDir?AppText.L("[フォルダ] ","[Folder] "):AppText.L("[ファイル] ","[File] ");
        var trimmedRoot=rootPath.TrimEnd('\\','/');
        var winRel=relativePath.Replace('/','\\').TrimStart('\\');
        var fullPath=string.IsNullOrEmpty(trimmedRoot)?winRel:$"{trimmedRoot}\\{winRel}";
        return prefix+fullPath;
    }

    private async Task OpenScanAccessDeniedDialogAsync()
    {
        if(!ready||disposed||dialogOpen||lastScanAccessDeniedCount==0||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        try
        {
            var summary=AppText.L(
                $"アクセス権がないため {lastScanAccessDeniedCount:N0} 件のフォルダ・ファイルをスキップして、他のアクセス可能な項目を読み込みました。",
                $"Skipped {lastScanAccessDeniedCount:N0} folder(s) or file(s) due to access denied while indexing all accessible items.");
            if(lastScanAccessDeniedTruncated)
                summary+="\n"+AppText.L(
                    $"ログには先頭 {lastScanAccessDeniedEntries.Count:N0} 件のみ表示しています。",
                    $"Showing the first {lastScanAccessDeniedEntries.Count:N0} entries in this log.");
            var logText=string.Join("\n",lastScanAccessDeniedEntries.Select(entry=>FormatAccessDeniedLogLine(entry.RootPath,entry.RelativePath,entry.IsDir)));
            var panel=new StackPanel{Spacing=12};
            panel.Children.Add(new TextBlock{Text=summary,TextWrapping=TextWrapping.Wrap});
            var txt=new TextBox
            {
                IsReadOnly=true,
                AcceptsReturn=true,
                Text=logText,
                TextWrapping=TextWrapping.NoWrap,
                Height=280,
                FontFamily=new Microsoft.UI.Xaml.Media.FontFamily("Consolas, Cascadia Code, monospace")
            };
            ScrollViewer.SetHorizontalScrollBarVisibility(txt,ScrollBarVisibility.Auto);
            AutomationProperties.SetAutomationId(txt,"TxtScanAccessDeniedLog");
            panel.Children.Add(txt);
            var copyStatus=new TextBlock{TextWrapping=TextWrapping.Wrap,Visibility=Visibility.Collapsed,Style=(Style)Resources["MediaMetadataStyle"]};
            var copyBtn=new Button{Content=AppText.L("ログをコピー","Copy log"),HorizontalAlignment=HorizontalAlignment.Left};
            AutomationProperties.SetAutomationId(copyBtn,"BtnCopyScanAccessDeniedLog");
            copyBtn.Click+=(_,_)=>{
                var package=new Windows.ApplicationModel.DataTransfer.DataPackage();
                package.SetText(logText);
                Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(package);
                copyStatus.Text=AppText.L("✓ クリップボードにコピーしました。","✓ Copied to clipboard.");
                copyStatus.Visibility=Visibility.Visible;
            };
            panel.Children.Add(copyBtn);
            panel.Children.Add(copyStatus);
            var dialog=new ContentDialog
            {
                XamlRoot=XamlRoot,
                RequestedTheme=ActualTheme,
                Title=AppText.L("アクセス拒否によりスキップされた一覧","Skipped due to access denied"),
                CloseButtonText=AppText.L("閉じる","Close"),
                Content=panel
            };
            AutomationProperties.SetAutomationId(dialog,"ScanAccessDeniedDialog");
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();}
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
            var dialog=new ContentDialog {XamlRoot=root,RequestedTheme=ActualTheme,Title=AppText.L("関連語","Related terms"),Content=editorScroll,CloseButtonText=AppText.L("閉じる","Close"),DefaultButton=ContentDialogButton.Close};
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

    private static string DescribeProfileCapabilities(JsonNode? modalitiesNode,string? adapter)
    {
        var list=new List<string>();
        var modalities=modalitiesNode is JsonArray arr?arr.Select(x=>x?.GetValue<string>()).Where(s=>s is not null).ToHashSet():[];
        if(modalities.Contains("text"))list.Add(AppText.L("名前・タグ","Names & tags"));
        if(modalities.Contains("cover"))list.Add(AppText.L("画像","Images"));
        if(adapter=="embeddinggemma2"){list.Add(AppText.L("動画","Video"));list.Add(AppText.L("音声","Audio"));}
        return list.Count>0?string.Join(AppText.L("、",", "),list):AppText.L("未確認","Unverified");
    }
    private async void AI_Click(object sender,RoutedEventArgs e)=>await OpenAISettingsAsync();
    private async Task OpenAISettingsAsync(string? initialSection = null)
    {
        if(dialogOpen||saving||!await transitions.WaitAsync(0))return;
        var timer=DispatcherQueue.CreateTimer();timer.Interval=TimeSpan.FromSeconds(1);
        bool reload=false,openEnvironment=false,openDownload=false;
        XamlRoot? capturedRoot=null;
        Windows.Foundation.TypedEventHandler<XamlRoot,XamlRootChangedEventArgs>? rootChanged=null;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            dialogOpen=true;reload=false;
            var explanation=new TextBlock {Text=AppText.L("モデル・保存先の変更は再起動後に反映されます。","Model and folder changes take effect after restarting."),TextWrapping=TextWrapping.Wrap};
            ToolTipService.SetToolTip(explanation,AppText.L("AI検索には検索モデルと実行環境が必要です。新しいモデルを使うにはAI検索データの作り直しが必要です。","AI search requires a search model and runtime. Switching models requires rebuilding the AI index."));
            var environmentButton=new Button{Content=AppText.L("手元のファイルを使う","Use local files")};AutomationProperties.SetAutomationId(environmentButton,"AIEnvironmentOpen");
            var downloadButton=new Button{Content=AppText.L("モデルをダウンロード","Download models"),Style=(Style)Resources["AccentButtonStyle"]};AutomationProperties.SetAutomationId(downloadButton,"AIModelDownloadOpen");
            var setupActions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};setupActions.Children.Add(downloadButton);setupActions.Children.Add(environmentButton);
            var modelChoice=new ComboBox {Header=AppText.L("使用するモデル","Model to use"),HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(modelChoice,"AIProfileChoice");
            var modelCaps=new TextBlock {TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            AutomationProperties.SetAutomationId(modelCaps,"AIProfileCapabilities");
            var modelWarning=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(modelWarning,"AIProfileWarning");
            var modelApply=new Button {Content=AppText.L("保存","Save"),IsEnabled=false};
            AutomationProperties.SetAutomationId(modelApply,"AIProfileApply");
            var modelFeedback=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(modelFeedback,"AIProfileFeedback");
            var profileWarnings=new Dictionary<string,string>();
            var profileLabels=new Dictionary<string,string>();
            var profileCaps=new Dictionary<string,string>();
            bool savingProfile=false;
            string savedProfile="default";
            bool fetchingProfiles=false;
            void UpdateProfileWarning()
            {
                if(modelChoice.SelectedItem is not ComboBoxItem selected || selected.Tag is not string id) {
                    modelCaps.Text="";
                    modelApply.IsEnabled=false;return;
                }
                modelCaps.Text=profileCaps.GetValueOrDefault(id,"");
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
                    profileWarnings.Clear();profileLabels.Clear();profileCaps.Clear();modelChoice.Items.Clear();
                    foreach(var entry in data["profiles"]!.AsArray())
                    {
                        if(entry is null)continue;
                        var id=entry["id"]!.GetValue<string>();
                        var label=entry["label"]?.GetValue<string>() ?? id;
                        var valid=entry["valid"]?.GetValue<bool>()==true;
                        var ready=entry["ready"]?.GetValue<bool>()==true;
                        var caps=DescribeProfileCapabilities(entry["modalities"],entry["adapter"]?.GetValue<string>());
                        var item=new ComboBoxItem {Content=AppText.L($"{label}（{(ready ? "準備済み" : "未準備")}）",$"{label} ({(ready ? "Ready" : "Not ready")})"),Tag=id,IsEnabled=valid};
                        AutomationProperties.SetAutomationId(item,"AIProfile_"+id.Replace(':','_'));
                        profileLabels[id]=label;
                        profileCaps[id]=AppText.L($"対応：{caps} · {(ready ? "このPCでファイル確認済み" : "未準備")}",$"Supports: {caps} · {(ready ? "Verified on this PC" : "Not ready")}");
                        profileWarnings[id]=AppText.TranslateBackend(entry["warning"]?.GetValue<string>() ?? "");
                        modelChoice.Items.Add(item);
                        if(id==savedProfile)modelChoice.SelectedItem=item;
                    }
                    if(modelChoice.SelectedItem is null && modelChoice.Items.Count>0)modelChoice.SelectedIndex=0;
                    var active=data["active"]?.GetValue<string>() ?? "default";
                    var overridden=data["command_line_override"]?.GetValue<bool>()==true;
                    var restart=data["restart_required"]?.GetValue<bool>()==true;
                    var activeLabel=active=="command-line"?AppText.L("起動引数で指定したモデル","Model set by launch argument"):profileLabels.GetValueOrDefault(active,AppText.L("確認が必要","Needs attention"));
                    var selectedLabel=profileLabels.GetValueOrDefault(savedProfile,savedProfile);
                    modelFeedback.Text=AppText.L($"使用中: {activeLabel}\n設定: {selectedLabel}",$"Active: {activeLabel}\nConfigured: {selectedLabel}")
                        +(overridden?AppText.L("\n起動引数の指定が優先されています","\nOverridden by launch argument")
                            :restart?AppText.L("\n再起動後に切り替わります","\nTakes effect after restart")
                            :"")
                        +(data["error"]?.GetValue<string>() is string err && err.Length>0?"\n"+AppText.TranslateBackend(err):"");
                }
                catch(Exception ex) {modelFeedback.Text=AppText.L("モデル一覧を取得できません: ","Could not load model list: ")+AppText.TranslateBackend(ex.Message);}
                finally {fetchingProfiles=false;UpdateProfileWarning();}
                _ = StartRuntimeVerifyPollingAsync();
            }
            modelApply.Click+=async(_,_)=>{
                if(savingProfile || modelChoice.SelectedItem is not ComboBoxItem item || item.Tag is not string id)return;
                savingProfile=true;modelApply.IsEnabled=false;modelChoice.IsEnabled=false;
                try {
                    await api.PostAsync("api/library/ai/profile",new JsonObject{{"id",id}});
                    reload=true;
                    await RefreshProfiles();
                } catch(Exception ex) {modelFeedback.Text=AppText.L("設定を保存できません: ","Could not save settings: ")+AppText.TranslateBackend(ex.Message);}
                finally {savingProfile=false;modelChoice.IsEnabled=true;UpdateProfileWarning();}
            };
            var indexArt=VisualAssets.Sticker(72);
            var status=new TextBlock {TextWrapping=TextWrapping.Wrap};AutomationProperties.SetAutomationId(status,"AIStatus");
            var statusDetailText=new TextBlock {TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true,Style=(Style)Resources["MediaMetadataStyle"]};
            var statusDetailExpander=new Expander {Header=AppText.L("詳細情報","Details"),Content=statusDetailText,Visibility=Visibility.Collapsed,HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(statusDetailExpander,"AIIndexErrorDetails");
            var start=new Button {Content=AppText.L("AI検索データを作成","Build AI search index"),Style=(Style)Resources["AccentButtonStyle"],IsEnabled=false};AutomationProperties.SetAutomationId(start,"StartAIIndex");
            var cancel=new Button {Content=AppText.L("中止","Cancel"),IsEnabled=false};AutomationProperties.SetAutomationId(cancel,"CancelAIIndex");
            var resumeBooks=new Button{Content=AppText.L("前回の本の追加を再開","Resume previous book batch"),Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(resumeBooks,"ResumeBookBatch");
            PageBatchStatus? resumableBooks=null;
            var resumeChunks=new Button{Content=AppText.L("前回のページ追加を再開","Resume previous page batch"),Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(resumeChunks,"ResumeBookChunks");
            PageChunkStatus? resumableChunks=null;string? ownedPageJob=null;
            var resumeContinuation=new Button{Content=AppText.L("前回の続きから作成","Resume previous continuation"),Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(resumeContinuation,"ResumeAIContinuation");AutomationProperties.SetName(resumeContinuation,AppText.L("前回の続きから作成","Resume previous continuation"));
            IndexContinuationStatus? resumableContinuation=null;string? ownedContinuationJob=null;
            IndexContinuationPlan? continuationPlan=null;bool planningContinuation=false;string? activeProfile=null;
            var planContinuation=new Button{Content=AppText.L("未作成の対象を確認","Check unindexed items"),IsEnabled=false};AutomationProperties.SetAutomationId(planContinuation,"PlanAIContinuation");AutomationProperties.SetName(planContinuation,AppText.L("未作成の対象を確認","Check unindexed items"));
            var startContinuation=new Button{Content=AppText.L("続きから作成","Continue indexing"),Visibility=Visibility.Collapsed,IsEnabled=false};AutomationProperties.SetAutomationId(startContinuation,"StartAIContinuation");AutomationProperties.SetName(startContinuation,AppText.L("続きから作成","Continue indexing"));
            var continuationText=new TextBlock{TextWrapping=TextWrapping.Wrap,Visibility=Visibility.Collapsed};AutomationProperties.SetAutomationId(continuationText,"AIContinuationSummary");AutomationProperties.SetName(continuationText,AppText.L("未作成のAI検索データ計画状況","Unindexed items plan status"));
            void InvalidateContinuationPlan()
            {
                continuationPlan=null;
                continuationText.Text="";
                continuationText.Visibility=Visibility.Collapsed;
                startContinuation.Visibility=Visibility.Collapsed;
            }
            var release=new Button {Content=AppText.L("メモリを解放","Release memory"),IsEnabled=false};
            AutomationProperties.SetAutomationId(release,"AIRelease");
            var releaseResult=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(releaseResult,"AIReleaseResult");
            var modeChoice=new ComboBox {Header=AppText.L("索引作成の速度モード","Indexing speed mode"),HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(modeChoice,"AIIndexMode");
            AutomationProperties.SetName(modeChoice,AppText.L("AI索引作成時の速度とPC負荷のバランス","Balance between indexing speed and PC load"));
            var autoTuneSummary=new TextBlock {Text=AppText.L("初回索引時にGPU性能を自動計測し、最適なバッチサイズに調整します。","Automatically benchmarks your GPU on first batch indexing to tune batch size."),TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            AutomationProperties.SetAutomationId(autoTuneSummary,"AIAutoTuneSummary");
            var idleChoice=new ComboBox {Header=AppText.L("未使用時の自動解放","Auto-unload when idle"),HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(idleChoice,"AIIdleRelease");
            AutomationProperties.SetName(idleChoice,AppText.L("使っていないモデルをメモリから外すまでの時間","Delay before unloading unused models from memory"));
            var pauseChoice=new ComboBox {Header=AppText.L("作成中の休止（負荷軽減）","Pause between items (reduce load)"),HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(pauseChoice,"AIIndexPause");
            AutomationProperties.SetName(pauseChoice,AppText.L("1回のAI処理後に休む時間","Delay between AI indexing steps"));
            var saveResource=new Button {Content=AppText.L("保存","Save")};
            ToolTipService.SetToolTip(saveResource,AppText.L("保存後すぐ適用されます（GPU使用率やゲームFPSの上限は保証しません）","Applies right away after saving (does not cap GPU usage or game FPS)."));
            AutomationProperties.SetAutomationId(saveResource,"AISaveResource");
            var resourceResult=new TextBlock {TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(resourceResult,"AIResourceStatus");
            void AddOption(ComboBox control,int value,string label) {
                var option=new ComboBoxItem {Content=label,Tag=value};
                AutomationProperties.SetAutomationId(option,$"{AutomationProperties.GetAutomationId(control)}_{value}");
                control.Items.Add(option);
            }
            void AddStringOption(ComboBox control,string value,string label) {
                var option=new ComboBoxItem {Content=label,Tag=value};
                AutomationProperties.SetAutomationId(option,$"{AutomationProperties.GetAutomationId(control)}_{value}");
                control.Items.Add(option);
            }
            AddStringOption(modeChoice,"normal",AppText.L("普段使い（省負荷・バランス）","Everyday (balanced, lower load)"));
            AddStringOption(modeChoice,"turbo",AppText.L("ターボ（一括作成向け・最大速度）","Turbo (max throughput for bulk indexing)"));
            foreach(var seconds in new[]{0,60,300,900})
                AddOption(idleChoice,seconds,seconds==0?AppText.L("使わない","Off"):seconds<60?AppText.L($"{seconds}秒",$"{seconds}s"):AppText.L($"{seconds/60}分",$"{seconds/60}m"));
            foreach(var ms in new[]{0,50,200,500,1000})
                AddOption(pauseChoice,ms,ms==0?AppText.L("待機なし","None"):$"{ms}ms");
            void SelectOption(ComboBox box,int amount,string suffix) {
                var match=box.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Tag is int value && value==amount);
                if(match is null) {match=new ComboBoxItem {Content=AppText.L($"{amount}{suffix}（保存済み）",$"{amount}{suffix} (saved)"),Tag=amount};box.Items.Add(match);}
                box.SelectedItem=match;
            }
            void SelectStringOption(ComboBox box,string value) {
                var match=box.Items.OfType<ComboBoxItem>().FirstOrDefault(x=>x.Tag is string s && s==value);
                box.SelectedItem=match ?? box.Items.OfType<ComboBoxItem>().FirstOrDefault();
            }
            async Task RefreshResource()
            {
                try {
                    var policy=await api.GetAsync("api/library/ai/resource");
                    SelectStringOption(modeChoice,policy["policy"]?["index_mode"]?.GetValue<string>() ?? "normal");
                    SelectOption(idleChoice,policy["policy"]?["idle_release_seconds"]?.GetValue<int>() ?? 0,AppText.L("秒","s"));
                    SelectOption(pauseChoice,policy["policy"]?["index_pause_ms"]?.GetValue<int>() ?? 0,"ms");
                    resourceResult.Text=AppText.L("保存後すぐ適用されます","Applies right away after saving");
                } catch(Exception ex) {resourceResult.Text=AppText.L("設定を取得できません: ","Could not load settings: ")+AppText.TranslateBackend(ex.Message);}
            }
            saveResource.Click+=async (_,_)=>{
                if(idleChoice.SelectedItem is not ComboBoxItem idle || idle.Tag is not int idleValue ||
                   pauseChoice.SelectedItem is not ComboBoxItem pause || pause.Tag is not int pauseValue)return;
                var modeValue=(modeChoice.SelectedItem as ComboBoxItem)?.Tag as string ?? "normal";
                saveResource.IsEnabled=false;modeChoice.IsEnabled=false;idleChoice.IsEnabled=false;pauseChoice.IsEnabled=false;
                try {
                    await api.PostAsync("api/library/ai/resource",new JsonObject{{"idle_release_seconds",idleValue},{"index_pause_ms",pauseValue},{"index_mode",modeValue}});
                    resourceResult.Text=AppText.L("✓ 保存しました（次のバッチ／待機時間から有効）","✓ Saved (takes effect on next batch/idle step)");
                }catch(Exception ex){resourceResult.Text=AppText.L("保存できません: ","Could not save: ")+AppText.TranslateBackend(ex.Message);}
                finally{saveResource.IsEnabled=true;modeChoice.IsEnabled=true;idleChoice.IsEnabled=true;pauseChoice.IsEnabled=true;}
            };
            var scopePagesSummary=new TextBlock {TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            AutomationProperties.SetAutomationId(scopePagesSummary,"AIScopePagesSummary");
            var scopeUnsavedNotice=new TextBlock {TextWrapping=TextWrapping.Wrap,Visibility=Visibility.Collapsed,Style=(Style)Resources["MediaMetadataStyle"]};
            AutomationProperties.SetAutomationId(scopeUnsavedNotice,"AIScopeUnsavedNotice");
            void UpdateScopePagesSummary()=>scopePagesSummary.Text=AppText.L("CBZ・本の対象: ","CBZ & book pages: ")+(aiScope?["book_pages"]?.GetValue<string>()=="all_pages"?AppText.L("内部のすべての画像を含む","Include all inner pages"):AppText.L("表紙のみ","Covers only"));
            UpdateScopePagesSummary();
            using var scopeEditor=new AIScopeEditor(api,value=>{if(!JsonNode.DeepEquals(aiScope,value))reload=true;aiScope=value;aiScopeError=AppText.L("AI検索の対象範囲を選び直して保存してください。","Please re-select and save your AI search scope.");UpdateScopePagesSummary();});
            bool availableForIndex=false,indexRunning=false,starting=false;
            void UpdateStart()
            {
                start.IsEnabled=availableForIndex&&!indexRunning&&!starting&&!planningContinuation&&scopeEditor.Ready;
                planContinuation.IsEnabled=availableForIndex&&!indexRunning&&!starting&&!planningContinuation&&scopeEditor.Ready&&aiScope is not null;
                startContinuation.IsEnabled=availableForIndex&&!indexRunning&&!starting&&!planningContinuation&&continuationPlan?.CanStart==true&&continuationPlan?.Profile==activeProfile&&aiScope is not null;
                resumeBooks.IsEnabled=start.IsEnabled&&resumableBooks?.CanResume==true;
                resumeChunks.IsEnabled=start.IsEnabled&&resumableChunks?.CanResume==true&&aiScope is not null&&resumableChunks.MatchesScope(aiScope);
                resumeContinuation.IsEnabled=start.IsEnabled&&resumableContinuation?.CanResume==true&&aiScope is not null&&resumableContinuation.MatchesScope(aiScope);
                scopeUnsavedNotice.Visibility=scopeEditor.HasUnsavedChanges?Visibility.Visible:Visibility.Collapsed;
                if(scopeEditor.HasUnsavedChanges)
                {
                    scopeUnsavedNotice.Text=scopeEditor.JobBusy
                        ? AppText.L("⚠ 対象範囲に未保存の変更があります（AI作成中は保存できません）。","⚠ Unsaved scope changes (cannot save while AI indexing is running).")
                        : scopeEditor.CanSave
                        ? AppText.L("⚠ 対象範囲に未保存の変更があります。「AI検索の対象範囲」内の「保存」を押してください。","⚠ Unsaved scope changes. Click Save inside \"AI Search Scope\".")
                        : AppText.L("⚠ 対象範囲に未保存の変更があります。「件数を確認」のあと「保存」を押してください。","⚠ Unsaved scope changes. Click Check Counts, then Save.");
                }
            }
            scopeEditor.ScopeEdited+=InvalidateContinuationPlan;
            scopeEditor.StateChanged+=UpdateStart;
            bool polling=false;
            bool releasing=false;
            release.Click+=async (_,_)=>{
                releasing=true;release.IsEnabled=false;
                try {
                    var result=await api.PostAsync("api/library/ai/release",new JsonObject());
                    releaseResult.Text=result["released"]?.GetValue<bool>()==true?AppText.L("解放しました。次の検索でモデルを準備します。","Released. The model will load again on the next search."):AppText.L("AIは既にメモリから解放されています。","AI is already unloaded from memory.");
                }catch(Exception ex){releaseResult.Text=AppText.L("解放できません: ","Could not release: ")+AppText.TranslateBackend(ex.Message);}
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
                    VisualAssets.State(indexArt,running?"indexing":state=="complete"?"completed":state=="failed"?"error":null);
                    var label=state switch {"idle"=>AppText.L("未作成","Not built"),"running"=>AppText.L("作成中","Building"),"cancelling"=>AppText.L("中断待ち","Canceling"),"complete"=>AppText.L("準備完了","Ready"),"cancelled"=>AppText.L("中断済み","Canceled"),"interrupted"=>AppText.L("前回中断","Interrupted"),"failed"=>AppText.L("失敗","Failed"),"partial"=>AppText.L("一部完了","Partial"),_=>state};
                    var model=data["model"]?.GetValue<string>() ?? AppText.L("未選択","None selected");
                    var capabilities=DescribeProfileCapabilities(data["modalities"],data["adapter"]?.GetValue<string>());
                    var errorText=AppText.TranslateBackend(data["error"]?.GetValue<string>() ?? "");
                    if(available)
                    {
                        var unit=data["job"]?.GetValue<string>() is "book-pages" or "book-page-batch" or "book-pages-chunked"?AppText.L("ページ","pages"):AppText.L("件","items");
                        status.Text=AppText.L($"{model}（対応：{capabilities}）\n作成状況: {label} · {data["processed"]}/{data["total"]} {unit}{(string.IsNullOrEmpty(errorText)?"":$"\n{errorText}")}",
                            $"{model} ({capabilities})\nStatus: {label} · {data["processed"]}/{data["total"]} {unit}{(string.IsNullOrEmpty(errorText)?"":$"\n{errorText}")}");
                        statusDetailText.Text="";statusDetailExpander.Visibility=Visibility.Collapsed;
                    }
                    else
                    {
                        var statusCode=data["status_code"]?.GetValue<string>() ?? "";
                        status.Text=statusCode.Contains("runtime")||errorText.Contains("Python")||errorText.Contains("ライブラリ")||errorText.Contains("library",StringComparison.OrdinalIgnoreCase)
                            ?AppText.L("① AI実行環境：未導入（上の「手元のファイルを使う」または自動セットアップを用意）","① AI runtime: Not installed (use \"Use local files\" above or AI Auto-Setup)")
                            :statusCode.Contains("model")||statusCode.Contains("missing")||string.IsNullOrEmpty(data["model_id"]?.GetValue<string>())
                                ?AppText.L("② 検索モデル：未導入（ダウンロードまたは手元のファイルを用意）","② Search model: Not installed (download or choose local files)")
                            :statusCode.Contains("profile")||statusCode.Contains("revision")||statusCode.Contains("invalid")
                                ?AppText.L("② 検索モデル：要確認（モデル設定または診断情報を確認）","② Search model: Needs attention (check model settings or Diagnostics)")
                                :AppText.L("状態を確認できません（診断情報を確認してください）","Could not check status (review Diagnostics)");
                        statusDetailText.Text=errorText;
                        statusDetailExpander.Visibility=string.IsNullOrEmpty(errorText)?Visibility.Collapsed:Visibility.Visible;
                    }
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
                                if(aiScope is null||!cont.MatchesScope(aiScope))status.Text+=AppText.L("\n前回と同じ対象範囲を保存すると再開できます。","\nSave the same search scope as before to resume.");
                            }
                        }
                        catch(System.IO.InvalidDataException){status.Text+=AppText.L("\n前回の継続索引の情報を復元できません。未準備分を計画し直してください。","\nCould not restore continuation state. Re-plan unindexed items.");}
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
                                if(aiScope is null||!chunk.MatchesScope(aiScope))status.Text+=AppText.L("\n前回と同じ対象範囲を保存すると再開できます。","\nSave the same search scope as before to resume.");
                            }
                        }
                        catch(System.IO.InvalidDataException){status.Text+=AppText.L("\n前回の選択情報を復元できません。本の追加範囲を開き直してください。","\nCould not restore previous selection. Reopen the book page selector.");}
                    }
                    if(data["job"]?.GetValue<string>()=="book-page-batch")
                    {
                        var batch=PageBatchStatus.Parse(System.Text.Encoding.UTF8.GetBytes(data.ToJsonString()),data["profile"]!.GetValue<string>());
                        status.Text+="\n"+batch.Summary;
                        if(batch.CanResume){resumableBooks=batch;resumeBooks.Visibility=Visibility.Visible;}
                    }
                    availableForIndex=available;indexRunning=running;scopeEditor.SetJobBusy(running);UpdateStart();cancel.IsEnabled=running;
                    UpdateScopePagesSummary();
                    var resident=data["resident"]?.GetValue<bool>()==true;
                    release.IsEnabled=available&&!running&&resident&&!releasing;
                    if(available)status.Text+=(resident?AppText.L("\nAIはメモリ内で待機中。","\nAI is loaded and ready in memory."):AppText.L("\nAIは待機中・次の検索でモデルを準備します。","\nAI is idle; model loads on next search."));
                    if(data["telemetry"]?["auto_tune"] is JsonObject tuned)
                    {
                        var imgBs=tuned["tuned_image_batch"]?.GetValue<int>() ?? 0;
                        var txtBs=tuned["tuned_text_batch"]?.GetValue<int>() ?? 0;
                        var ips=tuned["tuned_images_per_sec"]?.GetValue<double>() ?? 0.0;
                        var tunedDev=(tuned["device"]?.GetValue<string>() ?? "cpu").ToUpperInvariant();
                        if(imgBs>0)
                        {
                            autoTuneSummary.Text=AppText.L(
                                $"自動調整済み: 画像バッチ {imgBs}・テキスト {txtBs}"+(ips>0?$"（約 {ips:F1} 枚/秒・{tunedDev}）":$"（{tunedDev}）"),
                                $"Auto-tuned: image batch {imgBs}, text {txtBs}"+(ips>0?$" (~{ips:F1} img/s · {tunedDev})":$" ({tunedDev})"));
                        }
                    }
                    ApplyRuntimeVerificationSnapshot(data);
                }
                catch(Exception ex){availableForIndex=false;resumableChunks=null;resumableContinuation=null;ownedPageJob=null;ownedContinuationJob=null;status.Text=AppText.TranslateBackend(ex.Message);start.IsEnabled=resumeChunks.IsEnabled=resumeContinuation.IsEnabled=planContinuation.IsEnabled=startContinuation.IsEnabled=cancel.IsEnabled=false;}
                finally{polling=false;}
            }
            start.Click+=async(_,_)=>{
                if(!start.IsEnabled||aiScope is null)return;
                starting=true;UpdateStart();
                try{await api.PostAsync("api/library/ai/index",AIScopeRequests.Scoped(aiScope));reload=true;await Refresh();}
                catch(Exception ex){status.Text=AppText.TranslateBackend(ex.Message);}
                finally{starting=false;UpdateStart();}
            };
            planContinuation.Click+=async(_,_)=>{
                if(!planContinuation.IsEnabled||aiScope is null||activeProfile is null)return;
                planningContinuation=true;UpdateStart();
                try
                {
                    var plan=await api.Continuation.PlanAsync(aiScope,activeProfile);
                    continuationPlan=plan;
                    continuationText.Text=plan.DetailSummary+(plan.CanStart?"\n"+plan.Summary:AppText.L("\n追加する未準備アイテムはありません。","\nNo remaining unindexed items."));
                    continuationText.Visibility=Visibility.Visible;
                    if(plan.CanStart)
                    {
                        startContinuation.Content=AppText.L($"続きから作成（残り {plan.SelectedTotal:N0}件）",$"Continue indexing ({plan.SelectedTotal:N0} left)");
                        startContinuation.Visibility=Visibility.Visible;
                    }
                    else
                    {
                        startContinuation.Visibility=Visibility.Collapsed;
                    }
                }
                catch(Exception ex){continuationText.Text=AppText.L("計画を作成できません: ","Could not build plan: ")+AppText.TranslateBackend(ex.Message);continuationText.Visibility=Visibility.Visible;InvalidateContinuationPlan();}
                finally{planningContinuation=false;UpdateStart();}
            };
            startContinuation.Click+=async(_,_)=>{
                if(!startContinuation.IsEnabled||continuationPlan is null||aiScope is null)return;
                starting=true;UpdateStart();
                try
                {
                    var started=await api.Continuation.StartAsync(continuationPlan);
                    reload=true;
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
                try{await api.PageEvidences.ResumeBatchAsync(resumableBooks.JobId,aiScope,resumableBooks.Profile);reload=true;await Refresh();}
                catch(Exception ex){status.Text=ex.Message;}
                finally{starting=false;UpdateStart();}
            };
            resumeChunks.Click+=async(_,_)=>{
                if(!resumeChunks.IsEnabled||resumableChunks is null||aiScope is null)return;
                starting=true;UpdateStart();
                try{await api.PageEvidences.ResumeChunksAsync(resumableChunks,aiScope);reload=true;await Refresh();}
                catch(Exception ex){status.Text=ex.Message;}
                finally{starting=false;UpdateStart();}
            };
            resumeContinuation.Click+=async(_,_)=>{
                if(!resumeContinuation.IsEnabled||resumableContinuation is null||aiScope is null)return;
                starting=true;UpdateStart();
                try
                {
                    var resumed=await api.Continuation.ResumeAsync(resumableContinuation,aiScope);
                    reload=true;
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
                    reload=true;
                    await Refresh();
                }
                catch(Exception ex){status.Text=ex.Message;}
                finally{UpdateStart();}};
            timer.Tick+=async(_,_)=>await Refresh();
            var panel=new StackPanel {Spacing=12,MinWidth=320};
            using var audioPreparation=new AudioPreparationPanel(api.AudioContent,AudioIndexConditions);
            using var videoPreparation=new VideoPreparationPanel(api.VideoContent,AudioIndexConditions);
            using var videoAudioPreparation=new AudioPreparationPanel(api.VideoAudioContent,AudioIndexConditions);
            Border MakeCard(string heading,params UIElement[] items)
            {
                var cardStack=new StackPanel{Spacing=8};
                cardStack.Children.Add(new TextBlock{Text=heading,Style=(Style)Application.Current.Resources["BodyStrongTextBlockStyle"]});
                foreach(var item in items)cardStack.Children.Add(item);
                return new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=cardStack};
            }
            var modelCard=MakeCard(AppText.L("モデルとセットアップ","Models & Setup"),setupActions,explanation,modelChoice,modelCaps,modelWarning,modelApply,modelFeedback);
            var scopeCard=MakeCard(AppText.L("AI検索の対象範囲","AI Search Scope"),scopeEditor.Content);
            var mediaCard=MakeCard(AppText.L("動画・音声の個別データ作成","Video & Audio Indexing"),audioPreparation.Content,videoPreparation.Content,videoAudioPreparation.Content);
            var resourceCard=MakeCard(AppText.L("メモリと負荷","Memory & Resource Limits"),release,releaseResult,modeChoice,autoTuneSummary,idleChoice,pauseChoice,saveResource,resourceResult);
            panel.Children.Add(modelCard);
            panel.Children.Add(scopeCard);
            panel.Children.Add(mediaCard);
            panel.Children.Add(resourceCard);
            var content=new Grid {RowSpacing=12,MaxHeight=Math.Max(160,ActualHeight-240)};
            AutomationProperties.SetAutomationId(content,"AISettingsLayout");
            void SyncDialogWidth(){content.Width=Math.Clamp((XamlRoot?.Size.Width??1200)-112,460,620);}
            SyncDialogWidth();
            capturedRoot=XamlRoot;
            if(capturedRoot is not null)
            {
                rootChanged=(_,_)=>SyncDialogWidth();
                capturedRoot.Changed+=rootChanged;
            }
            content.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
            content.RowDefinitions.Add(new RowDefinition {Height=new GridLength(1,GridUnitType.Star)});
            content.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
            var navBar=new StackPanel {Orientation=Orientation.Horizontal,Spacing=6};
            Button MakeSectionButton(string label,string autoId,Border targetCard,bool expandScope=false,bool expandMedia=false)
            {
                var btn=new Button {Content=label,Padding=new Thickness(10,4,10,4)};
                AutomationProperties.SetAutomationId(btn,autoId);
                btn.Click+=(_,_)=>{
                    if(expandScope)
                    {
                        scopeEditor.Content.IsExpanded=true;
                    }
                    if(expandMedia)
                    {
                        audioPreparation.Content.IsExpanded=true;
                        videoPreparation.Content.IsExpanded=true;
                        videoAudioPreparation.Content.IsExpanded=true;
                    }
                    targetCard.StartBringIntoView();
                };
                return btn;
            }
            navBar.Children.Add(MakeSectionButton(AppText.L("モデル","Models"),"AISecModel",modelCard));
            navBar.Children.Add(MakeSectionButton(AppText.L("対象範囲","Scope"),"AISecScope",scopeCard,expandScope:true));
            navBar.Children.Add(MakeSectionButton(AppText.L("動画・音声","Video/Audio"),"AISecMedia",mediaCard,expandMedia:true));
            navBar.Children.Add(MakeSectionButton(AppText.L("メモリ・負荷","Memory/Load"),"AISecResource",resourceCard));
            content.Children.Add(navBar);
            var modelOptions=new ScrollViewer {Content=FormScrollContent.Wrap(panel),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            AutomationProperties.SetAutomationId(modelOptions,"AIOptions");
            AutomationProperties.SetName(modelOptions,AppText.L("モデル・AIリソース設定","Model & AI Resource Settings"));
            Grid.SetRow(modelOptions,1);content.Children.Add(modelOptions);
            var indexActions=new StackPanel {Orientation=Orientation.Horizontal,Spacing=8};
            indexActions.Children.Add(start);indexActions.Children.Add(cancel);indexActions.Children.Add(planContinuation);indexActions.Children.Add(startContinuation);
            var indexInfo=new StackPanel {Spacing=8};
            AutomationProperties.SetAutomationId(indexInfo,"AIIndexSummary");
            indexInfo.Children.Add(new TextBlock {Text=AppText.L("AI検索データ","AI Search Index"),Style=(Style)Application.Current.Resources["SubtitleTextBlockStyle"]});
            indexInfo.Children.Add(status);
            indexInfo.Children.Add(scopePagesSummary);
            indexInfo.Children.Add(scopeUnsavedNotice);
            indexInfo.Children.Add(statusDetailExpander);
            indexInfo.Children.Add(continuationText);
            indexInfo.Children.Add(indexActions);
            indexInfo.Children.Add(resumeContinuation);
            indexInfo.Children.Add(resumeBooks);
            indexInfo.Children.Add(resumeChunks);
            var indexRow=new Grid{ColumnSpacing=12};
            indexRow.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            indexRow.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            Grid.SetColumn(indexInfo,1);
            indexRow.Children.Add(indexArt);
            indexRow.Children.Add(indexInfo);
            var indexCard=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=indexRow};
            Grid.SetRow(indexCard,2);content.Children.Add(indexCard);
            await RefreshProfiles();await RefreshResource();await Refresh();UpdateScopePagesSummary();timer.Start();
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=AppText.L("AI検索を設定","Configure AI Search"),Content=content,CloseButtonText=AppText.L("閉じる","Close")};
            dialog.Resources["ContentDialogMaxWidth"]=680d;
            AutomationProperties.SetAutomationId(dialog,"AISettingsDialog");
            dialog.Opened+=(_,_)=>{
                if(initialSection=="media")
                {
                    audioPreparation.Content.IsExpanded=true;
                    videoPreparation.Content.IsExpanded=true;
                    videoAudioPreparation.Content.IsExpanded=true;
                    DispatcherQueue.TryEnqueue(()=>mediaCard.StartBringIntoView());
                }
            };
            environmentButton.Click+=(_,_)=>{if(scopeEditor.Saving)return;openEnvironment=true;dialog.Hide();};
            downloadButton.Click+=(_,_)=>{if(scopeEditor.Saving)return;openDownload=true;dialog.Hide();};
            dialog.Closing+=(_,args)=>{if(scopeEditor.Saving)args.Cancel=true;};
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            if(capturedRoot is not null&&rootChanged is not null)capturedRoot.Changed-=rootChanged;
            timer.Stop();dialogOpen=false;
            try
            {
                if(reload&&!disposed)
                {
                    if(settingsHubOpen||folderHubOpen)
                    {
                        if(SearchMethod.FromIndex(lastMode).IsAI||similarityOrigin is not null)resultsNeedRefresh=true;
                        if(folderHubOpen)_ = RefreshFolderAIStatusAsync(fetchCoverage:true,force:true);
                    }
                    else if(SearchMethod.FromIndex(lastMode).IsAI||similarityOrigin is not null)
                    {
                        await LoadAsync();
                    }
                }
            }
            finally{transitions.Release();}
        }
        if(openDownload&&!disposed)await OpenAIDownloadDialogAsync();
        else if(openEnvironment&&!disposed)await OpenAIEnvironmentDialogAsync();
    }

    public Task FlushReaderProgressAsync()=>readerView?.FlushProgressAsync()??Task.CompletedTask;
    public async Task FlushViewerStateAsync()
    {
        if(readerView is {} activeReader)await activeReader.FlushProgressAsync();
        if(imageViewer is {} activeImage)await activeImage.FlushFavoriteAsync();
        if(videoPlayer is {} activeVideo)await activeVideo.FlushFavoriteAsync();
    }
    public void Stop(){if(disposed)return;disposed=true;bulkTagGenerationCts?.Cancel();settingsAiPollTimer?.Stop();folderAiPollTimer?.Stop();folderAiLoadLifetime?.Cancel();folderAiLoadLifetime?.Dispose();folderAiLoadLifetime=null;settingsLoadLifetime?.Cancel();settingsLoadLifetime?.Dispose();settingsLoadLifetime=null;runtimeVerifyLifetime.Cancel();runtimeVerifyLifetime.Dispose();selectionPreparation?.Cancel();startupUpdateTimer?.Stop();runtimeVerifyTimer.Stop();folderFilterTimer.Stop();resultKeepAliveTimer?.Stop();ResetFastScroll();thumbnails.ResetSession();DetachXamlRoot();itemSizeTimer.Stop();CloseShelfHubCore();if(resultScroll is not null)resultScroll.ViewChanged-=ResultScroll_Changed;smoothWheelScroller.Detach();resultWindow?.Dispose();resultWindow=null;SaveItemSize();tagReview?.Dispose();scanPollTimer.Stop();viewerWindow?.ForceCloseFromOwner();viewerWindow=null;similarityCancellation?.Cancel();renderCancellation.Cancel();foreach(var item in realizedItems.ToArray())ReleaseContainer(item,detachVisualTree:true);detailCancellation?.Cancel();readerView?.Dispose();imageViewer?.Dispose();videoPlayer?.Dispose();searches.Next();searchTimer.Stop();var session=resultSession;resultSession=null;if(session is null)api.Dispose();else _=CloseResultsAndApiAsync(session);}
}

