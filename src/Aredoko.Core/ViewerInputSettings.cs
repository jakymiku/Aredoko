using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record ViewerInputSettings(bool WheelUpAdvances=false,int LibraryItemScale=100)
{
    public int WheelStep(int delta)=>delta==0?0:(delta>0)==WheelUpAdvances?1:-1;
    public static ViewerInputSettings Load(string path)
    {
        try
        {
            if(new FileInfo(path).Length>2048)return new();
            using var doc=JsonDocument.Parse(File.ReadAllBytes(path));var root=doc.RootElement;
            if(root.GetProperty("version").GetInt32()!=1)return new();
            var scale=root.TryGetProperty("library_item_scale",out var size)&&size.ValueKind==JsonValueKind.Number&&size.TryGetInt32(out var value)?value:100;
            return new(root.GetProperty("wheel_up_advances").GetBoolean(),NormalizeScale(scale));
        }
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or KeyNotFoundException or FormatException){return new();}
    }
    public static int NormalizeScale(int value)=>value is >=60 and <=180&&value%20==0?value:100;
    public void Save(string path)
    {
        var absolute=Path.GetFullPath(path);Directory.CreateDirectory(Path.GetDirectoryName(absolute)!);
        var temporary=absolute+"."+Guid.NewGuid().ToString("N")+".tmp";
        try
        {
            File.WriteAllText(temporary,new JsonObject{{"version",1},{"wheel_up_advances",WheelUpAdvances},{"library_item_scale",NormalizeScale(LibraryItemScale)}}.ToJsonString());
            File.Move(temporary,absolute,true);
        }
        finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
}
