using System.Text.Json.Nodes;
namespace Aredoko.Core;

public sealed record RegisteredRootRow(
    int Id,
    string Path,
    bool Enabled,
    bool Online,
    string DefaultShelf,
    IReadOnlyList<string> Exclusions,
    int PresentCount = 0,
    string? LastScannedAt = null,
    bool FolderBooks = false,
    bool Recursive = true)
{
    public string ModeLabel => FolderBooks ? "画像フォルダを一冊として扱う" : "画像は1枚ずつ";

    public string Name
    {
        get
        {
            // Split on both separators so Core behaves the same on Linux CI/tests
            // (System.IO.Path there does not treat "\\" as a separator).
            var trimmed = Path.TrimEnd('\\', '/');
            var cut = trimmed.LastIndexOfAny(['\\', '/']);
            var name = cut < 0 ? trimmed : trimmed[(cut + 1)..];
            return string.IsNullOrEmpty(name) || name.EndsWith(':') ? Path : name;
        }
    }

    public string ShortPath
    {
        get
        {
            var normalized = Path.Replace('\\', '/').TrimEnd('/');
            var parts = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
            return parts.Length >= 2 ? $"{parts[^2]}/{parts[^1]}" : Path;
        }
    }

    public string StatusLabel => !Enabled
        ? "登録解除済み（再登録でタグ・棚を復元）"
        : (Online ? "登録中 · 接続OK" : "登録中 · 未接続") + $" · {PresentCount:N0} 件";

    public string ShelfLabel => string.IsNullOrEmpty(DefaultShelf) ? "初期棚: 棚なし" : $"初期棚: {DefaultShelf}";

    public static IReadOnlyList<RegisteredRootRow> ParseList(JsonNode data)
    {
        var items = data["items"]?.AsArray() ?? throw new InvalidDataException("Invalid roots response");
        var list = new List<RegisteredRootRow>(items.Count);
        foreach (var node in items)
        {
            var row = node?.AsObject() ?? throw new InvalidDataException("Invalid root entry");
            var id = row["id"]!.GetValue<int>();
            var path = row["path"]!.GetValue<string>();
            var enabled = row["enabled"]!.GetValue<int>() == 1;
            var online = row["online"]!.GetValue<bool>();
            var shelf = row["default_shelf"]?.GetValue<string>() ?? "";
            var excludes = row["excludes"]?.AsArray().Select(x => x!.GetValue<string>()).ToArray() ?? [];
            var count = row["present_count"] is JsonNode c ? c.GetValue<int>() : 0;
            var scanned = row["last_scanned_at"]?.GetValue<string>();
            var folderBooks = row["folder_books"] is JsonNode f && f.GetValueKind() == System.Text.Json.JsonValueKind.True;
            list.Add(new RegisteredRootRow(id, path, enabled, online, shelf, excludes, count, scanned, folderBooks, row["recursive"]?.GetValue<bool>()??true));
        }
        return list;
    }
}

public enum BatchShelfMode
{
    KeepExisting,
    ClearToNone,
    ExistingShelf,
    NewShelf
}

public sealed record ShelfSummary(bool IsMixed, string? CommonShelf, string DisplayText);

public sealed class FolderSettingsDraft
{
    private readonly IReadOnlyList<RegisteredRootRow> targets;
    private readonly List<int> remainingIds;
    private readonly string initialExclusionsText;
    public IReadOnlyList<int> TargetIds => remainingIds;
    public bool IsBatch => targets.Count > 1;
    public ShelfSummary Summary { get; }
    public BatchShelfMode ShelfMode { get; set; }
    public string SelectedExistingShelf { get; set; } = "";
    public string NewShelfName { get; set; } = "";
    public bool FillUnset { get; set; }
    public string ExclusionsText { get; set; }

    public FolderSettingsDraft(IReadOnlyList<RegisteredRootRow> selectedTargets)
    {
        if (selectedTargets is null || selectedTargets.Count == 0 || selectedTargets.Any(r => !r.Enabled))
            throw new ArgumentException("Select at least one active registered root", nameof(selectedTargets));
        targets = selectedTargets.ToArray();
        remainingIds = targets.Select(r => r.Id).ToList();
        Summary = SummarizeDefaultShelf(targets);
        if (IsBatch)
        {
            ShelfMode = BatchShelfMode.KeepExisting;
            SelectedExistingShelf = Summary.CommonShelf ?? "";
        }
        else
        {
            var current = targets[0].DefaultShelf;
            ShelfMode = current.Length == 0 ? BatchShelfMode.ClearToNone : BatchShelfMode.ExistingShelf;
            SelectedExistingShelf = current;
        }
        initialExclusionsText = IsBatch ? "" : string.Join(", ", targets[0].Exclusions);
        ExclusionsText = initialExclusionsText;
    }

