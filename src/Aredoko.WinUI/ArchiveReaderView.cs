using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;
using Windows.System;

namespace Aredoko_WinUI;

// Same native canvas/overlay tokens as the image viewer. No extraction or prefetch.
internal sealed class ArchiveReaderView : Grid, IDisposable
{
    private bool actualPixels;
    private readonly LibraryApi api;
    private readonly int itemId;
    private readonly CancellationTokenSource lifetime = new();
    private readonly CancellationToken cancellation;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer hideTimer;
    private readonly Grid canvas = new();
    private readonly StackPanel pages = new() { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
    private readonly Image image = new() { Stretch = Stretch.Uniform };
    private readonly Image second = new() { Stretch = Stretch.Uniform, Visibility = Visibility.Collapsed };
    private readonly ScrollViewer viewport = new()
    {
        ZoomMode = ZoomMode.Enabled, MinZoomFactor = 1, MaxZoomFactor = 4, IsTabStop = true,
        HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        HorizontalContentAlignment = HorizontalAlignment.Center, VerticalContentAlignment = VerticalAlignment.Center, RequestedTheme = ElementTheme.Dark
    };
    private readonly Border header = new() { VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0), RequestedTheme = ElementTheme.Dark };
    private readonly Border toolbar = new() { VerticalAlignment = VerticalAlignment.Bottom, HorizontalAlignment = HorizontalAlignment.Stretch, Margin = new Thickness(0), RequestedTheme = ElementTheme.Dark };
    private readonly Button previous = IconButton(Symbol.Back), next = IconButton(Symbol.Forward), zoomOut = IconButton(Symbol.ZoomOut), zoomIn = IconButton(Symbol.ZoomIn);
    private readonly Button fit = IconButton(Symbol.FullScreen), retry = IconButton(Symbol.Refresh), reopen = IconButton(Symbol.RepeatAll), settings = IconButton(Symbol.Setting), close = IconButton(Symbol.Cancel);
    private readonly Button actualSize=new(){Content="原寸",MinWidth=36,Padding=new Thickness(8)};
    private readonly TextBlock count = new() { Text = "—", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock zoom = new() { Text = "倍率 100%", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock status = new() { Visibility = Visibility.Collapsed, TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center };
    private readonly TextBlock progressStatus=new(){Visibility=Visibility.Collapsed,TextWrapping=TextWrapping.Wrap,HorizontalAlignment=HorizontalAlignment.Center};
    private readonly MenuFlyoutItem saveProgress=new(){Text="読書位置を保存し直す"};
    private bool allowProgressSave=true;
    private readonly MenuFlyout menu = new();
    private readonly List<RadioMenuFlyoutItem> modes = [];
    private ArchiveManifest? manifest;
    private ReaderDisplayMode mode;
    private int page;
    private readonly PageTextMatch? initialMatch;
    private readonly AIPageMatch? initialPageMatch;
    private bool busy, disposed, failed, loaded, keyboardChrome, menuOpen;
    public event Action<int>? ContentOpened;
    public event EventHandler? CloseRequested;

    public ArchiveReaderView(LibraryApi api, int itemId, string title, PageTextMatch? initialMatch=null,AIPageMatch? initialPageMatch=null)
    {
        this.api=api;this.itemId=itemId;this.initialMatch=initialMatch;this.initialPageMatch=initialPageMatch;cancellation=lifetime.Token;
        hideTimer=DispatcherQueue.CreateTimer();hideTimer.Interval=TimeSpan.FromSeconds(2.5);hideTimer.IsRepeating=false;
        hideTimer.Tick+=(_,_)=>{if(!disposed&&!keyboardChrome&&!menuOpen&&!busy&&!failed){viewport.Focus(FocusState.Programmatic);header.Visibility=toolbar.Visibility=Visibility.Collapsed;}};
        viewport.Style=(Style)Application.Current.Resources["ImageViewerCanvasStyle"];
        header.Style=toolbar.Style=(Style)Application.Current.Resources["ImageViewerOverlayStyle"];
        // Edge overlays must paint the last pixel; a translucent stroke reveals the page underneath.
        header.BorderThickness=toolbar.BorderThickness=new Thickness(0);
        pages.Children.Add(image);pages.Children.Add(second);canvas.Children.Add(pages);viewport.Content=canvas;Children.Add(viewport);
        viewport.SizeChanged+=(_,_)=>FitImages();viewport.ViewChanged+=(_,_)=>UpdateActions();
        var heading=new Grid{ColumnSpacing=12};heading.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
        heading.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});heading.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
        var name=new TextBlock{Text=title,TextTrimming=TextTrimming.CharacterEllipsis,VerticalAlignment=VerticalAlignment.Center};
        name.Style=count.Style=zoom.Style=status.Style=progressStatus.Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"];
        ToolTipService.SetToolTip(name,title);heading.Children.Add(name);SetColumn(count,1);heading.Children.Add(count);SetColumn(close,2);heading.Children.Add(close);header.Child=heading;Children.Add(header);
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8,HorizontalAlignment=HorizontalAlignment.Center};
        foreach(var control in new UIElement[]{previous,next,zoomOut,zoomIn,fit,actualSize,zoom,retry,reopen,settings})actions.Children.Add(control);
        var bottom=new StackPanel{Spacing=4};bottom.Children.Add(actions);bottom.Children.Add(status);bottom.Children.Add(progressStatus);toolbar.Child=bottom;Children.Add(toolbar);
        Identify(actualSize,"ReaderActualSize","本のページを原寸で表示");ToolTipService.SetToolTip(actualSize,"原寸表示（画像の1pxを画面の1pxで表示）");
        actualSize.Click+=(_,_)=>{if(OriginalZoom()<1){actualPixels=true;FitImages();viewport.ChangeView(0,0,1,true);}else viewport.ChangeView(null,null,(float)OriginalZoom(),true);};
        Identify(viewport,"ReaderViewport","本の表示。左右キーでページ送り、右クリックで表示設定");Identify(image,"ReaderImage","本のページ");Identify(second,"ReaderImageSecond","見開きのもう一方のページ");
        Identify(previous,"ReaderPrevious","前のページ");Identify(next,"ReaderNext","次のページ");Identify(zoomOut,"ReaderZoomOut","本を縮小");Identify(zoomIn,"ReaderZoomIn","本を拡大");Identify(fit,"ReaderFit","本の表示をリセット");
        Identify(retry,"ReaderRetry","現在のページを再試行");Identify(reopen,"ReaderReopen","本を最初から開き直す");Identify(settings,"ReaderSettings","本の表示設定");Identify(close,"ReaderClose","読書画面を閉じる");
        Identify(header,"ReaderHeader","本の情報と閉じる");Identify(toolbar,"ReaderToolbar","本の操作");AutomationProperties.SetAutomationId(count,"ReaderPageNumber");AutomationProperties.SetAutomationId(status,"ReaderStatus");AutomationProperties.SetAutomationId(zoom,"ReaderZoomStatus");
        Identify(progressStatus,"ReaderProgressStatus","読書位置の保存状態");Identify(saveProgress,"ReaderSaveProgress","読書位置を保存し直す");
        AutomationProperties.SetLiveSetting(progressStatus,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        AutomationProperties.SetLiveSetting(status,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        foreach(var (button,text) in new[]{(previous,"前へ"),(next,"次へ"),(zoomOut,"縮小"),(zoomIn,"拡大"),(fit,"画面に合わせる"),(retry,"再試行"),(reopen,"最初から開き直す"),(settings,"単ページ・見開きの設定"),(close,"閉じる（Esc）")})ToolTipService.SetToolTip(button,text);
        foreach(var (value,label,id) in new[]{(ReaderDisplayMode.Single,"単ページ","ReaderSingle"),(ReaderDisplayMode.RightToLeft,"見開き（右→左）","ReaderRtl"),(ReaderDisplayMode.LeftToRight,"見開き（左→右）","ReaderLtr")})
        {
            var option=new RadioMenuFlyoutItem{Text=label,GroupName="ReaderDisplay",IsChecked=value==ReaderDisplayMode.Single};Identify(option,id,label);modes.Add(option);menu.Items.Add(option);
            option.Click+=async(_,_)=>{if(busy||disposed)return;allowProgressSave=true;mode=value;previous.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Forward:Symbol.Back);next.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Back:Symbol.Forward);if(manifest is not null)await LoadAsync(ReaderSpreadPolicy.Anchor(page,manifest.PageCount,mode));};
        }
        menu.Items.Add(new MenuFlyoutSeparator());menu.Items.Add(saveProgress);
        saveProgress.Click+=async(_,_)=>{if(busy||disposed||!loaded||manifest is null)return;allowProgressSave=true;busy=true;UpdateActions();try{await SaveProgressAsync(manifest);}finally{busy=false;if(!disposed)UpdateActions();}};
        menu.Opened+=(_,_)=>{menuOpen=true;ShowChrome();};menu.Closed+=(_,_)=>{menuOpen=false;ShowChrome();};settings.Flyout=menu;viewport.ContextFlyout=menu;
        previous.Click+=async(_,_)=>{if(manifest is not null){allowProgressSave=true;await LoadAsync(ReaderSpreadPolicy.Previous(page,manifest.PageCount,mode));}};
        next.Click+=async(_,_)=>{if(manifest is not null){allowProgressSave=true;await LoadAsync(ReaderSpreadPolicy.Next(page,manifest.PageCount,mode));}};
        retry.Click+=async(_,_)=>{if(manifest is null)await OpenAsync();else await LoadAsync(page);};reopen.Click+=async(_,_)=>await OpenAsync(true);
        zoomOut.Click+=(_,_)=>viewport.ChangeView(null,null,Math.Max(viewport.MinZoomFactor,viewport.ZoomFactor-.5f),true);zoomIn.Click+=(_,_)=>viewport.ChangeView(null,null,Math.Min(viewport.MaxZoomFactor,viewport.ZoomFactor+.5f),true);fit.Click+=(_,_)=>{actualPixels=false;FitImages();viewport.ChangeView(0,0,1,true);};
        close.Click+=(_,_)=>CloseRequested?.Invoke(this,EventArgs.Empty);UpdateActions();ShowChrome();
    }
    private static Button IconButton(Symbol symbol)=>new(){Content=new SymbolIcon(symbol),MinWidth=36,Padding=new Thickness(8)};
    private static void Identify(DependencyObject control,string id,string name){AutomationProperties.SetAutomationId(control,id);AutomationProperties.SetName(control,name);}
    private void ShowChrome()
    {if(disposed)return;header.Visibility=toolbar.Visibility=Visibility.Visible;hideTimer.Stop();if(!keyboardChrome&&!menuOpen&&!busy&&!failed)hideTimer.Start();}
    private void FitImages()
    {
        canvas.Width=Math.Max(1,viewport.ActualWidth);canvas.Height=Math.Max(1,viewport.ActualHeight);
        if(image.Source is not BitmapImage first)return;
        var a=(double)Math.Max(1,first.PixelWidth)/Math.Max(1,first.PixelHeight);
        var b=second.Source is BitmapImage other?(double)Math.Max(1,other.PixelWidth)/Math.Max(1,other.PixelHeight):0;
        var height=actualPixels?first.PixelHeight/(XamlRoot?.RasterizationScale??1):Math.Min(ViewerOptions.Value.EnlargeSmallImages?double.PositiveInfinity:first.PixelHeight/(XamlRoot?.RasterizationScale??1),Math.Min(canvas.Height,canvas.Width/(a+b)));image.Width=height*a;image.Height=height;
        second.Width=height*b;second.Height=height;
        viewport.MaxZoomFactor=(float)Math.Max(4,OriginalZoom());
        AutomationProperties.SetHelpText(image,$"{first.PixelWidth} x {first.PixelHeight} pixels");
        ToolTipService.SetToolTip(image,$"{first.PixelWidth} × {first.PixelHeight} px");
    }
    private double OriginalZoom()=>image.Source is BitmapImage first?Math.Max(.001,first.PixelWidth/Math.Max(1,image.Width)/(XamlRoot?.RasterizationScale??1)):1;
