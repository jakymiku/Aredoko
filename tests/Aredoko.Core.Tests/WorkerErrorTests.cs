using Aredoko.Core;

internal static class WorkerErrorTests
{
    public static void Run(Action<bool,string> check)
    {
        foreach(var code in new[]{"ai_runtime_dependencies_unavailable","ai_runtime_architecture_incompatible","ai_runtime_initialization_failed"})
        {
            var text=ErrorText.AIWorkerFailure(code);
            check(text is not null&&text.Contains("基本検索と閲覧")&&(text.Contains("設定")||text.Contains("確認")),"worker failure has a safe recovery step: "+code);
            var audio=new AudioContentStatus(true,true,"failed",1,1,0,0,0,0,0,false,code);
            var video=new VideoContentStatus(true,true,"failed",1,1,0,0,0,0,0,false,code);
            check(audio.Message==text&&video.Message==text,"media preparation preserves runtime failure: "+code);
            check((audio with{State="cancelled"}).Message.StartsWith("中断しました"),"cancellation wins over old runtime failure: "+code);
        }
        check(ErrorText.AIWorkerFailure("private unknown text") is null&&ErrorText.AIWorkerFailure(null) is null,"unknown worker codes cannot become user text");
        check(ErrorText.FromResponse("""{"error":"AI runtime dependencies unavailable","error_code":"ai_unavailable"}""",503)==ErrorText.AIWorkerFailure("ai_runtime_dependencies_unavailable"),"legacy HTTP error code still localizes the fixed worker message");
    }
}
