using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record ViewerInputSettings(bool WheelUpAdvances=false,int LibraryItemScale=100,string Theme="system",bool EnlargeSmallImages=false,bool AlwaysShowControls=false,bool LoopBookPages=false,bool OpenExternally=false,int AISetupFeatures=3)
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
            var theme=root.TryGetProperty("theme",out var t)&&t.ValueKind==JsonValueKind.String?NormalizeTheme(t.GetString()):"system";
            var enlarge=root.TryGetProperty("enlarge_small_images",out var e)&&e.ValueKind==JsonValueKind.True;
            var controls=root.TryGetProperty("always_show_controls",out var c)&&c.ValueKind==JsonValueKind.True;
            var loop=root.TryGetProperty("loop_book_pages",out var l)&&l.ValueKind==JsonValueKind.True;
            var external=root.TryGetProperty("double_click_viewer",out var viewer)&&viewer.ValueKind==JsonValueKind.String&&viewer.GetString()=="external";
            var features=root.TryGetProperty("ai_setup_features",out var f)&&f.ValueKind==JsonValueKind.Number&&f.TryGetInt32(out var mask)?AISetupSelection.Normalize(mask):3;
            return new(root.GetProperty("wheel_up_advances").GetBoolean(),NormalizeScale(scale),theme,enlarge,controls,loop,external,features);
        }
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or KeyNotFoundException or FormatException){return new();}
    }
    public static string NormalizeTheme(string? theme)=>theme is "light" or "dark"?theme:"system";
    public static int NormalizeScale(int value)=>value is >=60 and <=180&&value%20==0?value:100;
    public JsonObject ToJson()=>new(){["version"]=1,["wheel_up_advances"]=WheelUpAdvances,["library_item_scale"]=NormalizeScale(LibraryItemScale),["theme"]=NormalizeTheme(Theme),["enlarge_small_images"]=EnlargeSmallImages,["always_show_controls"]=AlwaysShowControls,["loop_book_pages"]=LoopBookPages,["double_click_viewer"]=OpenExternally?"external":"internal",["ai_setup_features"]=AISetupSelection.Normalize(AISetupFeatures)};
    public void Save(string path)
    {
        var absolute=Path.GetFullPath(path);Directory.CreateDirectory(Path.GetDirectoryName(absolute)!);
        var temporary=absolute+"."+Guid.NewGuid().ToString("N")+".tmp";
        try
        {
            File.WriteAllText(temporary,ToJson().ToJsonString());
            File.Move(temporary,absolute,true);
        }
        finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
}
