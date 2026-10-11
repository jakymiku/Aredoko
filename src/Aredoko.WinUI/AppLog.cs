using System.IO;
namespace Aredoko_WinUI;
internal static class AppLog {
    public static void Error(Exception error) {
        try { var directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Aredoko","logs");
            Directory.CreateDirectory(directory);
            File.AppendAllText(Path.Combine(directory,"winui.log"),$"{DateTimeOffset.Now:O} {error}\n");
        } catch(IOException) { } catch(UnauthorizedAccessException) { }
    }
}
