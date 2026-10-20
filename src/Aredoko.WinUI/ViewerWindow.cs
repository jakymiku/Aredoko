using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

// One owned native window. The OS title bar remains; content has no dialog bezel.
internal sealed class ViewerWindow : Window
{
    [DllImport("user32.dll", SetLastError=true)] private static extern IntPtr SetWindowLongPtrW(IntPtr hwnd,int index,IntPtr value);
    [DllImport("user32.dll")] private static extern bool EnableWindow(IntPtr hwnd,bool enabled);
    [DllImport("user32.dll")] private static extern bool IsWindowEnabled(IntPtr hwnd);
    private readonly TaskCompletionSource closed=new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly IntPtr owner;
    private readonly bool ownerWasEnabled;
    private bool preparingClose,closePrepared;
    public Func<Task>? BeforeCloseAsync {get;set;}
    public ViewerWindow(Grid content,string title,string id)
    {
        Title="Aredoko — "+title;
        owner=WinRT.Interop.WindowNative.GetWindowHandle(MainWindow.Current);
        var handle=WinRT.Interop.WindowNative.GetWindowHandle(this);
        Marshal.SetLastPInvokeError(0);
        var previous=SetWindowLongPtrW(handle,-8,owner);
        if(previous==IntPtr.Zero && Marshal.GetLastPInvokeError()!=0)
        {var error=Marshal.GetLastPInvokeError();Close();throw new Win32Exception(error);}
        AutomationProperties.SetAutomationId(content,id);AutomationProperties.SetName(content,title);
        Content=content;AppWindow.SetIcon("Assets/AppIcon.ico");
        var main=MainWindow.Current.AppWindow;
        AppWindow.MoveAndResize(new Windows.Graphics.RectInt32(main.Position.X,main.Position.Y,main.Size.Width,main.Size.Height));
        ownerWasEnabled=IsWindowEnabled(owner);
        AppWindow.Closing+=async(_,args)=>
        {
            if(BeforeCloseAsync is null||closePrepared)return;
            args.Cancel=true;await RequestCloseAsync();
        };
        Closed+=(_,_)=>
        {
            if(ownerWasEnabled)EnableWindow(owner,true);
            closed.TrySetResult();
            Content=null;
        };
    }
    public async Task ShowAsync(Func<Task> load)
    {
        if(ownerWasEnabled)EnableWindow(owner,false);
        try { Activate();_ = load();await closed.Task; }
        finally { if(ownerWasEnabled)EnableWindow(owner,true); }
    }
    // AppWindow.Closing covers system close affordances. Buttons/Escape and
    // owner shutdown also use this explicit path before Window.Close().
    public new void Close()=>_=RequestCloseAsync();
    public async Task RequestCloseAsync()
    {
        if(preparingClose||closePrepared)return;preparingClose=true;
        try
        {
            if(BeforeCloseAsync is not null)await BeforeCloseAsync();
            closePrepared=true;base.Close();
        }
        catch(Exception ex){closePrepared=false;AppLog.Error(ex);}
        finally{preparingClose=false;}
    }
}
