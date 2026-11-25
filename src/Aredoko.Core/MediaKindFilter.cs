namespace Aredoko.Core;

// A display/query category; persistent book/archive values and reader routing
// remain compatible with old catalogs and API clients.
public static class MediaKindFilter
{
    public static string FromIndex(int index)=>index switch
        {1=>"book",2=>"image",3=>"video",4=>"audio",5=>"compressed",6=>"material",_=>""};
    public static bool IsCompressed(MediaRow row)=>row.Kind=="archive"||row.Kind=="book"&&row.Location.EndsWith(".cbz",StringComparison.OrdinalIgnoreCase);
    public static string DisplayName(MediaRow row)=>IsCompressed(row)?AppText.L("圧縮ファイル", "Archive"):row.Kind switch
        {"book"=>AppText.L("本", "Book"),"image"=>AppText.L("画像", "Image"),"video"=>AppText.L("動画", "Video"),"audio"=>AppText.L("音声・音楽", "Audio / Music"),_=>AppText.L("素材", "Material")};
}
