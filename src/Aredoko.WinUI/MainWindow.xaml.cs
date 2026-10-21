using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;
namespace Aredoko_WinUI;
public sealed partial class MainWindow : Window
{
    public new static MainWindow Current { get; private set; } = null!;
    private bool closing;
    private bool preparingClose;
    [DllImport("user32.dll")] private static extern uint GetDpiForWindow(IntPtr hwnd);
    public MainWindow() {
        AppLog.Startup("window_constructing");
        Current=this;InitializeComponent();
        AppLog.Startup("window_xaml_loaded");
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
        AppLog.Startup("page_navigation_starting");
        if(!RootFrame.Navigate(typeof(MainPage)))throw new InvalidOperationException("ライブラリ画面を開けませんでした。");
        AppLog.Startup("page_navigation_completed");
        AppWindow.Closing+=async(_,e)=>
        {
            if(closing)return;e.Cancel=true;if(preparingClose)return;preparingClose=true;
            try
            {
                if(RootFrame.Content is MainPage page&&await page.ConfirmDiscardAsync())
                {await page.FlushReaderProgressAsync();closing=true;Close();}
            }
            catch(Exception ex){AppLog.Error(ex);}
            finally{preparingClose=false;}
        };
        Closed+=(_,_)=>{if(RootFrame.Content is MainPage page)page.Stop();};
    }
    internal void ApplyTheme(string theme)=>WindowRoot.RequestedTheme=theme.ToLowerInvariant() switch
    {"light"=>ElementTheme.Light,"dark"=>ElementTheme.Dark,_=>ElementTheme.Default};
    internal Task InitializeOwnedStartupAsync()=>RootFrame.Content is MainPage page?page.InitializeFirstPageAsync():Task.FromException(new InvalidOperationException("ライブラリ画面がありません。"));

}
