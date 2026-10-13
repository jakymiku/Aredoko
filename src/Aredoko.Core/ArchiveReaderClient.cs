using System.Net;
using System.Net.Http;
using System.Text.Json;

namespace Aredoko.Core;

public sealed record ArchiveManifest(int ItemId, int PageCount, string Revision)
{
    public static bool CanOpen(MediaRow row) => row.Availability == "present" &&
        (row.Location.EndsWith(".cbz", StringComparison.OrdinalIgnoreCase) ||
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

    public async Task<ArchiveManifest> ManifestAsync(int itemId, CancellationToken cancellation)
    {
        if (itemId < 1) throw new ArgumentOutOfRangeException(nameof(itemId));
        var data = await ReadAsync($"api/library/reader/{itemId}", 4096, false, cancellation);
        return ArchiveManifest.Parse(data, itemId);
    }

    public Task<byte[]> PageAsync(ArchiveManifest manifest, int page, CancellationToken cancellation)
    {
        manifest.Validate();
        if (page < 0 || page >= manifest.PageCount) throw new ArgumentOutOfRangeException(nameof(page));
        return ReadAsync($"api/library/reader/{manifest.ItemId}/pages/{page}?revision={manifest.Revision}",
            PreviewPolicy.MaxSourceBytes, true, cancellation);
    }

    private async Task<byte[]> ReadAsync(string route, int limit, bool image, CancellationToken cancellation)
    {
        // HttpClient's timeout ends at response headers with ResponseHeadersRead.
        // Keep a deadline through streaming, including a stalled response body.
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(40));
        var token = deadline.Token;
        using var response = await client.GetAsync(route, HttpCompletionOption.ResponseHeadersRead, token);
        if (!response.IsSuccessStatusCode) throw new ArchiveReadException(response.StatusCode);
        var mime = response.Content.Headers.ContentType?.MediaType;
        if (image ? mime is null || !ImageTypes.Contains(mime) : mime != "application/json")
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
        return output.ToArray();
    }
}
