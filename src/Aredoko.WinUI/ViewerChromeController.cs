using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Windows.UI;

namespace Aredoko_WinUI;

internal interface IViewerWindowTitle
{
    string WindowTitle {get;}
    event Action<string>? TitleChanged;
}

// Owns only transient chrome; notices and image geometry never participate in
// its layout. Moving into the bottom hotzone or over the toolbar reveals it
// smoothly; moving off fades it out quickly unless pinned or kept open.
internal sealed class ViewerChromeController : IDisposable
{
    private const double BottomHotzonePx = 72;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer timer;
    private readonly Grid root;
    private readonly Border toolbar;
    private readonly UIElement viewport;
    private readonly Func<bool> keepVisible;
    private readonly Border hoverHint=new(){IsHitTestVisible=false,Visibility=Visibility.Collapsed,RequestedTheme=ElementTheme.Dark,Background=new SolidColorBrush(Color.FromArgb(0xEB,0x20,0x20,0x26)),BorderBrush=new SolidColorBrush(Color.FromArgb(0x55,0xFF,0xFF,0xFF)),BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(8),Padding=new Thickness(10,4,10,4),HorizontalAlignment=HorizontalAlignment.Left,VerticalAlignment=VerticalAlignment.Bottom};
    private readonly TextBlock hoverHintText=new(){Foreground=new SolidColorBrush(Colors.White),TextWrapping=TextWrapping.NoWrap};
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer hoverHintTimer;
    private FrameworkElement? hoverTarget;
    private Func<string>? hoverTextProvider;
    private Storyboard? activeStoryboard;
    private long animVersion;
    private bool overToolbar,inHotzone,hiding,disposed;

    public ViewerChromeController(Grid root,Border toolbar,UIElement viewport,Func<bool> keepVisible)
    {
        this.root=root;this.toolbar=toolbar;this.viewport=viewport;this.keepVisible=keepVisible;
        hoverHintText.Style=(Style)Application.Current.Resources["CaptionTextBlockStyle"];
        hoverHint.Child=hoverHintText;
        Canvas.SetZIndex(hoverHint,20);
        hoverHintTimer=root.DispatcherQueue.CreateTimer();hoverHintTimer.Interval=TimeSpan.FromMilliseconds(140);hoverHintTimer.IsRepeating=false;
        hoverHintTimer.Tick+=(_,_)=>ShowHoverHint();
        timer=root.DispatcherQueue.CreateTimer();timer.Interval=TimeSpan.FromMilliseconds(140);timer.IsRepeating=false;
        timer.Tick+=(_,_)=>
        {
            if(ShouldStayVisible())return;
            FadeOut();
        };
        toolbar.PointerEntered+=(_,_)=>{overToolbar=true;timer.Stop();if(hiding||toolbar.Visibility!=Visibility.Visible||toolbar.Opacity<0.99)FadeIn();};
        toolbar.PointerExited+=(_,_)=>{overToolbar=false;Start(fast:true);};
        root.AddHandler(UIElement.PointerMovedEvent,new PointerEventHandler((_,args)=>
        {
            var point=args.GetCurrentPoint(root).Position;
            var overBottom=point.Y>=Math.Max(0,root.ActualHeight-BottomHotzonePx);
            if(overBottom)
            {
                inHotzone=true;
                timer.Stop();
                if(hiding||toolbar.Visibility!=Visibility.Visible||toolbar.Opacity<0.99)FadeIn();
            }
            else
            {
                var leftHotzone=inHotzone;
                inHotzone=false;
                if(!ShouldStayVisible()&&toolbar.Visibility==Visibility.Visible&&!hiding&&(leftHotzone||!timer.IsRunning))
                    Start(fast:true);
            }
        }),true);
        root.PointerExited+=(_,_)=>{overToolbar=false;inHotzone=false;Start(fast:true);};
        if(ViewerOptions.Value.AlwaysShowControls)
        {
            toolbar.Visibility=Visibility.Visible;toolbar.Opacity=1;toolbar.IsHitTestVisible=true;
        }
        else
        {
            toolbar.Visibility=Visibility.Collapsed;toolbar.Opacity=0;toolbar.IsHitTestVisible=false;
        }
    }

    private bool ShouldStayVisible()=>disposed||overToolbar||inHotzone||keepVisible()||ViewerOptions.Value.AlwaysShowControls;

    public void Show()
    {
        if(disposed)return;
        FadeIn();
        Start(fast:false);
    }

    public void Start()=>Start(fast:false);

