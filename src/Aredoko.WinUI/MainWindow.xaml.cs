using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
namespace Aredoko_WinUI;
public sealed partial class MainWindow : Window
{
    public new static MainWindow Current { get; private set; } = null!;
    private bool closing;
    [DllImport("user32.dll")] private static extern uint GetDpiForWindow(IntPtr hwnd);
    public MainWindow() {
        Current=this;InitializeComponent();ExtendsContentIntoTitleBar=true;SetTitleBar(AppTitleBar);
        AppWindow.SetIcon("Assets/AppIcon.ico");
        var scale=GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this))/96.0;
        AppWindow.Resize(new Windows.Graphics.SizeInt32((int)(1200*scale),(int)(820*scale)));
        RootFrame.Navigate(typeof(MainPage));
        AppWindow.Closing+=async(_,e)=>{if(closing)return;e.Cancel=true;if(RootFrame.Content is MainPage page && await page.ConfirmDiscardAsync()){closing=true;Close();}};
        Closed+=(_,_)=>{if(RootFrame.Content is MainPage page)page.Stop();};
    }
}
