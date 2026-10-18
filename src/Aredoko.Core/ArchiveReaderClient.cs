using System.Net;
using System.Net.Http;
using System.Text.Json;

namespace Aredoko.Core;

public sealed record ArchiveManifest(int ItemId, int PageCount, string Revision)
{
    public static bool CanOpen(MediaRow row) => row.Availability == "present" &&
        (row.IsFolderBook || row.Location.EndsWith(".cbz", StringComparison.OrdinalIgnoreCase) ||
         row.Location.EndsWith(".zip", StringComparison.OrdinalIgnoreCase));

    public void Validate()
    {
        if (ItemId < 1 || PageCount is < 1 or > 10000 || Revision is null ||
            Revision.Length != 64 || Revision.Any(c => !(c is >= '0' and <= '9' or >= 'a' and <= 'f')))
            throw new InvalidDataException("読書情報が無効です。開き直してください。");
    }

    public static ArchiveManifest Parse(byte[] json, int expectedItemId)
    {
        try
        {
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            var result = new ArchiveManifest(root.GetProperty("item_id").GetInt32(),
                root.GetProperty("page_count").GetInt32(), root.GetProperty("revision").GetString()!);
            result.Validate();
            if (result.ItemId != expectedItemId) throw new InvalidDataException("別の作品の読書情報を受信しました。");
            return result;
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            throw new InvalidDataException("読書情報を読み取れません。開き直してください。", ex);
        }
    }
}

public sealed class ArchiveReadException(HttpStatusCode status) : Exception(status switch
{
    HttpStatusCode.Conflict => "ファイルが更新されました。閉じて再スキャンしてから、開き直してください。",
    HttpStatusCode.NotFound => "このページは読み取れません。破損・未対応形式・容量制限などを確認してください。",
    HttpStatusCode.ServiceUnavailable => "ほかの画像を読み込み中です。少し待って再試行してください。",
    HttpStatusCode.Forbidden => "接続が切れました。閉じてライブラリから再接続してください。",
    _ => "ページを取得できませんでした。再試行してください。"
})
{
    public HttpStatusCode Status { get; } = status;
    public bool RequiresReopen => Status is HttpStatusCode.Conflict or HttpStatusCode.Forbidden;
}

// Uses LibraryApi's existing loopback session. Owns neither HttpClient nor files.
public sealed class ArchiveReaderClient(HttpClient client)
{
    private static readonly HashSet<string> ImageTypes =
        ["image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp"];
    private static readonly HashSet<string> VideoTypes =
        ["video/mp4", "video/webm", "video/x-matroska", "video/x-msvideo", "video/quicktime", "video/x-ms-wmv", "video/mp2t"];

    public async Task<ArchiveManifest> ManifestAsync(int itemId, CancellationToken cancellation)
    {
        if (itemId < 1) throw new ArgumentOutOfRangeException(nameof(itemId));
        var (data, _) = await ReadMediaAsync($"api/library/reader/{itemId}", 4096, null, cancellation);
        return ArchiveManifest.Parse(data, itemId);
    }

    public async Task<byte[]> PageAsync(ArchiveManifest manifest, int page, CancellationToken cancellation)
    {
        manifest.Validate();
        if (page < 0 || page >= manifest.PageCount) throw new ArgumentOutOfRangeException(nameof(page));
        var (data, _) = await ReadMediaAsync($"api/library/reader/{manifest.ItemId}/pages/{page}?revision={manifest.Revision}",
            PreviewPolicy.MaxSourceBytes, ImageTypes, cancellation);
        return data;
    }

    public async Task<byte[]> ImageAsync(int itemId, CancellationToken cancellation)
    {
        if (itemId < 1) throw new ArgumentOutOfRangeException(nameof(itemId));
        var (data, _) = await ReadMediaAsync($"api/library/preview/{itemId}", PreviewPolicy.MaxSourceBytes, ImageTypes, cancellation);
        return data;
    }

    public async Task<ImageAnimationManifest> ImageManifestAsync(int itemId, CancellationToken cancellation)
    {
        if (itemId < 1) throw new ArgumentOutOfRangeException(nameof(itemId));
        var (data, _) = await ReadMediaAsync($"api/library/preview/{itemId}/manifest", 16384, null, cancellation, seconds: 10);
        return ImageAnimationManifest.Parse(data, itemId);
    }

    public async Task<byte[]> ImageFrameAsync(ImageAnimationManifest manifest, int frame, CancellationToken cancellation)
    {
        manifest.Validate();
        if (frame < 0 || frame >= manifest.FrameCount) throw new ArgumentOutOfRangeException(nameof(frame));
        var (data, _) = await ReadMediaAsync($"api/library/preview/{manifest.ItemId}/frames/{frame}?revision={manifest.Revision}",
            PreviewPolicy.MaxSourceBytes, ["image/png"], cancellation, seconds: 15);
        return data;
    }

