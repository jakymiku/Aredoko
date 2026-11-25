using Aredoko.Core;
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
        AppLog.Startup(success?"ready_sending":"failure_sending");
        if(Nonce is null||Instance is null||!Regex.IsMatch(Nonce,"\\A[0-9a-f]{32}\\z")||!Regex.IsMatch(Instance,"\\A[0-9a-f]{32}\\z"))
            throw new InvalidOperationException(AppText.L("起動情報を確認できません。", "Could not verify startup info."));
        var data=Encoding.UTF8.GetBytes("{\"format\":\"aredoko-frontend-ready-v1\",\"nonce\":\""+Nonce+"\",\"instance_id\":\""+Instance+"\",\"status\":\""+(success?"ready":"failed")+"\"}\n");
        await Task.Run(()=>{using var output=Console.OpenStandardOutput();output.Write(data);output.Flush();});
        sent=true;
        AppLog.Startup(success?"ready_sent":"failure_sent");
    }
    internal static async Task FirstFrameAsync()
    {
        AppLog.Startup("first_frame_waiting");
        var rendered=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        EventHandler<object> handler=(_,_)=>rendered.TrySetResult();
        CompositionTarget.Rendering+=handler;
        try
        {
            if(MainWindow.Current.Content is FrameworkElement root){root.InvalidateMeasure();root.InvalidateArrange();root.UpdateLayout();}
            await rendered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        }
        finally{CompositionTarget.Rendering-=handler;}
        AppLog.Startup("first_frame_received");
        // This is a compositor callback, not a measured physical presentation time.
        await SignalAsync(true);
    }
}
