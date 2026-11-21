using System.Net;
using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Storage.Streams;
using Windows.System;

namespace Aredoko_WinUI;

// Bounded read-only native video player. Uses the authenticated loopback API
// and bounded range streams; never opens, locks or mutates source paths directly.
internal sealed class VideoPlayerView : Grid, IDisposable, IViewerWindowTitle
{
    [System.Runtime.InteropServices.DllImport("user32.dll")] private static extern uint GetDoubleClickTime();
    private readonly LibraryApi api;
    private readonly int itemId;
    private readonly string itemTitle;
    private readonly int? initialPositionMs;
    private readonly bool isAudio;
    private readonly bool autoPlayOnOpen;
    private readonly int doubleClickMs;
    private readonly ViewerFavoriteAction favorite;
    public event Action<int,bool,bool>? FavoriteChanged;
    public Task FlushFavoriteAsync()=>favorite.FlushAsync();
    private readonly CancellationTokenSource lifetime = new();
    private readonly ViewerChromeController hideTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer positionTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer previewTimer;
    private readonly Slider seekBar = new() { Minimum=0, Maximum=1, SmallChange=1, LargeChange=10, StepFrequency=0.1, IsThumbToolTipEnabled=false, HorizontalAlignment=HorizontalAlignment.Stretch };
    private readonly Image seekImage = new() { Width=256, Height=144, Stretch=Stretch.Uniform };
    private readonly TextBlock seekHint = new() { Text="読み込み中…", HorizontalAlignment=HorizontalAlignment.Center, VerticalAlignment=VerticalAlignment.Center };
    private readonly TextBlock seekTime = new() { HorizontalAlignment=HorizontalAlignment.Center };
    private readonly Border seekPreview = new() { Width=272, HorizontalAlignment=HorizontalAlignment.Left, VerticalAlignment=VerticalAlignment.Bottom, Visibility=Visibility.Collapsed, IsHitTestVisible=false, RequestedTheme=ElementTheme.Dark };
    private CancellationTokenSource? previewRequest;
    private bool updatingSeek, seekHover, seekDragging, previewBusy, updatingVolume, compatAttempted, preTapPlaying;
    private long lastSingleTapTick, lastDoubleTapTick, lastMaximizeTick;
    private readonly Slider volumeSlider=new(){Minimum=0,Maximum=100,StepFrequency=1,SmallChange=5,LargeChange=20,Width=88,VerticalAlignment=VerticalAlignment.Center};
    private readonly Dictionary<int,BitmapImage> previewFrames=[];
    private readonly Queue<int> previewFrameOrder=[];
    private int previewWanted=-1, previewDisplayed=-1;
    private readonly Grid viewport = new() { IsTabStop = true, RequestedTheme = ElementTheme.Dark };
    private readonly MediaPlayerElement playerElement = new()
    {
        AreTransportControlsEnabled = false,
        Stretch = Stretch.Uniform,
        HorizontalAlignment = HorizontalAlignment.Stretch,
        VerticalAlignment = VerticalAlignment.Stretch
    };
    private readonly Border toolbar = new() { VerticalAlignment = VerticalAlignment.Bottom, HorizontalAlignment = HorizontalAlignment.Center, RequestedTheme = ElementTheme.Dark };
    private readonly Button playPause = IconButton(Symbol.Play);
    private readonly Button seekBack = IconButton(Symbol.Back);
    private readonly Button seekForward = IconButton(Symbol.Forward);
    private readonly Button mute = IconButton(Symbol.Volume);
    private readonly Button volumeDown = TextButton("−");
    private readonly Button volumeUp = TextButton("＋");
    private readonly Button retry = IconButton(Symbol.Refresh);
    private readonly Button openExternal = new() { Content = "外部アプリで開く", Visibility = Visibility.Collapsed, IsEnabled = false, Padding = new Thickness(10, 4, 10, 4), CornerRadius = new CornerRadius(14) };
    private readonly Button editDetails = IconButton(Symbol.Edit);
    private readonly Button settings = IconButton(Symbol.More);
    private readonly Microsoft.UI.Xaml.Controls.Primitives.ToggleButton pinButton;
    private readonly Action syncPin;
    private readonly MenuFlyout menu = new();
    private readonly MenuFlyoutItem? findSimilarFrame;
    private readonly ToggleMenuFlyoutItem alwaysControlsMenuItem = new() { Text = "操作バーを常時表示" };
    private int menuTargetMs;
    private bool menuOpen;
    private readonly TextBlock positionText = new() { Text = "—", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock volumeText = new() { Text = "80%", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock status = new() { Visibility = Visibility.Collapsed, TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center };
    private CancellationTokenSource? request;
    private MediaPlayer? mediaPlayer;
    private MediaSource? mediaSource;
    private IRandomAccessStream? mediaStream;
    private VideoRangeSource? mediaRange;
    private TimeSpan duration = TimeSpan.Zero;
    private TimeSpan position = TimeSpan.Zero;
    private TimeSpan lastTickPosition = TimeSpan.Zero;
    private int volume = 80;
    private int version, stalledAtEndTicks;
    private bool busy, disposed, failed, loaded, playing, ended, observedPlaying, muted, keyboardChrome;
    public event Action<int>? ContentOpened;
    public event EventHandler? CloseRequested;
    public event Action? EditDetailsRequested;
    public event Action? OpenExternalRequested;
    public event Action? ToggleMaximizeRequested;
    public event Action<int,int>? FindSimilarFrameRequested;
    public string WindowTitle => $"{itemTitle} — Aredoko";
    public event Action<string>? TitleChanged;

    public VideoPlayerView(LibraryApi api, int itemId, string titleText, int? initialPositionMs = null, bool isAudio = false,ResultSession? favoriteSession=null,int favoriteOrdinal=0,bool autoPlay=false)
    {
        this.api = api;
        this.itemId = itemId;
        itemTitle = titleText;
        this.initialPositionMs = initialPositionMs;
        this.isAudio = isAudio;
        autoPlayOnOpen = autoPlay;
        doubleClickMs = Math.Clamp((int)GetDoubleClickTime(), 250, 500);
        favorite=new(favoriteSession,message=>ViewerNotice.Set(status,message));favorite.Attach();
        favorite.Changed+=(id,value,kept)=>FavoriteChanged?.Invoke(id,value,kept);
        favorite.ReturnRequested+=()=>CloseRequested?.Invoke(this,EventArgs.Empty);
        favorite.StateChanged+=()=>{if(favorite.IsSaving)ShowChrome();UpdateControls();};
        positionTimer = DispatcherQueue.CreateTimer(); positionTimer.Interval = TimeSpan.FromMilliseconds(200);
        positionTimer.Tick += (_, _) => SyncPosition();
        previewTimer=DispatcherQueue.CreateTimer();previewTimer.Interval=TimeSpan.FromMilliseconds(320);previewTimer.IsRepeating=false;
        previewTimer.Tick+=async(_,_)=>await LoadSeekPreviewAsync();
        viewport.Background = (Brush)Application.Current.Resources["SolidBackgroundFillColorBaseBrush"];
        viewport.Children.Add(playerElement);
        Children.Add(viewport);
        ViewerChromeController.StyleFloatingPill(toolbar, cornerRadius: 20, padding: new Thickness(14, 8, 14, 8));
        toolbar.MinWidth = 540;
        toolbar.MaxWidth = 760;
        SizeChanged += (_, _) => { toolbar.Width = ActualWidth > 0 ? Math.Clamp(ActualWidth - 48, 320, 740) : 700; };
        positionText.Style = volumeText.Style = status.Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"];
        positionText.HorizontalAlignment = HorizontalAlignment.Center;
        positionText.TextWrapping = TextWrapping.NoWrap;
        positionText.TextAlignment = TextAlignment.Center;
        positionText.MinWidth = 96;
        Microsoft.UI.Xaml.Documents.Typography.SetNumeralAlignment(positionText, FontNumeralAlignment.Tabular);
        Microsoft.UI.Xaml.Documents.Typography.SetNumeralAlignment(seekTime, FontNumeralAlignment.Tabular);
        ViewerChromeController.FixNumericSlot(volumeText, 40, TextAlignment.Right);
        var actions = new Grid { ColumnSpacing = 8 };
        actions.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        actions.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        actions.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        ViewerChromeController.StylePillButton(favorite.Button);
        (pinButton, syncPin) = ViewerChromeController.CreatePinButton("VideoPinToolbar", () => { alwaysControlsMenuItem.IsChecked = ViewerOptions.Value.AlwaysShowControls; hideTimer?.SyncPinState(); hideTimer?.RefreshHoverHint(); }, ex => { ViewerNotice.Set(status, "設定を保存できませんでした。"); AppLog.Error(ex); });
        var playback=new StackPanel{Orientation=Orientation.Horizontal,Spacing=4};
        foreach(var control in new UIElement[]{playPause,seekBack,seekForward,favorite.Button,editDetails,retry,openExternal})playback.Children.Add(control);
        Identify(favorite.Button,isAudio?"AudioFavorite":"VideoFavorite","お気に入りを読み込み中");
        Identify(editDetails,"PlayerEditDetails","詳細で編集");
        editDetails.Click += (_, _) => EditDetailsRequested?.Invoke();
        var audio=new StackPanel{Orientation=Orientation.Horizontal,Spacing=4,HorizontalAlignment=HorizontalAlignment.Right};
        foreach(var control in new UIElement[]{mute,volumeDown,volumeSlider,volumeUp,volumeText,ViewerChromeController.Divider(),settings,pinButton})audio.Children.Add(control);
        ViewerChromeController.ApplySliderTheme(volumeSlider);
        actions.Children.Add(playback); SetColumn(positionText,1); actions.Children.Add(positionText); SetColumn(audio,2); actions.Children.Add(audio);
        Identify(volumeSlider,"VideoVolume","音量（0〜100）");
        volumeSlider.ValueChanged+=(_,_)=>{if(updatingVolume)return;volume=VideoPlayerPolicy.ClampVolume((int)Math.Round(volumeSlider.Value));if(mediaPlayer is not null)mediaPlayer.Volume=volume/100.0;UpdateControls();ShowChrome();};
        viewport.Tapped+=(_,args)=>
        {
            if(Environment.TickCount64-lastDoubleTapTick<=doubleClickMs+80)return;
            if(!busy&&loaded&&!failed&&!ViewerInputGestures.IsInteractiveControl(args.OriginalSource,viewport))
            {
                args.Handled=true;
                preTapPlaying=playing;
                lastSingleTapTick=Environment.TickCount64;
                TogglePlayPause(revealChrome:false);
            }
        };
        viewport.DoubleTapped+=(_,args)=>
        {
            if(ViewerInputGestures.IsInteractiveControl(args.OriginalSource,viewport))return;
            args.Handled=true;
            var now=Environment.TickCount64;
            var revertFirstTap=(now-lastSingleTapTick)<=doubleClickMs+100;
            lastDoubleTapTick=now;
            lastMaximizeTick=now;
            var shouldPlay=revertFirstTap?preTapPlaying:playing;
            if(loaded&&!busy&&!failed&&shouldPlay!=playing)
                TogglePlayPause(revealChrome:false);
            ToggleMaximizeRequested?.Invoke();
            if(shouldPlay)
                DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low,()=>
                {
                    if(!disposed&&loaded&&!failed&&playing&&mediaPlayer is not null
                        &&mediaPlayer.PlaybackSession.PlaybackState is not (MediaPlaybackState.Playing or MediaPlaybackState.Buffering))
                        mediaPlayer.Play();
                });
        };
        seekBar.HorizontalAlignment = HorizontalAlignment.Stretch;
        var seekHost = ViewerChromeController.WrapScrubber(seekBar, double.NaN);
        var bottom = new StackPanel { Spacing = 6, HorizontalAlignment=HorizontalAlignment.Stretch }; bottom.Children.Add(seekHost);bottom.Children.Add(actions);
        toolbar.Child = bottom; Children.Add(toolbar);
        ViewerChromeController.AttachNotices(this,104,status);
        hideTimer = new(this,toolbar,viewport,()=>keyboardChrome||menuOpen||seekHover||seekDragging||busy||failed||favorite.IsSaving);
        AutomationProperties.SetAutomationId(alwaysControlsMenuItem,"VideoAlwaysControls");
        alwaysControlsMenuItem.IsChecked=ViewerOptions.Value.AlwaysShowControls;
        alwaysControlsMenuItem.Click+=(_,_)=>
        {
            try
            {
                ViewerOptions.SavePresentation(ViewerOptions.Value.EnlargeSmallImages,alwaysControlsMenuItem.IsChecked,ViewerOptions.Value.LoopBookPages);
                syncPin();hideTimer.SyncPinState();
            }
            catch(Exception ex){alwaysControlsMenuItem.IsChecked=ViewerOptions.Value.AlwaysShowControls;ViewerNotice.Set(status,"設定を保存できませんでした。");AppLog.Error(ex);}
        };
        if(!isAudio)
        {
            findSimilarFrame=new MenuFlyoutItem{Text="≈ この場面に似た画像・動画を探す"};
            Identify(findSimilarFrame,"VideoFindSimilarFrame","この場面に似た画像・動画を探す");
            findSimilarFrame.Click+=(_,_)=>
            {
                if(busy||disposed||!loaded||failed)return;
                var targetMs=menuTargetMs;
                if(playing)TogglePlayPause();
                FindSimilarFrameRequested?.Invoke(itemId,targetMs);
            };
            menu.Items.Add(findSimilarFrame);
            menu.Items.Add(new MenuFlyoutSeparator());
        }
        menu.Items.Add(alwaysControlsMenuItem);
        menu.Opened+=(_,_)=>
        {
            alwaysControlsMenuItem.IsChecked=ViewerOptions.Value.AlwaysShowControls;
            if(findSimilarFrame is not null)
            {
                var pos=loaded&&mediaPlayer is not null?VideoPlayerPolicy.ClampSeek(mediaPlayer.PlaybackSession.Position,duration):position;
                if(pos>position)position=pos;
                menuTargetMs=(int)Math.Clamp(Math.Round(position.TotalMilliseconds),0,86_400_000);
                var label=VideoPlayerPolicy.FormatTime(TimeSpan.FromMilliseconds(menuTargetMs));
                findSimilarFrame.Text=playing?$"≈ 一時停止してこの場面（{label}）に似た画像・動画を探す":$"≈ この場面（{label}）に似た画像・動画を探す";
                AutomationProperties.SetName(findSimilarFrame,findSimilarFrame.Text);
                findSimilarFrame.IsEnabled=!busy&&!disposed&&loaded&&!failed;
            }
            menuOpen=true;hideTimer.HideHoverHint();ShowChrome();
        };
        menu.Closed+=(_,_)=>{menuOpen=false;hideTimer.Start();};
        viewport.ContextFlyout=menu;settings.Flyout=menu;
        seekPreview.Style=(Style)Application.Current.Resources["ImageViewerOverlayStyle"];
        seekTime.Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"];
        seekHint.Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"];
        var frameHost=new Grid();frameHost.Children.Add(seekImage);frameHost.Children.Add(seekHint);
        var previewContent=new StackPanel { Spacing=4 };previewContent.Children.Add(seekTime);previewContent.Children.Add(frameHost);seekPreview.Child=previewContent;Children.Add(seekPreview);
        Identify(seekBar,"VideoSeek","再生位置（秒）。左右キーで移動");
        Identify(seekImage,"VideoSeekImage","シーク先のサムネイル");Identify(seekTime,"VideoSeekTime","シーク先の時刻");Identify(seekPreview,"VideoSeekPreview","シーク先のプレビュー");
        seekBar.AddHandler(PointerPressedEvent,new PointerEventHandler((_,_)=>{seekDragging=true;hideTimer.Show();}),true);
        seekBar.AddHandler(PointerReleasedEvent,new PointerEventHandler((_,_)=>FinishSeekDrag()),true);
        seekBar.PointerCaptureLost+=(_,_)=>FinishSeekDrag();
        seekBar.PointerCanceled+=(_,_)=>FinishSeekDrag();
        seekBar.ValueChanged+=(_,_)=>
        {
            if(updatingSeek)return;
            SeekTo(TimeSpan.FromSeconds(seekBar.Value),revealChrome:!seekDragging);
        };
        seekBar.AddHandler(PointerMovedEvent,new PointerEventHandler((_,args)=>
        {
            if(!loaded||busy||failed||seekBar.ActualWidth<=0)return;
            seekHover=true;hideTimer.Stop();var point=args.GetCurrentPoint(seekBar).Position;
            var rootX=args.GetCurrentPoint(this).Position.X;
            var seconds=Math.Clamp(point.X/seekBar.ActualWidth,0,1)*duration.TotalSeconds;
            var millis=(int)Math.Min(86_400_000,Math.Max(0,Math.Min(seconds,duration.TotalSeconds-0.05))*1000);
            previewWanted=(int)Math.Clamp(Math.Round(millis/1000.0)*1000,0,Math.Max(0,Math.Floor((duration.TotalMilliseconds-50)/1000)*1000));
            seekTime.Text=VideoPlayerPolicy.FormatPosition(TimeSpan.FromMilliseconds(previewWanted),duration).Split(" / ")[0];
            seekPreview.Margin=new Thickness(Math.Clamp(rootX-136,8,Math.Max(8,ActualWidth-280)),0,0,toolbar.ActualHeight+24);
            if(isAudio)
            {
                seekHint.Visibility=Visibility.Collapsed;
                seekImage.Visibility=Visibility.Collapsed;
            }
            else if(previewFrames.TryGetValue(previewWanted,out var cached))
            {seekImage.Visibility=Visibility.Visible;seekImage.Source=cached;previewDisplayed=previewWanted;seekHint.Visibility=Visibility.Collapsed;AutomationProperties.SetName(seekImage,seekTime.Text+"のサムネイル");}
            else if(previewDisplayed!=previewWanted)
            {
                seekImage.Visibility=Visibility.Visible;
                if(seekImage.Source is null){seekHint.Text="読み込み中…";seekHint.Visibility=Visibility.Visible;}
                else seekTime.Text=VideoPlayerPolicy.FormatPosition(TimeSpan.FromMilliseconds(previewDisplayed),duration).Split(" / ")[0]+"（次を準備中）";
                if(!previewBusy){previewTimer.Stop();previewTimer.Start();}
            }
            seekPreview.Visibility=Visibility.Visible;
        }),true);
        seekBar.PointerExited+=(_,_)=>{if(!seekDragging){HideSeekPreview();ShowChrome();}};
        Identify(viewport, "VideoViewport", isAudio ? "音声再生。スペースで再生・一時停止、左右キーで移動" : "動画表示。スペースで再生・一時停止、左右キーで移動");
        Identify(playerElement, "VideoElement", itemTitle + (isAudio ? "の音声" : "の動画"));
        Identify(toolbar, "VideoToolbar", (isAudio ? "音声" : "動画") + "の操作");
        Identify(settings, "VideoSettings", isAudio ? "音声のメニュー" : "動画のメニュー（この場面に似た作品を探す・操作バー設定）");
        Identify(playPause, "VideoPlayPause", "再生");
        Identify(seekBack, "VideoSeekBack", "1秒戻る"); Identify(seekForward, "VideoSeekForward", "1秒進む");
        Identify(mute, "VideoMute", "消音");
        Identify(volumeDown, "VideoVolumeDown", "音量を下げる"); Identify(volumeUp, "VideoVolumeUp", "音量を上げる");
        Identify(retry, "VideoRetry", (isAudio ? "音声" : "動画") + "を再試行");
        Identify(openExternal, "VideoOpenExternal", "既定のアプリで開く");
        openExternal.Click += (_, _) => OpenExternalRequested?.Invoke();
        AutomationProperties.SetAutomationId(positionText, "VideoPosition");
        AutomationProperties.SetAutomationId(volumeText, "VideoVolumeStatus");
        AutomationProperties.SetAutomationId(status, "VideoStatus");
        AutomationProperties.SetLiveSetting(status, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        hideTimer.AttachHoverHint(playPause, () => playing ? "一時停止（Space）" : "再生（Space）");
        hideTimer.AttachHoverHint(seekBack, "1秒戻る（←）");
        hideTimer.AttachHoverHint(seekForward, "1秒進む（→）");
        hideTimer.AttachHoverHint(favorite.Button, () => AutomationProperties.GetName(favorite.Button));
        hideTimer.AttachHoverHint(editDetails, "詳細でタグ・棚を編集（プレーヤーを閉じる）");
        hideTimer.AttachHoverHint(retry, isAudio ? "音声の読み込みを再試行" : "動画の読み込みを再試行");
        hideTimer.AttachHoverHint(openExternal, "既定の外部アプリで再生します");
        hideTimer.AttachHoverHint(mute, () => muted ? "消音解除（M）" : "消音（M）");
        hideTimer.AttachHoverHint(volumeDown, "音量を下げる");
        hideTimer.AttachHoverHint(volumeUp, "音量を上げる");
        hideTimer.AttachHoverHint(settings, isAudio ? "再生メニュー" : "メニュー（この場面に似た作品を探す・操作バー設定）");
        hideTimer.AttachHoverHint(pinButton, () => ViewerOptions.Value.AlwaysShowControls ? "操作バーの固定を解除" : "操作バーを常に表示（ピン留め）");
        playPause.Click += (_, _) => TogglePlayPause();
        seekBack.Click += (_, _) => Seek(-1); seekForward.Click += (_, _) => Seek(1);
        mute.Click += (_, _) => ToggleMute();
        volumeDown.Click += (_, _) => AdjustVolume(-20); volumeUp.Click += (_, _) => AdjustVolume(20);
        retry.Click += async (_, _) => await OpenCoreAsync(allowAutoPlay: false);
        favorite.Refresh(itemId,favoriteOrdinal);UpdateControls(); ShowChrome();
    }

    private static Button IconButton(Symbol symbol) => ViewerChromeController.PillButton(symbol);
    private static Button TextButton(string label) => ViewerChromeController.PillTextButton(label);
    private static void Identify(DependencyObject control, string id, string name)
    { AutomationProperties.SetAutomationId(control, id); AutomationProperties.SetName(control, name); }

    private void ShowChrome() { if (!disposed) hideTimer.Show(); }

    public void AttachNavigation(UIElement dialog)
    {
        dialog.AddHandler(PointerMovedEvent, new PointerEventHandler((_, _) => { keyboardChrome = false; }), true);
        dialog.PreviewKeyDown += (_, args) =>
        {
            if (args.Key == VirtualKey.Escape) { args.Handled = true; CloseRequested?.Invoke(this, EventArgs.Empty); return; }
            if (args.Key == VirtualKey.Tab) { keyboardChrome = true; ShowChrome(); return; }
            foreach (var modifier in new[] { VirtualKey.Control, VirtualKey.Shift, VirtualKey.Menu, VirtualKey.LeftWindows, VirtualKey.RightWindows })
                if ((Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(modifier) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0) return;
            if (args.Key == VirtualKey.F10) { keyboardChrome = true; ShowChrome(); args.Handled = true; return; }
            if (ViewerInputGestures.IsNativeControlKey(args.OriginalSource,args.Key)) return;
            if (args.Key == VirtualKey.Space) { args.Handled = true; TogglePlayPause(); return; }
            if (args.Key == VirtualKey.M) { args.Handled = true; ToggleMute(); return; }
            if (args.Key == VirtualKey.Left) { args.Handled = true; Seek(-1); return; }
            if (args.Key == VirtualKey.Right) { args.Handled = true; Seek(1); }
        };
    }

    public Task OpenAsync() => OpenCoreAsync(autoPlayOnOpen);

    private async Task OpenRangeStreamAsync(Func<Task<VideoRangeSource>> opener, int timeoutSeconds, bool isCompat, int current, CancellationToken cancellation)
    {
        IRandomAccessStream? stream = null;
        VideoRangeSource? rangeSource = null;
        MediaSource? source = null;
        MediaPlayer? nextPlayer = null;
        var openSettled = false;
        try
        {
            rangeSource = await opener();
            var localRange = rangeSource;
            stream = new VideoRandomAccessStream(rangeSource);
            var mime = rangeSource.Manifest.Mime;
            cancellation.ThrowIfCancellationRequested();
            source = MediaSource.CreateFromStream(stream, mime);
            await source.OpenAsync().AsTask(cancellation);
            if (source.State != MediaSourceState.Opened) throw new InvalidDataException(isAudio ? "音声を開けません。" : "動画を開けません。");
            var opened = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            nextPlayer = new MediaPlayer { AutoPlay = false, Volume = volume / 100.0, IsMuted = muted };
            var player = nextPlayer;
            player.MediaOpened += (_, _) => opened.TrySetResult(true);
            player.PlaybackSession.PlaybackStateChanged += (session, _) =>
            {
                var state = session.PlaybackState;
                var sessionPos = session.Position;
                DispatcherQueue.TryEnqueue(() =>
                {
                    if (disposed || current != version || !loaded || !playing || !ReferenceEquals(mediaPlayer, player)) return;
                    if (state == MediaPlaybackState.Playing) { observedPlaying = true; return; }
                    if (state == MediaPlaybackState.Paused && Environment.TickCount64 - lastMaximizeTick <= 1500 && !IsNearEnd(sessionPos, duration))
                    {
                        mediaPlayer.Play();
                        return;
                    }
                    if (state is MediaPlaybackState.Paused or MediaPlaybackState.None && !seekDragging)
                    {
                        if (IsNearEnd(sessionPos, duration)) HandlePlaybackEnded();
                        else if (observedPlaying) HandlePlaybackPaused(sessionPos);
                    }
                });
            };
            player.MediaFailed += (sender, args) =>
            {
                var failure = localRange?.Failure ?? mediaRange?.Failure ?? new InvalidDataException(args.ErrorMessage);
                opened.TrySetException(failure);
                if (openSettled)
                    DispatcherQueue.TryEnqueue(() =>
                    {
                        if (disposed || current != version || !loaded || !ReferenceEquals(mediaPlayer, player)) return;
                        if (!isAudio && !isCompat && !compatAttempted && localRange?.Failure is not ArchiveReadException { Status: HttpStatusCode.Forbidden or HttpStatusCode.NotFound or HttpStatusCode.Conflict or HttpStatusCode.ServiceUnavailable })
                            _ = TryCompatFallbackAsync(current, resumePlay: playing);
                        else
                            ReportFailure(failure);
                    });
            };
            player.MediaEnded += (_, _) => DispatcherQueue.TryEnqueue(() =>
            {
                if (!disposed && current == version && loaded && ReferenceEquals(mediaPlayer, player))
                    HandlePlaybackEnded();
            });
            playerElement.SetMediaPlayer(player);
            player.Source = source;
            await opened.Task.WaitAsync(TimeSpan.FromSeconds(timeoutSeconds), cancellation);
            openSettled = true;
            if (disposed || current != version)
            {
                rangeSource?.Dispose(); nextPlayer.Source = null; playerElement.SetMediaPlayer(null); nextPlayer.Dispose(); source.Dispose(); stream.Dispose();
                rangeSource = null; nextPlayer = null; source = null; stream = null;
                return;
            }
            mediaStream = stream; mediaRange = rangeSource; mediaSource = source; mediaPlayer = nextPlayer;
            stream = null; rangeSource = null; source = null; nextPlayer = null;
            var natural = mediaPlayer.PlaybackSession.NaturalDuration;
            duration = natural > TimeSpan.Zero && natural != TimeSpan.MaxValue
                ? natural
                : mediaSource.Duration is TimeSpan d && d > TimeSpan.Zero ? d : TimeSpan.FromSeconds(1);
            position = TimeSpan.Zero;
            if (initialPositionMs is int startMs && startMs > 0 && duration > TimeSpan.Zero)
            {
                var maxStart = duration.TotalMilliseconds > 300 ? duration.TotalMilliseconds - 250 : 0;
                var target = TimeSpan.FromMilliseconds(Math.Min(startMs, maxStart));
                try { mediaPlayer.PlaybackSession.Position = target; position = target; } catch { }
            }
            positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
            loaded = true;
            ContentOpened?.Invoke(itemId);
            ViewerNotice.Set(status);
        }
        catch (Exception ex) when (rangeSource?.Failure is { } sourceFailure && !ReferenceEquals(ex, sourceFailure))
        {
            throw sourceFailure;
        }
        finally
        {
            rangeSource?.Dispose();
            if (nextPlayer is not null) { try { nextPlayer.Source = null; playerElement.SetMediaPlayer(null); nextPlayer.Dispose(); } catch { } }
            source?.Dispose();
            stream?.Dispose();
        }
    }

    private async Task TryCompatFallbackAsync(int expectedVersion, bool resumePlay)
    {
        if (disposed || compatAttempted || isAudio || expectedVersion != version || lifetime.IsCancellationRequested) return;
        compatAttempted = true;
        request?.Cancel(); request?.Dispose();
        request = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        var ct = request.Token;
        busy = true; failed = loaded = playing = false;
        ClearMedia();
        positionText.Text = "—";
        ViewerNotice.Set(status, "互換形式で再生を準備しています…");
        hideTimer.Stop(); UpdateControls();
        try
        {
            await OpenRangeStreamAsync(() => api.OpenVideoCompatRangeAsync(itemId, ct), 15, isCompat: true, expectedVersion, ct);
        }
        catch (OperationCanceledException) when (!lifetime.IsCancellationRequested && expectedVersion != version) { }
        catch (Exception compatEx) { if (!disposed && expectedVersion == version) ReportFailure(compatEx); }
        finally
        {
            if (!disposed && expectedVersion == version)
            {
                busy = false;
                UpdateControls();
                TitleChanged?.Invoke(WindowTitle);
                if (resumePlay && loaded && !failed && !playing) StartPlayback();
                if (!keyboardChrome && !failed) hideTimer.Start();
            }
        }
    }

    private async Task OpenCoreAsync(bool allowAutoPlay)
    {
        if (disposed||favorite.IsSaving) return;
        var current = ++version;
        compatAttempted = false;
        request?.Cancel(); request?.Dispose();
        request = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        var cancellation = request.Token;
        busy = true; failed = loaded = playing = false;
        ClearMedia();
        positionText.Text = "—";
        ViewerNotice.Set(status,isAudio ? "音声を読み込んでいます…" : "動画を読み込んでいます…");
        hideTimer.Stop(); UpdateControls();
        try
        {
            await OpenRangeStreamAsync(isAudio ? () => api.OpenAudioRangeAsync(itemId, cancellation) : () => api.OpenVideoRangeAsync(itemId, cancellation), 8, isCompat: false, current, cancellation);
        }
        catch (OperationCanceledException) when (!lifetime.IsCancellationRequested && current != version) { }
        catch (Exception ex) when (!isAudio && !disposed && current == version && !cancellation.IsCancellationRequested
            && ex is not OperationCanceledException
            && ex is not HttpRequestException
            && ex is not ArchiveReadException { Status: HttpStatusCode.Forbidden or HttpStatusCode.NotFound or HttpStatusCode.Conflict or HttpStatusCode.ServiceUnavailable })
        {
            AppLog.Error(ex);
            compatAttempted = true;
            ClearMedia();
            ViewerNotice.Set(status, "互換形式で再生を準備しています…");
            try
            {
                await OpenRangeStreamAsync(() => api.OpenVideoCompatRangeAsync(itemId, cancellation), 15, isCompat: true, current, cancellation);
            }
            catch (OperationCanceledException) when (!lifetime.IsCancellationRequested && current != version) { }
            catch (Exception compatEx) { if (current == version) ReportFailure(compatEx); }
        }
        catch (Exception ex) { if (current == version) ReportFailure(ex); }
        finally
        {
            if (!disposed && current == version)
            {
                busy = false;
                UpdateControls();
                TitleChanged?.Invoke(WindowTitle);
                if (allowAutoPlay && loaded && !failed && !playing) StartPlayback();
                if (!keyboardChrome && !failed) hideTimer.Start();
            }
        }
    }

    private static bool IsNearEnd(TimeSpan pos, TimeSpan dur)
        => dur > TimeSpan.Zero && pos >= dur - TimeSpan.FromMilliseconds(Math.Min(350, dur.TotalMilliseconds * 0.25));

    private void HandlePlaybackEnded()
    {
        if (disposed || !loaded) return;
        var wasPlaying = playing;
        playing = false;
        ended = true;
        observedPlaying = false;
        stalledAtEndTicks = 0;
        positionTimer.Stop();
        position = duration;
        positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
        ViewerNotice.Set(status);
        UpdateControls();
        if (wasPlaying) ShowChrome();
    }

    private void HandlePlaybackPaused(TimeSpan sessionPos)
    {
        if (disposed || !loaded || !playing) return;
        playing = false;
        observedPlaying = false;
        stalledAtEndTicks = 0;
        positionTimer.Stop();
        position = VideoPlayerPolicy.ClampSeek(sessionPos, duration);
        positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
        ViewerNotice.Set(status);
        UpdateControls();
        ShowChrome();
    }

    private void SyncPosition()
    {
        if (disposed || !loaded || !playing || mediaPlayer is null) return;
        var session = mediaPlayer.PlaybackSession;
        var state = session.PlaybackState;
        var sessionPos = session.Position;
        if (sessionPos > position) position = VideoPlayerPolicy.ClampSeek(sessionPos, duration);
        if (state == MediaPlaybackState.Playing) observedPlaying = true;
        if (!seekDragging && duration > TimeSpan.Zero)
        {
            if (state is MediaPlaybackState.Paused or MediaPlaybackState.None)
            {
                if (IsNearEnd(sessionPos, duration) || IsNearEnd(position, duration)) { HandlePlaybackEnded(); return; }
                if (observedPlaying && Environment.TickCount64 - lastMaximizeTick > 1500) { HandlePlaybackPaused(sessionPos); return; }
            }
            else if (state == MediaPlaybackState.Playing && observedPlaying && sessionPos >= duration - TimeSpan.FromMilliseconds(60))
            {
                if (Math.Abs((sessionPos - lastTickPosition).TotalMilliseconds) < 5)
                {
                    if (++stalledAtEndTicks >= 2) { mediaPlayer.Pause(); HandlePlaybackEnded(); return; }
                }
                else
                {
                    stalledAtEndTicks = 0;
                }
            }
            else
            {
                stalledAtEndTicks = 0;
            }
        }
        lastTickPosition = sessionPos;
        positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
        SyncSeekBar();
    }

    private void StartPlayback(bool revealChrome = true)
    {
        if (!loaded || busy || failed || mediaPlayer is null || playing) return;
        if (ended || IsNearEnd(position, duration))
        {
            position = TimeSpan.Zero;
            mediaPlayer.PlaybackSession.Position = TimeSpan.Zero;
        }
        ended = false;
        observedPlaying = false;
        stalledAtEndTicks = 0;
        lastTickPosition = position;
        playing = true;
        mediaPlayer.Play();
        positionTimer.Start();
        ViewerNotice.Set(status);
        UpdateControls();
        if (revealChrome) ShowChrome();
    }

    private void TogglePlayPause(bool revealChrome = true)
    {
        if (!loaded || busy || failed || mediaPlayer is null) return;
        if (!playing) { StartPlayback(revealChrome); return; }
        var session = mediaPlayer.PlaybackSession;
        if (observedPlaying && session.PlaybackState is MediaPlaybackState.Paused or MediaPlaybackState.None && IsNearEnd(session.Position, duration))
        {
            playing = false;
            ended = true;
            StartPlayback(revealChrome);
            return;
        }
        playing = false;
        observedPlaying = false;
        stalledAtEndTicks = 0;
        positionTimer.Stop();
        mediaPlayer.Pause();
        var sessionPos = session.Position;
        if (sessionPos > position) position = VideoPlayerPolicy.ClampSeek(sessionPos, duration);
        positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
        ViewerNotice.Set(status);
        UpdateControls();
        if (revealChrome) ShowChrome();
    }

    private void FinishSeekDrag()
    {
        if (!seekDragging) return;
        seekDragging = false;
        SeekTo(TimeSpan.FromSeconds(seekBar.Value), revealChrome: false);
        hideTimer.Start();
    }

    private void Seek(double deltaSeconds)=>SeekTo(position+TimeSpan.FromSeconds(deltaSeconds));

    private void SeekTo(TimeSpan target, bool revealChrome = true)
    {
        if(!loaded||busy||failed||mediaPlayer is null)return;
        ended = false;
        stalledAtEndTicks = 0;
        position=VideoPlayerPolicy.ClampSeek(target,duration);mediaPlayer.PlaybackSession.Position=position;
        lastTickPosition = position;
        positionText.Text=VideoPlayerPolicy.FormatPosition(position,duration);
        ViewerNotice.Set(status);UpdateControls();
        if(revealChrome)ShowChrome();
    }
    private void SyncSeekBar()
    {
        if(seekDragging)return;
        updatingSeek=true;
        try{seekBar.Maximum=Math.Max(0.1,duration.TotalSeconds);seekBar.Value=Math.Clamp(position.TotalSeconds,0,seekBar.Maximum);}
        finally{updatingSeek=false;}
    }
    private void HideSeekPreview()
    {seekHover=false;previewWanted=-1;previewDisplayed=-1;previewTimer.Stop();seekPreview.Visibility=Visibility.Collapsed;seekImage.Source=null;}

    private async Task LoadSeekPreviewAsync()
    {
        if(disposed||previewBusy||!seekHover||previewWanted<0||previewWanted==previewDisplayed||mediaRange is null)return;
        var wanted=previewWanted;var current=version;var manifest=mediaRange.Manifest;
        previewBusy=true;previewRequest=CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token,request!.Token);var token=previewRequest.Token;
        try
        {
            var bytes=await api.VideoFrameAsync(manifest,wanted,token);
            using var stream=new InMemoryRandomAccessStream();using(var writer=new DataWriter(stream)){writer.WriteBytes(bytes);await writer.StoreAsync().AsTask(token);writer.DetachStream();}stream.Seek(0);
            var bitmap=new BitmapImage();await bitmap.SetSourceAsync(stream).AsTask(token);
            if(!disposed&&current==version)
            {
                if(!previewFrames.ContainsKey(wanted)){previewFrameOrder.Enqueue(wanted);previewFrames[wanted]=bitmap;}
                while(previewFrameOrder.Count>8)previewFrames.Remove(previewFrameOrder.Dequeue());
                if(seekHover&&previewWanted==wanted)
                {seekImage.Source=bitmap;seekHint.Visibility=Visibility.Collapsed;previewDisplayed=wanted;seekTime.Text=VideoPlayerPolicy.FormatPosition(TimeSpan.FromMilliseconds(wanted),duration).Split(" / ")[0];AutomationProperties.SetName(seekImage,seekTime.Text+"のサムネイル");}
            }
        }
        catch(OperationCanceledException) { }
        catch(Exception)
        {
            if(!disposed&&current==version&&seekHover&&previewWanted==wanted)
            {previewDisplayed=wanted;seekHint.Text="サムネイルなし";seekHint.Visibility=Visibility.Visible;seekImage.Source=null;AutomationProperties.SetName(seekImage,"サムネイルを取得できません。シークは利用できます");}
        }
        finally
        {
            previewRequest?.Dispose();previewRequest=null;previewBusy=false;
            if(!disposed&&seekHover&&previewWanted>=0&&previewWanted!=previewDisplayed){previewTimer.Stop();previewTimer.Start();}
        }
    }

    private void AdjustVolume(int delta)
    {
        volume = VideoPlayerPolicy.ClampVolume(volume + delta);
        if (mediaPlayer is not null) mediaPlayer.Volume = volume / 100.0;
        UpdateControls(); ShowChrome();
    }

    private void ToggleMute()
    {
        muted = !muted;
        if (mediaPlayer is not null) mediaPlayer.IsMuted = muted;
        UpdateControls(); ShowChrome();
    }

    private void ClearMedia()
    {
        HideSeekPreview();previewRequest?.Cancel();previewFrames.Clear();previewFrameOrder.Clear();
        mediaRange?.Dispose();mediaRange=null;
        positionTimer.Stop();
        playing = false;
        ended = false;
        observedPlaying = false;
        stalledAtEndTicks = 0;
        duration = position = lastTickPosition = TimeSpan.Zero;
        if (mediaPlayer is not null)
        {
            try { mediaPlayer.Pause(); mediaPlayer.Source = null; playerElement.SetMediaPlayer(null); mediaPlayer.Dispose(); } catch { }
            mediaPlayer = null;
        }
        mediaSource?.Dispose(); mediaSource = null;
        mediaStream?.Dispose(); mediaStream = null;mediaRange?.Dispose();mediaRange=null;
    }

    private void ReportFailure(Exception ex)
    {
        if (disposed || lifetime.IsCancellationRequested) return;
        ClearMedia();
        failed = true; loaded = false;
        positionText.Text = "—";
        ViewerNotice.Set(status,ex switch
        {
            ArchiveReadException { Status: HttpStatusCode.Conflict } => ex.Message,
            ArchiveReadException { Status: HttpStatusCode.ServiceUnavailable } => "ほかのメディアを読み込み中です。少し待って再試行してください。",
            ArchiveReadException { Status: HttpStatusCode.Forbidden } => ex.Message,
            OperationCanceledException => "読み込みがタイムアウトしました。再試行してください。",
            HttpRequestException => "接続できません。閉じてライブラリから再接続してください。",
            _ => "この動画は再生できません（未対応の形式・コーデック）"
        });
        ShowChrome();
    }

    private void UpdateControls()
    {
        favorite.UpdateAvailability(!disposed&&!busy&&loaded&&!failed);
        seekBar.IsEnabled=!busy&&loaded&&!failed;SyncSeekBar();
        playPause.IsEnabled = !busy && loaded;
        playPause.Content = new SymbolIcon(playing ? Symbol.Pause : Symbol.Play);
        AutomationProperties.SetName(playPause, playing ? "一時停止" : "再生");
        seekBack.IsEnabled = !busy && loaded && position > TimeSpan.Zero;
        seekForward.IsEnabled = !busy && loaded && position < duration;
        mute.IsEnabled = !busy;
        mute.Content = new SymbolIcon(muted ? Symbol.Mute : Symbol.Volume);
        AutomationProperties.SetName(mute, muted ? "消音解除" : "消音");
        volumeDown.IsEnabled = !busy && volume > 0;
        volumeUp.IsEnabled = !busy && volume < 100;
        updatingVolume=true;try{volumeSlider.Value=volume;volumeSlider.IsEnabled=!busy;}finally{updatingVolume=false;}
        volumeText.Text = muted ? "消音" : $"{volume}%";
        retry.Visibility = failed ? Visibility.Visible : Visibility.Collapsed;
        retry.IsEnabled = !busy && failed&&!favorite.IsSaving;
        openExternal.Visibility = !isAudio && failed && !busy ? Visibility.Visible : Visibility.Collapsed;
        openExternal.IsEnabled = !isAudio && failed && !busy && !favorite.IsSaving;
        hideTimer?.RefreshHoverHint();
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        favorite.Dispose();
        hideTimer.Dispose();menu.Hide();previewTimer.Stop();
        lifetime.Cancel();
        request?.Cancel();
        ClearMedia();
        request?.Dispose();
        lifetime.Dispose();
    }
}
