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
        ExtendsContentIntoTitleBar=true;SetTitleBar(AppTitleBar);
        ApplyTheme(theme.Equals("system",StringComparison.OrdinalIgnoreCase)?ViewerOptions.Value.Theme:theme);
        AppWindow.SetIcon(System.IO.Path.Combine(AppContext.BaseDirectory,"Assets","AppIcon.ico"));
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
                {
                    try{await page.FlushViewerStateAsync().WaitAsync(TimeSpan.FromSeconds(3));}
                    catch(Exception flushEx){AppLog.Error(flushEx);}
                    closing=true;Close();
                }
            }
            catch(Exception ex){AppLog.Error(ex);}
            finally{preparingClose=false;}
        };
        Closed+=(_,_)=>{if(RootFrame.Content is MainPage page)page.Stop();};
    }
    internal void CompleteRestoreRestart()
    {
        // Caller already passed the dirty guard and published an owned restart.
        closing=true;Close();
    }
    internal void ApplyTheme(string theme)
    {
        var resolved=theme.ToLowerInvariant() switch{"light"=>ElementTheme.Light,"dark"=>ElementTheme.Dark,_=>ElementTheme.Default};
        WindowRoot.RequestedTheme=resolved;
        if(!Microsoft.UI.Windowing.AppWindowTitleBar.IsCustomizationSupported())return;
        var titleBar=AppWindow.TitleBar;
        titleBar.ButtonBackgroundColor=Microsoft.UI.Colors.Transparent;
        titleBar.ButtonInactiveBackgroundColor=Microsoft.UI.Colors.Transparent;
        if(new Windows.UI.ViewManagement.AccessibilitySettings().HighContrast||resolved==ElementTheme.Default)
        {
            titleBar.ButtonForegroundColor=null;
            titleBar.ButtonHoverForegroundColor=null;
            titleBar.ButtonHoverBackgroundColor=null;
            titleBar.ButtonPressedForegroundColor=null;
            titleBar.ButtonPressedBackgroundColor=null;
            titleBar.ButtonInactiveForegroundColor=null;
            return;
        }
        if(resolved==ElementTheme.Light)
        {
            titleBar.ButtonForegroundColor=Windows.UI.Color.FromArgb(0xE4,0x00,0x00,0x00);
            titleBar.ButtonHoverForegroundColor=Windows.UI.Color.FromArgb(0xE4,0x00,0x00,0x00);
            titleBar.ButtonHoverBackgroundColor=Windows.UI.Color.FromArgb(0x09,0x00,0x00,0x00);
            titleBar.ButtonPressedForegroundColor=Windows.UI.Color.FromArgb(0x9E,0x00,0x00,0x00);
            titleBar.ButtonPressedBackgroundColor=Windows.UI.Color.FromArgb(0x06,0x00,0x00,0x00);
            titleBar.ButtonInactiveForegroundColor=Windows.UI.Color.FromArgb(0x5C,0x00,0x00,0x00);
        }
        else
        {
            titleBar.ButtonForegroundColor=Microsoft.UI.Colors.White;
            titleBar.ButtonHoverForegroundColor=Microsoft.UI.Colors.White;
            titleBar.ButtonHoverBackgroundColor=Windows.UI.Color.FromArgb(0x0F,0xFF,0xFF,0xFF);
            titleBar.ButtonPressedForegroundColor=Windows.UI.Color.FromArgb(0xC5,0xFF,0xFF,0xFF);
            titleBar.ButtonPressedBackgroundColor=Windows.UI.Color.FromArgb(0x0A,0xFF,0xFF,0xFF);
            titleBar.ButtonInactiveForegroundColor=Windows.UI.Color.FromArgb(0x5D,0xFF,0xFF,0xFF);
        }
    }
    internal Task InitializeOwnedStartupAsync()=>RootFrame.Content is MainPage page?page.InitializeFirstPageAsync():Task.FromException(new InvalidOperationException("ライブラリ画面がありません。"));

}
