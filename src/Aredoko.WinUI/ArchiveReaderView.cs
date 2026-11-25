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
    private readonly MenuFlyoutItem saveProgress=new(){Text=AppText.L("読書位置を保存し直す", "Save reading progress again")};
    private readonly MenuFlyoutItem findSimilarPage1=new(){Text=AppText.L("≈ このページに似た画像を探す", "≈ Find similar images to this page")};
    private readonly MenuFlyoutItem findSimilarPage2=new(){Text=AppText.L("≈ もう一方のページに似た画像を探す", "≈ Find similar images to other page"),Visibility=Visibility.Collapsed};
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
            ViewerNotice.Set(progressStatus,error is null?"":AppText.L("読書位置を保存できませんでした。設定から保存し直せます。", "Could not save reading progress. You can save it again from Settings."));
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
        (pinButton,syncPin)=ViewerChromeController.CreatePinButton("ReaderPinToolbar",()=>{hideTimer.SyncPinState();hideTimer.RefreshHoverHint();},ex=>{ViewerNotice.Set(status,AppText.L("設定を保存できませんでした。", "Could not save settings."));AppLog.Error(ex);});
        menu=ViewerChromeController.Settings(true,()=>{syncPin();hideTimer.SyncPinState();FitImages();UpdateActions();},ex=>{ViewerNotice.Set(status,AppText.L("設定を保存できませんでした。", "Could not save settings."));AppLog.Error(ex);});
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
        Identify(pageScrubber,"ReaderPageSeek",AppText.L("ページ位置の移動", "Go to page"));
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
        Identify(favorite.Button,"ReaderFavorite",AppText.L("お気に入りを読み込み中", "Loading favorite state"));
        Identify(editDetails,"ReaderEditDetails",AppText.L("詳細で編集", "Edit in details"));
        editDetails.Click+=(_,_)=>EditDetailsRequested?.Invoke();
        toolbar.Child=actions;Children.Add(toolbar);ViewerChromeController.AttachNotices(this,76,status,progressStatus);
        Identify(actualSize,"ReaderActualSize",AppText.L("本のページを原寸で表示", "View book page at original size"));
        actualSize.Click+=(_,_)=>{if(OriginalZoom()<1){actualPixels=true;FitImages();viewport.ChangeView(0,0,1,true);}else ViewerInputGestures.ZoomCentered(viewport,(float)OriginalZoom());};
        Identify(viewport,"ReaderViewport",AppText.L("本の表示。左右キーでページ送り、右クリックで表示設定", "Book viewer. Left/Right keys to turn pages, right-click for display settings"));Identify(image,"ReaderImage",AppText.L("本のページ", "Book page"));Identify(second,"ReaderImageSecond",AppText.L("見開きのもう一方のページ", "Opposite spread page"));
        Identify(previous,"ReaderPrevious",AppText.L("前のページ", "Previous page"));Identify(next,"ReaderNext",AppText.L("次のページ", "Next page"));Identify(zoomOut,"ReaderZoomOut",AppText.L("本を縮小", "Zoom out book"));Identify(zoomIn,"ReaderZoomIn",AppText.L("本を拡大", "Zoom in book"));Identify(fit,"ReaderFit",AppText.L("本の表示をリセット", "Reset book zoom"));
        Identify(retry,"ReaderRetry",AppText.L("現在のページを再試行", "Retry current page"));Identify(reopen,"ReaderReopen",AppText.L("本を最初から開き直す", "Reopen book from page 1"));Identify(settings,"ReaderSettings",AppText.L("本の表示と操作", "Book display & actions"));
        Identify(toolbar,"ReaderToolbar",AppText.L("本の操作", "Book controls"));AutomationProperties.SetAutomationId(count,"ReaderPageNumber");AutomationProperties.SetAutomationId(status,"ReaderStatus");AutomationProperties.SetAutomationId(zoom,"ReaderZoomStatus");
        Identify(progressStatus,"ReaderProgressStatus",AppText.L("読書位置の保存状態", "Reading progress status"));Identify(saveProgress,"ReaderSaveProgress",AppText.L("読書位置を保存し直す", "Save reading progress again"));
        Identify(findSimilarPage1,"ReaderFindSimilarPage",AppText.L("このページに似た画像を探す", "Find similar images to this page"));
        Identify(findSimilarPage2,"ReaderFindSimilarPage2",AppText.L("2枚目のページに似た画像を探す", "Find similar images to second page"));
        findSimilarPage1.Click+=(_,_)=>{if(!busy&&!disposed&&loaded&&currentPageIndexes.Length>=1)FindSimilarPageRequested?.Invoke(itemId,currentPageIndexes[0]);};
        findSimilarPage2.Click+=(_,_)=>{if(!busy&&!disposed&&loaded&&currentPageIndexes.Length>=2)FindSimilarPageRequested?.Invoke(itemId,currentPageIndexes[1]);};
        AutomationProperties.SetLiveSetting(progressStatus,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        AutomationProperties.SetLiveSetting(status,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        foreach(var (button,text) in new (FrameworkElement,string)[]{(fit,AppText.L("画面に合わせる", "Fit to screen")),(actualSize,AppText.L("原寸表示（画像の1pxを画面の1pxで表示）", "Actual size (1:1 pixels)")),(zoomOut,AppText.L("縮小", "Zoom out")),(zoomIn,AppText.L("拡大", "Zoom in")),(previous,AppText.L("前のページ", "Previous page")),(next,AppText.L("次のページ", "Next page")),(editDetails,AppText.L("詳細でタグ・棚を編集（ビューアを閉じる）", "Edit tags & shelves in details (closes viewer)")),(retry,AppText.L("再試行", "Retry")),(reopen,AppText.L("先頭ページから開き直す", "Reopen from first page")),(settings,AppText.L("表示設定（単ページ・見開き・類似検索）", "Display settings (single / spread / similar)"))})
            hideTimer.AttachHoverHint(button,text);
        hideTimer.AttachHoverHint(favorite.Button,()=>AutomationProperties.GetName(favorite.Button));
        hideTimer.AttachHoverHint(zoom, () => image.Source is BitmapImage bmp && bmp.PixelWidth > 0 ? AppText.L($"表示倍率（原寸 {bmp.PixelWidth} × {bmp.PixelHeight} px）", $"Zoom (original {bmp.PixelWidth} × {bmp.PixelHeight} px)") : AppText.L("表示倍率", "Zoom"));
        hideTimer.AttachHoverHint(count, AppText.L("ページ位置（左右キーまたはバーで移動）", "Page position (Left/Right keys or slider)"));
        hideTimer.AttachHoverHint(pinButton,()=>ViewerOptions.Value.AlwaysShowControls?AppText.L("操作バーの固定を解除", "Unpin control bar"):AppText.L("操作バーを常に表示（ピン留め）", "Always show control bar (Pin)"));
        menu.Items.Add(findSimilarPage1);menu.Items.Add(findSimilarPage2);menu.Items.Add(new MenuFlyoutSeparator());
        foreach(var (value,label,id) in new[]{(ReaderDisplayMode.Single,AppText.L("単ページ", "Single page"),"ReaderSingle"),(ReaderDisplayMode.RightToLeft,AppText.L("見開き（右→左）", "Spread (Right → Left)"),"ReaderRtl"),(ReaderDisplayMode.LeftToRight,AppText.L("見開き（左→右）", "Spread (Left → Right)"),"ReaderLtr")})
        {
            var option=new RadioMenuFlyoutItem{Text=label,GroupName="ReaderDisplay",Tag=value,IsChecked=value==ReaderDisplayMode.Single};Identify(option,id,label);modes.Add(option);menu.Items.Add(option);
            option.Click+=async(_,_)=>{if(busy||disposed)return;allowProgressSave=true;mode=value;previous.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Forward:Symbol.Back);next.Content=new SymbolIcon(mode==ReaderDisplayMode.RightToLeft?Symbol.Back:Symbol.Forward);if(manifest is not null)await LoadAsync(ReaderSpreadPolicy.Anchor(page,manifest.PageCount,mode));};
        }
        menu.Items.Add(new MenuFlyoutSeparator());menu.Items.Add(saveProgress);
        saveProgress.Click+=async(_,_)=>{if(busy||disposed||!loaded||manifest is null)return;allowProgressSave=true;busy=true;UpdateActions();try{await SaveProgressAsync(manifest);}finally{busy=false;if(!disposed)UpdateActions();}};
        menu.Opened+=(_,_)=>{
            if(!busy&&!disposed&&loaded&&manifest is not null&&currentPageIndexes.Length>0)
            {
                if(currentPageIndexes.Length==1)
                {
                    findSimilarPage1.Text=AppText.L($"≈ このページ（{currentPageIndexes[0]+1}ページ目）に似た画像・動画を探す", $"≈ Find similar to this page (p.{currentPageIndexes[0]+1})");
                    AutomationProperties.SetName(findSimilarPage1,findSimilarPage1.Text);
                    findSimilarPage1.IsEnabled=true;findSimilarPage1.Visibility=Visibility.Visible;
                    findSimilarPage2.Visibility=Visibility.Collapsed;
                }
                else
                {
                    findSimilarPage1.Text=AppText.L($"≈ {currentPageIndexes[0]+1}ページ目に似た画像・動画を探す", $"≈ Find similar to p.{currentPageIndexes[0]+1}");
                    AutomationProperties.SetName(findSimilarPage1,findSimilarPage1.Text);
                    findSimilarPage1.IsEnabled=true;findSimilarPage1.Visibility=Visibility.Visible;
                    findSimilarPage2.Text=AppText.L($"≈ {currentPageIndexes[1]+1}ページ目に似た画像・動画を探す", $"≈ Find similar to p.{currentPageIndexes[1]+1}");
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
            ShowBoundaryNotice(direction<0?AppText.L("先頭のページです", "First page"):AppText.L("最後のページです", "Last page"));
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
        if(busy||disposed||closing||favorite.IsSaving)return;busy=true;failed=loaded=false;manifest=null;page=0;ClearImages();pageCache.Clear();preload?.Cancel();count.Text="—";ViewerNotice.Set(status,AppText.L("本を開いています…", "Opening book..."));hideTimer.Stop();UpdateActions();
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
            {allowProgressSave=fromBeginning;ViewerNotice.Set(progressStatus,AppText.L("読書位置を読み込めないため先頭から表示します", "Could not load reading progress; opening from page 1"));}
            if(!fromBeginning&&(initialPageMatch?.InitialReaderPage(result)??initialMatch?.InitialReaderPage(result)) is int requested)
            {
                start=ReaderSpreadPolicy.Anchor(requested,result.PageCount,mode);
            }
            else if(openAtEnd&&!fromBeginning)
            {
                start=ReaderSpreadPolicy.Anchor(result.PageCount-1,result.PageCount,mode);
            }
            if(cancellation.IsCancellationRequested)return;
            foreach(var option in modes)option.IsChecked=option.Tag is ReaderDisplayMode m&&m==mode;
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
        if(progressWriter.HasPending){ViewerNotice.Set(progressStatus,AppText.L("読書位置を保存しています…", "Saving reading progress..."));ShowChrome();}
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
        ViewerNotice.Set(status,AppText.L("ページを読み込んでいます…", "Loading page..."));UpdateActions();
        try
        {
            // Finish cancelled speculative work before foreground reads.
            await preloadTask;
            trace.Mark("preload-drained");
            var bitmaps=await Task.WhenAll(indexes.Select(index=>ReadPageAsync(book,index,cancellation)));
            if(disposed||closing||manifest!=book)return;
            page=target;viewport.ChangeView(0,0,1,true);
            currentPageIndexes=indexes;
            image.Source=bitmaps[0];AutomationProperties.SetName(image,AppText.L($"{indexes[0]+1}ページ", $"Page {indexes[0]+1}"));
            if(bitmaps.Length==2){second.Source=bitmaps[1];second.Visibility=Visibility.Visible;AutomationProperties.SetName(second,AppText.L($"{indexes[1]+1}ページ", $"Page {indexes[1]+1}"));}
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
    private void ClearImages(){currentPageIndexes=[];image.Source=second.Source=null;second.Visibility=Visibility.Collapsed;AutomationProperties.SetName(image,AppText.L("ページ未表示", "Page not loaded"));AutomationProperties.SetName(second,AppText.L("ページ未表示", "Page not loaded"));}
    private void ReportFailure(Exception ex)
    {
        if(disposed||cancellation.IsCancellationRequested)return;ClearImages();failed=true;loaded=false;ViewerNotice.Set(progressStatus,AppText.L("前に読めたページの位置を保持しています", "Keeping previously read page position"));
        if(ex is ArchiveReadException{RequiresReopen:true}){manifest=null;count.Text="—";}
        ViewerNotice.Set(status,ex switch{ArchiveReadException=>ex.Message,OperationCanceledException=>AppText.L("読み込みがタイムアウトしました。再試行してください", "Loading timed out. Please retry."),HttpRequestException=>AppText.L("接続できません。閉じて再接続してください", "Cannot connect. Close and reconnect."),_=>AppText.L("表示できません（未対応形式または破損）", "Cannot display (unsupported format or corrupted)")});ShowChrome();
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
