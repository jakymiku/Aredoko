using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.System;

namespace Aredoko_WinUI;

internal static class ViewerOptions
{
    private static readonly string path=SettingsPath();
    private static string SettingsPath()
    {
        var args=Environment.GetCommandLineArgs();
        var at=Array.IndexOf(args,"--viewer-settings");
        return at>=0&&at+1<args.Length?System.IO.Path.GetFullPath(args[at+1]):System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Aredoko","viewer-settings.json");
    }
    public static string BackupChoicesPath=>path+".backup.json";
    public static ViewerInputSettings Value {get;private set;}=ViewerInputSettings.Load(path);
    public static void Save(bool wheelUpAdvances)=>SaveValue(Value with {WheelUpAdvances=wheelUpAdvances});
    public static void SavePreferences(bool wheel,string theme,bool enlarge)=>SaveValue(Value with {WheelUpAdvances=wheel,Theme=ViewerInputSettings.NormalizeTheme(theme),EnlargeSmallImages=enlarge});
    public static void SaveLibraryItemScale(int scale)=>SaveValue(Value with {LibraryItemScale=ViewerInputSettings.NormalizeScale(scale)});
    public static void SavePresentation(bool enlarge,bool controls,bool loop)=>SaveValue(Value with{EnlargeSmallImages=enlarge,AlwaysShowControls=controls,LoopBookPages=loop});
    private static void SaveValue(ViewerInputSettings next){next.Save(path);Value=next;}
}

internal static class ViewerInputGestures
{
    public static void ZoomCentered(ScrollViewer viewport,float factor)
    {
        var x=ViewerViewportMath.ZoomOffset(viewport.HorizontalOffset,Math.Max(1,viewport.ViewportWidth),viewport.ZoomFactor,factor);
        var y=ViewerViewportMath.ZoomOffset(viewport.VerticalOffset,Math.Max(1,viewport.ViewportHeight),viewport.ZoomFactor,factor);
        viewport.ChangeView(x,y,factor,true);
    }
    public static void AttachPan(ScrollViewer viewport)
    {
        uint? pointer=null;Windows.Foundation.Point start=default;double horizontal=0,vertical=0;
        viewport.AddHandler(UIElement.PointerPressedEvent,new PointerEventHandler((_,args)=>
        {
            var point=args.GetCurrentPoint(viewport);
            if(!point.Properties.IsLeftButtonPressed||viewport.ZoomFactor<=1.01||pointer is not null)return;
            for(var node=args.OriginalSource as DependencyObject;node is not null&&node!=viewport;node=VisualTreeHelper.GetParent(node))
                if(node is ButtonBase or ScrollBar or Slider or TextBox)return;
            if(!viewport.CapturePointer(args.Pointer))return;
            pointer=args.Pointer.PointerId;start=point.Position;horizontal=viewport.HorizontalOffset;vertical=viewport.VerticalOffset;args.Handled=true;
        }),true);
        viewport.AddHandler(UIElement.PointerMovedEvent,new PointerEventHandler((_,args)=>
        {
            if(pointer!=args.Pointer.PointerId)return;
            var point=args.GetCurrentPoint(viewport).Position;
            viewport.ChangeView(Math.Clamp(horizontal+start.X-point.X,0,viewport.ScrollableWidth),Math.Clamp(vertical+start.Y-point.Y,0,viewport.ScrollableHeight),null,true);args.Handled=true;
        }),true);
        viewport.PointerReleased+=(_,args)=>{if(pointer==args.Pointer.PointerId){pointer=null;viewport.ReleasePointerCapture(args.Pointer);args.Handled=true;}};
        viewport.PointerCanceled+=(_,_)=>pointer=null;viewport.PointerCaptureLost+=(_,_)=>pointer=null;
    }
    public static void Attach(UIElement root,ScrollViewer viewport,Func<int,Task> move)
    {
        long lastWheel=0;
        root.AddHandler(UIElement.PointerPressedEvent,new PointerEventHandler(async(_,args)=>
        {
            var point=args.GetCurrentPoint(root).Properties;
            if(!point.IsXButton1Pressed&&!point.IsXButton2Pressed)return;
            args.Handled=true;await move(point.IsXButton1Pressed?-1:1);
        }),true);
        root.AddHandler(UIElement.PointerWheelChangedEvent,new PointerEventHandler(async(_,args)=>
        {
            if(viewport.ZoomFactor>1.01)return;
            foreach(var key in new[]{VirtualKey.Control,VirtualKey.Shift,VirtualKey.Menu})
                if((Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(key)&Windows.UI.Core.CoreVirtualKeyStates.Down)!=0)return;
            for(var node=args.OriginalSource as DependencyObject;node is not null&&node!=viewport;node=VisualTreeHelper.GetParent(node))
                if(node is ButtonBase or Slider or ScrollBar or TextBox)return;
            var point=args.GetCurrentPoint(root).Properties;
            if(point.IsHorizontalMouseWheel||point.MouseWheelDelta==0)return;
            args.Handled=true;
            var now=Environment.TickCount64;if(now-lastWheel<180)return;lastWheel=now;
            await move(ViewerOptions.Value.WheelStep(point.MouseWheelDelta));
        }),true);
    }
}
