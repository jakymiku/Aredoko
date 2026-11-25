using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Aredoko.Core;

public static class DiagnosticsReport
{
    private static readonly Regex UserPathRegex = new(@"(([A-Za-z]:[\\/]|//|\\\\|[\\/])[Uu]sers[\\/]|/home[\\/])[^\\/\r\n]+", RegexOptions.Compiled);
    private static readonly Regex TokenRegex = new(@"(\b(bearer\s+token|bearer|token|x-aredoko-token)[=:\s""']+)[A-Za-z0-9_\-\.]+", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    private static string RedactCurrentUserName(string input)
    {
        try
        {
            var user = Environment.UserName;
            if (!string.IsNullOrWhiteSpace(user) && user.Length >= 2 &&
                !string.Equals(user, "SYSTEM", StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(user, "Administrator", StringComparison.OrdinalIgnoreCase))
            {
                input = Regex.Replace(input, @"(?<=[\\/])" + Regex.Escape(user) + @"(?=[\\/\r\n""']|\b)", "[USER]", RegexOptions.IgnoreCase);
            }
        }
        catch { }
        return input;
    }

    public static string RedactPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) return "";
        var sanitized = UserPathRegex.Replace(path, "$1[USER]");
        sanitized = RedactCurrentUserName(sanitized);
        return sanitized;
    }

    public static string RedactText(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return "";
        var sanitized = UserPathRegex.Replace(text, "$1[USER]");
        sanitized = RedactCurrentUserName(sanitized);
        sanitized = TokenRegex.Replace(sanitized, "$1[REDACTED]");
        return sanitized;
    }

