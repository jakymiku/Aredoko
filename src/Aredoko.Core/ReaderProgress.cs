using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record ReaderProgress(string Revision,int Page,ReaderDisplayMode Mode)
{
    public static string ModeName(ReaderDisplayMode mode)=>mode switch
    {ReaderDisplayMode.Single=>"single",ReaderDisplayMode.RightToLeft=>"rtl",ReaderDisplayMode.LeftToRight=>"ltr",_=>throw new InvalidDataException(AppText.L("読書方向が無効です。", "Invalid reading direction."))};
    public void Validate()
    {
        new ArchiveManifest(1,10000,Revision).Validate();
        if(Page is <0 or >=10000)throw new InvalidDataException(AppText.L("読書位置が無効です。", "Invalid reading position."));
        _=ModeName(Mode);
    }
    public int RestorePage(ArchiveManifest manifest)
    {manifest.Validate();Validate();return Revision==manifest.Revision && Page<manifest.PageCount?ReaderSpreadPolicy.Anchor(Page,manifest.PageCount,Mode):0;}
    public JsonObject ToJson()
    {Validate();return new JsonObject{{"revision",Revision},{"page",Page},{"mode",ModeName(Mode)}};}
    public static ReaderProgress? Parse(byte[] json)
    {
        try
        {
            using var doc=JsonDocument.Parse(json);var value=doc.RootElement.GetProperty("progress");
            if(value.ValueKind==JsonValueKind.Null)return null;
            var mode=value.GetProperty("mode").GetString() switch
            {"single"=>ReaderDisplayMode.Single,"rtl"=>ReaderDisplayMode.RightToLeft,"ltr"=>ReaderDisplayMode.LeftToRight,_=>throw new InvalidDataException(AppText.L("読書方向が無効です。", "Invalid reading direction."))};
            var result=new ReaderProgress(value.GetProperty("revision").GetString()!,value.GetProperty("page").GetInt32(),mode);result.Validate();return result;
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException(AppText.L("保存された読書位置を読み取れません。", "Unable to read saved reading progress."),ex);}
    }
}
