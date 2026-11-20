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
    private IViewerWindowTitle? titleSource;
    private bool preparingClose,closePrepared;
    public Func<Task>? BeforeCloseAsync {get;set;}
    public ViewerWindow(Grid content,string title,string id)
    {
        Title="Aredoko — "+title;
        titleSource=content as IViewerWindowTitle;
        if(titleSource is not null){Title=titleSource.WindowTitle;titleSource.TitleChanged+=UpdateTitle;}
        owner=WinRT.Interop.WindowNative.GetWindowHandle(MainWindow.Current);
        var handle=WinRT.Interop.WindowNative.GetWindowHandle(this);
        Marshal.SetLastPInvokeError(0);
        var previous=SetWindowLongPtrW(handle,-8,owner);
        if(previous==IntPtr.Zero && Marshal.GetLastPInvokeError()!=0)
        {var error=Marshal.GetLastPInvokeError();Close();throw new Win32Exception(error);}
        AutomationProperties.SetAutomationId(content,id);AutomationProperties.SetName(content,title);
        Content=content;AppWindow.SetIcon(System.IO.Path.Combine(AppContext.BaseDirectory,"Assets","AppIcon.ico"));
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
            if(titleSource is not null)titleSource.TitleChanged-=UpdateTitle;
            titleSource=null;
            if(ownerWasEnabled)EnableWindow(owner,true);
            closed.TrySetResult();
            Content=null;
        };
    }
    private void UpdateTitle(string value)=>Title=value;
    public void ToggleMaximize()
    {
        if(AppWindow.Presenter is Microsoft.UI.Windowing.OverlappedPresenter presenter)
        {
            if(presenter.State==Microsoft.UI.Windowing.OverlappedPresenterState.Maximized)presenter.Restore();
            else presenter.Maximize();
        }
    }
    public void SwapContent(Grid nextContent,string title,string id)
    {
        if(titleSource is not null)titleSource.TitleChanged-=UpdateTitle;
        titleSource=nextContent as IViewerWindowTitle;
        Title=titleSource?.WindowTitle??("Aredoko — "+title);
        if(titleSource is not null)titleSource.TitleChanged+=UpdateTitle;
        AutomationProperties.SetAutomationId(nextContent,id);
        AutomationProperties.SetName(nextContent,title);
        Content=nextContent;
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
    internal void ForceCloseFromOwner()
    {
        if(closePrepared)return;
        BeforeCloseAsync=null;
        closePrepared=true;
        try{base.Close();}
        catch(Exception ex)
        {
            if(ownerWasEnabled)EnableWindow(owner,true);
            closed.TrySetResult();
            AppLog.Error(ex);
        }
    }
    public async Task RequestCloseAsync()
    {
        if(preparingClose||closePrepared)return;preparingClose=true;
        try
        {
            if(BeforeCloseAsync is not null)
            {
                try{await BeforeCloseAsync();}
                catch(Exception flushEx){AppLog.Error(flushEx);}
            }
            closePrepared=true;base.Close();
        }
        catch(Exception ex)
        {
            closePrepared=false;
            if(ownerWasEnabled)EnableWindow(owner,true);
            closed.TrySetResult();
            AppLog.Error(ex);
        }
        finally{preparingClose=false;}
    }
}
