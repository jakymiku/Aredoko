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
    private List<MediaRow> rows=[];
    private MediaRow? active;
    private EditorState saved;
    private bool ready, populating, saving, dialogOpen, tiles, disposed;
    private int page, lastKind;
    private string view="all", lastQuery="";

    public MainPage() {
        InitializeComponent();
        thumbnails = new ThumbnailService(api);
        searchTimer=DispatcherQueue.CreateTimer(); searchTimer.Interval=TimeSpan.FromMilliseconds(300);
        searchTimer.Tick+=async (_,_)=>{searchTimer.Stop(); if(Query.Text!=lastQuery||Kind.SelectedIndex!=lastKind) await NavigateAsync(0);};
    }
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
        try { renderCancellation.Cancel(); thumbnails.Clear(); await api.ConnectAsync(); await LoadAsync(); }
        catch(Exception ex) { Notice("バックエンドに接続できません", "start-winui.ps1を起動して再接続してください。"+ex.Message,InfoBarSeverity.Error); }
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
        var query=Query.Text; var kind=KindValue();var selectedKind=Kind.SelectedIndex;
        try {
            var result=await api.SearchAsync(query,kind,view,page);
            if(!searches.IsCurrent(version)||disposed)return;
            if(result.Items.Count==0 && page>0){page=Math.Max(0,(result.Total-1)/60);await LoadAsync();return;}
            lastQuery=query; lastKind=selectedKind;
            rows=result.Items; active=null; DetailsButton.IsEnabled=false;detailCancellation?.Cancel(); DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed; Tags.Text="";Shelf.Text="";Favorite.IsChecked=false;Reviewed.IsChecked=false;RenderRows();
            ItemTitle.Text="作品を選んでください"; ItemPath.Text=""; EditStatus.Text="";
            Count.Text=$"{result.Total:N0} 件"; PageNumber.Text=$"{page+1} / {Math.Max(1,(result.Total+59)/60)}";
            Previous.IsEnabled=page>0; Next.IsEnabled=(page+1)*60<result.Total;
            Empty.Visibility=rows.Count==0?Visibility.Visible:Visibility.Collapsed;
            Empty.Text=query.Length>0?"一致する名前・タグがありません。検索条件を変えてください。":"フォルダ管理からフォルダを登録し、スキャンしてください。";
            Notice("読込完了","名前・タグの文字検索。元ファイルは変更しません。");
        } catch(Exception ex) { if(searches.IsCurrent(version)){rows=[];active=null;DetailsButton.IsEnabled=false;detailCancellation?.Cancel();DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed;ItemTitle.Text="作品を選んでください";ItemPath.Text="";Tags.Text="";Shelf.Text="";Favorite.IsChecked=false;Reviewed.IsChecked=false;EditStatus.Text="";RenderRows();Empty.Visibility=Visibility.Visible;Empty.Text="再接続からやり直してください。";Failure(ex);} }
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
                text.Children.Add(new TextBlock { Text = (row.Favorite ? "★ " : "") + row.Title, TextTrimming = TextTrimming.CharacterEllipsis });
                text.Children.Add(new TextBlock { Text = $"{KindLabel(row.Kind)} · {AvailabilityLabel(row.Availability)} · {string.Join("、", row.Tags)}", TextTrimming = TextTrimming.CharacterEllipsis, Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"] });
                var previewStatus = new TextBlock { Text = row.Availability == "present" && row.Kind is "image" or "book" or "archive" ? "読込中" : "プレビューなし", Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"] };
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
            if(!await ConfirmDiscardAsync()){populating=true;Query.Text=lastQuery;Kind.SelectedIndex=lastKind;populating=false;return;}
            page=nextPage;await LoadAsync();
        }finally{transitions.Release();if((Query.Text!=lastQuery||Kind.SelectedIndex!=lastKind)&&!disposed){searchTimer.Stop();searchTimer.Start();}}
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
    private void UpdateDirty(){if(!ready)return;EditStatus.Text=Dirty?"未保存の変更":"保存済み";Save.IsEnabled=active is not null&&Dirty&&!saving;}
    private void Editor_Changed(object sender,TextChangedEventArgs e)=>UpdateDirty();
    private void Editor_Checked(object sender,RoutedEventArgs e)=>UpdateDirty();
    public async Task<bool> ConfirmDiscardAsync() {
        if(saving||dialogOpen)return false;
        if(!Dirty)return true;
        dialogOpen=true;
        try {
            var dialog=new ContentDialog {XamlRoot=XamlRoot,Title="変更を破棄しますか？",Content=active?.Title,PrimaryButtonText="変更を破棄",CloseButtonText="編集を続ける",DefaultButton=ContentDialogButton.Close};
            return await dialog.ShowAsync()==ContentDialogResult.Primary;
        }finally{dialogOpen=false;}
    }
    private async Task SaveAsync() {
        if(active is null||saving||dialogOpen||!Dirty)return;
        var snapshot=Current();var error=snapshot.Validate();
        if(error is not null){EditStatus.Text=error;return;}
        saving=true;Editor.IsEnabled=false;var id=active.Id;
        try {
            await api.SaveAsync(id,snapshot);
            saved=snapshot;active.Tags=snapshot.ParsedTags;active.Shelf=snapshot.Shelf;active.Favorite=snapshot.Favorite;active.Reviewed=snapshot.Reviewed;
            RenderRows();RestoreSelection();EditStatus.Text="保存しました";Notice("保存しました");
        }catch(Exception ex){Failure(ex);EditStatus.Text="保存できませんでした。変更内容は残っています。";}
        finally{saving=false;Editor.IsEnabled=true;Save.IsEnabled=Dirty;if(Query.Text!=lastQuery||Kind.SelectedIndex!=lastKind){searchTimer.Stop();searchTimer.Start();}}
    }
    private async void Save_Click(object sender,RoutedEventArgs e)=>await SaveAsync();
    private async void SaveShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){e.Handled=true;await SaveAsync();}
    private void SearchShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs e){e.Handled=true;Query.Focus(FocusState.Keyboard);}
    private void Query_Changed(object sender,TextChangedEventArgs e){if(ready&&!populating){searchTimer.Stop();searchTimer.Start();}}
    private async void Search_Click(object sender,RoutedEventArgs e){searchTimer.Stop();await NavigateAsync(0);}
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
        finally { transitions.Release();if((Query.Text!=lastQuery||Kind.SelectedIndex!=lastKind)&&!disposed){searchTimer.Stop();searchTimer.Start();} }
    }
    private void Layout_Click(object sender,RoutedEventArgs e){tiles=!tiles;LayoutButton.Content=tiles?"リスト表示":"タイル表示";RenderRows();RestoreSelection();}
    private void OpenDetails_Click(object sender,RoutedEventArgs e){if(active is not null)Details.IsPaneOpen=true;}
    private async void CloseDetails_Click(object sender,RoutedEventArgs e){if(await ConfirmDiscardAsync()){active=null;DetailsButton.IsEnabled=false;detailCancellation?.Cancel();DetailPreview.Source=null;DetailPreview.Visibility=Visibility.Collapsed;Editor.IsEnabled=false;Details.IsPaneOpen=false;RestoreSelection();}}
    private void Page_SizeChanged(object sender,SizeChangedEventArgs e){if(Details is null)return;Details.DisplayMode=e.NewSize.Width<1000?SplitViewDisplayMode.Overlay:SplitViewDisplayMode.Inline;Details.OpenPaneLength=Math.Min(320,Math.Max(240,e.NewSize.Width-64));if(e.NewSize.Width>=1000)Details.IsPaneOpen=true;else if(active is null)Details.IsPaneOpen=false;}

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
            var dialog=new ContentDialog {XamlRoot=XamlRoot,Title="フォルダ管理",Content=new ScrollViewer {Content=panel,MaxHeight=480},CloseButtonText="閉じる"};
            await dialog.ShowAsync();
        }catch(Exception ex){Failure(ex);}
        finally{timer.Stop();dialogOpen=false;try{if(!disposed){renderCancellation.Cancel();thumbnails.Clear();await LoadAsync();}}finally{transitions.Release();}}
    }
    public void Stop(){renderCancellation.Cancel();detailCancellation?.Cancel();disposed=true;searches.Next();searchTimer.Stop();api.Dispose();}
}
