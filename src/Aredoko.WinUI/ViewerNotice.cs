using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

// Successful playback/display is represented by the canvas and transport.
// Keep a live, visible notice only for loading, warnings and failures.
internal static class ViewerNotice
{
    public static void Set(TextBlock target,string message="")
    {
        target.Text=message;
        target.Visibility=string.IsNullOrEmpty(message)?Visibility.Collapsed:Visibility.Visible;
    }
}
