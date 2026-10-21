using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml;
using System.Text;
using System.Text.RegularExpressions;

namespace Aredoko_WinUI;

// Used only by the explicit portable owner. Ordinary MSIX activation is unchanged.
internal static class StartupReady
{
    private static readonly string? Nonce=Environment.GetEnvironmentVariable("AREDOKO_STARTUP_NONCE");
    private static readonly string? Instance=Environment.GetEnvironmentVariable("AREDOKO_STARTUP_INSTANCE");
    private static bool sent;
    internal static bool Pending=>!sent&&Nonce is not null;
    internal static async Task SignalAsync(bool success)
    {
        if(!Pending)return;
        sent=true;
        if(Nonce is null||Instance is null||!Regex.IsMatch(Nonce,"\\A[0-9a-f]{32}\\z")||!Regex.IsMatch(Instance,"\\A[0-9a-f]{32}\\z"))
            throw new InvalidOperationException("起動情報を確認できません。");
        var data=Encoding.UTF8.GetBytes("{\"format\":\"aredoko-frontend-ready-v1\",\"nonce\":\""+Nonce+"\",\"instance_id\":\""+Instance+"\",\"status\":\""+(success?"ready":"failed")+"\"}\n");
        await Task.Run(()=>{using var output=Console.OpenStandardOutput();output.Write(data);output.Flush();});
    }
    internal static async Task FirstFrameAsync()
    {
        var rendered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        EventHandler<object> handler=(_,_)=>rendered.TrySetResult();
        CompositionTarget.Rendering+=handler;
        try
        {
            if(MainWindow.Current.Content is FrameworkElement root){root.InvalidateMeasure();root.InvalidateArrange();root.UpdateLayout();}
            await rendered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        }
        finally{CompositionTarget.Rendering-=handler;}
        // This is a compositor callback, not a measured physical presentation time.
        await SignalAsync(true);
    }
}
