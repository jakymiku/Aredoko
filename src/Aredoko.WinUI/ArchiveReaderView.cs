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

// Original-resolution pages with per-use revalidation and bounded next-spread preload.
internal sealed class ArchiveReaderView : Grid, IDisposable, IViewerWindowTitle
{
    private bool actualPixels;
    private readonly LibraryApi api;
    private readonly ViewerFavoriteAction favorite;
    public event Action<int,bool,bool>? FavoriteChanged;
    private readonly ViewerPageCache<(string Revision,int Page),BitmapImage> pageCache=new();
    private readonly ReaderProgressWriter progressWriter;
    private CancellationTokenSource? preload;
    private Task preloadTask=Task.CompletedTask;
    private bool closing;
    private readonly int itemId;
    private readonly CancellationTokenSource lifetime = new();
    private readonly CancellationToken cancellation;
    private readonly ViewerChromeController hideTimer;
    private readonly string bookTitle;
    public string WindowTitle=>$"{bookTitle}（{count.Text}）— Aredoko";
    public event Action<string>? TitleChanged;
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
    private readonly Border toolbar = new() { VerticalAlignment = VerticalAlignment.Bottom, HorizontalAlignment = HorizontalAlignment.Center, RequestedTheme = ElementTheme.Dark };
    private readonly Button previous = IconButton(Symbol.Back), next = IconButton(Symbol.Forward), zoomOut = IconButton(Symbol.ZoomOut), zoomIn = IconButton(Symbol.ZoomIn);
    private readonly Button fit = IconButton(Symbol.FullScreen), retry = IconButton(Symbol.Refresh), reopen = IconButton(Symbol.RepeatAll), settings = IconButton(Symbol.Setting);
    private readonly Button editDetails = IconButton(Symbol.Edit);
    private readonly Button actualSize=ViewerChromeController.PillTextButton("1:1");
    private readonly Microsoft.UI.Xaml.Controls.Primitives.ToggleButton pinButton;
    private readonly Action syncPin;
    private readonly Slider pageScrubber = new() { Minimum = 1, Maximum = 1, Value = 1, SmallChange = 1, LargeChange = 5, StepFrequency = 1, IsThumbToolTipEnabled = false };
    private readonly Border scrubberHost;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer scrubTimer;
    private int scrubTargetPage;
    private int? pendingScrubPage;
    private bool updatingScrubber, scrubberDragging;
    private readonly TextBlock count = new() { Text = "—", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(4, 0, 4, 0) };
    private readonly TextBlock zoom = new() { Text = "100%", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock status = new() { Visibility = Visibility.Collapsed, TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center };
    private readonly TextBlock progressStatus=new(){Visibility=Visibility.Collapsed,TextWrapping=TextWrapping.Wrap,HorizontalAlignment=HorizontalAlignment.Center};
    private readonly MenuFlyoutItem saveProgress=new(){Text="読書位置を保存し直す"};
    private readonly MenuFlyoutItem findSimilarPage1=new(){Text="≈ このページに似た画像を探す"};
    private readonly MenuFlyoutItem findSimilarPage2=new(){Text="≈ もう一方のページに似た画像を探す",Visibility=Visibility.Collapsed};
    private int[] currentPageIndexes=[];
    private bool allowProgressSave=true;
    private readonly MenuFlyout menu;
    private readonly List<RadioMenuFlyoutItem> modes = [];
    private ArchiveManifest? manifest;
    private ReaderDisplayMode mode;
    private int page;
    private int targetPage;
    private readonly PageTextMatch? initialMatch;
    private readonly AIPageMatch? initialPageMatch;
    private readonly bool openAtEnd, canNavigatePrevious, canNavigateNext;
    private bool busy, disposed, failed, loaded, keyboardChrome, menuOpen, navigatingOut;
    public event Action<int>? ContentOpened;
    public event EventHandler? CloseRequested;
    public event Action? EditDetailsRequested;
    public event Action? ToggleMaximizeRequested;
    public event Action<int,int>? FindSimilarPageRequested;
    public event Func<int,Task>? NavigateOutRequested;

    public ArchiveReaderView(LibraryApi api, int itemId, string title, PageTextMatch? initialMatch=null,AIPageMatch? initialPageMatch=null,ResultSession? favoriteSession=null,int favoriteOrdinal=0,bool openAtEnd=false,bool canNavigatePrevious=false,bool canNavigateNext=false)
    {
        this.api=api;this.itemId=itemId;bookTitle=title;this.initialMatch=initialMatch;this.initialPageMatch=initialPageMatch;this.openAtEnd=openAtEnd;this.canNavigatePrevious=canNavigatePrevious;this.canNavigateNext=canNavigateNext;cancellation=lifetime.Token;
        favorite=new(favoriteSession,message=>ViewerNotice.Set(status,message));favorite.Attach();
        favorite.Changed+=(id,value,kept)=>FavoriteChanged?.Invoke(id,value,kept);
        favorite.ReturnRequested+=()=>CloseRequested?.Invoke(this,EventArgs.Empty);
        favorite.StateChanged+=()=>{if(favorite.IsSaving)ShowChrome();UpdateActions();hideTimer?.RefreshHoverHint();};
        progressWriter=new((book,position)=>api.SaveReaderProgressAsync(book,position.Page,position.Mode,CancellationToken.None));
        progressWriter.StateChanged+=error=>
        {
            if(disposed)return;
            ViewerNotice.Set(progressStatus,error is null?"":"読書位置を保存できませんでした。設定から保存し直せます。");
            if(error is not null){keyboardChrome=true;ShowChrome();}
            if(error is not null)AppLog.Error(error);
        };
        hideTimer=new(this,toolbar,viewport,()=>keyboardChrome||menuOpen||scrubberDragging||favorite.IsSaving);
        scrubTimer=DispatcherQueue.CreateTimer();scrubTimer.Interval=TimeSpan.FromMilliseconds(60);scrubTimer.IsRepeating=false;
        scrubTimer.Tick+=async(_,_)=>
        {
            if(scrubberDragging||disposed||closing||manifest is null)return;
            var anchor=ReaderSpreadPolicy.Anchor(scrubTargetPage,manifest.PageCount,mode);
            if(anchor==page)return;
            allowProgressSave=true;
            if(busy){pendingScrubPage=anchor;return;}
            await LoadAsync(anchor);
        };
        scrubberHost=ViewerChromeController.WrapScrubber(pageScrubber,168);
        scrubberHost.Visibility=Visibility.Collapsed;
        (pinButton,syncPin)=ViewerChromeController.CreatePinButton("ReaderPinToolbar",()=>{hideTimer.SyncPinState();hideTimer.RefreshHoverHint();},ex=>{ViewerNotice.Set(status,"設定を保存できませんでした。");AppLog.Error(ex);});
        menu=ViewerChromeController.Settings(true,()=>{syncPin();hideTimer.SyncPinState();FitImages();UpdateActions();},ex=>{ViewerNotice.Set(status,"設定を保存できませんでした。");AppLog.Error(ex);});
        viewport.Style=(Style)Application.Current.Resources["ImageViewerCanvasStyle"];
        ViewerChromeController.StyleFloatingPill(toolbar);
        pages.Children.Add(image);pages.Children.Add(second);canvas.Children.Add(pages);viewport.Content=canvas;Children.Add(viewport);
        viewport.SizeChanged+=(_,_)=>FitImages();viewport.ViewChanged+=(_,_)=>UpdateActions();
        count.Style=zoom.Style=status.Style=progressStatus.Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"];
        ViewerChromeController.FixNumericSlot(zoom, 44);
        ViewerChromeController.FixNumericSlot(count, ViewerChromeController.CountSlotWidth(99, spread: true));
        ViewerInputGestures.AttachPan(viewport);
        ViewerChromeController.StylePillButton(favorite.Button);
        var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=4,HorizontalAlignment=HorizontalAlignment.Center};
        foreach(var control in new UIElement[]{fit,actualSize,zoomOut,zoomIn,zoom,ViewerChromeController.Divider(),previous,count,next,scrubberHost,ViewerChromeController.Divider(),favorite.Button,editDetails,retry,reopen,settings,pinButton})actions.Children.Add(control);
        Identify(pageScrubber,"ReaderPageSeek","ページ位置の移動");
        pageScrubber.AddHandler(PointerPressedEvent,new PointerEventHandler((_,_)=>{scrubberDragging=true;scrubTimer.Stop();hideTimer.Show();}),true);
        pageScrubber.AddHandler(PointerReleasedEvent,new PointerEventHandler((_,_)=>FinishScrubDrag()),true);
        pageScrubber.PointerCaptureLost+=(_,_)=>FinishScrubDrag();
        pageScrubber.PointerCanceled+=(_,_)=>FinishScrubDrag();
        pageScrubber.ValueChanged+=(_,_)=>
        {
            if(updatingScrubber||disposed||closing||manifest is null)return;
            scrubTargetPage=Math.Clamp((int)Math.Round(pageScrubber.Value)-1,0,manifest.PageCount-1);
            if(scrubberDragging){count.Text=$"{scrubTargetPage+1} / {manifest.PageCount}";return;}
            scrubTimer.Stop();scrubTimer.Start();
        };
        Identify(favorite.Button,"ReaderFavorite","お気に入りを読み込み中");
        Identify(editDetails,"ReaderEditDetails","詳細で編集");
        editDetails.Click+=(_,_)=>EditDetailsRequested?.Invoke();
        toolbar.Child=actions;Children.Add(toolbar);ViewerChromeController.AttachNotices(this,76,status,progressStatus);
        Identify(actualSize,"ReaderActualSize","本のページを原寸で表示");
        actualSize.Click+=(_,_)=>{if(OriginalZoom()<1){actualPixels=true;FitImages();viewport.ChangeView(0,0,1,true);}else ViewerInputGestures.ZoomCentered(viewport,(float)OriginalZoom());};
        Identify(viewport,"ReaderViewport","本の表示。左右キーでページ送り、右クリックで表示設定");Identify(image,"ReaderImage","本のページ");Identify(second,"ReaderImageSecond","見開きのもう一方のページ");
        Identify(previous,"ReaderPrevious","前のページ");Identify(next,"ReaderNext","次のページ");Identify(zoomOut,"ReaderZoomOut","本を縮小");Identify(zoomIn,"ReaderZoomIn","本を拡大");Identify(fit,"ReaderFit","本の表示をリセット");
        Identify(retry,"ReaderRetry","現在のページを再試行");Identify(reopen,"ReaderReopen","本を最初から開き直す");Identify(settings,"ReaderSettings","本の表示と操作");
        Identify(toolbar,"ReaderToolbar","本の操作");AutomationProperties.SetAutomationId(count,"ReaderPageNumber");AutomationProperties.SetAutomationId(status,"ReaderStatus");AutomationProperties.SetAutomationId(zoom,"ReaderZoomStatus");
        Identify(progressStatus,"ReaderProgressStatus","読書位置の保存状態");Identify(saveProgress,"ReaderSaveProgress","読書位置を保存し直す");
        Identify(findSimilarPage1,"ReaderFindSimilarPage","このページに似た画像を探す");
        Identify(findSimilarPage2,"ReaderFindSimilarPage2","2枚目のページに似た画像を探す");
        findSimilarPage1.Click+=(_,_)=>{if(!busy&&!disposed&&loaded&&currentPageIndexes.Length>=1)FindSimilarPageRequested?.Invoke(itemId,currentPageIndexes[0]);};
        findSimilarPage2.Click+=(_,_)=>{if(!busy&&!disposed&&loaded&&currentPageIndexes.Length>=2)FindSimilarPageRequested?.Invoke(itemId,currentPageIndexes[1]);};
        AutomationProperties.SetLiveSetting(progressStatus,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        AutomationProperties.SetLiveSetting(status,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        foreach(var (button,text) in new (FrameworkElement,string)[]{(fit,"画面に合わせる"),(actualSize,"原寸表示（画像の1pxを画面の1pxで表示）"),(zoomOut,"縮小"),(zoomIn,"拡大"),(previous,"前のページ"),(next,"次のページ"),(editDetails,"詳細でタグ・棚を編集（ビューアを閉じる）"),(retry,"再試行"),(reopen,"先頭ページから開き直す"),(settings,"表示設定（単ページ・見開き・類似検索）")})
            hideTimer.AttachHoverHint(button,text);
        hideTimer.AttachHoverHint(favorite.Button,()=>AutomationProperties.GetName(favorite.Button));
        hideTimer.AttachHoverHint(zoom, () => image.Source is BitmapImage bmp && bmp.PixelWidth > 0 ? $"表示倍率（原寸 {bmp.PixelWidth} × {bmp.PixelHeight} px）" : "表示倍率");
        hideTimer.AttachHoverHint(count, "ページ位置（左右キーまたはバーで移動）");
        hideTimer.AttachHoverHint(pinButton,()=>ViewerOptions.Value.AlwaysShowControls?"操作バーの固定を解除":"操作バーを常に表示（ピン留め）");
        menu.Items.Add(findSimilarPage1);menu.Items.Add(findSimilarPage2);menu.Items.Add(new MenuFlyoutSeparator());
        foreach(var (value,label,id) in new[]{(ReaderDisplayMode.Single,"単ページ","ReaderSingle"),(ReaderDisplayMode.RightToLeft,"見開き（右→左）","ReaderRtl"),(ReaderDisplayMode.LeftToRight,"見開き（左→右）","ReaderLtr")})
        {
            var option=new RadioMenuFlyoutItem{Text=label,GroupName="ReaderDisplay",IsChecked=value==ReaderDisplayMode.Single};Identify(option,id,label);modes.Add(option);menu.Items.Add(option);
            option.Click+=async(_,_)=>{if(busy||disposed)return;allowProgressSave=true;mode=value;previous.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Forward:Symbol.Back);next.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Back:Symbol.Forward);if(manifest is not null)await LoadAsync(ReaderSpreadPolicy.Anchor(page,manifest.PageCount,mode));};
        }
        menu.Items.Add(new MenuFlyoutSeparator());menu.Items.Add(saveProgress);
        saveProgress.Click+=async(_,_)=>{if(busy||disposed||!loaded||manifest is null)return;allowProgressSave=true;busy=true;UpdateActions();try{await SaveProgressAsync(manifest);}finally{busy=false;if(!disposed)UpdateActions();}};
        menu.Opened+=(_,_)=>{
            if(!busy&&!disposed&&loaded&&manifest is not null&&currentPageIndexes.Length>0)
            {
                if(currentPageIndexes.Length==1)
                {
                    findSimilarPage1.Text=$"≈ このページ（{currentPageIndexes[0]+1}ページ目）に似た画像・動画を探す";
                    AutomationProperties.SetName(findSimilarPage1,findSimilarPage1.Text);
                    findSimilarPage1.IsEnabled=true;findSimilarPage1.Visibility=Visibility.Visible;
                    findSimilarPage2.Visibility=Visibility.Collapsed;
                }
                else
                {
                    findSimilarPage1.Text=$"≈ {currentPageIndexes[0]+1}ページ目に似た画像・動画を探す";
                    AutomationProperties.SetName(findSimilarPage1,findSimilarPage1.Text);
                    findSimilarPage1.IsEnabled=true;findSimilarPage1.Visibility=Visibility.Visible;
                    findSimilarPage2.Text=$"≈ {currentPageIndexes[1]+1}ページ目に似た画像・動画を探す";
                    AutomationProperties.SetName(findSimilarPage2,findSimilarPage2.Text);
                    findSimilarPage2.IsEnabled=true;findSimilarPage2.Visibility=Visibility.Visible;
                }
            }
            else
            {
                findSimilarPage1.IsEnabled=false;findSimilarPage1.Visibility=Visibility.Visible;
                findSimilarPage2.Visibility=Visibility.Collapsed;
            }
            menuOpen=true;hideTimer.HideHoverHint();ShowChrome();
        };
        menu.Closed+=(_,_)=>{menuOpen=false;ShowChrome();};settings.Flyout=menu;viewport.ContextFlyout=menu;
        viewport.DoubleTapped+=(_,args)=>{if(ViewerInputGestures.IsInteractiveControl(args.OriginalSource,viewport))return;args.Handled=true;ToggleMaximizeRequested?.Invoke();};
        previous.Click+=async(_,_)=>await StepPageAsync(-1);
        next.Click+=async(_,_)=>await StepPageAsync(1);
        retry.Click+=async(_,_)=>{if(manifest is null)await OpenAsync();else await LoadAsync(targetPage);};reopen.Click+=async(_,_)=>await OpenAsync(true);
        zoomOut.Click+=(_,_)=>ViewerInputGestures.ZoomCentered(viewport,Math.Max(viewport.MinZoomFactor,viewport.ZoomFactor-.5f));zoomIn.Click+=(_,_)=>ViewerInputGestures.ZoomCentered(viewport,Math.Min(viewport.MaxZoomFactor,viewport.ZoomFactor+.5f));fit.Click+=(_,_)=>{actualPixels=false;FitImages();viewport.ChangeView(0,0,1,true);};
        UpdateActions();
        favorite.Refresh(itemId,favoriteOrdinal);
    }
    private void FinishScrubDrag()
    {
        if(!scrubberDragging)return;
        scrubberDragging=false;hideTimer.Start();
        if(disposed||closing||manifest is null)return;
        var anchor=ReaderSpreadPolicy.Anchor(scrubTargetPage,manifest.PageCount,mode);
        if(anchor==page){UpdateActions();return;}
        allowProgressSave=true;
        if(busy)pendingScrubPage=anchor;
        else _=LoadAsync(anchor);
    }
    private static Button IconButton(Symbol symbol)=>ViewerChromeController.PillButton(symbol);
    private static void Identify(DependencyObject control,string id,string name){AutomationProperties.SetAutomationId(control,id);AutomationProperties.SetName(control,name);}
    private void ShowChrome()=>hideTimer.Show();
    public void FocusViewport()=>viewport.Focus(FocusState.Programmatic);
    public void ShowBoundaryNotice(string message){if(!disposed){ViewerNotice.Set(status,message);ShowChrome();}}
    private async Task StepPageAsync(int direction)
    {
        if(busy||disposed||closing||favorite.IsSaving||navigatingOut)return;
        if(manifest is not {} book)
        {
            if(NavigateOutRequested is not null&&(direction<0?canNavigatePrevious:canNavigateNext))
            {
                navigatingOut=true;UpdateActions();
                try{await NavigateOutRequested(direction);}finally{navigatingOut=false;if(!disposed)UpdateActions();}
            }
            return;
        }
        var atStart=page<=0;
        var atEnd=ReaderSpreadPolicy.Next(page,book.PageCount,mode)>=book.PageCount;
        if((direction<0&&atStart)||(direction>0&&atEnd))
        {
            if(NavigateOutRequested is not null&&(direction<0?canNavigatePrevious:canNavigateNext))
            {
                navigatingOut=true;UpdateActions();
                try{await NavigateOutRequested(direction);}finally{navigatingOut=false;if(!disposed)UpdateActions();}
                return;
            }
            if(ViewerOptions.Value.LoopBookPages)
            {
                allowProgressSave=true;
                await LoadAsync(ReaderSpreadPolicy.Move(page,book.PageCount,mode,direction,true));
                return;
            }
            ShowBoundaryNotice(direction<0?"先頭のページです":"最後のページです");
            return;
        }
        allowProgressSave=true;
        await LoadAsync(ReaderSpreadPolicy.Move(page,book.PageCount,mode,direction,false));
    }
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
    }
    private double OriginalZoom()=>image.Source is BitmapImage first?Math.Max(.001,first.PixelWidth/Math.Max(1,image.Width)/(XamlRoot?.RasterizationScale??1)):1;
