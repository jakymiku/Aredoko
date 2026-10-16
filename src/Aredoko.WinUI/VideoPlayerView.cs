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
internal sealed class VideoPlayerView : Grid, IDisposable
{
    private readonly LibraryApi api;
    private readonly int itemId;
    private readonly string itemTitle;
    private readonly int? initialPositionMs;
    private readonly CancellationTokenSource lifetime = new();
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer hideTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer positionTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer previewTimer;
    private readonly Slider seekBar = new() { Minimum=0, Maximum=1, SmallChange=1, LargeChange=10, StepFrequency=0.1, IsThumbToolTipEnabled=false, HorizontalAlignment=HorizontalAlignment.Stretch };
    private readonly Image seekImage = new() { Width=256, Height=144, Stretch=Stretch.Uniform };
    private readonly TextBlock seekHint = new() { Text="読み込み中…", HorizontalAlignment=HorizontalAlignment.Center, VerticalAlignment=VerticalAlignment.Center };
    private readonly TextBlock seekTime = new() { HorizontalAlignment=HorizontalAlignment.Center };
    private readonly Border seekPreview = new() { Width=272, HorizontalAlignment=HorizontalAlignment.Left, VerticalAlignment=VerticalAlignment.Bottom, Visibility=Visibility.Collapsed, IsHitTestVisible=false, RequestedTheme=ElementTheme.Dark };
    private CancellationTokenSource? previewRequest;
    private bool updatingSeek, seekHover, previewBusy, updatingVolume;
    private readonly Slider volumeSlider=new(){Minimum=0,Maximum=100,StepFrequency=1,SmallChange=5,LargeChange=20,Width=112,VerticalAlignment=VerticalAlignment.Center};
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
    private readonly Border header = new() { VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0), RequestedTheme = ElementTheme.Dark };
    private readonly Border toolbar = new() { VerticalAlignment = VerticalAlignment.Bottom, HorizontalAlignment = HorizontalAlignment.Stretch, Margin = new Thickness(0), RequestedTheme = ElementTheme.Dark };
    private readonly Button playPause = IconButton(Symbol.Play);
    private readonly Button seekBack = IconButton(Symbol.Back);
    private readonly Button seekForward = IconButton(Symbol.Forward);
    private readonly Button mute = IconButton(Symbol.Volume);
    private readonly Button volumeDown = TextButton("−");
    private readonly Button volumeUp = TextButton("＋");
    private readonly Button retry = IconButton(Symbol.Refresh);
    private readonly Button close = IconButton(Symbol.Cancel);
    private readonly TextBlock title = new() { TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock positionText = new() { Text = "—", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock volumeText = new() { Text = "音量 80%", VerticalAlignment = VerticalAlignment.Center };
    private readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap, HorizontalAlignment = HorizontalAlignment.Center };
    private CancellationTokenSource? request;
    private MediaPlayer? mediaPlayer;
    private MediaSource? mediaSource;
    private IRandomAccessStream? mediaStream;
    private VideoRangeSource? mediaRange;
    private TimeSpan duration = TimeSpan.Zero;
    private TimeSpan position = TimeSpan.Zero;
    private int volume = 80;
    private int version;
    private bool busy, disposed, failed, loaded, playing, muted, keyboardChrome;
    public event Action<int>? ContentOpened;
    public event EventHandler? CloseRequested;

    public VideoPlayerView(LibraryApi api, int itemId, string titleText, int? initialPositionMs = null)
    {
        this.api = api;
        this.itemId = itemId;
        itemTitle = titleText;
        this.initialPositionMs = initialPositionMs;
        hideTimer = DispatcherQueue.CreateTimer(); hideTimer.Interval = TimeSpan.FromSeconds(2.5); hideTimer.IsRepeating = false;
        hideTimer.Tick += (_, _) => { if (!disposed && !keyboardChrome && !seekHover && !busy && !failed) HideChrome(); };
        positionTimer = DispatcherQueue.CreateTimer(); positionTimer.Interval = TimeSpan.FromMilliseconds(200);
        positionTimer.Tick += (_, _) => SyncPosition();
        previewTimer=DispatcherQueue.CreateTimer();previewTimer.Interval=TimeSpan.FromMilliseconds(320);previewTimer.IsRepeating=false;
        previewTimer.Tick+=async(_,_)=>await LoadSeekPreviewAsync();
        viewport.Background = (Brush)Application.Current.Resources["SolidBackgroundFillColorBaseBrush"];
        viewport.Children.Add(playerElement);
        Children.Add(viewport);
        header.Style = toolbar.Style = (Style)Application.Current.Resources["ImageViewerOverlayStyle"];
        var heading = new Grid { ColumnSpacing = 12 };
        heading.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        heading.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        heading.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        title.Text = itemTitle; ToolTipService.SetToolTip(title, itemTitle);
        title.Style = positionText.Style = volumeText.Style = status.Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"];
        heading.Children.Add(title); SetColumn(positionText, 1); heading.Children.Add(positionText); SetColumn(close, 2); heading.Children.Add(close);
        header.Child = heading; Children.Add(header);
        var actions=new Grid{ColumnSpacing=8};actions.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});actions.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
        var playback=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
        foreach(var control in new UIElement[]{playPause,seekBack,seekForward,retry})playback.Children.Add(control);
        var audio=new StackPanel{Orientation=Orientation.Horizontal,Spacing=4,HorizontalAlignment=HorizontalAlignment.Right};
        foreach(var control in new UIElement[]{mute,volumeDown,volumeSlider,volumeUp,volumeText})audio.Children.Add(control);
        actions.Children.Add(playback);SetColumn(audio,1);actions.Children.Add(audio);
        Identify(volumeSlider,"VideoVolume","音量（0〜100）");
        volumeSlider.ValueChanged+=(_,_)=>{if(updatingVolume)return;volume=VideoPlayerPolicy.ClampVolume((int)Math.Round(volumeSlider.Value));if(mediaPlayer is not null)mediaPlayer.Volume=volume/100.0;UpdateControls();ShowChrome();};
        viewport.Tapped+=(_,args)=>{if(!busy&&loaded&&!failed){args.Handled=true;TogglePlayPause();}};
        toolbar.BorderThickness=new Thickness(0,1,0,0);toolbar.CornerRadius=new CornerRadius(0);
        toolbar.MaxWidth=double.PositiveInfinity;toolbar.Padding=new Thickness(8,4,8,4);
        var bottom = new StackPanel { Spacing = 4, HorizontalAlignment=HorizontalAlignment.Stretch }; bottom.Children.Add(seekBar);bottom.Children.Add(actions); bottom.Children.Add(status);
        toolbar.Child = bottom; Children.Add(toolbar);
        seekPreview.Style=(Style)Application.Current.Resources["ImageViewerOverlayStyle"];
        seekTime.Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"];
        seekHint.Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"];
        var frameHost=new Grid();frameHost.Children.Add(seekImage);frameHost.Children.Add(seekHint);
        var previewContent=new StackPanel { Spacing=4 };previewContent.Children.Add(seekTime);previewContent.Children.Add(frameHost);seekPreview.Child=previewContent;Children.Add(seekPreview);
        Identify(seekBar,"VideoSeek","再生位置（秒）。左右キーで移動");
        Identify(seekImage,"VideoSeekImage","シーク先のサムネイル");Identify(seekTime,"VideoSeekTime","シーク先の時刻");Identify(seekPreview,"VideoSeekPreview","シーク先のプレビュー");
        seekBar.ValueChanged+=(_,_)=>{if(!updatingSeek)SeekTo(TimeSpan.FromSeconds(seekBar.Value));};
        seekBar.AddHandler(PointerMovedEvent,new PointerEventHandler((_,args)=>
        {
            if(!loaded||busy||failed||seekBar.ActualWidth<=0)return;
            seekHover=true;hideTimer.Stop();var point=args.GetCurrentPoint(seekBar).Position;
            var seconds=Math.Clamp(point.X/seekBar.ActualWidth,0,1)*duration.TotalSeconds;
            var millis=(int)Math.Min(86_400_000,Math.Max(0,Math.Min(seconds,duration.TotalSeconds-0.05))*1000);
            previewWanted=(int)Math.Clamp(Math.Round(millis/1000.0)*1000,0,Math.Max(0,Math.Floor((duration.TotalMilliseconds-50)/1000)*1000));
            seekTime.Text=VideoPlayerPolicy.FormatPosition(TimeSpan.FromMilliseconds(previewWanted),duration).Split(" / ")[0];
            seekPreview.Margin=new Thickness(Math.Clamp(point.X+8-136,8,Math.Max(8,ActualWidth-280)),0,0,toolbar.ActualHeight+8);
            if(previewFrames.TryGetValue(previewWanted,out var cached))
            {seekImage.Source=cached;previewDisplayed=previewWanted;seekHint.Visibility=Visibility.Collapsed;AutomationProperties.SetName(seekImage,seekTime.Text+"のサムネイル");}
            else if(previewDisplayed!=previewWanted)
            {
                if(seekImage.Source is null){seekHint.Text="読み込み中…";seekHint.Visibility=Visibility.Visible;}
                else seekTime.Text=VideoPlayerPolicy.FormatPosition(TimeSpan.FromMilliseconds(previewDisplayed),duration).Split(" / ")[0]+"（次を準備中）";
                if(!previewBusy){previewTimer.Stop();previewTimer.Start();}
            }
            seekPreview.Visibility=Visibility.Visible;
        }),true);
        seekBar.PointerExited+=(_,_)=>{HideSeekPreview();ShowChrome();};
        Identify(viewport, "VideoViewport", "動画表示。スペースで再生・一時停止、左右キーで移動");
        Identify(playerElement, "VideoElement", itemTitle + "の動画");
        Identify(header, "VideoHeader", "動画の情報と閉じる"); Identify(toolbar, "VideoToolbar", "動画の操作");
        Identify(playPause, "VideoPlayPause", "再生");
        Identify(seekBack, "VideoSeekBack", "1秒戻る"); Identify(seekForward, "VideoSeekForward", "1秒進む");
        Identify(mute, "VideoMute", "消音");
        Identify(volumeDown, "VideoVolumeDown", "音量を下げる"); Identify(volumeUp, "VideoVolumeUp", "音量を上げる");
        Identify(retry, "VideoRetry", "動画を再試行"); Identify(close, "VideoClose", "動画再生を閉じる");
        AutomationProperties.SetAutomationId(title, "VideoTitle");
        AutomationProperties.SetAutomationId(positionText, "VideoPosition");
        AutomationProperties.SetAutomationId(volumeText, "VideoVolumeStatus");
        AutomationProperties.SetAutomationId(status, "VideoStatus");
        AutomationProperties.SetLiveSetting(status, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        ToolTipService.SetToolTip(playPause, "再生 / 一時停止（Space）");
        ToolTipService.SetToolTip(seekBack, "1秒戻る（←）"); ToolTipService.SetToolTip(seekForward, "1秒進む（→）");
        ToolTipService.SetToolTip(mute, "消音 / 消音解除（M）");
        ToolTipService.SetToolTip(volumeDown, "音量を下げる"); ToolTipService.SetToolTip(volumeUp, "音量を上げる");
        ToolTipService.SetToolTip(retry, "読み込みを再試行"); ToolTipService.SetToolTip(close, "閉じる（Esc）");
        playPause.Click += (_, _) => TogglePlayPause();
        seekBack.Click += (_, _) => Seek(-1); seekForward.Click += (_, _) => Seek(1);
        mute.Click += (_, _) => ToggleMute();
        volumeDown.Click += (_, _) => AdjustVolume(-20); volumeUp.Click += (_, _) => AdjustVolume(20);
        retry.Click += async (_, _) => await OpenAsync();
        close.Click += (_, _) => CloseRequested?.Invoke(this, EventArgs.Empty);
        UpdateControls(); ShowChrome();
    }

    private static Button IconButton(Symbol symbol) => new() { Content = new SymbolIcon(symbol), MinWidth = 36, Padding = new Thickness(8) };
    private static Button TextButton(string label) => new() { Content = label, MinWidth = 36, Padding = new Thickness(8) };
    private static void Identify(DependencyObject control, string id, string name)
    { AutomationProperties.SetAutomationId(control, id); AutomationProperties.SetName(control, name); }

    private void ShowChrome()
    {
        if (disposed) return;
        header.Visibility = toolbar.Visibility = Visibility.Visible;
        hideTimer.Stop(); if (!keyboardChrome && !busy && !failed) hideTimer.Start();
    }

    private void HideChrome()
    {
        HideSeekPreview();viewport.Focus(FocusState.Programmatic);
        header.Visibility = toolbar.Visibility = Visibility.Collapsed;
    }

    public void AttachNavigation(UIElement dialog)
    {
        dialog.AddHandler(PointerMovedEvent, new PointerEventHandler((_, _) => { keyboardChrome = false; ShowChrome(); }), true);
        dialog.PreviewKeyDown += (_, args) =>
        {
            if (args.Key == VirtualKey.Escape) { args.Handled = true; CloseRequested?.Invoke(this, EventArgs.Empty); return; }
            if (args.Key == VirtualKey.Tab) { keyboardChrome = true; ShowChrome(); return; }
            foreach (var modifier in new[] { VirtualKey.Control, VirtualKey.Shift, VirtualKey.Menu, VirtualKey.LeftWindows, VirtualKey.RightWindows })
                if ((Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(modifier) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0) return;
            if (args.Key == VirtualKey.F10) { keyboardChrome = true; ShowChrome(); args.Handled = true; return; }
            if (args.Key == VirtualKey.Space) { args.Handled = true; TogglePlayPause(); return; }
            if (args.Key == VirtualKey.M) { args.Handled = true; ToggleMute(); return; }
            if (args.Key == VirtualKey.Left) { args.Handled = true; Seek(-1); return; }
            if (args.Key == VirtualKey.Right) { args.Handled = true; Seek(1); }
        };
    }

    public async Task OpenAsync()
    {
        if (disposed) return;
        var current = ++version;
        request?.Cancel(); request?.Dispose();
        request = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        var cancellation = request.Token;
        busy = true; failed = loaded = playing = false;
        ClearMedia();
        positionText.Text = "—";
        status.Text = "動画を読み込んでいます…";
        hideTimer.Stop(); UpdateControls();
        IRandomAccessStream? stream = null;
        VideoRangeSource? rangeSource = null;
        MediaSource? source = null;
        MediaPlayer? nextPlayer = null;
        try
        {
            rangeSource=await api.OpenVideoRangeAsync(itemId,cancellation);
            stream=new VideoRandomAccessStream(rangeSource);var mime=rangeSource.Manifest.Mime;
            cancellation.ThrowIfCancellationRequested();
            source = MediaSource.CreateFromStream(stream, mime);
            await source.OpenAsync().AsTask(cancellation);
            if (source.State != MediaSourceState.Opened) throw new InvalidDataException("動画を開けません。");
            var opened = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            nextPlayer = new MediaPlayer { AutoPlay = false, Volume = volume / 100.0, IsMuted = muted };
            nextPlayer.MediaOpened += (_, _) => opened.TrySetResult(true);
            nextPlayer.MediaFailed += (_, args) =>
            {
                opened.TrySetException(rangeSource?.Failure ?? mediaRange?.Failure ?? new InvalidDataException(args.ErrorMessage));
                DispatcherQueue.TryEnqueue(() => { if (!disposed && current == version) ReportFailure(rangeSource?.Failure ?? mediaRange?.Failure ?? new InvalidDataException(args.ErrorMessage)); });
            };
            nextPlayer.MediaEnded += (_, _) => DispatcherQueue.TryEnqueue(() =>
            {
                if (disposed || current != version || !loaded) return;
                playing = false; positionTimer.Stop();
                position = duration;
                positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
                status.Text = "最後まで再生しました。";
                UpdateControls(); ShowChrome();
            });
            playerElement.SetMediaPlayer(nextPlayer);
            nextPlayer.Source = source;
            await opened.Task.WaitAsync(TimeSpan.FromSeconds(8), cancellation);
            if (disposed || current != version)
            {
                rangeSource?.Dispose();nextPlayer.Source = null; playerElement.SetMediaPlayer(null); nextPlayer.Dispose(); source.Dispose(); stream.Dispose();
                return;
            }
            mediaStream = stream; mediaRange=rangeSource; mediaSource = source; mediaPlayer = nextPlayer;
            stream = null; rangeSource=null; source = null; nextPlayer = null;
            var natural = mediaPlayer.PlaybackSession.NaturalDuration;
            duration = natural > TimeSpan.Zero && natural != TimeSpan.MaxValue
                ? natural
                : mediaSource.Duration is TimeSpan d && d > TimeSpan.Zero ? d : TimeSpan.FromSeconds(1);
            position = TimeSpan.Zero;
            if (initialPositionMs is int startMs && startMs > 0 && duration > TimeSpan.Zero)
            {
                var target = TimeSpan.FromMilliseconds(Math.Min(startMs, Math.Max(0, duration.TotalMilliseconds - 50)));
                try { mediaPlayer.PlaybackSession.Position = target; position = target; } catch { }
            }
            positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
            loaded = true;
            ContentOpened?.Invoke(itemId);
            status.Text = "動画を開きました。再生ボタンまたはスペースキーで再生できます。";
        }
        catch (OperationCanceledException) when (!lifetime.IsCancellationRequested && current != version) { }
        catch (Exception ex) { if (current == version) ReportFailure(rangeSource?.Failure ?? ex); }
        finally
        {
            rangeSource?.Dispose();
            if (nextPlayer is not null) { try { nextPlayer.Source = null; playerElement.SetMediaPlayer(null); nextPlayer.Dispose(); } catch { } }
            source?.Dispose();
            stream?.Dispose();
            if (!disposed && current == version) { busy = false; UpdateControls(); if (!keyboardChrome && !failed) hideTimer.Start(); }
        }
    }

    private void SyncPosition()
    {
        if (disposed || !loaded || !playing || mediaPlayer is null) return;
        var sessionPos = mediaPlayer.PlaybackSession.Position;
        if (sessionPos > position) position = VideoPlayerPolicy.ClampSeek(sessionPos, duration);
        positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
        SyncSeekBar();
    }

    private void TogglePlayPause()
    {
        if (!loaded || busy || failed || mediaPlayer is null) return;
        if (!playing)
        {
            if (position >= duration && duration > TimeSpan.Zero)
            {
                position = TimeSpan.Zero;
                mediaPlayer.PlaybackSession.Position = TimeSpan.Zero;
            }
            playing = true;
            mediaPlayer.Play();
            positionTimer.Start();
            status.Text = "再生中";
        }
        else
        {
            playing = false;
            positionTimer.Stop();
            mediaPlayer.Pause();
            var sessionPos = mediaPlayer.PlaybackSession.Position;
            if (sessionPos > position) position = VideoPlayerPolicy.ClampSeek(sessionPos, duration);
            positionText.Text = VideoPlayerPolicy.FormatPosition(position, duration);
            status.Text = "一時停止中";
        }
        UpdateControls(); ShowChrome();
    }

    private void Seek(double deltaSeconds)=>SeekTo(position+TimeSpan.FromSeconds(deltaSeconds));

    private void SeekTo(TimeSpan target)
    {
        if(!loaded||busy||failed||mediaPlayer is null)return;
        position=VideoPlayerPolicy.ClampSeek(target,duration);mediaPlayer.PlaybackSession.Position=position;
        positionText.Text=VideoPlayerPolicy.FormatPosition(position,duration);
        status.Text=playing?"再生中":"一時停止中";UpdateControls();ShowChrome();
    }
    private void SyncSeekBar()
    {
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
        duration = position = TimeSpan.Zero;
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
        status.Text = ex switch
        {
            ArchiveReadException { Status: HttpStatusCode.Conflict } => ex.Message,
            ArchiveReadException { Status: HttpStatusCode.ServiceUnavailable } => "ほかのメディアを読み込み中です。少し待って再試行してください。",
            ArchiveReadException { Status: HttpStatusCode.Forbidden } => ex.Message,
            OperationCanceledException => "読み込みがタイムアウトしました。再試行してください。",
            HttpRequestException => "接続できません。閉じてライブラリから再接続してください。",
            _ => "この動画はWindowsの標準機能では再生できません。未対応の形式・コーデック、破損、または容量制限（2TBまで）を確認してください。"
        };
        ShowChrome();
    }

    private void UpdateControls()
    {
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
        volumeText.Text = muted ? $"消音中（{volume}%）" : $"音量 {volume}%";
        retry.IsEnabled = !busy && failed;
        close.IsEnabled = true;
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        hideTimer.Stop();previewTimer.Stop();
        lifetime.Cancel();
        request?.Cancel();
        ClearMedia();
        request?.Dispose();
        lifetime.Dispose();
    }
}
