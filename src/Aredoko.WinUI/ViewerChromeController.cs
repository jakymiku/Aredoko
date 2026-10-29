using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;

namespace Aredoko_WinUI;

internal interface IViewerWindowTitle
{
    string WindowTitle {get;}
    event Action<string>? TitleChanged;
}

// Owns only transient chrome; notices and image geometry never participate in
// its layout. Normal movement across the image does not reveal the toolbar.
internal sealed class ViewerChromeController : IDisposable
{
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer timer;
    private readonly Grid root;
    private readonly Border toolbar;
    private readonly ScrollViewer viewport;
    private readonly Func<bool> keepVisible;
    private bool overToolbar,disposed;
    public ViewerChromeController(Grid root,Border toolbar,ScrollViewer viewport,Func<bool> keepVisible)
    {
        this.root=root;this.toolbar=toolbar;this.viewport=viewport;this.keepVisible=keepVisible;
        timer=root.DispatcherQueue.CreateTimer();timer.Interval=TimeSpan.FromSeconds(1);timer.IsRepeating=false;
        timer.Tick+=(_,_)=>
        {
            if(disposed||overToolbar||keepVisible()||ViewerOptions.Value.AlwaysShowControls)return;
            viewport.Focus(FocusState.Programmatic);toolbar.Visibility=Visibility.Collapsed;
        };
        toolbar.PointerEntered+=(_,_)=>{overToolbar=true;Stop();};
        toolbar.PointerExited+=(_,_)=>{overToolbar=false;Start();};
        root.AddHandler(UIElement.PointerMovedEvent,new PointerEventHandler((_,args)=>
        {
            if(args.GetCurrentPoint(root).Position.Y>=root.ActualHeight-32)Show();
            else if(!timer.IsRunning)Start();
        }),true);
        root.PointerExited+=(_,_)=>{overToolbar=false;Start();};
        toolbar.Visibility=ViewerOptions.Value.AlwaysShowControls?Visibility.Visible:Visibility.Collapsed;
    }
    public void Show(){if(disposed)return;toolbar.Visibility=Visibility.Visible;Start();}
    public void Start(){if(disposed)return;timer.Stop();if(ViewerOptions.Value.AlwaysShowControls)toolbar.Visibility=Visibility.Visible;else timer.Start();}
    public void Stop()=>timer.Stop();
    public void Dispose(){disposed=true;timer.Stop();}
    public static void AttachNotices(Grid root,params TextBlock[] messages) => AttachNotices(root,64,messages);
    public static void AttachNotices(Grid root,double bottomInset,params TextBlock[] messages)
    {
        var stack=new StackPanel{Spacing=8,VerticalAlignment=VerticalAlignment.Bottom,HorizontalAlignment=HorizontalAlignment.Center,MaxWidth=600,Margin=new Thickness(16,0,16,bottomInset)};
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
        var enlarge=new ToggleMenuFlyoutItem{Text="小さい画像も画面に合わせて拡大"};
        var controls=new ToggleMenuFlyoutItem{Text="操作バーを常に表示"};
        var loop=new ToggleMenuFlyoutItem{Text="最後のページから先頭へ戻る"};
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
