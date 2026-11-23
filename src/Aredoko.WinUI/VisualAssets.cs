using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;

namespace Aredoko_WinUI;
internal static class VisualAssets
{
    internal static Image Sticker(double size=96)
    {
        var image=new Image{Width=size,Height=size,Stretch=Stretch.Uniform,IsHitTestVisible=false,Visibility=Visibility.Collapsed};
        AutomationProperties.SetAccessibilityView(image,AccessibilityView.Raw);
        return image;
    }
    internal static void State(Image image,string? state)
    {
        state=state is "greeting" or "searching" or "found" or "no_results" or "indexing" or "completed" or "error"?state:null;
        if(Equals(image.Tag,state))return;
        image.Tag=state;image.Visibility=state is null?Visibility.Collapsed:Visibility.Visible;
        var file=state=="greeting"?"aredoko_mascot_greeting_512.png":$"aredoko_state_{state}_512.png";
        image.Source=state is null?null:new BitmapImage(new Uri($"ms-appx:///Assets/Visual/{file}")){DecodePixelWidth=256};
    }
}