    public void Start(bool fast)
    {
        if(disposed)return;
        timer.Stop();
        if(ViewerOptions.Value.AlwaysShowControls||keepVisible()||overToolbar||inHotzone)
        {
            if(hiding||toolbar.Visibility!=Visibility.Visible||toolbar.Opacity<0.99)FadeIn();
            return;
        }
        timer.Interval=TimeSpan.FromMilliseconds(fast?140:600);
        timer.Start();
    }

    public void Stop()=>timer.Stop();

    public void SyncPinState()
    {
        if(disposed)return;
        if(ViewerOptions.Value.AlwaysShowControls)
        {
            timer.Stop();
            FadeIn();
        }
        else
        {
            Start(fast:true);
        }
    }

    private void FadeIn()
    {
        if(disposed)return;
        hiding=false;
        var token=++animVersion;
        var from=toolbar.Visibility==Visibility.Visible?toolbar.Opacity:0.0;
        activeStoryboard?.Stop();
        activeStoryboard=null;
        toolbar.Visibility=Visibility.Visible;
        toolbar.IsHitTestVisible=true;
        toolbar.Opacity=1.0;
        if(from>=0.98)return;
        var anim=new DoubleAnimation
        {
            From=from,
            To=1.0,
            Duration=new Duration(TimeSpan.FromMilliseconds(110)),
            EasingFunction=new CubicEase{EasingMode=EasingMode.EaseOut}
        };
        Storyboard.SetTarget(anim,toolbar);
        Storyboard.SetTargetProperty(anim,"Opacity");
        var sb=new Storyboard();
        sb.Children.Add(anim);
        sb.Completed+=(_,_)=>
        {
            if(!disposed&&animVersion==token){toolbar.Opacity=1.0;activeStoryboard=null;}
        };
        activeStoryboard=sb;
        sb.Begin();
    }

    private void FadeOut()
    {
        if(disposed||toolbar.Visibility==Visibility.Collapsed)return;
        HideHoverHint();
        hiding=true;
        var token=++animVersion;
        var from=toolbar.Opacity;
        activeStoryboard?.Stop();
        activeStoryboard=null;
        toolbar.IsHitTestVisible=false;
        toolbar.Opacity=0.0;
        var anim=new DoubleAnimation
        {
            From=from,
            To=0.0,
            Duration=new Duration(TimeSpan.FromMilliseconds(160)),
            EasingFunction=new QuadraticEase{EasingMode=EasingMode.EaseIn}
        };
        Storyboard.SetTarget(anim,toolbar);
        Storyboard.SetTargetProperty(anim,"Opacity");
        var sb=new Storyboard();
        sb.Children.Add(anim);
        sb.Completed+=(_,_)=>
        {
            if(disposed||animVersion!=token)return;
            hiding=false;
            activeStoryboard=null;
            if(ShouldStayVisible())
            {
                FadeIn();
                return;
            }
            if(IsFocusInside(toolbar,toolbar.XamlRoot))viewport.Focus(FocusState.Programmatic);
            toolbar.Visibility=Visibility.Collapsed;
        };
        activeStoryboard=sb;
        sb.Begin();
    }

    private static bool IsFocusInside(DependencyObject container,XamlRoot? xamlRoot)
    {
        if(xamlRoot is null)return false;
        for(var node=FocusManager.GetFocusedElement(xamlRoot) as DependencyObject;node is not null;node=VisualTreeHelper.GetParent(node))
            if(ReferenceEquals(node,container))return true;
        return false;
    }

    public void AttachHoverHint(FrameworkElement target,string text)=>AttachHoverHint(target,()=>text);
    public void AttachHoverHint(FrameworkElement target,Func<string> textProvider)
    {
        ToolTipService.SetToolTip(target,null);
        if(!root.Children.Contains(hoverHint))root.Children.Add(hoverHint);
        target.PointerEntered+=(_,_)=>
        {
            if(disposed)return;
            hoverTarget=target;hoverTextProvider=textProvider;
            if(hoverHint.Visibility==Visibility.Visible)ShowHoverHint();
            else { hoverHintTimer.Stop(); hoverHintTimer.Start(); }
        };
        target.PointerExited+=(_,_)=>{if(ReferenceEquals(hoverTarget,target))HideHoverHint();};
        target.AddHandler(UIElement.PointerPressedEvent,new PointerEventHandler((_,_)=>{if(ReferenceEquals(hoverTarget,target))HideHoverHint();}),true);
    }

    public void RefreshHoverHint()
    {
        if(!disposed&&hoverHint.Visibility==Visibility.Visible&&hoverTarget is not null&&hoverTextProvider is not null)
            ShowHoverHint();
    }

