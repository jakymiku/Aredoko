using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

// Reserve space inside form content, independently of an overlay scroll bar.
// Viewer canvases keep their own edge-to-edge scrolling policy.
internal static class FormScrollContent
{
    public static Border Wrap(UIElement child)=>new()
    {
        Padding=(Thickness)Application.Current.Resources["FormScrollGutter"],
        HorizontalAlignment=HorizontalAlignment.Stretch,Child=child
    };
}
