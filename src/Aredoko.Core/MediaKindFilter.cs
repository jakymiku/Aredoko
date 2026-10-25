namespace Aredoko.Core;

// A display/query category; persistent book/archive values and reader routing
// remain compatible with old catalogs and API clients.
public static class MediaKindFilter
{
    public static string FromIndex(int index)=>index switch
        {1=>"book",2=>"image",3=>"video",4=>"audio",5=>"compressed",6=>"material",_=>""};
    public static bool IsCompressed(MediaRow row)=>row.Kind=="archive"||row.Kind=="book"&&row.Location.EndsWith(".cbz",StringComparison.OrdinalIgnoreCase);
    public static string DisplayName(MediaRow row)=>IsCompressed(row)?"圧縮ファイル":row.Kind switch
        {"book"=>"本","image"=>"画像","video"=>"動画","audio"=>"音楽",_=>"素材"};
}
