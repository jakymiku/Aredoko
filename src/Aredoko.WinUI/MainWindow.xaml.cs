using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
namespace Aredoko_WinUI;
public sealed partial class MainWindow : Window
{
    public new static MainWindow Current { get; private set; } = null!;
    private bool closing;
    [DllImport("user32.dll")] private static extern uint GetDpiForWindow(IntPtr hwnd);
    public MainWindow() {
        Current=this;InitializeComponent();
        // WinUI OnLaunched.Arguments is unsupported; read the actual process args.
        // Only this bounded developer override is handled; normal startup follows Windows.
        var launchArguments=Environment.GetCommandLineArgs();
        var themeIndex=Array.IndexOf(launchArguments,"--ui-theme");
        var theme=themeIndex>0 && themeIndex+1<launchArguments.Length?launchArguments[themeIndex+1]:"System";
        ApplyTheme(theme.Equals("system",StringComparison.OrdinalIgnoreCase)?ViewerOptions.Value.Theme:theme);
        ExtendsContentIntoTitleBar=true;SetTitleBar(AppTitleBar);
        AppWindow.SetIcon("Assets/AppIcon.ico");
        var scale=GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this))/96.0;
        AppWindow.Resize(new Windows.Graphics.SizeInt32((int)(1200*scale),(int)(820*scale)));
        RootFrame.Navigate(typeof(MainPage));
        AppWindow.Closing+=async(_,e)=>{if(closing)return;e.Cancel=true;if(RootFrame.Content is MainPage page && await page.ConfirmDiscardAsync()){closing=true;Close();}};
        Closed+=(_,_)=>{if(RootFrame.Content is MainPage page)page.Stop();};
    }
    internal void ApplyTheme(string theme)=>WindowRoot.RequestedTheme=theme.ToLowerInvariant() switch
    {"light"=>ElementTheme.Light,"dark"=>ElementTheme.Dark,_=>ElementTheme.Default};

}