public void AttachNavigation(UIElement dialog)
    {
        ViewerInputGestures.Attach(dialog,viewport,async direction=>
        {
            if(busy||disposed||menuOpen)return;
            await StepPageAsync(direction>0?1:-1);
        });
        dialog.AddHandler(PointerMovedEvent,new PointerEventHandler((_,_)=>{keyboardChrome=false;}),true);
        dialog.PreviewKeyDown+=async(_,args)=>
        {
            if(menuOpen)return;
            if(args.Key==VirtualKey.Escape){args.Handled=true;CloseRequested?.Invoke(this,EventArgs.Empty);return;}
            if(args.Key==VirtualKey.Tab){keyboardChrome=true;ShowChrome();return;}
            foreach(var modifier in new[]{VirtualKey.Control,VirtualKey.Shift,VirtualKey.Menu,VirtualKey.LeftWindows,VirtualKey.RightWindows})
                if((Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(modifier)&Windows.UI.Core.CoreVirtualKeyStates.Down)!=0)return;
            if(args.Key==VirtualKey.F10){keyboardChrome=true;ShowChrome();args.Handled=true;return;}
            if(args.Key is not(VirtualKey.Left or VirtualKey.Right)||menuOpen)return;
            args.Handled=true;var forward=mode==ReaderDisplayMode.RightToLeft?args.Key==VirtualKey.Left:args.Key==VirtualKey.Right;
            await StepPageAsync(forward?1:-1);
        };
    }
    public Task OpenAsync()=>OpenAsync(false);
    private async Task OpenAsync(bool fromBeginning)
    {
        if(busy||disposed||closing||favorite.IsSaving)return;busy=true;failed=loaded=false;manifest=null;page=0;ClearImages();pageCache.Clear();preload?.Cancel();count.Text="—";ViewerNotice.Set(status,"本を開いています…");hideTimer.Stop();UpdateActions();
        int start=0;allowProgressSave=true;ViewerNotice.Set(progressStatus);
        try
        {
            await progressWriter.FlushAsync();
            var result=await api.ReaderManifestAsync(itemId,cancellation);cancellation.ThrowIfCancellationRequested();manifest=result;
            count.Width=ViewerChromeController.CountSlotWidth(result.PageCount,spread:true);
            try
            {
                var saved=await api.ReaderProgressAsync(itemId,cancellation);cancellation.ThrowIfCancellationRequested();
                if(saved is not null){mode=saved.Mode;start=fromBeginning?0:saved.RestorePage(result);}
            }
            catch(Exception) when(!cancellation.IsCancellationRequested)
            {allowProgressSave=fromBeginning;ViewerNotice.Set(progressStatus,"読書位置を読み込めないため先頭から表示します");}
            if(!fromBeginning&&(initialPageMatch?.InitialReaderPage(result)??initialMatch?.InitialReaderPage(result)) is int requested)
            {
                start=ReaderSpreadPolicy.Anchor(requested,result.PageCount,mode);
            }
            else if(openAtEnd&&!fromBeginning)
            {
                start=ReaderSpreadPolicy.Anchor(result.PageCount-1,result.PageCount,mode);
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
        if(disposed||closing||!allowProgressSave)return;
        ViewerNotice.Set(progressStatus);
        progressWriter.Queue(book,page,mode);
        await progressWriter.FlushAsync();
    }
    public async Task FlushProgressAsync()
    {
        closing=true;preload?.Cancel();UpdateActions();
        await favorite.FlushAsync();
        if(progressWriter.HasPending){ViewerNotice.Set(progressStatus,"読書位置を保存しています…");ShowChrome();}
        await progressWriter.FlushAsync();
    }
    private async Task<BitmapImage> ReadPageAsync(ArchiveManifest book,int index,CancellationToken token)
    {
        var trace=new ViewerLoadTrace("reader-page");
        var bitmap=await pageCache.ReadAsync((book.Revision,index),async(etag,ct)=>
        {
            trace.Mark("source-start");var result=await api.ReaderOriginalSourceAsync(book,index,etag,ct);
            trace.Mark(result.NotModified?"source-revalidated":"source-body");return result;
        },async(data,speculative,ct)=>
        {
            var result=await ViewerImageCodec.DecodeCachedAsync(data,speculative,ct);trace.Mark("decode-ready");return result;
        },token);
        trace.Mark("ready");return bitmap;
    }
    private async Task PreloadNextAsync(ArchiveManifest book,int anchor,ReaderDisplayMode display,CancellationToken token)
    {
        var nextPage=ReaderSpreadPolicy.Next(anchor,book.PageCount,display);
        if(nextPage>=book.PageCount)return;
        foreach(var index in ReaderSpreadPolicy.Pages(nextPage,book.PageCount,display))
        {
            if(token.IsCancellationRequested)return;
            await pageCache.PreloadAsync((book.Revision,index),(etag,ct)=>api.ReaderOriginalSourceAsync(book,index,etag,ct),ViewerImageCodec.DecodeCachedAsync,token);
        }
    }
    private async Task LoadAsync(int requestedPage)
    {
        var book=manifest;if(busy||disposed||closing||favorite.IsSaving||book is null||requestedPage<0||requestedPage>=book.PageCount)return;
        var trace=new ViewerLoadTrace("reader-spread");
        actualPixels=false;busy=true;failed=false;preload?.Cancel();hideTimer.Stop();
        var target=ReaderSpreadPolicy.Anchor(requestedPage,book.PageCount,mode);
        targetPage=target;
        var indexes=ReaderSpreadPolicy.Pages(target,book.PageCount,mode);
        ViewerNotice.Set(status,"ページを読み込んでいます…");UpdateActions();
        try
        {
            // Finish cancelled speculative work before foreground reads.
            await preloadTask;
            trace.Mark("preload-drained");
            var bitmaps=await Task.WhenAll(indexes.Select(index=>ReadPageAsync(book,index,cancellation)));
            if(disposed||closing||manifest!=book)return;
            page=target;viewport.ChangeView(0,0,1,true);
            currentPageIndexes=indexes;
            image.Source=bitmaps[0];AutomationProperties.SetName(image,$"{indexes[0]+1}ページ");
            if(bitmaps.Length==2){second.Source=bitmaps[1];second.Visibility=Visibility.Visible;AutomationProperties.SetName(second,$"{indexes[1]+1}ページ");}
            else{second.Source=null;second.Visibility=Visibility.Collapsed;}
            count.Text=indexes.Length==1?$"{page+1} / {book.PageCount}":$"{page+1}–{page+2} / {book.PageCount}";
            FitImages();loaded=true;ViewerNotice.Set(status);ContentOpened?.Invoke(itemId);
            trace.Mark("assigned");
            if(allowProgressSave)progressWriter.Queue(book,page,mode);
            preload?.Dispose();preload=CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            preloadTask=PreloadNextAsync(book,page,mode,preload.Token);
        }
        catch(Exception ex){ReportFailure(ex);}
        finally
        {
            busy=false;
            if(!disposed)
            {
                if(!closing&&pendingScrubPage is int queued&&queued!=page)
                {
                    pendingScrubPage=null;
                    _=LoadAsync(queued);
                }
                else
                {
                    pendingScrubPage=null;
                    UpdateActions();
                    if(!keyboardChrome&&!failed)hideTimer.Start();
                }
            }
        }
    }
    private void ClearImages(){currentPageIndexes=[];image.Source=second.Source=null;second.Visibility=Visibility.Collapsed;AutomationProperties.SetName(image,"ページ未表示");AutomationProperties.SetName(second,"ページ未表示");}
    private void ReportFailure(Exception ex)
    {
        if(disposed||cancellation.IsCancellationRequested)return;ClearImages();failed=true;loaded=false;ViewerNotice.Set(progressStatus,"前に読めたページの位置を保持しています");
        if(ex is ArchiveReadException{RequiresReopen:true}){manifest=null;count.Text="—";}
        ViewerNotice.Set(status,ex switch{ArchiveReadException=>ex.Message,OperationCanceledException=>"読み込みがタイムアウトしました。再試行してください",HttpRequestException=>"接続できません。閉じて再接続してください",_=>"表示できません（未対応形式または破損）"});ShowChrome();
    }
    private void UpdateActions()
    {
        TitleChanged?.Invoke(WindowTitle);
        var blocked=busy||closing||favorite.IsSaving||navigatingOut;
        favorite.UpdateAvailability(!disposed&&!busy&&!closing&&loaded&&manifest is not null);
        previous.IsEnabled=!blocked&&((manifest is not null&&(page>0||ViewerOptions.Value.LoopBookPages))||canNavigatePrevious);
        next.IsEnabled=!blocked&&((manifest is not null&&ReaderSpreadPolicy.Move(page,manifest.PageCount,mode,1,ViewerOptions.Value.LoopBookPages)<manifest.PageCount)||canNavigateNext);
        retry.Visibility=failed?Visibility.Visible:Visibility.Collapsed;
        retry.IsEnabled=failed&&!blocked;reopen.IsEnabled=!blocked;settings.IsEnabled=!blocked;
        editDetails.IsEnabled=!closing&&!disposed;
        foreach(var option in modes)option.IsEnabled=!blocked;saveProgress.IsEnabled=!blocked&&loaded&&manifest is not null;
        zoom.Text=$"{viewport.ZoomFactor/OriginalZoom()*100:0}%";zoomOut.IsEnabled=loaded&&!busy&&viewport.ZoomFactor>viewport.MinZoomFactor;zoomIn.IsEnabled=loaded&&!busy&&viewport.ZoomFactor<viewport.MaxZoomFactor;actualSize.IsEnabled=loaded&&!busy;fit.IsEnabled=loaded&&!busy;
        var hasMultiPages=manifest is {PageCount:>1};
        scrubberHost.Visibility=hasMultiPages?Visibility.Visible:Visibility.Collapsed;
        pageScrubber.IsEnabled=!disposed&&!closing&&!favorite.IsSaving&&!navigatingOut&&hasMultiPages;
        if(manifest is {} currentBook&&!scrubberDragging&&pendingScrubPage is null)
        {
            updatingScrubber=true;
            try
            {
                pageScrubber.Maximum=Math.Max(1,currentBook.PageCount);
                pageScrubber.Value=Math.Clamp(page+1,1,currentBook.PageCount);
            }
            finally{updatingScrubber=false;}
        }
    }
    public void Dispose(){if(disposed)return;disposed=true;scrubTimer.Stop();favorite.Dispose();hideTimer.Dispose();menu.Hide();preload?.Cancel();lifetime.Cancel();pageCache.Dispose();ClearImages();manifest=null;lifetime.Dispose();}
}
