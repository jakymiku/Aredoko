using System.Diagnostics;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

// Opt-in stage timings. "assigned" means XAML source assignment, not physical
// presentation. Never record media names, paths, queries, tokens or source data.
internal sealed class ViewerLoadTrace
{
    private static readonly object sync=new();
    private static long nextId;
    private readonly long id;
    private readonly string kind;
    private readonly Stopwatch? clock;
    public ViewerLoadTrace(string kind)
    {
        this.kind=kind;
        if(Environment.GetEnvironmentVariable("AREDOKO_VIEWER_TIMINGS")=="1")
        {id=Interlocked.Increment(ref nextId);clock=Stopwatch.StartNew();Mark("begin");}
    }
    public void Mark(string stage)
    {
        if(clock is null)return;
        var elapsed=clock.Elapsed.TotalMilliseconds;
        try
        {
            var directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Aredoko","logs");
            lock(sync)
            {
                Directory.CreateDirectory(directory);var path=Path.Combine(directory,"viewer-load.jsonl");
                if(File.Exists(path)&&new FileInfo(path).Length>=8*1024*1024)return;
                var value=new JsonObject{{"load",id},{"kind",kind},{"stage",stage},{"elapsed_ms",elapsed}};
                File.AppendAllText(path,value.ToJsonString()+Environment.NewLine);
            }
        }
        catch(IOException) { }
        catch(UnauthorizedAccessException) { }
    }
}
