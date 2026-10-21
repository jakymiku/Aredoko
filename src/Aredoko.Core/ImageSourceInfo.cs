using System.Text.Json;

namespace Aredoko.Core;

// UI-neutral container information. A signature is not a decoding guarantee.
public sealed record ImageSourceInfo(int ItemId,string Revision,string Mime,long SizeBytes,bool AnimationCandidate)
{
    public bool IsNativeGif => Mime=="image/gif";

    public static ImageSourceInfo Parse(byte[] json,int expectedItemId)
    {
        try
        {
            using var document=JsonDocument.Parse(json);
            var root=document.RootElement;
            var item=root.GetProperty("item_id").GetInt32();
            var revision=root.GetProperty("revision").GetString();
            var mime=root.GetProperty("mime").GetString();
            var size=root.GetProperty("size_bytes").GetInt64();
            var animation=root.GetProperty("animation_candidate").GetBoolean();
            if(item<1||item!=expectedItemId||revision is null||revision.Length!=64||
                revision.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f'))||
                mime is not ("image/png" or "image/jpeg" or "image/webp" or "image/gif" or "image/bmp")||
                size<1||size>PreviewPolicy.ViewerSourceBytes||
                (animation&&mime is not ("image/png" or "image/webp" or "image/gif"))||
                (mime=="image/gif"&&!animation))
                throw new InvalidDataException("画像形式の情報が無効です。");
            return new(item,revision,mime,size,animation);
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException("画像形式の情報を読み取れません。",ex);}
    }
}
