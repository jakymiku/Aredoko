using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.System;
using System.Runtime.InteropServices.WindowsRuntime;

namespace Aredoko_WinUI;

// Hallmark · pre-emit critique: P4 H4 E4 S4 R5 V3 (native component scope).
// Existing Fluent tokens/states; image first, compact chrome, no page macrostructure.
// One bounded display image and one loading pipeline; never opens a source path.
internal sealed class ImageViewerView : Grid, IDisposable, IViewerWindowTitle
{
    private bool actualPixels;
    private readonly LibraryApi api;
    private readonly ImageViewerSequence sequence;
    private readonly Func<int, int, CancellationToken, Task<ResultNeighbor?>>? visualNeighbor;
    private readonly Func<int, CancellationToken, Task<ResultNeighbor?>>? visualAtOrdinal;
    private readonly ViewerFavoriteAction favorite;
    private bool visualPrevExhausted, visualNextExhausted;
    public event Action<int,bool,bool>? FavoriteChanged;
    public Task FlushFavoriteAsync()=>favorite.FlushAsync();
    private readonly CancellationTokenSource lifetime = new();
    private readonly ViewerChromeController hideTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer animTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer scrubTimer;
    private readonly Border toolbarHost = new() { VerticalAlignment = VerticalAlignment.Bottom, HorizontalAlignment = HorizontalAlignment.Center, RequestedTheme = ElementTheme.Dark };
    private readonly Button settings = IconButton(Symbol.Setting);
    private bool menuOpen, updatingScrubber, scrubberDragging;
    private int scrubTargetOrdinal;
    public string WindowTitle=>$"{sequence.Current.Title}（{sequence.Position+1}/{sequence.Count}）— Aredoko";
    public event Action<string>? TitleChanged;
    private bool keyboardChrome, failed;
    public event Action<int>? ContentOpened;
    public event EventHandler? CloseRequested;
    public event Action? EditDetailsRequested;
    public event Action? ToggleMaximizeRequested;
    public event Action<int>? FindSimilarRequested;
    public event Func<ResultNeighbor, int, Task>? NavigateToItemRequested;
    private CancellationTokenSource? request;
    private ViewerImageCodec.NativeAnimation? nativeAnimation;
    private readonly ViewerPageCache<int,BitmapImage> staticCache=new(3,96*1024*1024);
    private AnimationStream? animationStream;
    private CancellationTokenSource? animationRequest;
    private readonly Queue<AnimationFrame> animationFrames = new();
    private WriteableBitmap? animationBitmap;
    private bool animationFetching, animationWaiting, animationDone;
    private readonly AnimationPlaybackClock animationClock=new();
    private int animationWidth, animationHeight;
    private readonly Grid canvas = new();
    private readonly Image image = new() { Stretch = Stretch.Uniform, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
    private double imageWidth = 1, imageHeight = 1;
    private readonly ScrollViewer viewport = new()
    {
        ZoomMode = ZoomMode.Enabled, MinZoomFactor = 1, MaxZoomFactor = 4, IsTabStop = true,
        HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        HorizontalContentAlignment = HorizontalAlignment.Center, VerticalContentAlignment = VerticalAlignment.Center,
        RequestedTheme = ElementTheme.Dark
    };
    private readonly Button previous = IconButton(Symbol.Back);
    private readonly Button next = IconButton(Symbol.Forward);
    private readonly Button zoomOut = IconButton(Symbol.ZoomOut);
    private readonly Button zoomIn = IconButton(Symbol.ZoomIn);
    private readonly Button fit = IconButton(Symbol.FullScreen);
    private readonly Button actualSize=ViewerChromeController.PillTextButton("1:1");
    private readonly Button retry = IconButton(Symbol.Refresh);
    private readonly Button editDetails = IconButton(Symbol.Edit);
    private readonly Microsoft.UI.Xaml.Controls.Primitives.ToggleButton pinButton;
    private readonly Action syncPin;
    private readonly Slider sequenceScrubber = new() { Minimum = 1, Maximum = 1, Value = 1, SmallChange = 1, LargeChange = 5, StepFrequency = 1, IsThumbToolTipEnabled = false };
    private readonly Border scrubberHost;
    private readonly TextBlock title = new() { TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock count = new() { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(4, 0, 4, 0) };
    private readonly TextBlock zoom = new() { Text = "100%", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock status = new() { Visibility = Visibility.Collapsed, TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center };
    private bool busy, disposed, loaded, navigating;
    private int version;

    public ImageViewerView(LibraryApi api, ImageViewerSequence sequence,ResultSession? favoriteSession=null, Func<int, int, CancellationToken, Task<ResultNeighbor?>>? visualNeighbor = null, Func<int, CancellationToken, Task<ResultNeighbor?>>? visualAtOrdinal = null)
    {
        this.api = api; this.sequence = sequence; this.visualNeighbor = visualNeighbor; this.visualAtOrdinal = visualAtOrdinal;
        favorite=new(favoriteSession,message=>ViewerNotice.Set(status,message));
        favorite.Attach();favorite.Changed+=(id,value,kept)=>FavoriteChanged?.Invoke(id,value,kept);
        favorite.ReturnRequested+=()=>CloseRequested?.Invoke(this,EventArgs.Empty);
        favorite.StateChanged+=()=>{if(favorite.IsSaving)ShowChrome();UpdateControls();};
        hideTimer = new(this,toolbarHost,viewport,()=>keyboardChrome||menuOpen||scrubberDragging||favorite.IsSaving);
        animTimer = DispatcherQueue.CreateTimer(); animTimer.IsRepeating = false;
        animTimer.Tick += (_, _) => AdvanceAnimationFrame();
        scrubTimer = DispatcherQueue.CreateTimer(); scrubTimer.Interval = TimeSpan.FromMilliseconds(80); scrubTimer.IsRepeating = false;
        scrubTimer.Tick += async (_, _) => await JumpToOrdinalAsync(scrubTargetOrdinal);
        scrubberHost = ViewerChromeController.WrapScrubber(sequenceScrubber, 160);
        scrubberHost.Visibility = sequence.Count > 1 && (!sequence.IsSession || visualAtOrdinal is not null) ? Visibility.Visible : Visibility.Collapsed;
        (pinButton, syncPin) = ViewerChromeController.CreatePinButton("ImagePinToolbar", () => hideTimer.SyncPinState(), ex => { ViewerNotice.Set(status, "設定を保存できませんでした。"); AppLog.Error(ex); });
        ViewerChromeController.StyleFloatingPill(toolbarHost);
        viewport.Style = (Style)Application.Current.Resources["ImageViewerCanvasStyle"];
        canvas.Children.Add(image); viewport.Content = canvas; Children.Add(viewport);
        ViewerInputGestures.AttachPan(viewport);
        viewport.SizeChanged += (_, _) => FitImage();
        viewport.ViewChanged += (_, _) => UpdateControls();
        ViewerChromeController.StylePillButton(favorite.Button);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, HorizontalAlignment = HorizontalAlignment.Center };
        foreach (var control in new UIElement[] { fit, actualSize, zoomOut, zoomIn, zoom, ViewerChromeController.Divider(), previous, count, next, scrubberHost, ViewerChromeController.Divider(), favorite.Button, editDetails, retry, settings, pinButton }) actions.Children.Add(control);
        Identify(sequenceScrubber, "ImageSequenceSeek", "作品位置の移動");
        sequenceScrubber.AddHandler(PointerPressedEvent, new PointerEventHandler((_, _) => { scrubberDragging = true; hideTimer.Show(); }), true);
        sequenceScrubber.AddHandler(PointerReleasedEvent, new PointerEventHandler((_, _) => { scrubberDragging = false; hideTimer.Start(); }), true);
        sequenceScrubber.PointerCaptureLost += (_, _) => { scrubberDragging = false; };
        sequenceScrubber.ValueChanged += (_, _) =>
        {
            if (updatingScrubber || disposed || sequence.Count <= 1) return;
            scrubTargetOrdinal = Math.Clamp((int)Math.Round(sequenceScrubber.Value) - 1, 0, sequence.Count - 1);
            scrubTimer.Stop(); scrubTimer.Start();
        };
        Identify(favorite.Button,"ImageFavorite","お気に入りを読み込み中");
        Identify(editDetails,"ImageEditDetails","詳細で編集");
        ToolTipService.SetToolTip(editDetails,"閉じて詳細パネルを開く");
        editDetails.Click+=(_,_)=>EditDetailsRequested?.Invoke();
        toolbarHost.Child=actions;Children.Add(toolbarHost);ViewerChromeController.AttachNotices(this,76,status);
        title.Style = count.Style = zoom.Style = status.Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"];
        Identify(viewport, "ImageViewport", "画像表示。左右キーで画像送り、拡大してスクロールできます");
        Identify(image, "ViewerImage", sequence.Current.Title + "の画像");
        Identify(toolbarHost, "ImageToolbar", "画像の操作");
        Identify(previous, "ImagePrevious", "前の画像"); Identify(next, "ImageNext", "次の画像");
        Identify(zoomOut, "ImageZoomOut", "画像を縮小"); Identify(zoomIn, "ImageZoomIn", "画像を拡大");
        Identify(actualSize,"ImageActualSize","画像を原寸で表示");ToolTipService.SetToolTip(actualSize,"原寸表示（画像の1pxを画面の1pxで表示）");
        Identify(fit, "ImageFit", "画像の表示をリセット"); Identify(retry, "ImageRetry", "画像を再試行");
        ToolTipService.SetToolTip(previous, "前の画像（←）"); ToolTipService.SetToolTip(next, "次の画像（→）");
        ToolTipService.SetToolTip(zoomOut, "縮小"); ToolTipService.SetToolTip(zoomIn, "拡大");
        ToolTipService.SetToolTip(fit, "画面に合わせる"); ToolTipService.SetToolTip(retry, "読み込みを再試行");
        AutomationProperties.SetAutomationId(title, "ImageTitle"); AutomationProperties.SetAutomationId(count, "ImagePosition");
        AutomationProperties.SetAutomationId(zoom, "ImageZoomStatus"); AutomationProperties.SetAutomationId(status, "ImageStatus");
        AutomationProperties.SetLiveSetting(status, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        Identify(settings,"ImageSettings","画像ビューアの設定");ToolTipService.SetToolTip(settings,"表示・操作バーの設定");
        var menu=ViewerChromeController.Settings(false,()=>{syncPin();hideTimer.SyncPinState();FitImage();UpdateControls();},ex=>{ViewerNotice.Set(status,"設定を保存できませんでした。");AppLog.Error(ex);});
        var findSimilar=new MenuFlyoutItem{Text="≈ この画像に似た画像・動画を探す"};
        Identify(findSimilar,"ImageFindSimilar","この画像に似た画像・動画を探す");
        findSimilar.Click+=(_,_)=>{if(!busy&&!navigating&&loaded)FindSimilarRequested?.Invoke(sequence.Current.Id);};
        menu.Items.Insert(0,findSimilar);
        menu.Items.Insert(1,new MenuFlyoutSeparator());
        settings.Flyout=menu;viewport.ContextFlyout=menu;
        menu.Opened+=(_,_)=>{findSimilar.IsEnabled=!busy&&!navigating&&loaded;menuOpen=true;ShowChrome();};menu.Closed+=(_,_)=>{menuOpen=false;hideTimer.Start();};
        viewport.DoubleTapped+=(_,args)=>{if(ViewerInputGestures.IsInteractiveControl(args.OriginalSource,viewport))return;args.Handled=true;ToggleMaximizeRequested?.Invoke();};
        previous.Click += async (_, _) => await MoveAsync(-1); next.Click += async (_, _) => await MoveAsync(1);
        zoomOut.Click += (_, _) => ViewerInputGestures.ZoomCentered(viewport,Math.Max(viewport.MinZoomFactor, viewport.ZoomFactor - .5f));
        zoomIn.Click += (_, _) => ViewerInputGestures.ZoomCentered(viewport,Math.Min(viewport.MaxZoomFactor, viewport.ZoomFactor + .5f));
        fit.Click += (_, _) => {actualPixels=false;FitImage();viewport.ChangeView(0,0,1,true);};
        actualSize.Click+=(_,_)=>{if(OriginalZoom()<1){actualPixels=true;FitImage();viewport.ChangeView(0,0,1,true);}else ViewerInputGestures.ZoomCentered(viewport,(float)OriginalZoom());};
        retry.Click += async (_, _) => await OpenAsync();
        UpdateIdentity(); UpdateControls();
    }
    public void FocusViewport()=>viewport.Focus(FocusState.Programmatic);
    private void ShowChrome()=>hideTimer.Show();
    private static Button IconButton(Symbol symbol) => ViewerChromeController.PillButton(symbol);
    private static void Identify(DependencyObject control, string id, string name)
    { AutomationProperties.SetAutomationId(control, id); AutomationProperties.SetName(control, name); }
    private void FitImage()
    {
        canvas.Width = Math.Max(1, viewport.ActualWidth); canvas.Height = Math.Max(1, viewport.ActualHeight);
        var scale = actualPixels?1/(XamlRoot?.RasterizationScale??1):Math.Min(ViewerOptions.Value.EnlargeSmallImages?double.PositiveInfinity:1/(XamlRoot?.RasterizationScale??1),Math.Min(canvas.Width / imageWidth, canvas.Height / imageHeight));
        image.Width = imageWidth * scale; image.Height = imageHeight * scale;
        viewport.MaxZoomFactor=(float)Math.Max(4,OriginalZoom());
        ToolTipService.SetToolTip(image,$"{imageWidth:0} × {imageHeight:0} px");
        AutomationProperties.SetHelpText(image,$"{imageWidth:0} x {imageHeight:0} pixels");
    }
    private double OriginalZoom()=>double.IsFinite(image.Width)&&image.Width>0?Math.Max(.001,imageWidth/image.Width/(XamlRoot?.RasterizationScale??1)):1;
    private void UpdateIdentity()
    {
        TitleChanged?.Invoke(WindowTitle);
        title.Text = sequence.Current.Title; ToolTipService.SetToolTip(title, title.Text);
        count.Text = $"{sequence.Position + 1} / {sequence.Count}";
        ToolTipService.SetToolTip(count, sequence.IsSession ? "検索結果内の位置。画像だけを検索順に移動します" : "現在の検索結果ページに含まれる画像");
        AutomationProperties.SetName(image, title.Text + "の画像");
        favorite.Refresh(sequence.Current.Id,sequence.Position);
    }
    private void UpdateControls()
    {
        previous.IsEnabled = !disposed && !navigating && !favorite.IsSaving && sequence.HasPrevious && !visualPrevExhausted; next.IsEnabled = !disposed && !navigating && !favorite.IsSaving && sequence.HasNext && !visualNextExhausted;
        favorite.UpdateAvailability(!disposed&&!navigating&&loaded);
        editDetails.IsEnabled=!disposed&&!navigating&&loaded;
        retry.Visibility = failed ? Visibility.Visible : Visibility.Collapsed;
        retry.IsEnabled = failed && !busy && !navigating && !disposed;
        zoom.Text = loaded?$"{viewport.ZoomFactor/OriginalZoom() * 100:0}%":"—";
        zoomOut.IsEnabled = loaded && !busy && viewport.ZoomFactor > viewport.MinZoomFactor;
        zoomIn.IsEnabled = loaded && !busy && viewport.ZoomFactor < viewport.MaxZoomFactor; actualSize.IsEnabled=loaded&&!busy; fit.IsEnabled = loaded && !busy;
        var hasScrubber = sequence.Count > 1 && (!sequence.IsSession || visualAtOrdinal is not null);
        scrubberHost.Visibility = hasScrubber ? Visibility.Visible : Visibility.Collapsed;
        sequenceScrubber.IsEnabled = !disposed && !navigating && !favorite.IsSaving && hasScrubber;
        updatingScrubber = true;
        try
        {
            sequenceScrubber.Maximum = Math.Max(1, sequence.Count);
            sequenceScrubber.Value = Math.Clamp(sequence.Position + 1, 1, Math.Max(1, sequence.Count));
        }
        finally { updatingScrubber = false; }
        ToolTipService.SetToolTip(sequenceScrubber, $"{sequence.Position + 1} / {sequence.Count}");
    }
    // Tunnel before ScrollViewer consumes arrow keys; scope is this modal only.
    public void AttachNavigation(UIElement dialog)
    {
        ViewerInputGestures.Attach(dialog,viewport,MoveAsync);
        dialog.AddHandler(PointerMovedEvent, new PointerEventHandler((_, _) => { keyboardChrome = false; }), true);
        dialog.PreviewKeyDown += async (_, args) =>
        {
            if (menuOpen) return;
            if (args.Key == VirtualKey.Escape) { args.Handled = true; CloseRequested?.Invoke(this, EventArgs.Empty); return; }
            if (args.Key is VirtualKey.Tab or VirtualKey.F10)
            { keyboardChrome = true; ShowChrome(); if (args.Key == VirtualKey.F10) args.Handled = true; return; }
            if (args.Key is not (VirtualKey.Left or VirtualKey.Right)) return;
            foreach (var modifier in new[] { VirtualKey.Control, VirtualKey.Shift, VirtualKey.Menu, VirtualKey.LeftWindows, VirtualKey.RightWindows })
                if ((Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(modifier) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0) return;
            args.Handled = true; await MoveAsync(args.Key == VirtualKey.Left ? -1 : 1);
        };
    }
    private void StopAnimation(bool preserveCurrent=false)
    {
        animTimer.Stop();
        if(nativeAnimation is not null)
        {
            if(preserveCurrent){if(nativeAnimation.Bitmap.IsAnimatedBitmap)nativeAnimation.Bitmap.Stop();}
            else{image.Source=null;nativeAnimation.Dispose();nativeAnimation=null;}
        }
        animationRequest?.Cancel(); animationRequest?.Dispose(); animationRequest = null;
        var oldStream = animationStream; animationStream = null;
        if (oldStream is not null) _ = CloseAnimationAsync(oldStream);
        animationFrames.Clear(); animationBitmap = null;
        animationClock.Reset();
        animationFetching = animationWaiting = animationDone = false;
    }

    private static async Task CloseAnimationAsync(AnimationStream stream)
    {
        try { await stream.DisposeAsync(); }
        catch (Exception ex) { AppLog.Error(ex); }
    }

    private void DisplayAnimationFrame(AnimationFrame frame)
    {
        animationBitmap ??= new WriteableBitmap(animationWidth, animationHeight);
        using (var pixels = animationBitmap.PixelBuffer.AsStream()) pixels.Write(frame.Pixels);
        animationBitmap.Invalidate();
        if(!ReferenceEquals(image.Source,animationBitmap))image.Source = animationBitmap;
        AutomationProperties.SetName(image, $"{sequence.Current.Title}の画像（アニメーション {frame.Index + 1}）");
        var now=System.Diagnostics.Stopwatch.GetTimestamp()*1000d/System.Diagnostics.Stopwatch.Frequency;
        animTimer.Interval = TimeSpan.FromMilliseconds(animationClock.NextDelay(now,frame.DurationMs));
        animTimer.Start();
    }

    private void AdvanceAnimationFrame()
    {
        if (disposed || animationStream is null) return;
        if (animationFrames.TryDequeue(out var frame))
        {
            if(animationWaiting)animationClock.Reset();
            animationWaiting = false; DisplayAnimationFrame(frame);
            _ = FillAnimationAsync();
        }
        else if (animationDone)
        {
            var finished = animationStream; animationStream = null;
            _ = CloseAnimationAsync(finished); // Retain the last successfully displayed frame.
        }
        else
        {
            animationWaiting = true; _ = FillAnimationAsync();
        }
    }

    private async Task FillAnimationAsync()
    {
        if (disposed || animationFetching || animationDone || animationStream is null || animationRequest is null) return;
        var capacity=AnimationStreamClient.BufferCapacity(animationWidth,animationHeight);
        if(animationFrames.Count>=capacity)return;
        var stream = animationStream; var stamp = version; var ct = animationRequest.Token;
        animationFetching = true;
        try
        {
            // Queued + in-flight raw pixels stay within four frames/128MiB.
            // Larger original frames reduce the count instead of the resolution.
            // Each frame owns its bytes; consumed batches retain no old arrays.
            var batch = await stream.ReadAsync(capacity - animationFrames.Count, ct);
            if (disposed || stamp != version || stream != animationStream || ct.IsCancellationRequested) return;
            if (batch.Width != animationWidth || batch.Height != animationHeight) throw new InvalidDataException("Animation dimensions changed");
            foreach (var frame in batch.Frames) animationFrames.Enqueue(frame);
            animationDone = batch.Done;
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
        catch (Exception ex)
        {
            if (!disposed && stamp == version && stream == animationStream)
            {
                StopAnimation(true); failed = true; UpdateControls();
                ViewerNotice.Set(status, "アニメーションを読み取れません。開き直してください。"); ShowChrome(); AppLog.Error(ex);
            }
        }
        finally
        {
            if (!disposed && stamp == version && stream == animationStream)
            {
                animationFetching = false;
                if (animationWaiting) AdvanceAnimationFrame();
            }
        }
    }

    public async Task MoveAsync(int direction)
    {
        if (disposed || navigating || menuOpen || favorite.IsSaving) return;
        if (direction < 0 ? (!sequence.HasPrevious || visualPrevExhausted) : (!sequence.HasNext || visualNextExhausted)) return;
        var moved = false; ResultNeighbor? handoffTarget = null;
        navigating = true; UpdateControls();
        try
        {
            if (visualNeighbor is not null)
            {
                var target = await visualNeighbor(sequence.Current.Id, direction, lifetime.Token);
                if (disposed) return;
                if (target is null)
                {
                    if (direction < 0) visualPrevExhausted = true; else visualNextExhausted = true;
                    ViewerNotice.Set(status, direction < 0 ? "前の作品はありません" : "次の作品はありません");
                    ShowChrome();
                }
                else if (ImageViewerPolicy.CanOpen(target.Item))
                {
                    sequence.MoveTo(target);
                    visualPrevExhausted = visualNextExhausted = false;
                    moved = true;
                }
                else if (ArchiveManifest.CanOpen(target.Item))
                {
                    handoffTarget = target;
                }
            }
            else
            {
                moved = await sequence.TryMoveAsync(direction, lifetime.Token);
            }
        }
        catch (OperationCanceledException) when (disposed || lifetime.IsCancellationRequested) { }
        catch (Exception ex)
        {
            if (disposed) return;
            failed = true; ShowChrome();
            ViewerNotice.Set(status, ex is ResultSessionException
                ? "結果の有効期限が切れました。閉じて再検索してください"
                : "次の作品を取得できません。接続を確認して再試行してください");
            AppLog.Error(ex);
        }
        finally { navigating = false; if (!disposed && handoffTarget is null) UpdateControls(); }
        if (handoffTarget is not null && !disposed)
        {
            await favorite.FlushAsync();
            if (!disposed && NavigateToItemRequested is not null)
                await NavigateToItemRequested(handoffTarget, direction);
            return;
        }
        if (!moved || disposed) return;
        actualPixels=false;version++; loaded = false; StopAnimation(true); retry.IsEnabled = false;
        UpdateIdentity(); ViewerNotice.Set(status,"画像を読み込んでいます…"); UpdateControls();
        // New navigation may cancel a slow foreground image while the old
        // pipeline drains; only neighbor lookup itself is single-flight.
        if (busy) { request?.Cancel(); return; }
        await OpenAsync();
    }
    private async Task JumpToOrdinalAsync(int targetOrdinal)
    {
        if (disposed || menuOpen || sequence.Count <= 1) return;
        if (navigating || favorite.IsSaving) { scrubTimer.Stop(); scrubTimer.Start(); return; }
        if (targetOrdinal == sequence.Position) return;
        var direction = targetOrdinal >= sequence.Position ? 1 : -1;
        var moved = false; ResultNeighbor? handoffTarget = null;
        navigating = true; UpdateControls();
        try
        {
            if (!sequence.IsSession)
            {
                moved = sequence.TryJumpTo(targetOrdinal);
            }
            else if (visualAtOrdinal is not null)
            {
                var target = await visualAtOrdinal(targetOrdinal, lifetime.Token);
                if (disposed) return;
                if (target is null)
                {
                    ViewerNotice.Set(status, "移動先に画像・本がありません");
                    ShowChrome();
                }
                else if (target.Item.Id == sequence.Current.Id)
                {
                    return;
                }
                else if (ImageViewerPolicy.CanOpen(target.Item))
                {
                    sequence.MoveTo(target);
                    visualPrevExhausted = visualNextExhausted = false;
                    moved = true;
                }
                else if (ArchiveManifest.CanOpen(target.Item))
                {
                    handoffTarget = target;
                }
            }
        }
        catch (OperationCanceledException) when (disposed || lifetime.IsCancellationRequested) { }
        catch (Exception ex)
        {
            if (disposed) return;
            failed = true; ShowChrome();
            ViewerNotice.Set(status, ex is ResultSessionException
                ? "結果の有効期限が切れました。閉じて再検索してください"
                : "指定位置の作品を取得できません。接続を確認して再試行してください");
            AppLog.Error(ex);
        }
        finally { navigating = false; if (!disposed && handoffTarget is null) UpdateControls(); }
        if (handoffTarget is not null && !disposed)
        {
            await favorite.FlushAsync();
            if (!disposed && NavigateToItemRequested is not null)
                await NavigateToItemRequested(handoffTarget, direction);
            return;
        }
        if (!moved || disposed) return;
        actualPixels=false;version++; loaded = false; StopAnimation(true); retry.IsEnabled = false;
        UpdateIdentity(); ViewerNotice.Set(status,"画像を読み込んでいます…"); UpdateControls();
        if (busy) { request?.Cancel(); return; }
        await OpenAsync();
    }
    public async Task OpenAsync()
    {
        if (busy || disposed) return;
        busy = true; hideTimer.Stop();
        try
        {
            int requestedVersion;
            do
            {
                requestedVersion = version;
                loaded = false; failed = false; retry.IsEnabled = false; StopAnimation(true);
                ViewerNotice.Set(status,"画像を読み込んでいます…"); UpdateControls();
                using var loading = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                request = loading; var cancellation = loading.Token; var item = sequence.Current;
                var trace=new ViewerLoadTrace("image");
                try
                {
                    // Routing follows the guarded source header, including renamed
                    // WebP/GIF/PNG files. This probe does not enumerate all frames.
                    var sourceInfo=await api.ImageInfoAsync(item.Id,cancellation);
                    if(disposed||requestedVersion!=version)continue;
                    if(sourceInfo.IsNativeGif)
                    {
                        var source=await api.OriginalImageAsync(item.Id,cancellation);
                        trace.Mark("source-body");
                        ViewerImageCodec.NativeAnimation? decoded=null;
                        try {decoded=await ViewerImageCodec.DecodeGifAsync(source,cancellation);}
                        catch(Exception ex) when(ex is System.Runtime.InteropServices.COMException or InvalidDataException or ArgumentException)
                        {AppLog.Error(ex);} // Try the owned streaming decoder below.
                        if(decoded is not null)
                        {
                            trace.Mark("decode-ready");
                            if(disposed||requestedVersion!=version){decoded.Dispose();continue;}
                            StopAnimation();nativeAnimation=decoded;var bitmap=decoded.Bitmap;
                            imageWidth=Math.Max(1,bitmap.PixelWidth);imageHeight=Math.Max(1,bitmap.PixelHeight);
                            FitImage();image.Source=bitmap;loaded=true;viewport.ChangeView(0,0,1,true);
                            AutomationProperties.SetName(image,item.Title+"の画像");
                            trace.Mark("assigned");
                            ContentOpened?.Invoke(item.Id);ViewerNotice.Set(status);
                            continue;
                        }
                    }
                    if (sourceInfo.AnimationCandidate)
                    {
                        var opened = await api.Animations.OpenFirstAsync(sourceInfo, cancellation);
                        var stream = opened.Stream;
                        try
                        {
                            var first = opened.First;
                            if (first.Frames.Count != 1) throw new InvalidDataException("Animation has no first frame");
                            if (disposed || requestedVersion != version) { await stream.DisposeAsync(); continue; }
                            StopAnimation(); animationStream = stream;
                            animationRequest = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                            animationWidth = first.Width; animationHeight = first.Height; animationDone = first.Done;
                            imageWidth = first.Width; imageHeight = first.Height; FitImage();
                            DisplayAnimationFrame(first.Frames[0]);
                            trace.Mark("first-frame-assigned");
                            loaded = true; viewport.ChangeView(0, 0, 1, true);
                            ContentOpened?.Invoke(item.Id); ViewerNotice.Set(status);
                            _ = FillAnimationAsync();
                        }
                        catch { await stream.DisposeAsync(); throw; }
                    }
                    else
                    {
                        var bitmap=await staticCache.ReadAsync(item.Id,async(etag,ct)=>
                        {
                            var result=await api.OriginalImageSourceAsync(item.Id,etag,ct);
                            trace.Mark(result.NotModified?"source-revalidated":"source-body");return result;
                        },async(data,speculative,ct)=>
                        {
                            var result=await ViewerImageCodec.DecodeCachedAsync(data,speculative,ct);trace.Mark("decode-ready");return result;
                        },cancellation);
                        if (disposed || requestedVersion != version) continue;
                        StopAnimation();
                        imageWidth = Math.Max(1, bitmap.PixelWidth); imageHeight = Math.Max(1, bitmap.PixelHeight);
                        FitImage(); image.Source = bitmap; loaded = true; viewport.ChangeView(0, 0, 1, true);
                        AutomationProperties.SetName(image,item.Title+"の画像");
                        trace.Mark("assigned");
                        ContentOpened?.Invoke(sequence.Current.Id);
                        ViewerNotice.Set(status);
                    }
                }
                catch (Exception ex)
                {
                    if (disposed || requestedVersion != version) continue;
                    StopAnimation(true);
                    ViewerNotice.Set(status,ex switch
                    {
                        ArchiveReadException { Status: System.Net.HttpStatusCode.NotFound } => "画像を読み込めません（未接続・破損の可能性）",
                        ArchiveReadException => ex.Message,
                        OperationCanceledException => "読み込みがタイムアウトしました。再試行してください",
                        HttpRequestException => "接続できません。閉じて再接続してください",
                        _ => "表示できません（未対応形式または破損）"
                    });
                    failed = true; retry.IsEnabled = true; ShowChrome();
                }
                finally { request = null; }
            } while (!disposed && requestedVersion != version);
        }
        finally { busy = false; if (!disposed) { UpdateControls(); if (!keyboardChrome && !failed) hideTimer.Start(); } }
    }
    public void Dispose()
    { if (disposed) return; disposed = true; scrubTimer.Stop(); favorite.Dispose();hideTimer.Dispose(); StopAnimation(); lifetime.Cancel(); staticCache.Dispose();image.Source = null; lifetime.Dispose(); }
}
