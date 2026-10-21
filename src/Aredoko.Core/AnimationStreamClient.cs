using System.Buffers.Binary;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Aredoko.Core;

public sealed record AnimationFrame(long Sequence, int Index, int Cycle, int DurationMs, byte[] Pixels);
public sealed record AnimationBatch(int Width, int Height, bool Done, IReadOnlyList<AnimationFrame> Frames);

// Pull-driven ownership and bounded raw pixels; no WinUI types or source paths.
public sealed class AnimationStreamClient(HttpClient client)
{
    public const int MaxFrames = 4;
    public const int MaxBytes = 128 * 1024 * 1024;
    public async Task<AnimationStream> OpenAsync(ImageSourceInfo source, CancellationToken cancellation)
    {
        var id = Guid.NewGuid().ToString("N");
        var stream = new AnimationStream(client, source, id);
        try
        {
            using var response = await SendAsync(client, "open", new JsonObject
            { ["item_id"] = source.ItemId, ["revision"] = source.Revision, ["session_id"] = id }, cancellation);
            var bytes = await BoundedBodyAsync(response, 8192, cancellation);
            using var doc = JsonDocument.Parse(bytes);
            var root = doc.RootElement;
            if (root.GetProperty("session_id").GetString() != id ||
                root.GetProperty("item_id").GetInt32() != source.ItemId ||
                root.GetProperty("revision").GetString() != source.Revision ||
                root.GetProperty("max_batch_frames").GetInt32() != MaxFrames ||
                root.GetProperty("max_batch_bytes").GetInt32() != MaxBytes)
                throw new InvalidDataException("Invalid animation session");
            return stream;
        }
        catch
        {
            await stream.DisposeAsync();
            throw;
        }
    }

    internal static async Task<HttpResponseMessage> SendAsync(HttpClient client, string action, JsonObject body, CancellationToken cancellation)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "api/library/animation/" + action)
        { Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json") };
        var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        if (!response.IsSuccessStatusCode)
        {
            var status = response.StatusCode;
            response.Dispose();
            throw new ArchiveReadException(status);
        }
        return response;
    }

    internal static async Task<byte[]> BoundedBodyAsync(HttpResponseMessage response, int max, CancellationToken cancellation)
    {
        if (response.Content.Headers.ContentLength is not long length || length < 1 || length > max)
            throw new InvalidDataException("Invalid animation response size");
        await using var body = await response.Content.ReadAsStreamAsync(cancellation);
        var bytes = new byte[(int)length];
        await body.ReadExactlyAsync(bytes, cancellation);
        return bytes;
    }
}

public sealed class AnimationStream(HttpClient client, ImageSourceInfo source, string id) : IAsyncDisposable
{
    private long nextSequence;
    private int width, height, disposed, reading;
    public async Task<AnimationBatch> ReadAsync(int count, CancellationToken cancellation)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
        if (count is < 1 or > AnimationStreamClient.MaxFrames) throw new ArgumentOutOfRangeException(nameof(count));
        if (Interlocked.Exchange(ref reading, 1) != 0) throw new InvalidOperationException("Animation pull already active");
        try
        {
            using var response = await AnimationStreamClient.SendAsync(client, "next",
                new JsonObject { ["session_id"] = id, ["count"] = count }, cancellation);
            if (response.Content.Headers.ContentType?.MediaType != "application/vnd.aredoko.animation-frame-batch" ||
                response.Content.Headers.ContentLength is not long length || length < 4 || length > AnimationStreamClient.MaxBytes + 8196)
                throw new InvalidDataException("Invalid animation frame response");
            await using var body = await response.Content.ReadAsStreamAsync(cancellation);
            var prefix = new byte[4]; await body.ReadExactlyAsync(prefix, cancellation);
            var headerLength = BinaryPrimitives.ReadInt32LittleEndian(prefix);
            if (headerLength is < 2 or > 8192 || headerLength + 4 > length) throw new InvalidDataException("Invalid frame header");
            var header = new byte[headerLength]; await body.ReadExactlyAsync(header, cancellation);
            using var doc = JsonDocument.Parse(header); var root = doc.RootElement;
            var w = root.GetProperty("width").GetInt32(); var h = root.GetProperty("height").GetInt32();
            if (root.GetProperty("session_id").GetString() != id || root.GetProperty("item_id").GetInt32() != source.ItemId || root.GetProperty("revision").GetString() != source.Revision ||
                w is < 1 or > 2048 || h is < 1 or > 2048 || (width != 0 && (width != w || height != h)) ||
                root.GetProperty("stride").GetInt32() != w * 4 || root.GetProperty("pixel_format").GetString() != "bgra8" ||
                root.GetProperty("alpha").GetString() != "premultiplied") throw new InvalidDataException("Invalid frame layout");
            var done = root.GetProperty("done").GetBoolean(); var descriptions = root.GetProperty("frames");
            if (descriptions.GetArrayLength() > count || (descriptions.GetArrayLength() == 0 && !done)) throw new InvalidDataException("Invalid frame count");
            var frameBytes = checked(w * h * 4);
            if (length != 4L + headerLength + (long)frameBytes * descriptions.GetArrayLength()) throw new InvalidDataException("Invalid pixel payload");
            var frames = new List<AnimationFrame>(); var expected = nextSequence;
            foreach (var entry in descriptions.EnumerateArray())
            {
                var sequence = entry.GetProperty("sequence").GetInt64(); var index = entry.GetProperty("index").GetInt32();
                var cycle = entry.GetProperty("cycle").GetInt32(); var duration = entry.GetProperty("duration_ms").GetInt32();
                if (sequence != expected++ || index < 0 || cycle < 0 || duration is < 20 or > 60000 || entry.GetProperty("byte_length").GetInt32() != frameBytes)
                    throw new InvalidDataException("Invalid animation frame order");
                var pixels = new byte[frameBytes]; await body.ReadExactlyAsync(pixels, cancellation);
                frames.Add(new(sequence, index, cycle, duration, pixels));
            }
            cancellation.ThrowIfCancellationRequested();
            ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
            nextSequence = expected; width = w; height = h;
            return new(w, h, done, frames);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or FormatException or OverflowException)
        { throw new InvalidDataException("Invalid animation response", ex); }
        finally { Volatile.Write(ref reading, 0); }
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref disposed, 1) != 0) return;
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        try
        {
            using var response = await AnimationStreamClient.SendAsync(client, "close", new JsonObject { ["session_id"] = id }, timeout.Token);
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or ObjectDisposedException or ArchiveReadException)
        { /* Backend's idle owner is the bounded fallback after connection loss. */ }
    }
}
