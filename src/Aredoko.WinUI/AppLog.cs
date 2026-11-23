using System.IO;
namespace Aredoko_WinUI;
internal static class AppLog {
    private static readonly object StartupLock = new();
    internal static string? DirectoryForSession() =>
        Environment.GetEnvironmentVariable("LOCALAPPDATA") is {} root && Path.IsPathFullyQualified(root)
            ? Path.Combine(root,"Aredoko","logs") : null;
    // Fixed stage labels only: no media paths, queries, session tokens or DB contents.
    internal static void Startup(string stage) {
        var nonce=Environment.GetEnvironmentVariable("AREDOKO_STARTUP_NONCE");
        if(nonce is null||!System.Text.RegularExpressions.Regex.IsMatch(nonce,"\\A[0-9a-f]{32}\\z"))return;
        try {
            var directory=DirectoryForSession();if(directory is null)return;
            lock(StartupLock) {
                Directory.CreateDirectory(directory);
                File.AppendAllText(Path.Combine(directory,"frontend-startup-"+nonce+".log"),$"{DateTimeOffset.Now:O} {stage}\n");
            }
        } catch(IOException) { } catch(UnauthorizedAccessException) { } catch(ArgumentException) { }
    }
    public static void Error(Exception error) {
        try { var directory=DirectoryForSession();if(directory is null)return;
            Directory.CreateDirectory(directory);
            File.AppendAllText(Path.Combine(directory,"winui.log"),$"{DateTimeOffset.Now:O} {error}\n");
        } catch(IOException) { } catch(UnauthorizedAccessException) { } catch(ArgumentException) { }
    }
}
