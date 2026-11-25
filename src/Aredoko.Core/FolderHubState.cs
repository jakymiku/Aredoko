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
    bool Recursive = true,
    bool Favorite = false,
    IReadOnlyList<long>? ShelfIds = null,
    string StartupScan = "none")
{
    public string ModeLabel => FolderBooks
        ? AppText.L("画像フォルダを一冊として扱う", "Folder treated as one book")
        : AppText.L("画像は1枚ずつ", "Images individually");

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
        ? AppText.L("登録解除済み（再登録でタグ・棚を復元）", "Unregistered (re-add to restore tags & shelves)")
        : (Online ? AppText.L("登録中 · 接続OK", "Active · Online") : AppText.L("登録中 · 未接続", "Active · Offline"))
          + AppText.L($" · {PresentCount:N0} 件", $" · {PresentCount:N0} items");

    public string ShelfLabel => string.IsNullOrEmpty(DefaultShelf)
        ? AppText.L("初期棚: 棚なし", "Default shelf: None")
        : AppText.L($"初期棚: {DefaultShelf}", $"Default shelf: {DefaultShelf}") + (ShelfIds is {Count:>1}?AppText.L($" ほか{ShelfIds.Count-1}棚",$" +{ShelfIds.Count-1} more"):"");

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
            var memberships=row["shelf_ids"]?.AsArray().Select(x=>x!.GetValue<long>()).ToArray();if(memberships is not null)ShelfProtocol.ValidateIds(memberships);
            var startup=row["startup_scan"]?.GetValue<string>()??"none";
            if(startup is not ("none" or "list" or "list_and_ai"))throw new InvalidDataException("Invalid startup scan preference");
            list.Add(new RegisteredRootRow(id, path, enabled, online, shelf, excludes, count, scanned, folderBooks, row["recursive"]?.GetValue<bool>()??true,row["favorite"]?.GetValue<bool>()??false,memberships,startup));
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
    private string initialExclusionsText;
    public IReadOnlyList<int> TargetIds => remainingIds;
    public bool IsBatch => targets.Count > 1;
    public ShelfSummary Summary { get; }
    public BatchShelfMode ShelfMode { get; set; }
    public string SelectedExistingShelf { get; set; } = "";
    public string NewShelfName { get; set; } = "";
    private long[]? selectedShelfIds;
    public IReadOnlyList<long>? ShelfIdsToSave => selectedShelfIds?.ToArray();
    public void SelectShelfIds(IReadOnlyList<long> ids){ShelfProtocol.ValidateIds(ids);selectedShelfIds=ids.Order().ToArray();}
    public void ClearShelfIdSelection()=>selectedShelfIds=null;
    public bool FillUnset { get; set; }
    public string ExclusionsText { get; set; }

    public FolderSettingsDraft(IReadOnlyList<RegisteredRootRow> selectedTargets)
    {
        if (selectedTargets is null || selectedTargets.Count == 0 || selectedTargets.Any(r => !r.Enabled))
            throw new ArgumentException("Select at least one active registered root", nameof(selectedTargets));
        targets = selectedTargets.ToArray();
        remainingIds = targets.Select(r => r.Id).ToList();
        Summary = SummarizeDefaultShelf(targets);
        if(targets[0].ShelfIds is {} memberships && targets.All(root=>root.ShelfIds is {} ids&&ids.Order().SequenceEqual(memberships.Order())))SelectShelfIds(memberships);
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
        if (roots.Count == 0) return new(false, "", AppText.L("棚なし", "No shelf"));
        var first = roots[0].DefaultShelf;
        if (roots.All(r => r.DefaultShelf == first && (r.ShelfIds is null || roots[0].ShelfIds is null || r.ShelfIds.Order().SequenceEqual(roots[0].ShelfIds!.Order()))))
            return new(false, first, first.Length == 0 ? AppText.L("棚なし", "No shelf") : first+(roots[0].ShelfIds is {Count:>1} ids?AppText.L($" ほか{ids.Count-1}棚", $" +{ids.Count-1} more"):""));
        return new(true, null, AppText.L("複数の設定値", "Multiple values"));
    }

    public bool IsShelfChanged
    {
        get
        {
            if(selectedShelfIds is not null)return FillUnset&&selectedShelfIds.Length>0 || targets.Any(root=>root.ShelfIds is null || !root.ShelfIds.Order().SequenceEqual(selectedShelfIds));
            if (IsBatch) return ShelfMode != BatchShelfMode.KeepExisting;
            var current = targets[0].DefaultShelf;
            return ShelfMode switch
            {
                BatchShelfMode.KeepExisting => false,
                BatchShelfMode.ClearToNone => current.Length != 0 || targets[0].ShelfIds is {Count:>0},
                BatchShelfMode.ExistingShelf => SelectedExistingShelf != current || FillUnset || targets[0].ShelfIds is {Count:>1},
                BatchShelfMode.NewShelf => true,
                _ => false
            };
        }
    }

    public bool IsExclusionsChanged => !IsBatch && NormalizeExclusionsText(ExclusionsText) != NormalizeExclusionsText(initialExclusionsText);

    public void MarkExclusionsSaved(string savedText) => initialExclusionsText = savedText;

    public bool IsDirty => IsShelfChanged || IsExclusionsChanged;

    // Returns null when the shelf must NOT be modified (KeepExisting or unchanged single root without FillUnset).
    public string? ResolveShelfToSave()
    {
        if (selectedShelfIds is not null || !IsShelfChanged) return null;
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
            throw new InvalidOperationException(AppText.L("新しい棚の名前を入力してください。", "Enter a new shelf name."));
        if (trimmed.Length > 80)
            throw new InvalidOperationException(AppText.L("棚の名前は80文字以内にしてください。", "Shelf name must be 80 characters or fewer."));
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
            var summary = AppText.L($"検索対象: すべての登録フォルダ（{totalActive} フォルダ）", $"Search scope: All registered folders ({totalActive})");
            var warning = offlineCount > 0 ? AppText.L($"未接続のフォルダが {offlineCount} 件あります（登録内容は保持）。", $"{offlineCount} folder(s) currently offline (records preserved).") : null;
            return (summary, warning);
        }
        if (selectedRootIds.Count == 0)
            return (AppText.L("検索対象: 選択なし（0 フォルダ）", "Search scope: None (0 folders)"), AppText.L("検索するフォルダを1つ以上選んでください。", "Select at least one folder to search."));

        var missing = selectedRootIds.Where(id => !activeById.ContainsKey(id)).ToArray();
        var present = selectedRootIds.Where(activeById.ContainsKey).Select(id => activeById[id]).ToArray();
        var names = string.Join(AppText.L("、", ", "), present.Take(3).Select(r => r.ShortPath)) + (present.Length > 3 ? AppText.L($" ほか{present.Length - 3}件", $" +{present.Length - 3} more") : "");
        var label = present.Length == 1
            ? AppText.L($"検索対象: {present[0].ShortPath}（1 フォルダ）", $"Search scope: {present[0].ShortPath} (1 folder)")
            : AppText.L($"検索対象: {names}（{selectedRootIds.Count} フォルダをまとめて検索）", $"Search scope: {names} ({selectedRootIds.Count} folders)");

        var notes = new List<string>();
        if (missing.Length > 0)
            notes.Add(AppText.L($"選択中のフォルダ {missing.Length} 件が登録解除されています。対象を見直してください。", $"{missing.Length} selected folder(s) unregistered. Review your scope."));
        var offline = present.Count(r => !r.Online);
        if (offline > 0)
            notes.Add(AppText.L($"選択中のフォルダに未接続が {offline} 件あります。", $"{offline} selected folder(s) offline."));
        if (isAiOrSimilar && aiScope?["root_ids"] is JsonArray scopedArray)
        {
            var allowed = scopedArray.Select(n => n!.GetValue<int>()).ToHashSet();
            var effective = selectedRootIds.Count(allowed.Contains);
            if (effective < selectedRootIds.Count)
                notes.Add(AppText.L($"AI索引の対象設定との共通範囲は {effective}/{selectedRootIds.Count} フォルダです。", $"{effective} of {selectedRootIds.Count} selected folder(s) included in AI scope."));
        }
        return (label, notes.Count > 0 ? string.Join(" ", notes) : null);
    }
}