    public static string Generate(
        JsonNode? aiStatus,
        JsonNode? aiScope,
        IReadOnlyList<RegisteredRootRow>? roots = null,
        int shelfCount = -1,
        int termCount = -1,
        string theme = "Dark",
        string appVersion = "1.0.0-beta",
        int rootCount = -1,
        int enabledRootCount = -1,
        BasicRuntimeDiagnostic? basicRuntime = null)
    {
        var sb = new StringBuilder();
        sb.AppendLine(AppText.L("=== Aredoko 診断サマリー (Opt-in Diagnostic Report) ===", "=== Aredoko Diagnostic Summary (Opt-in) ==="));
        sb.AppendLine($"{AppText.L("生成日時", "Generated")}: {DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} UTC");
        sb.AppendLine($"{AppText.L("アプリ版", "App Version")}: Aredoko v{appVersion}");
        sb.AppendLine($"{AppText.L("OS環境", "OS")}: {RuntimeInformation.OSDescription} ({RuntimeInformation.ProcessArchitecture})");
        sb.AppendLine($"{AppText.L("ランタイム", "Runtime")}: {RuntimeInformation.FrameworkDescription}");
        if(basicRuntime is {} runtime)
        {
            var implementation=runtime.Implementation=="cpython"?"CPython":runtime.Implementation;
            var environment=runtime.VirtualEnvironment?AppText.L("仮想環境","venv"):AppText.L("ベース環境","base");
            sb.AppendLine(AppText.L($"基本Python: {implementation} {runtime.Version}（{runtime.Bits}ビット、{environment}）", $"Base Python: {implementation} {runtime.Version} ({runtime.Bits}-bit, {environment})"));
        }
        sb.AppendLine($"{AppText.L("UIテーマ", "UI Theme")}: {theme}");
        sb.AppendLine();

        sb.AppendLine(AppText.L("--- ライブラリ状態 ---", "--- Library Status ---"));
        var rTotal = rootCount >= 0 ? rootCount : (roots?.Count ?? 0);
        var rEnabled = enabledRootCount >= 0 ? enabledRootCount : (roots?.Count(r => r.Enabled) ?? 0);
        sb.AppendLine(AppText.L($"登録フォルダ数: {rTotal} 件 (パス情報は非公開)", $"Registered Folders: {rTotal} (paths omitted)"));
        sb.AppendLine(AppText.L($"有効フォルダ数: {rEnabled} 件", $"Enabled Folders: {rEnabled}"));
        sb.AppendLine($"{AppText.L("棚の数", "Shelves")}: {(shelfCount >= 0 ? AppText.L($"{shelfCount} 件", $"{shelfCount}") : AppText.L("未確認", "Unconfirmed"))}");
        sb.AppendLine($"{AppText.L("登録した関連語", "Synonyms & Aliases")}: {(termCount >= 0 ? AppText.L($"{termCount} 件", $"{termCount}") : AppText.L("未確認", "Unconfirmed"))}");
        sb.AppendLine();

        sb.AppendLine(AppText.L("--- AI機能・モデル状態 ---", "--- AI & Model Status ---"));
        if (aiStatus is not null)
        {
            var available = aiStatus["available"]?.GetValue<bool>() ?? false;
            var state = aiStatus["state"]?.GetValue<string>() ?? "unknown";
            var statusCode = aiStatus["status_code"]?.GetValue<string>() ?? (available ? "ready" : "model_missing");
            var model = aiStatus["model"]?.GetValue<string>() ?? AppText.L("未選択", "Not selected");
            var modelId = aiStatus["model_id"]?.GetValue<string>() ?? "none";
            var resident = aiStatus["resident"]?.GetValue<bool>() ?? false;
            var device = aiStatus["device"]?.GetValue<string>() ?? "";
            var modalities = aiStatus["modalities"] is JsonArray arr
                ? string.Join(", ", arr.Select(m => m?.GetValue<string>() ?? ""))
                : "none";

            sb.AppendLine($"{AppText.L("AI利用可否", "AI Available")}: {(available ? AppText.L("利用可能", "Available") : AppText.L("未導入・無効", "Unavailable / Not installed"))}");
            sb.AppendLine(AppText.L($"状態コード: {statusCode} (内部状態: {state})", $"Status Code: {statusCode} (State: {state})"));
            sb.AppendLine($"{AppText.L("モデル", "Model")}: {model} (ID: {modelId})");
            sb.AppendLine($"{AppText.L("対応モダリティ", "Modalities")}: {modalities}");
            sb.AppendLine($"{AppText.L("常駐プロセス", "Worker Process")}: {(resident ? AppText.L("メモリ常駐中", "Loaded in memory") : AppText.L("待機中/未ロード", "Idle / Unloaded"))}{(string.IsNullOrEmpty(device) ? "" : $" (Device: {device})")}");

            var error = aiStatus["error"]?.GetValue<string>();
            if (!string.IsNullOrWhiteSpace(error))
            {
                sb.AppendLine($"{AppText.L("直近エラー", "Last Error")}: {RedactText(AppText.TranslateBackend(error))}");
            }
        }
        else
        {
            sb.AppendLine(AppText.L("AI機能情報: 取得できませんでした (バックエンド未接続または無効)", "AI Info: Unavailable (backend disconnected or disabled)"));
        }
        sb.AppendLine();

        sb.AppendLine(AppText.L("--- 検索対象スコープ ---", "--- Search Scope ---"));
        if (aiScope is not null)
        {
            var rootsArr = aiScope["root_ids"] as JsonArray;
            var scopeRootCount = rootsArr?.Count ?? 0;
            sb.AppendLine(AppText.L($"AI対象フォルダ設定: {(scopeRootCount == 0 ? "すべての登録フォルダ" : $"{scopeRootCount} フォルダに制限")}", $"AI Scope Folders: {(scopeRootCount == 0 ? "All registered folders" : $"Limited to {scopeRootCount} folder(s)")}"));
        }
        else
        {
            sb.AppendLine(AppText.L("AI対象スコープ: 未設定または全フォルダ", "AI Scope: Default / All folders"));
        }
        sb.AppendLine();

        sb.AppendLine(AppText.L("--- 機密保護・プライバシー注記 ---", "--- Privacy Notice ---"));
        sb.AppendLine(AppText.L("※ 認証トークンとユーザー名は伏字にしています。実行場所やAI状態など、共有前に内容を確認してください。", "* Auth tokens and user names are redacted. Review locations and status before sharing."));
        sb.AppendLine(AppText.L("※ この診断情報は外部サーバーへ自動送信されません。クリップボードへのコピーのみ可能です。", "* Diagnostic data is never sent automatically; it is copied to clipboard only on request."));
        sb.AppendLine("====================================================");

        return sb.ToString();
    }
}