    public void HideHoverHint()
    {
        hoverHintTimer.Stop();
        hoverTarget=null;
        hoverTextProvider=null;
        hoverHint.Visibility=Visibility.Collapsed;
    }

    private void ShowHoverHint()
    {
        if(disposed||hoverTarget is null||hoverTextProvider is null||!hoverTarget.IsLoaded||toolbar.Visibility!=Visibility.Visible||hiding)
        {
            hoverHint.Visibility=Visibility.Collapsed;
            return;
        }
        var text=hoverTextProvider();
        if(string.IsNullOrWhiteSpace(text))
        {
            hoverHint.Visibility=Visibility.Collapsed;
            return;
        }
        hoverHintText.Text=text;
        hoverHint.Measure(new Windows.Foundation.Size(420,60));
        var center=hoverTarget.TransformToVisual(root).TransformPoint(new Windows.Foundation.Point(hoverTarget.ActualWidth/2,0)).X;
        var rootWidth=root.ActualWidth>0?root.ActualWidth:hoverHint.DesiredSize.Width+16;
        var left=Math.Clamp(center-hoverHint.DesiredSize.Width/2,8,Math.Max(8,rootWidth-hoverHint.DesiredSize.Width-8));
        var bottom=(toolbar.ActualHeight>0?toolbar.ActualHeight:44)+24;
        hoverHint.Margin=new Thickness(left,0,0,bottom);
        hoverHint.Visibility=Visibility.Visible;
    }

    public void Dispose()
    {
        disposed=true;timer.Stop();HideHoverHint();
        activeStoryboard?.Stop();activeStoryboard=null;
    }

    public static void StyleFloatingPill(Border toolbar,double cornerRadius=24,Thickness? padding=null)
    {
        toolbar.RequestedTheme=ElementTheme.Dark;
        toolbar.Style=(Style)Application.Current.Resources["ViewerFloatingPillStyle"];
        toolbar.HorizontalAlignment=HorizontalAlignment.Center;
        toolbar.VerticalAlignment=VerticalAlignment.Bottom;
        toolbar.Margin=new Thickness(16,0,16,16);
        toolbar.CornerRadius=new CornerRadius(cornerRadius);
        if(padding is {} value)toolbar.Padding=value;
    }

    public static Button PillButton(Symbol symbol)=>new()
    {
        Content=new SymbolIcon(symbol),
        MinWidth=32,
        Height=32,
        Padding=new Thickness(6),
        CornerRadius=new CornerRadius(16),
        Background=new SolidColorBrush(Colors.Transparent),
        BorderThickness=new Thickness(0)
    };

    public static void StylePillButton(ButtonBase button)
    {
        button.MinWidth=32;
        button.Height=32;
        button.Padding=new Thickness(6);
        button.CornerRadius=new CornerRadius(16);
        button.Background=new SolidColorBrush(Colors.Transparent);
        button.BorderThickness=new Thickness(0);
    }

    public static Button PillTextButton(string text)=>new()
    {
        Content=text,
        MinWidth=32,
        Height=32,
        Padding=new Thickness(8,4,8,4),
        CornerRadius=new CornerRadius(16),
        Background=new SolidColorBrush(Colors.Transparent),
        BorderThickness=new Thickness(0)
    };

    public static Border Divider()=>new()
    {
        Width=1,
        Height=18,
        Margin=new Thickness(2,0,2,0),
        VerticalAlignment=VerticalAlignment.Center,
        Background=new SolidColorBrush(Color.FromArgb(0x38,0xFF,0xFF,0xFF))
    };

    public static Border WrapScrubber(Slider slider,double width)
    {
        slider.VerticalAlignment=VerticalAlignment.Center;
        slider.Padding=new Thickness(0);
        if(double.IsFinite(width)&&width>0)slider.Width=width;
        ApplySliderTheme(slider);
        return new Border
        {
            Background=new SolidColorBrush(Color.FromArgb(0x52,0x00,0x00,0x00)),
            BorderBrush=new SolidColorBrush(Color.FromArgb(0x28,0xFF,0xFF,0xFF)),
            BorderThickness=new Thickness(1),
            CornerRadius=new CornerRadius(15),
            Height=30,
            Padding=new Thickness(10,0,10,0),
            VerticalAlignment=VerticalAlignment.Center,
            Child=slider
        };
    }

