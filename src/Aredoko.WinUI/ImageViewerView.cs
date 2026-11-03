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
    private readonly ResultSession? favoriteSession;
    private readonly Button favorite=IconButton(Symbol.OutlineStar);
    private bool? favoriteValue;
    private bool savingFavorite;
    private Task favoriteSave=Task.CompletedTask;
    public event Action<int,bool,bool>? FavoriteChanged;
    public Task FlushFavoriteAsync()=>favoriteSave;
    private readonly CancellationTokenSource lifetime = new();
    private readonly ViewerChromeController hideTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer animTimer;
    private readonly Border toolbarHost = new() { VerticalAlignment = VerticalAlignment.Bottom, HorizontalAlignment = HorizontalAlignment.Stretch, Margin = new Thickness(0), RequestedTheme = ElementTheme.Dark };
    private readonly Button settings = IconButton(Symbol.Setting);
    private bool menuOpen;
    public string WindowTitle=>$"Aredoko — 画像ビューア　{sequence.Current.Title} [{sequence.Position+1}/{sequence.Count}]";
    public event Action<string>? TitleChanged;
    private bool keyboardChrome, failed;
    public event Action<int>? ContentOpened;
    public event EventHandler? CloseRequested;
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
    private readonly Button actualSize=new(){Content="原寸",MinWidth=36,Padding=new Thickness(8)};
    private readonly Button retry = IconButton(Symbol.Refresh);
    private readonly TextBlock title = new() { TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock count = new() { VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock zoom = new() { Text = "倍率 100%", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock status = new() { Visibility = Visibility.Collapsed, TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center };
    private bool busy, disposed, loaded, navigating;
    private int version;

    public ImageViewerView(LibraryApi api, ImageViewerSequence sequence,ResultSession? favoriteSession=null)
    {
        this.api = api; this.sequence = sequence;
        this.favoriteSession=favoriteSession;
        hideTimer = new(this,toolbarHost,viewport,()=>keyboardChrome||menuOpen||savingFavorite);
        animTimer = DispatcherQueue.CreateTimer(); animTimer.IsRepeating = false;
        animTimer.Tick += (_, _) => AdvanceAnimationFrame();
        toolbarHost.Style=(Style)Application.Current.Resources["ImageViewerOverlayStyle"];
        toolbarHost.BorderThickness=new Thickness(0);
        viewport.Style = (Style)Application.Current.Resources["ImageViewerCanvasStyle"];
        canvas.Children.Add(image); viewport.Content = canvas; Children.Add(viewport);
        ViewerInputGestures.AttachPan(viewport);
        viewport.SizeChanged += (_, _) => FitImage();
        viewport.ViewChanged += (_, _) => UpdateControls();
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Center };
        foreach (var control in new UIElement[] { previous, next, zoomOut, zoomIn, fit, actualSize, zoom, favorite,retry,settings }) actions.Children.Add(control);
        favorite.Visibility=favoriteSession is null?Visibility.Collapsed:Visibility.Visible;
        Identify(favorite,"ImageFavorite","お気に入りを読み込み中");
        favorite.Click+=async(_,_)=>{favoriteSave=SaveFavoriteAsync();await favoriteSave;};
        toolbarHost.Child=actions;Children.Add(toolbarHost);ViewerChromeController.AttachNotices(this,status);
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
        var menu=ViewerChromeController.Settings(false,()=>{FitImage();UpdateControls();hideTimer.Start();},ex=>{ViewerNotice.Set(status,"設定を保存できませんでした。");AppLog.Error(ex);});
        settings.Flyout=menu;viewport.ContextFlyout=menu;
        menu.Opened+=(_,_)=>{menuOpen=true;ShowChrome();};menu.Closed+=(_,_)=>{menuOpen=false;hideTimer.Start();};
        previous.Click += async (_, _) => await MoveAsync(-1); next.Click += async (_, _) => await MoveAsync(1);
        zoomOut.Click += (_, _) => ViewerInputGestures.ZoomCentered(viewport,Math.Max(viewport.MinZoomFactor, viewport.ZoomFactor - .5f));
        zoomIn.Click += (_, _) => ViewerInputGestures.ZoomCentered(viewport,Math.Min(viewport.MaxZoomFactor, viewport.ZoomFactor + .5f));
        fit.Click += (_, _) => {actualPixels=false;FitImage();viewport.ChangeView(0,0,1,true);};
        actualSize.Click+=(_,_)=>{if(OriginalZoom()<1){actualPixels=true;FitImage();viewport.ChangeView(0,0,1,true);}else ViewerInputGestures.ZoomCentered(viewport,(float)OriginalZoom());};
        retry.Click += async (_, _) => await OpenAsync();
        UpdateIdentity(); UpdateControls();
    }
    private void ShowChrome()=>hideTimer.Show();
    private static Button IconButton(Symbol symbol) => new() { Content = new SymbolIcon(symbol), MinWidth = 36, Padding = new Thickness(8) };
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
        favoriteValue=null;
        favorite.Content=new SymbolIcon(Symbol.OutlineStar);
        AutomationProperties.SetName(favorite,"お気に入りを読み込み中");
        ToolTipService.SetToolTip(favorite,"お気に入りを読み込み中");
        if(favoriteSession is not null)_=LoadFavoriteAsync();
    }
    private void UpdateControls()
    {
        previous.IsEnabled = !disposed && !navigating && !savingFavorite && sequence.HasPrevious; next.IsEnabled = !disposed && !navigating && !savingFavorite && sequence.HasNext;
        favorite.IsEnabled=!disposed&&!navigating&&!savingFavorite&&loaded&&favoriteValue is not null;
        zoom.Text = loaded?$"倍率 {viewport.ZoomFactor/OriginalZoom() * 100:0}%":"倍率 —";
        zoomOut.IsEnabled = loaded && !busy && viewport.ZoomFactor > viewport.MinZoomFactor;
        zoomIn.IsEnabled = loaded && !busy && viewport.ZoomFactor < viewport.MaxZoomFactor; actualSize.IsEnabled=loaded&&!busy; fit.IsEnabled = loaded && !busy;
    }
    private async Task LoadFavoriteAsync()
    {
        var id=sequence.Current.Id;var ordinal=sequence.Position;var requestedVersion=version;
        try
        {
            var result=await favoriteSession!.RangeAsync(ordinal,1,lifetime.Token);
            if(disposed||version!=requestedVersion||sequence.Current.Id!=id)return;
            if(result.Items.Count!=1||result.Items[0].Id!=id)throw new InvalidDataException("表示中の画像を確認できません。");
            favoriteValue=result.Items[0].Favorite;UpdateFavoriteControl();
        }
        catch(OperationCanceledException) when(lifetime.IsCancellationRequested){}
        catch(Exception ex){if(!disposed&&version==requestedVersion&&sequence.Current.Id==id){AutomationProperties.SetName(favorite,"お気に入りの状態を取得できません");ToolTipService.SetToolTip(favorite,"お気に入りの状態を取得できません。一覧で確認してください。");AppLog.Error(ex);}}
    }
    private void UpdateFavoriteControl()
    {
        favorite.Content=new SymbolIcon(favoriteValue==true?Symbol.SolidStar:Symbol.OutlineStar);
        var label=favoriteValue==true?"お気に入りを解除":"お気に入りに登録";
        AutomationProperties.SetName(favorite,label);ToolTipService.SetToolTip(favorite,label);UpdateControls();
    }
    private async Task SaveFavoriteAsync()
    {
        if(disposed||navigating||savingFavorite||favoriteValue is null||favoriteSession is null)return;
        var id=sequence.Current.Id;var value=!favoriteValue.Value;savingFavorite=true;ShowChrome();UpdateControls();
        try
        {
            var kept=await favoriteSession.EditFavoriteAsync(id,value,CancellationToken.None);
            favoriteValue=value;FavoriteChanged?.Invoke(id,value,kept);UpdateFavoriteControl();
            ViewerNotice.Set(status,value?"お気に入りに登録しました。":"お気に入りを解除しました。");
            if(!kept){ViewerNotice.Set(status,"保存しました。検索結果を更新するため一覧へ戻ります。");CloseRequested?.Invoke(this,EventArgs.Empty);}
        }
        catch(Exception ex){ViewerNotice.Set(status,"お気に入りを保存できませんでした。一覧で状態を確認してください。");AppLog.Error(ex);}
        finally{savingFavorite=false;if(!disposed)UpdateControls();}
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
                StopAnimation(true); failed = true; retry.IsEnabled = true;
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
        if (disposed || navigating || menuOpen || savingFavorite) return;
        var moved = false; navigating = true; UpdateControls();
        try { moved = await sequence.TryMoveAsync(direction, lifetime.Token); }
        catch (OperationCanceledException) when (disposed || lifetime.IsCancellationRequested) { }
        catch (Exception ex)
        {
            if (disposed) return;
            failed = true; ShowChrome();
            ViewerNotice.Set(status, ex is ResultSessionException
                ? "検索結果が更新されたか、有効期限が切れました。閉じて同じ条件で再検索してください。"
                : "次の画像を取得できません。接続を確認して、もう一度操作してください。");
            AppLog.Error(ex);
        }
        finally { navigating = false; if (!disposed) UpdateControls(); }
        if (!moved || disposed) return;
        actualPixels=false;version++; loaded = false; StopAnimation(true); retry.IsEnabled = false;
        UpdateIdentity(); ViewerNotice.Set(status,"画像を読み込んでいます…"); UpdateControls();
        // New navigation may cancel a slow foreground image while the old
        // pipeline drains; only neighbor lookup itself is single-flight.
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
                        ArchiveReadException { Status: System.Net.HttpStatusCode.NotFound } => "画像を読み取れません。未接続・破損・容量制限を確認し、更新した場合は再スキャンしてください。",
                        ArchiveReadException => ex.Message,
                        OperationCanceledException => "読み込みがタイムアウトしました。再試行してください。",
                        HttpRequestException => "接続できません。閉じてライブラリから再接続してください。",
                        _ => "画像を表示できません。未対応形式・破損・画像サイズを確認してください。"
                    });
                    failed = true; retry.IsEnabled = true; ShowChrome();
                }
                finally { request = null; }
            } while (!disposed && requestedVersion != version);
        }
        finally { busy = false; if (!disposed) { UpdateControls(); if (!keyboardChrome && !failed) hideTimer.Start(); } }
    }
    public void Dispose()
    { if (disposed) return; disposed = true; hideTimer.Dispose(); StopAnimation(); lifetime.Cancel(); staticCache.Dispose();image.Source = null; lifetime.Dispose(); }
}
