using System.Globalization;
using System.Text.Json;

namespace Aredoko.Core;

internal static class MediaProgressTitle
{
    public static string? Read(JsonElement row)
    {
        if(!row.TryGetProperty("item_title",out var value)||value.ValueKind==JsonValueKind.Null)return null;
        if(value.ValueKind!=JsonValueKind.String)throw new InvalidDataException("Invalid progress item title");
        var title=value.GetString()!;
        if(title.Length>160||title.Any(c=>c is '/' or '\\'||char.IsControl(c)||
            char.IsWhiteSpace(c)&&c!=' '||char.GetUnicodeCategory(c)==UnicodeCategory.Format))
            throw new InvalidDataException("Invalid progress item title");
        return title.Length==0?null:title;
    }
}