    public static ShelfSummary SummarizeDefaultShelf(IReadOnlyList<RegisteredRootRow> roots)
    {
        if (roots.Count == 0) return new(false, "", "棚なし");
        var first = roots[0].DefaultShelf;
        if (roots.All(r => r.DefaultShelf == first))
            return new(false, first, first.Length == 0 ? "棚なし" : first);
        return new(true, null, "複数の設定値");
    }

    public bool IsShelfChanged
    {
        get
        {
            if (IsBatch) return ShelfMode != BatchShelfMode.KeepExisting;
            var current = targets[0].DefaultShelf;
            return ShelfMode switch
            {
                BatchShelfMode.KeepExisting => false,
                BatchShelfMode.ClearToNone => current.Length != 0,
                BatchShelfMode.ExistingShelf => SelectedExistingShelf != current || FillUnset,
                BatchShelfMode.NewShelf => true,
                _ => false
            };
        }
    }

    public bool IsExclusionsChanged => !IsBatch && NormalizeExclusionsText(ExclusionsText) != NormalizeExclusionsText(initialExclusionsText);

    public bool IsDirty => IsShelfChanged || IsExclusionsChanged;

    // Returns null when the shelf must NOT be modified (KeepExisting or unchanged single root without FillUnset).
    public string? ResolveShelfToSave()
    {
        if (!IsShelfChanged) return null;
        return ShelfMode switch
        {
            BatchShelfMode.KeepExisting => null,
            BatchShelfMode.ClearToNone => "",
            BatchShelfMode.ExistingShelf => ValidateShelf(SelectedExistingShelf, requireNonEmpty: true),
            BatchShelfMode.NewShelf => ValidateShelf(NewShelfName, requireNonEmpty: true),
            _ => null
        };
    }

    public string[] ParseExclusions() =>
        ExclusionsText.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    public void RecordSucceeded(int rootId) => remainingIds.Remove(rootId);

    private static string ValidateShelf(string value, bool requireNonEmpty)
    {
        var trimmed = (value ?? "").Trim();
        if (requireNonEmpty && trimmed.Length == 0)
            throw new InvalidOperationException("新しい棚の名前を入力してください。");
        if (trimmed.Length > 80)
            throw new InvalidOperationException("棚の名前は80文字以内にしてください。");
        return trimmed;
    }

    private static string NormalizeExclusionsText(string text) =>
        string.Join(", ", (text ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
}

public static class FolderScopeDescriber
{
    public static (string Summary, string? Warning) DescribeSearchScope(
        IReadOnlyList<RegisteredRootRow> allRoots,
        IReadOnlyList<int>? selectedRootIds,
        bool isAiOrSimilar,
        JsonObject? aiScope)
    {
        var activeById = allRoots.Where(r => r.Enabled).ToDictionary(r => r.Id);
        if (selectedRootIds is null)
        {
            var totalActive = activeById.Count;
            var offlineCount = activeById.Values.Count(r => !r.Online);
            var summary = $"検索対象: すべての登録フォルダ（{totalActive} フォルダ）";
            var warning = offlineCount > 0 ? $"未接続のフォルダが {offlineCount} 件あります（登録内容は保持）。" : null;
            return (summary, warning);
        }
        if (selectedRootIds.Count == 0)
            return ("検索対象: 選択なし（0 フォルダ）", "検索するフォルダを1つ以上選んでください。");

        var missing = selectedRootIds.Where(id => !activeById.ContainsKey(id)).ToArray();
        var present = selectedRootIds.Where(activeById.ContainsKey).Select(id => activeById[id]).ToArray();
        var names = string.Join("、", present.Take(3).Select(r => r.ShortPath)) + (present.Length > 3 ? $" ほか{present.Length - 3}件" : "");
        var label = present.Length == 1
            ? $"検索対象: {present[0].ShortPath}（1 フォルダ）"
            : $"検索対象: {names}（{selectedRootIds.Count} フォルダをまとめて検索）";

        var notes = new List<string>();
        if (missing.Length > 0)
            notes.Add($"選択中のフォルダ {missing.Length} 件が登録解除されています。対象を見直してください。");
        var offline = present.Count(r => !r.Online);
        if (offline > 0)
            notes.Add($"選択中のフォルダに未接続が {offline} 件あります。");
        if (isAiOrSimilar && aiScope?["root_ids"] is JsonArray scopedArray)
        {
            var allowed = scopedArray.Select(n => n!.GetValue<int>()).ToHashSet();
            var effective = selectedRootIds.Count(allowed.Contains);
            if (effective < selectedRootIds.Count)
                notes.Add($"AI索引の対象設定との共通範囲は {effective}/{selectedRootIds.Count} フォルダです。");
        }
        return (label, notes.Count > 0 ? string.Join(" ", notes) : null);
    }
}
