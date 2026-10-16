using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record ViewerInputSettings(bool WheelUpAdvances=false)
{
    public int WheelStep(int delta)=>delta==0?0:(delta>0)==WheelUpAdvances?1:-1;
    public static ViewerInputSettings Load(string path)
    {
        try
        {
            if(new FileInfo(path).Length>2048)return new();
            using var doc=JsonDocument.Parse(File.ReadAllBytes(path));var root=doc.RootElement;
            if(root.GetProperty("version").GetInt32()!=1)return new();
            return new(root.GetProperty("wheel_up_advances").GetBoolean());
        }
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or KeyNotFoundException or FormatException){return new();}
    }
    public void Save(string path)
    {
        var absolute=Path.GetFullPath(path);Directory.CreateDirectory(Path.GetDirectoryName(absolute)!);
        var temporary=absolute+"."+Guid.NewGuid().ToString("N")+".tmp";
        try
        {
            File.WriteAllText(temporary,new JsonObject{{"version",1},{"wheel_up_advances",WheelUpAdvances}}.ToJsonString());
            File.Move(temporary,absolute,true);
        }
        finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
}