    public Task<(byte[] Data, string Mime)> VideoAsync(int itemId, CancellationToken cancellation)
    {
        if (itemId < 1) throw new ArgumentOutOfRangeException(nameof(itemId));
        return ReadMediaAsync($"api/library/video/{itemId}", VideoPlayerPolicy.MaxSourceBytes, VideoTypes, cancellation);
    }

    public async Task<VideoRangeSource> OpenVideoRangeAsync(int itemId,CancellationToken cancellation)
    {
        if(itemId<1)throw new ArgumentOutOfRangeException(nameof(itemId));
        var (data,_)=await ReadMediaAsync($"api/library/video/{itemId}/manifest",4096,null,cancellation,seconds:5);
        return new VideoRangeSource(client,VideoManifest.Parse(data,itemId),cancellation);
    }

    public async Task<VideoRangeSource> OpenAudioRangeAsync(int itemId,CancellationToken cancellation)
    {
        if(itemId<1)throw new ArgumentOutOfRangeException(nameof(itemId));
        var (data,_)=await ReadMediaAsync($"api/library/audio/{itemId}/manifest",4096,null,cancellation,seconds:5);
        return new VideoRangeSource(client,VideoManifest.Parse(data,itemId),cancellation,routePrefix:"api/library/audio");
    }

    public async Task<byte[]> VideoFrameAsync(VideoManifest manifest,int atMs,CancellationToken cancellation)
    {
        manifest.Validate();if(atMs<0||atMs>86_400_000)throw new ArgumentOutOfRangeException(nameof(atMs));
        var (data,_)=await ReadMediaAsync($"api/library/video/{manifest.ItemId}/frame?revision={manifest.Revision}&at_ms={atMs}",512*1024,["image/png"],cancellation,seconds:12);
        return data;
    }

    public async Task<ReaderProgress?> ProgressAsync(int itemId,CancellationToken cancellation)
    {
        if(itemId<1)throw new ArgumentOutOfRangeException(nameof(itemId));
        var (data,_)=await ReadMediaAsync($"api/library/reader/{itemId}/progress",4096,null,cancellation,seconds:5);
        return ReaderProgress.Parse(data);
    }
    public async Task SaveProgressAsync(ArchiveManifest manifest,int page,ReaderDisplayMode mode,CancellationToken cancellation)
    {
        manifest.Validate();if(page<0||page>=manifest.PageCount)throw new ArgumentOutOfRangeException(nameof(page));
        var value=new ReaderProgress(manifest.Revision,page,mode).ToJson().ToJsonString();
        var (data,_)=await ReadMediaAsync($"api/library/reader/{manifest.ItemId}/progress",4096,null,cancellation,value,5);
        using var doc=JsonDocument.Parse(data);
        if(!doc.RootElement.TryGetProperty("saved",out var saved)||saved.ValueKind!=JsonValueKind.True)
            throw new InvalidDataException("読書位置の保存を確認できませんでした。");
    }

    private async Task<(byte[] Data, string Mime)> ReadMediaAsync(string route, int limit, HashSet<string>? allowedTypes, CancellationToken cancellation,string? json=null,int seconds=40)
    {
        // HttpClient's timeout ends at response headers with ResponseHeadersRead.
        // Keep a deadline through streaming, including a stalled response body.
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        var token = deadline.Token;
        using var outgoing=new HttpRequestMessage(json is null?HttpMethod.Get:HttpMethod.Post,route);
        if(json is not null)outgoing.Content=new StringContent(json,System.Text.Encoding.UTF8,"application/json");
        using var response = await client.SendAsync(outgoing, HttpCompletionOption.ResponseHeadersRead, token);
        if (!response.IsSuccessStatusCode) throw new ArchiveReadException(response.StatusCode);
        var mime = response.Content.Headers.ContentType?.MediaType;
        if (allowedTypes is not null ? mime is null || !allowedTypes.Contains(mime) : mime != "application/json")
            throw new InvalidDataException("未対応のページ形式です。");
        if (response.Content.Headers.ContentLength is not long size || size < 1 || size > limit)
            throw new InvalidDataException("ページのデータ量が制限を超えています。");
        await using var source = await response.Content.ReadAsStreamAsync(token);
        using var output = new MemoryStream((int)size);
        var buffer = new byte[16 * 1024];
        int count;
        while ((count = await source.ReadAsync(buffer, token)) != 0)
        {
            if (output.Length + count > size) throw new InvalidDataException("ページのデータ量が一致しません。");
            output.Write(buffer, 0, count);
        }
        if (output.Length != size) throw new InvalidDataException("ページを最後まで受信できませんでした。");
        token.ThrowIfCancellationRequested();
        return (output.ToArray(), mime!);
    }
}
