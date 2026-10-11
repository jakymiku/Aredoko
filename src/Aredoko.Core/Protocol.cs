// Reflection-free JSON protocol shared by the production client and tests.
// Uses the System.Text.Json DOM and Utf8JsonWriter: no runtime reflection or
// JsonSerializerContext needed, including for packaged trimmed Release builds.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Aredoko.Core;

public sealed class MediaRow
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public string Kind { get; set; } = "";
    public string[] Tags { get; set; } = [];
    public string Shelf { get; set; } = "";
    public bool Favorite { get; set; }
    public bool Reviewed { get; set; }
    public int RootId { get; set; }
    public long Modified { get; set; }
    public long Size { get; set; }
    public string PreviewKey => $"{RootId}:{Id}:{Modified}:{Size}";
    public string Location { get; set; } = "";
    public string Availability { get; set; } = "";
    public string KindAndTags => $"{Kind} · {string.Join("、", Tags)}";
}

public sealed class SearchResponse
{
    public int Total { get; set; }
    public List<MediaRow> Items { get; set; } = [];
}

public sealed class SessionResponse
{
    public string Token { get; set; } = "";
}

public static class Protocol
{
    public static SessionResponse ParseSession(string text)
    {
        using var doc = JsonDocument.Parse(text);
        return new SessionResponse {
            Token = doc.RootElement.GetProperty("token").GetString() ?? ""
        };
    }

    public static SearchResponse ParseSearch(string text)
    {
        using var doc = JsonDocument.Parse(text);
        var root = doc.RootElement;
        var result = new SearchResponse { Total = root.GetProperty("total").GetInt32() };
        foreach (var element in root.GetProperty("items").EnumerateArray())
            result.Items.Add(ReadRow(element));
        return result;
    }

    public static MediaRow ParseItem(string text)
    {
        using var doc = JsonDocument.Parse(text);
        return ReadRow(doc.RootElement);
    }

    private static MediaRow ReadRow(JsonElement row) => new() {
        Id = row.GetProperty("id").GetInt32(),
        Title = row.GetProperty("title").GetString() ?? "",
        Kind = row.GetProperty("kind").GetString() ?? "",
        Tags = row.GetProperty("tags").EnumerateArray().Select(t => t.GetString() ?? "").ToArray(),
        Shelf = row.GetProperty("shelf").GetString() ?? "",
        Favorite = row.GetProperty("favorite").GetBoolean(),
        Reviewed = row.GetProperty("reviewed").GetBoolean(),
        RootId = row.TryGetProperty("root_id", out var rootId) ? rootId.GetInt32() : 0,
        Modified = row.TryGetProperty("mtime_ns", out var modified) ? modified.GetInt64() : 0,
        Size = row.TryGetProperty("size_bytes", out var size) ? size.GetInt64() : 0,
        Location = row.TryGetProperty("relative_path", out var loc) ? loc.GetString() ?? "" : "",
        Availability = row.TryGetProperty("availability", out var av) ? av.GetString() ?? "" : ""
    };

    public static string CreateUpdate(int id, IEnumerable<string> tags, string shelf, bool favorite, bool reviewed)
    {
        using var stream = new MemoryStream();
        using (var json = new Utf8JsonWriter(stream)) {
            json.WriteStartObject();
            json.WritePropertyName("ids");
            json.WriteStartArray();
            json.WriteNumberValue(id);
            json.WriteEndArray();
            json.WritePropertyName("changes");
            json.WriteStartObject();
            json.WritePropertyName("tags");
            json.WriteStartArray();
            foreach (var tag in tags) json.WriteStringValue(tag);
            json.WriteEndArray();
            json.WriteString("shelf", shelf);
            json.WriteBoolean("favorite", favorite);
            json.WriteBoolean("reviewed", reviewed);
            json.WriteEndObject();
            json.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }
}
