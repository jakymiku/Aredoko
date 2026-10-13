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
    private CancellationTokenSource renderCancellation = new();
    private CancellationTokenSource? detailCancellation;
    private ArchiveReaderView? readerView;
    private List<MediaRow> rows=[];
    private MediaRow? active;
    private EditorState saved;
    private bool ready, populating, saving, dialogOpen, tiles, disposed;
    private int page, lastKind, lastMode;
    private JsonObject? aiScope;
    private string aiScopeError="AI索引の画面で対象を確認・保存してください。";
    private string view="all", lastQuery="";

    public MainPage() {
        InitializeComponent();
        UpdateSearchMethod();
        thumbnails = new ThumbnailService(api);
        searchTimer=DispatcherQueue.CreateTimer(); searchTimer.Interval=TimeSpan.FromMilliseconds(300);
        searchTimer.Tick+=async (_,_)=>{searchTimer.Stop(); if(PendingSearch) await NavigateAsync(0);};
    }
    private bool PendingSearch => Query.Text!=lastQuery||Kind.SelectedIndex!=lastKind||SearchMode.SelectedIndex!=lastMode;
    private EditorState Current()=>new(Tags.Text,Shelf.Text,Favorite.IsChecked==true,Reviewed.IsChecked==true);
    private bool Dirty=>active is not null && EditorState.IsDirty(saved,Current());
    private void Notice(string title,string message="",InfoBarSeverity severity=InfoBarSeverity.Informational) {
        Status.Title=title; Status.Message=message; Status.Severity=severity;
    }
    private void Failure(Exception ex) {
        Notice("操作を完了できません",ex.Message,InfoBarSeverity.Error);
        AppLog.Error(ex);
    }
    private async void Page_Loaded(object sender,RoutedEventArgs e) {
        if(ready)return; ready=true;
        await ConnectAsync();
    }
    private async Task ConnectAsync() {
        try { renderCancellation.Cancel(); thumbnails.Clear(); await api.ConnectAsync(); await LoadAIScopeAsync(); await LoadAsync(); }
        catch(Exception ex) { Notice("バックエンドに接続できません", "start-winui.ps1を起動して再接続してください。"+ex.Message,InfoBarSeverity.Error); }
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
    private async Task LoadAsync() {
        var version=searches.Next(); Busy.Visibility=Visibility.Visible;
        // Do not allow editing an old record while a different result is loading.
        Editor.IsEnabled=false; Items.IsEnabled=false;
        var query=Query.Text; var kind=KindValue();var selectedKind=Kind.SelectedIndex;var selectedMode=SearchMode.SelectedIndex;
        try {
            var method=SearchMethod.FromIndex(selectedMode);
            if(selectedMode>0&&!string.IsNullOrWhiteSpace(query)&&aiScope is null)throw new InvalidOperationException(aiScopeError);
            var result=await api.SearchAsync(query,kind,view,page,method.IsAI,method.Source,aiScope);
            if(!searches.IsCurrent(version)||disposed)return;
            if(result.Items.Count==0 && page>0){page=Math.Max(0,(result.Total-1)/60);await LoadAsync();return;}
            lastQuery=query; lastKind=selectedKind;lastMode=selectedMode;
            rows=result.Items; active=null; Details.IsPaneOpen=false; DetailsButton.IsEnabled=false;detailCancellation?.Cancel(); DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed; Tags.Text="";Shelf.Text="";Favorite.IsChecked=false;Reviewed.IsChecked=false;RenderRows();
            ItemTitle.Text="作品を選んでください"; ItemPath.Text=""; EditStatus.Text="";
            Count.Text=$"{result.Total:N0} 件"; PageNumber.Text=$"{page+1} / {Math.Max(1,(result.Total+59)/60)}";
            Previous.IsEnabled=page>0; Next.IsEnabled=(page+1)*60<result.Total;
            Empty.Visibility=rows.Count==0?Visibility.Visible:Visibility.Collapsed;
            Empty.Text=query.Length>0?"候補がありません。検索条件やAI索引の状態を確認してください。":"フォルダ管理からフォルダを登録し、スキャンしてください。";
            Notice("読込完了",selectedMode>0 && query.Length>0 ? $"AI検索の候補です。{(result.CoverageLimit is int coverage ? $"最大{coverage:N0}件の対象から、" : "")}索引済みの作品を類似順に表示します。" : selectedMode>0 ? "探したい内容を文章で入力してください。AI索引の作成は「AI索引」から。" : "名前・タグの文字検索。"+Protocol.DescribePartial(result.PartialWords)+Protocol.DescribeExpansions(result.Expansions));
        } catch(Exception ex) { if(searches.IsCurrent(version)){lastQuery=query;lastKind=selectedKind;lastMode=selectedMode;rows=[];active=null;Details.IsPaneOpen=false;DetailsButton.IsEnabled=false;detailCancellation?.Cancel();DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed;ItemTitle.Text="作品を選んでください";ItemPath.Text="";Tags.Text="";Shelf.Text="";Favorite.IsChecked=false;Reviewed.IsChecked=false;EditStatus.Text="";RenderRows();Empty.Visibility=Visibility.Visible;Count.Text="—";PageNumber.Text="—";Previous.IsEnabled=false;Next.IsEnabled=false;Empty.Text=selectedMode>0?"この条件ではAI検索を利用できません。\n名前・タグ検索に切り替えるか、AI索引の設定を確認してください。":"検索を完了できませんでした。再接続からやり直してください。";Failure(ex);} }
        finally {if(searches.IsCurrent(version)){Busy.Visibility=Visibility.Collapsed;Items.IsEnabled=true;}}
    }
    private void RenderRows()
    {
        renderCancellation.Cancel(); renderCancellation.Dispose(); renderCancellation = new();
        populating = true;
        try
        {
            Items.Items.Clear();
            Items.ItemsPanel = (ItemsPanelTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load(tiles
                ? "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsWrapGrid Orientation=\"Horizontal\"/></ItemsPanelTemplate>"
                : "<ItemsPanelTemplate xmlns=\"http://schemas.microsoft.com/winfx/2006/xaml/presentation\"><ItemsStackPanel/></ItemsPanelTemplate>");
            foreach (var row in rows)
            {
                var content = new Grid { Padding = new Thickness(8), ColumnSpacing = 12, RowSpacing = 8 };
                var image = new Image { Width = tiles ? 200 : 48, Height = tiles ? 144 : 64, Stretch = Stretch.Uniform };
                AutomationProperties.SetAutomationId(image, $"Preview{row.Id}");
                AutomationProperties.SetName(image, row.Title + "のサムネイル");
                var text = new StackPanel { Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
                text.Children.Add(new TextBlock { Text = (row.Favorite ? "★ " : "") + row.Title, TextTrimming = TextTrimming.CharacterEllipsis, Style = (Style)Resources["MediaTitleStyle"] });
                text.Children.Add(new TextBlock { Text = $"{KindLabel(row.Kind)} · {AvailabilityLabel(row.Availability)} · {string.Join("、", row.Tags)}", TextTrimming = TextTrimming.CharacterEllipsis, Style = (Style)Resources["MediaMetadataStyle"] });
                var previewStatus = new TextBlock { Text = row.Availability == "present" && row.Kind is "image" or "book" or "archive" ? "読込中" : "プレビューなし", Style = (Style)Resources["MediaMetadataStyle"] };
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
                var item = new ListViewItem { Content = content, Width = tiles ? 232 : double.NaN, HorizontalContentAlignment = HorizontalAlignment.Stretch };
                AutomationProperties.SetAutomationId(item, $"Item{row.Id}"); AutomationProperties.SetName(item, row.Title);
                var renderToken = renderCancellation.Token;
                CancellationTokenSource? visible = null;
                item.Loaded += async (_, _) =>
                {
                    visible?.Cancel(); visible?.Dispose(); visible = CancellationTokenSource.CreateLinkedTokenSource(renderToken);
                    var cancellation = visible.Token;
                    try
                    {
                        var bitmap = await thumbnails.GetAsync(row, cancellation);
                        if (cancellation.IsCancellationRequested || disposed) return;
                        image.Source = bitmap;
                        previewStatus.Text = bitmap is null ? "プレビューなし" : row.Kind == "image" ? "画像プレビュー" : "先頭画像";
                    }
                    catch (OperationCanceledException) { }
                };
                item.Unloaded += (_, _) => { visible?.Cancel();visible?.Dispose();visible=null;image.Source = null; };
                Items.Items.Add(item);
            }
        }
        finally { populating = false; }
    }
    private static string KindLabel(string kind) => kind switch { "book" => "本", "image" => "画像", "archive" => "ZIP", "video" => "動画", "audio" => "音楽", _ => "素材" };
    private static string AvailabilityLabel(string state) => state switch { "present" => "登録済み", "missing" => "ファイル不明", _ => state };
    private async Task ShowDetailPreviewAsync(MediaRow row)
    {
        detailCancellation?.Cancel(); detailCancellation?.Dispose();
        detailCancellation = new CancellationTokenSource(); var cancellation = detailCancellation.Token;
        DetailPreview.Source = null; DetailPreview.Visibility = Visibility.Collapsed;
        try
        {
            var image = await thumbnails.GetAsync(row, cancellation);
            if (cancellation.IsCancellationRequested || active?.Id != row.Id || disposed) return;
            DetailPreview.Source = image; DetailPreview.Visibility = image is null ? Visibility.Collapsed : Visibility.Visible;
        }
        catch (OperationCanceledException) { }
    }
    private async Task NavigateAsync(int nextPage) {
        if(!ready||saving||!await transitions.WaitAsync(0))return;
        try {
            if(!await ConfirmDiscardAsync()){populating=true;Query.Text=lastQuery;Kind.SelectedIndex=lastKind;SearchMode.SelectedIndex=lastMode;populating=false;return;}
            page=nextPage;await LoadAsync();
        }finally{transitions.Release();if((PendingSearch)&&!disposed){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void Items_Changed(object sender,SelectionChangedEventArgs e) {
        if(populating||!ready)return;
        var index=Items.SelectedIndex;
        if(index<0||index>=rows.Count)return;
        if(saving||!await transitions.WaitAsync(0)){RestoreSelection();return;}
        try {
            if(!await ConfirmDiscardAsync()){RestoreSelection();return;}
            active=rows[index]; saved=new(string.Join(", ",active.Tags),active.Shelf,active.Favorite,active.Reviewed);
            Tags.Text=saved.Tags;Shelf.Text=saved.Shelf;Favorite.IsChecked=saved.Favorite;Reviewed.IsChecked=saved.Reviewed;
            ItemTitle.Text=active.Title;ItemPath.Text=active.Location;Editor.IsEnabled=true;DetailsButton.IsEnabled=true;Details.IsPaneOpen=true;
            UpdateDirty();
            _ = ShowDetailPreviewAsync(active);
        }finally{transitions.Release();}
    }
    private void RestoreSelection(){populating=true;Items.SelectedIndex=active is null?-1:rows.FindIndex(r=>r.Id==active.Id);populating=false;}
    private void UpdateDirty(){if(!ready)return;EditStatus.Text=Dirty?"未保存の変更":"保存済み";Save.IsEnabled=active is not null&&Dirty&&!saving;OpenBook.IsEnabled=active is not null&&ArchiveManifest.CanOpen(active);}
    private void Editor_Changed(object sender,TextChangedEventArgs e)=>UpdateDirty();
    private void Editor_Checked(object sender,RoutedEventArgs e)=>UpdateDirty();
    public async Task<bool> ConfirmDiscardAsync() {
        if(saving||dialogOpen)return false;
        if(!Dirty)return true;
        dialogOpen=true;
        try {
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="変更を破棄しますか？",Content=active?.Title,PrimaryButtonText="変更を破棄",CloseButtonText="編集を続ける",DefaultButton=ContentDialogButton.Close};
            return await dialog.ShowAsync()==ContentDialogResult.Primary;
        }finally{dialogOpen=false;}
    }
    private async Task SaveAsync() {
        if(active is null||saving||dialogOpen||!Dirty)return;
        var snapshot=Current();var error=snapshot.Validate();
        if(error is not null){EditStatus.Text=error;return;}
        // Disabling the editor moves WinUI focus elsewhere. Restore only an
        // editor control, and only if the user has not chosen another control
        // while the request was pending. Never take focus from another window.
        var focused=FocusManager.GetFocusedElement(XamlRoot) as Control;
        var restore=focused==Tags||focused==Shelf||focused==Favorite||focused==Reviewed||focused==Save;
        var focusState=focused?.FocusState==FocusState.Keyboard?FocusState.Keyboard:FocusState.Programmatic;
        saving=true;Editor.IsEnabled=false;var id=active.Id;
        var displacedFocus=FocusManager.GetFocusedElement(XamlRoot);
        try {
            await api.SaveAsync(id,snapshot);
            saved=snapshot;active.Tags=snapshot.ParsedTags;active.Shelf=snapshot.Shelf;active.Favorite=snapshot.Favorite;active.Reviewed=snapshot.Reviewed;
            RenderRows();RestoreSelection();EditStatus.Text="保存しました";Notice("保存しました");
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
    private void SearchShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){e.Handled=true;Query.Focus(FocusState.Keyboard);}
    private void Query_Changed(object sender,TextChangedEventArgs e){if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private async void Search_Click(object sender,RoutedEventArgs e){searchTimer.Stop();await NavigateAsync(0);}
    private void UpdateSearchMethod()
    {
        // SelectionChanged also runs during initialization and dirty-state rollback.
        if(Query is null || SearchMethodHint is null)return;
        var ai=SearchMode.SelectedIndex>0;
        AutomationProperties.SetName(Query,ai?"AI検索の文章":"名前・タグ検索");
        Query.PlaceholderText=ai?"探したい内容を文章で入力":"名前・タグを検索（Ctrl+F）";
        SearchMethodHint.Text=SearchMode.SelectedIndex switch
        {
            1=>"名前・タグと画像・表紙を組み合わせて探します。",
            2=>"色・形・見た目を文章で指定し、画像・表紙から探します。",
            3=>"名前・タグの意味から探します。本の本文や音声は読み取りません。",
            _=>"名前・タグに含まれる文字で探します。"
        };
    }
    private void SearchMode_Changed(object sender,SelectionChangedEventArgs e)
    {
        UpdateSearchMethod();
        if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}
    }
    private void Kind_Changed(object sender,SelectionChangedEventArgs e){if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private async void Previous_Click(object sender,RoutedEventArgs e)=>await NavigateAsync(Math.Max(0,page-1));
    private async void Next_Click(object sender,RoutedEventArgs e)=>await NavigateAsync(page+1);
    private void RestoreNavigation()
    {
        populating=true; Nav.SelectedItem=Nav.MenuItems.OfType<NavigationViewItem>().First(x=>x.Tag?.ToString()==view); populating=false;
    }
    private async void Nav_SelectionChanged(NavigationView sender,NavigationViewSelectionChangedEventArgs args)
    {
        if(!ready||populating||args.SelectedItem is not NavigationViewItem item)return;
        var next=item.Tag?.ToString()??"all";
        if(saving||dialogOpen||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            view=next;page=0;await LoadAsync();
        }
        finally { transitions.Release();if((PendingSearch)&&!disposed){searchTimer.Stop();searchTimer.Start();} }
    }
    private void Layout_Click(object sender,RoutedEventArgs e){tiles=!tiles;LayoutButton.Content=tiles?"リスト表示":"グリッド表示";RenderRows();RestoreSelection();}
    private void OpenDetails_Click(object sender,RoutedEventArgs e){if(active is not null)Details.IsPaneOpen=true;}
    private async void OpenBook_Click(object sender,RoutedEventArgs e)
    {
        if(active is null||!ArchiveManifest.CanOpen(active)||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        // Opening a book neither saves nor discards the current metadata draft.
        dialogOpen=true;searchTimer.Stop();
        var root=XamlRoot;
        void Fit(XamlRoot sender,XamlRootChangedEventArgs args)=>readerView?.FitViewport(sender.Size);
        try
        {
            var reader=new ArchiveReaderView(api,active.Id);readerView=reader;
            reader.FitViewport(root.Size);root.Changed+=Fit;
            var dialog=new ContentDialog {XamlRoot=root,RequestedTheme=ActualTheme,Title=active.Title,
                Content=reader,CloseButtonText="閉じる",DefaultButton=ContentDialogButton.Close};
            dialog.Resources["ContentDialogMaxWidth"]=960d;
            AutomationProperties.SetAutomationId(dialog,"ArchiveReaderDialog");
            dialog.Opened+=async(_,_)=>await reader.OpenAsync();
            dialog.Closing+=(_,_)=>reader.Dispose();
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            root.Changed-=Fit;readerView?.Dispose();readerView=null;dialogOpen=false;transitions.Release();
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
            if(!await ConfirmDiscardAsync())return;
            active=null;Details.IsPaneOpen=false;DetailsButton.IsEnabled=false;
            detailCancellation?.Cancel();DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed;
            Editor.IsEnabled=false;RestoreSelection();
            Items.Focus(FocusState.Keyboard);
        }
        finally{transitions.Release();}
    }
    private void Page_SizeChanged(object sender,SizeChangedEventArgs e)
    {
        if(Details is null || ViewTools is null)return;
        Details.DisplayMode=e.NewSize.Width<1000?SplitViewDisplayMode.Overlay:SplitViewDisplayMode.Inline;
        Details.OpenPaneLength=Math.Min(320,Math.Max(240,e.NewSize.Width-64));
        if(active is null)Details.IsPaneOpen=false;
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
    }

    private async void Roots_Click(object sender,RoutedEventArgs e) {
        if(dialogOpen||saving||!await transitions.WaitAsync(0))return;
        if(!await ConfirmDiscardAsync()){transitions.Release();return;}
        dialogOpen=true;
        var timer=DispatcherQueue.CreateTimer();timer.Interval=TimeSpan.FromSeconds(1);
        try {
            var panel=new StackPanel {Spacing=12,MinWidth=260};
            var list=new ComboBox {Header="登録フォルダ",HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(list,"RootList");
            var folder=new TextBox {Header="追加するフォルダ",PlaceholderText="選択するか、絶対パスを入力"};AutomationProperties.SetAutomationId(folder,"RootPath");
            var choose=new Button {Content="フォルダを選ぶ"};AutomationProperties.SetAutomationId(choose,"ChooseFolder");
            choose.Click+=async(_,_)=>{try{var picker=new FolderPicker();picker.FileTypeFilter.Add("*");WinRT.Interop.InitializeWithWindow.Initialize(picker,WinRT.Interop.WindowNative.GetWindowHandle(MainWindow.Current));var selected=await picker.PickSingleFolderAsync();if(selected is not null)folder.Text=selected.Path;}catch(Exception ex){Failure(ex);}};
            var exclusions=new TextBox {Header="除外（カンマ区切り、例: cache, *.tmp）"};AutomationProperties.SetAutomationId(exclusions,"RootExcludes");
            var consent=new CheckBox {Content="このフォルダの読み取り専用登録を許可"};AutomationProperties.SetAutomationId(consent,"RootConsent");
            var add=new Button {Content="登録"};AutomationProperties.SetAutomationId(add,"AddRoot");
            var scan=new Button {Content="選択フォルダをスキャン / 再開"};AutomationProperties.SetAutomationId(scan,"ScanRoot");
            var cancel=new Button {Content="スキャンをキャンセル"};AutomationProperties.SetAutomationId(cancel,"CancelScan");
            var rules=new Button {Content="選択フォルダの除外を更新"};AutomationProperties.SetAutomationId(rules,"SaveExcludes");
            var progress=new TextBlock {TextWrapping=TextWrapping.Wrap};AutomationProperties.SetAutomationId(progress,"ScanStatus");
            var rootPatterns = new Dictionary<int,string>();
            list.SelectionChanged+=(_,_)=>{if(list.SelectedItem is ComboBoxItem selected && rootPatterns.TryGetValue((int)selected.Tag,out var patterns))exclusions.Text=patterns;};
            async Task RefreshRoots(){var roots=await api.GetAsync("api/library/roots");list.Items.Clear();rootPatterns.Clear();foreach(var row in roots["items"]!.AsArray()){rootPatterns[row!["id"]!.GetValue<int>()]=string.Join(", ",row["excludes"]!.AsArray().Select(x=>x!.GetValue<string>()));list.Items.Add(new ComboBoxItem {Content=row!["path"]!.GetValue<string>()+(row["online"]!.GetValue<bool>()?"":"（未接続）"),Tag=row["id"]!.GetValue<int>()});}if(list.Items.Count>0)list.SelectedIndex=list.Items.Count-1;}
            JsonArray Patterns()=>new(exclusions.Text.Split(',',StringSplitOptions.RemoveEmptyEntries|StringSplitOptions.TrimEntries).Select(s=>(JsonNode?)JsonValue.Create(s)).ToArray());
            int RootId()=>list.SelectedItem is ComboBoxItem item?(int)item.Tag:throw new InvalidOperationException("登録フォルダを選んでください。");
            add.Click+=async(_,_)=>{add.IsEnabled=false;try{if(consent.IsChecked!=true)throw new InvalidOperationException("読み取り登録の許可にチェックしてください。");await api.PostAsync("api/library/roots",new JsonObject{{"path",folder.Text},{"consent",true},{"excludes",Patterns()}});await RefreshRoots();folder.Text="";consent.IsChecked=false;progress.Text="登録しました。スキャンすると一覧に反映されます。";}catch(Exception ex){progress.Text=ex.Message;}finally{add.IsEnabled=true;}};
            scan.Click+=async(_,_)=>{try{await api.PostAsync("api/library/scan",new JsonObject{{"root_id",RootId()}});progress.Text="スキャン開始";}catch(Exception ex){progress.Text=ex.Message;}};
            cancel.Click+=async(_,_)=>{try{await api.PostAsync("api/library/cancel",new JsonObject());progress.Text="キャンセル要求済み。前回の索引を保持します。";}catch(Exception ex){progress.Text=ex.Message;}};
            rules.Click+=async(_,_)=>{try{await api.PostAsync("api/library/excludes",new JsonObject{{"root_id",RootId()},{"patterns",Patterns()}});progress.Text="除外を更新。次回スキャンで反映します。";}catch(Exception ex){progress.Text=ex.Message;}};
            bool polling=false;
            timer.Tick+=async(_,_)=>{if(polling)return;polling=true;try{var state=await api.GetAsync("api/library/scan");var phase=state["state"]!.GetValue<string>();progress.Text=$"{phase} · {state["discovered"]} 件 {state["error"]}";scan.IsEnabled=phase!="running";rules.IsEnabled=phase!="running";add.IsEnabled=phase!="running";cancel.IsEnabled=phase=="running";}catch(Exception ex){progress.Text=ex.Message;}finally{polling=false;}};
            foreach(var element in new UIElement[]{list,folder,choose,exclusions,consent,add,rules,scan,cancel,progress})panel.Children.Add(element);
            await RefreshRoots();timer.Start();
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="フォルダ管理",Content=new ScrollViewer {Content=panel,MaxHeight=Math.Max(160,ActualHeight-240)},CloseButtonText="閉じる"};
            await dialog.ShowAsync();
        }catch(Exception ex){Failure(ex);}
        finally{timer.Stop();dialogOpen=false;try{if(!disposed){renderCancellation.Cancel();thumbnails.Clear();await LoadAsync();}}finally{transitions.Release();}}
    }

    private async void RelatedTerms_Click(object sender,RoutedEventArgs e)
    {
        // Same transition guard as the other dialogs; unsaved tag drafts stay
        // in the editor because the dictionary never changes item metadata.
        if(dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        try{
            var editor=new RelatedTermsEditor(api);
            await editor.LoadAsync();
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="関連語",Content=new ScrollViewer {Content=editor.Content,MaxHeight=Math.Max(160,ActualHeight-240)},CloseButtonText="閉じる",DefaultButton=ContentDialogButton.Close};
            await dialog.ShowAsync();
        }catch(Exception ex){Failure(ex);}
        finally{
            dialogOpen=false;
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
        bool reload=false;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            dialogOpen=true;reload=true;
            var explanation=new TextBlock {Text="現在動いているモデルは変更しません。モデル選択は次回起動で反映します。新しいモデルではAI索引を作成してください。自動ダウンロードはしません。",TextWrapping=TextWrapping.Wrap};
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
                    modelFeedback.Text=(overridden?"起動引数 -AIProfile が優先。GUI選択は引数なしの次回起動で有効です。":
                        restart?"保存済み。Aredokoを閉じ、同じ起動スクリプトで起動し直してください。":"変更する場合は次回起動に設定を押してください。")
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
            void UpdateStart()=>start.IsEnabled=availableForIndex&&!indexRunning&&!starting&&scopeEditor.Ready;
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
                    var label=state switch {"idle"=>"未作成","running"=>"作成中","cancelling"=>"中断待ち","complete"=>"準備完了","cancelled"=>"中断済み","interrupted"=>"前回中断","failed"=>"失敗",_=>state};
                    var model=data["model"]?.GetValue<string>() ?? "未選択";
                    var capabilities=data["modalities"] is JsonArray modes && modes.Any(x=>x?.GetValue<string>()=="cover") ? "名前・タグ／画像・表紙" : "名前・タグ";
                    status.Text=available ? $"{model} · {capabilities}{(indexLimit is int cap ? $" · 最大{cap:N0}件" : "")}\n索引処理（開始時の対象）: {label} · {data["processed"]}/{data["total"]} 件\n{data["error"]!.GetValue<string>()}" : "現在のAI検索を利用できません。モデル設定・重み・Python環境を確認してください。文字検索は利用できます。\n"+(data["error"]?.GetValue<string>() ?? "");
                    availableForIndex=available;indexRunning=running;scopeEditor.SetJobBusy(running);UpdateStart();cancel.IsEnabled=running;
                    var resident=data["resident"]?.GetValue<bool>()==true;
                    release.IsEnabled=available&&!running&&resident&&!releasing;
                    if(available)status.Text+=(resident?"\nAIはメモリ内で待機中。":"\nAIは待機中・次の検索でモデルを準備します。");
                }
                catch(Exception ex){availableForIndex=false;status.Text=ex.Message;start.IsEnabled=false;}
                finally{polling=false;}
            }
            start.Click+=async(_,_)=>{
                if(!start.IsEnabled||aiScope is null)return;
                starting=true;UpdateStart();
                try{await api.PostAsync("api/library/ai/index",AIScopeRequests.Scoped(aiScope));await Refresh();}
                catch(Exception ex){status.Text=ex.Message;}
                finally{starting=false;UpdateStart();}
            };
            cancel.Click+=async(_,_)=>{try{await api.PostAsync("api/library/ai/cancel",new JsonObject());await Refresh();}catch(Exception ex){status.Text=ex.Message;}};
            timer.Tick+=async(_,_)=>await Refresh();
            var panel=new StackPanel {Spacing=12,MinWidth=320};
            foreach(var element in new UIElement[]{explanation,modelChoice,modelWarning,modelApply,modelFeedback,scopeEditor.Content,
                new TextBlock {Text="AIのメモリ・索引負荷",Style=(Style)Application.Current.Resources["SubtitleTextBlockStyle"]},
                release,releaseResult,idleChoice,pauseChoice,saveResource,resourceResult})panel.Children.Add(element);
            var content=new Grid {RowSpacing=12,MaxHeight=Math.Max(160,ActualHeight-240)};
            AutomationProperties.SetAutomationId(content,"AISettingsLayout");
            content.RowDefinitions.Add(new RowDefinition {Height=new GridLength(1,GridUnitType.Star)});
            content.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
            content.RowDefinitions.Add(new RowDefinition {Height=GridLength.Auto});
            var modelOptions=new ScrollViewer {Content=panel,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            AutomationProperties.SetAutomationId(modelOptions,"AIOptions");
            AutomationProperties.SetName(modelOptions,"モデル・AIリソース設定");
            content.Children.Add(modelOptions);
            var indexInfo=new StackPanel {Spacing=8};
            AutomationProperties.SetAutomationId(indexInfo,"AIIndexSummary");
            indexInfo.Children.Add(new TextBlock {Text="現在のAI索引",Style=(Style)Application.Current.Resources["SubtitleTextBlockStyle"]});
            indexInfo.Children.Add(status);Grid.SetRow(indexInfo,1);content.Children.Add(indexInfo);
            var actions=new StackPanel {Orientation=Orientation.Horizontal,Spacing=8};
            actions.Children.Add(start);actions.Children.Add(cancel);Grid.SetRow(actions,2);content.Children.Add(actions);
            await RefreshProfiles();await RefreshResource();await Refresh();timer.Start();
            var dialog=new ContentDialog {XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AI検索の準備",Content=content,CloseButtonText="閉じる"};
            dialog.Closing+=(_,args)=>{if(scopeEditor.Saving)args.Cancel=true;};
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{timer.Stop();dialogOpen=false;try{if(reload&&!disposed)await LoadAsync();}finally{transitions.Release();}}
    }

    public void Stop(){renderCancellation.Cancel();detailCancellation?.Cancel();readerView?.Dispose();disposed=true;searches.Next();searchTimer.Stop();api.Dispose();}
}