public void AttachNavigation(UIElement dialog)
    {
        ViewerInputGestures.Attach(dialog,viewport,async direction=>
        {
            if(busy||disposed||manifest is null||menuOpen)return;
            allowProgressSave=true;
            await LoadAsync(direction>0?ReaderSpreadPolicy.Next(page,manifest.PageCount,mode):ReaderSpreadPolicy.Previous(page,manifest.PageCount,mode));
        });
        dialog.AddHandler(PointerMovedEvent,new PointerEventHandler((_,_)=>{keyboardChrome=false;ShowChrome();}),true);
        dialog.PreviewKeyDown+=async(_,args)=>
        {
            if(args.Key==VirtualKey.Escape){if(menuOpen)return;args.Handled=true;CloseRequested?.Invoke(this,EventArgs.Empty);return;}
            if(args.Key==VirtualKey.Tab){keyboardChrome=true;ShowChrome();return;}
            foreach(var modifier in new[]{VirtualKey.Control,VirtualKey.Shift,VirtualKey.Menu,VirtualKey.LeftWindows,VirtualKey.RightWindows})
                if((Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(modifier)&Windows.UI.Core.CoreVirtualKeyStates.Down)!=0)return;
            if(args.Key==VirtualKey.F10){keyboardChrome=true;ShowChrome();args.Handled=true;return;}
            if(args.Key is not(VirtualKey.Left or VirtualKey.Right)||manifest is null||menuOpen)return;
            args.Handled=true;var forward=mode==ReaderDisplayMode.RightToLeft?args.Key==VirtualKey.Left:args.Key==VirtualKey.Right;
            allowProgressSave=true;await LoadAsync(forward?ReaderSpreadPolicy.Next(page,manifest.PageCount,mode):ReaderSpreadPolicy.Previous(page,manifest.PageCount,mode));
        };
    }
    public Task OpenAsync()=>OpenAsync(false);
    private async Task OpenAsync(bool fromBeginning)
    {
        if(busy||disposed)return;busy=true;failed=loaded=false;manifest=null;page=0;ClearImages();count.Text="—";ViewerNotice.Set(status,"本を開いています…");hideTimer.Stop();UpdateActions();
        int start=0;allowProgressSave=true;ViewerNotice.Set(progressStatus);
        try
        {
            var result=await api.ReaderManifestAsync(itemId,cancellation);cancellation.ThrowIfCancellationRequested();manifest=result;
            try
            {
                var saved=await api.ReaderProgressAsync(itemId,cancellation);cancellation.ThrowIfCancellationRequested();
                if(saved is not null){mode=saved.Mode;start=fromBeginning?0:saved.RestorePage(result);}
            }
            catch(Exception) when(!cancellation.IsCancellationRequested)
            {allowProgressSave=fromBeginning;ViewerNotice.Set(progressStatus,"読書位置を取得できませんでした。先頭から表示します。保存済み位置は移動するまで保持します。");}
            if(!fromBeginning&&(initialPageMatch?.InitialReaderPage(result)??initialMatch?.InitialReaderPage(result)) is int requested)
            {
                start=ReaderSpreadPolicy.Anchor(requested,result.PageCount,mode);
            }
            if(cancellation.IsCancellationRequested)return;
            foreach(var option in modes)option.IsChecked=option.Text== (mode switch{ReaderDisplayMode.RightToLeft=>"見開き（右→左）",ReaderDisplayMode.LeftToRight=>"見開き（左→右）",_=>"単ページ"});
            previous.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Forward:Symbol.Back);next.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Back:Symbol.Forward);
        }
        catch(Exception ex){ReportFailure(ex);}finally{busy=false;if(!disposed)UpdateActions();}
        if(manifest is not null&&!disposed)await LoadAsync(start);
    }
    private async Task SaveProgressAsync(ArchiveManifest book)
    {
        if(disposed||!allowProgressSave)return;
        ViewerNotice.Set(progressStatus);
        try
        {
            await api.SaveReaderProgressAsync(book,page,mode,cancellation);
            if(!disposed)ViewerNotice.Set(progressStatus);
        }
        catch(Exception) when(!cancellation.IsCancellationRequested)
        {if(!disposed){ViewerNotice.Set(progressStatus,"読書位置を保存できませんでした。設定から保存し直せます。");keyboardChrome=true;ShowChrome();}}
        catch(OperationCanceledException) { }
    }
    private async Task LoadAsync(int requestedPage)
    {
        var book=manifest;if(busy||disposed||book is null||requestedPage<0||requestedPage>=book.PageCount)return;
        actualPixels=false;busy=true;failed=loaded=false;page=ReaderSpreadPolicy.Anchor(requestedPage,book.PageCount,mode);ClearImages();hideTimer.Stop();viewport.ChangeView(0,0,1,true);
        var indexes=ReaderSpreadPolicy.Pages(page,book.PageCount,mode);
        count.Text=indexes.Length==1?$"{page+1} / {book.PageCount}":$"{page+1}–{page+2} / {book.PageCount}";ViewerNotice.Set(status,"ページを読み込んでいます…");UpdateActions();
        try
        {
            var bitmaps=new List<BitmapImage>();
            foreach(var index in indexes)
            {
                var source=await api.ReaderOriginalPageAsync(book,index,cancellation);
                var bitmap=await ViewerImageCodec.DecodeAsync(source,cancellation);bitmaps.Add(bitmap);
            }
            if(disposed||manifest!=book)return;
            image.Source=bitmaps[0];AutomationProperties.SetName(image,$"{indexes[0]+1}ページ");
            if(bitmaps.Count==2){second.Source=bitmaps[1];second.Visibility=Visibility.Visible;AutomationProperties.SetName(second,$"{indexes[1]+1}ページ");}
            FitImages();loaded=true;ViewerNotice.Set(status);await SaveProgressAsync(book);ContentOpened?.Invoke(itemId);
        }
        catch(Exception ex){ReportFailure(ex);}finally{busy=false;if(!disposed){UpdateActions();if(!keyboardChrome&&!failed)hideTimer.Start();}}
    }
    private void ClearImages(){image.Source=second.Source=null;second.Visibility=Visibility.Collapsed;AutomationProperties.SetName(image,"ページ未表示");AutomationProperties.SetName(second,"ページ未表示");}
    private void ReportFailure(Exception ex)
    {
        if(disposed||cancellation.IsCancellationRequested)return;ClearImages();failed=true;loaded=false;ViewerNotice.Set(progressStatus,"前に読めたページの位置を保持しています");
        if(ex is ArchiveReadException{RequiresReopen:true}){manifest=null;count.Text="—";}
        ViewerNotice.Set(status,ex switch{ArchiveReadException=>ex.Message,OperationCanceledException=>"読み込みがタイムアウトしました。再試行してください。",HttpRequestException=>"接続できません。閉じてライブラリから再接続してください。",_=>"このページを表示できません。未対応形式・破損・画像サイズを確認してください。"});ShowChrome();
    }
    private void UpdateActions()
    {
        previous.IsEnabled=!busy&&manifest is not null&&page>0;
        next.IsEnabled=!busy&&manifest is not null&&ReaderSpreadPolicy.Next(page,manifest.PageCount,mode)<manifest.PageCount;
        retry.IsEnabled=!busy&&failed;reopen.IsEnabled=!busy;settings.IsEnabled=!busy;
        foreach(var option in modes)option.IsEnabled=!busy;saveProgress.IsEnabled=!busy&&loaded&&manifest is not null;
        zoom.Text=$"倍率 {viewport.ZoomFactor/OriginalZoom()*100:0}%";zoomOut.IsEnabled=loaded&&!busy&&viewport.ZoomFactor>viewport.MinZoomFactor;zoomIn.IsEnabled=loaded&&!busy&&viewport.ZoomFactor<viewport.MaxZoomFactor;actualSize.IsEnabled=loaded&&!busy;fit.IsEnabled=loaded&&!busy;
    }
    public void Dispose(){if(disposed)return;disposed=true;hideTimer.Stop();menu.Hide();lifetime.Cancel();ClearImages();manifest=null;lifetime.Dispose();}
}
