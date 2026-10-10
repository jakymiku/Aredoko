using System.Text.Json;
using AredokoWinUiBench;

static void Check(bool condition, string message)
{
    if (!condition) throw new Exception("FAIL: " + message);
    Console.WriteLine("PASS: " + message);
}

// Match WinUI trimmed Release: no reflection-based JSON serialization allowed.
Check(!JsonSerializer.IsReflectionEnabledByDefault, "reflection-based JSON is disabled");
var session = BenchJson.ParseSession("""{"token":"local-session","mode":"demo","stats":{"total":50000}}""");
Check(session.Token == "local-session", "session token read without reflection");
var itemJson = """
    {"id":61,"title":"星空 — Sample 00061","kind":"image",
     "tags":["星空","サンプル"],"shelf":"本棚","favorite":true,
     "reviewed":false,"synthetic":true}
    """;
var item = BenchJson.ParseItem(itemJson);
Check(item.Id == 61 && item.Title.Contains("星空") && item.KindAndTags.Contains("サンプル"), "single item JSON");
var search = BenchJson.ParseSearch("{" + "\"total\":50000,\"page\":1,\"limit\":60,\"items\":[" + itemJson + "]}");
Check(search.Total == 50000 && search.Items.Count == 1 && search.Items[0].Favorite, "list search response JSON");
var outgoing = BenchJson.CreateUpdate(61, ["星空", "quoted \"tag\""], "制作", true, false);
using var doc = JsonDocument.Parse(outgoing);
var root = doc.RootElement;
Check(root.GetProperty("ids")[0].GetInt32() == 61, "POST target ID");
var changes = root.GetProperty("changes");
Check(changes.GetProperty("tags")[1].GetString() == "quoted \"tag\"" &&
      changes.GetProperty("shelf").GetString() == "制作" &&
      changes.GetProperty("favorite").GetBoolean() &&
      !changes.GetProperty("reviewed").GetBoolean(), "POST editable fields and JSON escaping");
Console.WriteLine("PASS: Aredoko WinUI JSON DOM smoke completed");
