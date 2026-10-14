using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;

namespace Aredoko.Core;

public sealed record VideoManifest(int ItemId,long SizeBytes,string Mime,string Revision)
{
    public const long MaxBytes=2L*1024*1024*1024*1024;
    public const int ChunkBytes=1024*1024;
    private static readonly HashSet<string> Mimes=["video/mp4","video/webm","video/x-matroska","video/x-msvideo","video/quicktime","video/x-ms-wmv","video/mp2t"];
    public void Validate()
    {if(ItemId<1||SizeBytes<1||SizeBytes>MaxBytes||!Mimes.Contains(Mime))throw new InvalidDataException("動画情報が無効です。");new ArchiveManifest(ItemId,1,Revision).Validate();}
    public static VideoManifest Parse(byte[] bytes,int expectedId)
    {
        try
        {
            using var doc=JsonDocument.Parse(bytes);var root=doc.RootElement;
            var result=new VideoManifest(root.GetProperty("item_id").GetInt32(),root.GetProperty("size_bytes").GetInt64(),root.GetProperty("mime").GetString()!,root.GetProperty("revision").GetString()!);
            result.Validate();if(result.ItemId!=expectedId)throw new InvalidDataException("別の動画の情報です。");return result;
        }
        catch(Exception ex) when(ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        {throw new InvalidDataException("動画情報を読み取れません。",ex);}
    }
}

// Shared by independent native stream cursors. Never owns HttpClient/source paths.
public sealed class VideoRangeSource : IDisposable
{
    private readonly HttpClient client;
    private readonly CancellationTokenSource lifetime;
    private readonly CancellationToken cancellation;
    private readonly SemaphoreSlim slots=new(2);
    private bool disposed;
    public VideoManifest Manifest {get;}
    public Exception? Failure {get;private set;}
    public VideoRangeSource(HttpClient client,VideoManifest manifest,CancellationToken cancellation)
    {manifest.Validate();this.client=client;Manifest=manifest;lifetime=CancellationTokenSource.CreateLinkedTokenSource(cancellation);this.cancellation=lifetime.Token;}
    public async Task<byte[]> ReadAsync(long offset,int count,CancellationToken caller)
    {
        ObjectDisposedException.ThrowIf(disposed,this);
        if(offset<0||offset>Manifest.SizeBytes||count<0||count>VideoManifest.ChunkBytes)throw new ArgumentOutOfRangeException(nameof(count));
        if(count==0||offset==Manifest.SizeBytes)return [];
        count=(int)Math.Min(count,Manifest.SizeBytes-offset);var end=offset+count-1;
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellation,caller);deadline.CancelAfter(TimeSpan.FromSeconds(40));var token=deadline.Token;
        await slots.WaitAsync(token).ConfigureAwait(false);
        try
        {
            using var req=new HttpRequestMessage(HttpMethod.Get,$"api/library/video/{Manifest.ItemId}/range?revision={Manifest.Revision}");req.Headers.Range=new RangeHeaderValue(offset,end);
            using var response=await client.SendAsync(req,HttpCompletionOption.ResponseHeadersRead,token).ConfigureAwait(false);
            if(response.StatusCode!=HttpStatusCode.PartialContent)
            {if(!response.IsSuccessStatusCode)throw new ArchiveReadException(response.StatusCode);throw new InvalidDataException("範囲取得ではない応答を受信しました。");}
            var range=response.Content.Headers.ContentRange;var tag=response.Headers.ETag;
            if(response.Content.Headers.ContentLength!=count||response.Content.Headers.ContentType?.MediaType!=Manifest.Mime||range?.Unit!="bytes"||range.From!=offset||range.To!=end||range.Length!=Manifest.SizeBytes||tag is null||tag.IsWeak||tag.Tag!="\""+Manifest.Revision+"\"")throw new InvalidDataException("動画の範囲情報が一致しません。");
            await using var body=await response.Content.ReadAsStreamAsync(token).ConfigureAwait(false);var result=new byte[count];var read=0;
            while(read<count){var n=await body.ReadAsync(result.AsMemory(read),token).ConfigureAwait(false);if(n==0)throw new InvalidDataException("動画の範囲が途中で切れました。");read+=n;}
            var extra=new byte[1];if(await body.ReadAsync(extra,token).ConfigureAwait(false)!=0)throw new InvalidDataException("動画の範囲が上限を超えました。");token.ThrowIfCancellationRequested();return result;
        }
        catch(Exception ex) when(!cancellation.IsCancellationRequested && !(ex is OperationCanceledException && caller.IsCancellationRequested))
        {Failure??=ex;throw;}
        finally{slots.Release();}
    }
    public void Dispose(){if(disposed)return;disposed=true;lifetime.Cancel();lifetime.Dispose();}
}