    public static void ApplySliderTheme(Slider slider)
    {
        var white=new SolidColorBrush(Colors.White);
        var whiteHover=new SolidColorBrush(Color.FromArgb(0xFF,0xF0,0xF0,0xF0));
        var whitePressed=new SolidColorBrush(Color.FromArgb(0xFF,0xDC,0xDC,0xDC));
        var track=new SolidColorBrush(Color.FromArgb(0x36,0xFF,0xFF,0xFF));
        var fill=new SolidColorBrush(Color.FromArgb(0xD8,0xFF,0xFF,0xFF));
        slider.Resources["SliderThumbBackground"]=white;
        slider.Resources["SliderThumbBackgroundPointerOver"]=whiteHover;
        slider.Resources["SliderThumbBackgroundPressed"]=whitePressed;
        slider.Resources["SliderTrackFill"]=track;
        slider.Resources["SliderTrackFillPointerOver"]=track;
        slider.Resources["SliderTrackFillPressed"]=track;
        slider.Resources["SliderTrackValueFill"]=fill;
        slider.Resources["SliderTrackValueFillPointerOver"]=white;
        slider.Resources["SliderTrackValueFillPressed"]=white;
    }

    public static (ToggleButton Button,Action Sync) CreatePinButton(string automationId,Action changed,Action<Exception> failed)
    {
        var icon=new FontIcon{FontFamily=new FontFamily("Segoe Fluent Icons"),Glyph="\uE718",FontSize=14};
        var button=new ToggleButton
        {
            Content=icon,
            MinWidth=32,
            Width=32,
            Height=32,
            Padding=new Thickness(0),
            CornerRadius=new CornerRadius(16),
            BorderThickness=new Thickness(0)
        };
        var syncing=false;
        void Sync()
        {
            syncing=true;
            try
            {
                var pinned=ViewerOptions.Value.AlwaysShowControls;
                button.IsChecked=pinned;
                var name=pinned?"操作バーの固定を解除":"操作バーを常に表示（ピン留め）";
                AutomationProperties.SetName(button,name);
                ToolTipService.SetToolTip(button,name);
            }
            finally{syncing=false;}
        }
        AutomationProperties.SetAutomationId(button,automationId);
        Sync();
        button.Click+=(_,_)=>
        {
            if(syncing)return;
            var target=button.IsChecked==true;
            try
            {
                ViewerOptions.SavePresentation(ViewerOptions.Value.EnlargeSmallImages,target,ViewerOptions.Value.LoopBookPages);
                Sync();
                changed();
            }
            catch(Exception ex)
            {
                Sync();
                failed(ex);
            }
        };
        return (button,Sync);
    }

    public static void AttachNotices(Grid root,params TextBlock[] messages) => AttachNotices(root,76,messages);
    public static void AttachNotices(Grid root,double bottomInset,params TextBlock[] messages)
    {
        var stack=new StackPanel{Spacing=8,VerticalAlignment=VerticalAlignment.Bottom,HorizontalAlignment=HorizontalAlignment.Center,MaxWidth=600,Margin=new Thickness(16,0,16,bottomInset),IsHitTestVisible=false};
        foreach(var message in messages)
        {
            var host=new Border{Child=message,RequestedTheme=ElementTheme.Dark,Style=(Style)Application.Current.Resources["ImageViewerOverlayStyle"]};
            host.SetBinding(UIElement.VisibilityProperty,new Binding{Source=message,Path=new PropertyPath("Visibility"),Mode=BindingMode.OneWay});
            stack.Children.Add(host);
        }
        root.Children.Add(stack);
    }

    public static MenuFlyout Settings(bool book,Action changed,Action<Exception> failed)
    {
        var menu=new MenuFlyout();
        var enlarge=new ToggleMenuFlyoutItem{Text="小さい画像を画面に合わせる"};
        var controls=new ToggleMenuFlyoutItem{Text="操作バーを常時表示"};
        var loop=new ToggleMenuFlyoutItem{Text="末尾から先頭へループ"};
        foreach(var (item,id) in new[]{(enlarge,"ViewerEnlargeImages"),(controls,"ViewerAlwaysControls"),(loop,"ViewerLoopPages")})
            AutomationProperties.SetAutomationId(item,id);
        void Sync(){enlarge.IsChecked=ViewerOptions.Value.EnlargeSmallImages;controls.IsChecked=ViewerOptions.Value.AlwaysShowControls;loop.IsChecked=ViewerOptions.Value.LoopBookPages;}
        Sync();menu.Opened+=(_,_)=>Sync();menu.Items.Add(enlarge);menu.Items.Add(controls);if(book)menu.Items.Add(loop);
        foreach(var item in new[]{enlarge,controls,loop})item.Click+=(_,_)=>
        {
            try{ViewerOptions.SavePresentation(enlarge.IsChecked,controls.IsChecked,book?loop.IsChecked:ViewerOptions.Value.LoopBookPages);changed();}
            catch(Exception ex){Sync();failed(ex);}
        };
        return menu;
    }
}
