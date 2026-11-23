using Windows.ApplicationModel;
using Windows.ApplicationModel.Activation;
using Windows.Foundation;
using Windows.Foundation.Collections;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.UI.Xaml.Shapes;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace Aredoko_WinUI;

/// <summary>
/// Provides application-specific behavior to supplement the default Application class.
/// </summary>
public partial class App : Application
{
    private Window? _window;
    
    /// <summary>
    /// Initializes the singleton application object.  This is the first line of authored code
    /// executed, and as such is the logical equivalent of main() or WinMain().
    /// </summary>
    public App()
    {
        AppLog.Startup("app_constructing");
        UnhandledException += (_, e) => AppLog.Error(e.Exception);
        InitializeComponent();
        AppLog.Startup("app_constructed");
    }

    /// <summary>
    /// Invoked when the application is launched.
    /// </summary>
    /// <param name="args">Details about the launch request and process.</param>
    protected override void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
    {
        AppLog.Startup("launch_entered");
        if(StartupReady.Pending) { _=LaunchOwnedAsync();return; }
        _window = new MainWindow();
        _window.Activate();
    }
    private async Task LaunchOwnedAsync()
    {
        try {
            _window=new MainWindow();
            _window.Activate();
            AppLog.Startup("window_activated");
            _window.AppWindow.Hide();
            AppLog.Startup("window_hidden_for_initialization");
            await ((MainWindow)_window).InitializeOwnedStartupAsync();
        }
        catch(Exception ex) {
            AppLog.Startup("owned_launch_failed");AppLog.Error(ex);
            try { await StartupReady.SignalAsync(false); }
            catch(Exception signalError) { AppLog.Error(signalError); }
        }
    }
}
