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
        sb.AppendLine("=== Aredoko 診断サマリー (Opt-in Diagnostic Report) ===");
        sb.AppendLine($"生成日時: {DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} UTC");
        sb.AppendLine($"アプリ版: Aredoko v{appVersion}");
        sb.AppendLine($"OS環境: {RuntimeInformation.OSDescription} ({RuntimeInformation.ProcessArchitecture})");
        sb.AppendLine($"ランタイム: {RuntimeInformation.FrameworkDescription}");
        if(basicRuntime is {} runtime)
        {
            var implementation=runtime.Implementation=="cpython"?"CPython":runtime.Implementation;
            var environment=runtime.VirtualEnvironment?"仮想環境":"ベース環境";
            sb.AppendLine($"基本Python: {implementation} {runtime.Version}（{runtime.Bits}ビット、{environment}）");
        }
        sb.AppendLine($"UIテーマ: {theme}");
        sb.AppendLine();

        sb.AppendLine("--- ライブラリ状態 ---");
        var rTotal = rootCount >= 0 ? rootCount : (roots?.Count ?? 0);
        var rEnabled = enabledRootCount >= 0 ? enabledRootCount : (roots?.Count(r => r.Enabled) ?? 0);
        sb.AppendLine($"登録フォルダ数: {rTotal} 件 (パス情報は非公開)");
        sb.AppendLine($"有効フォルダ数: {rEnabled} 件");
        sb.AppendLine($"棚の数: {(shelfCount >= 0 ? $"{shelfCount} 件" : "未確認")}");
        sb.AppendLine($"登録した関連語: {(termCount >= 0 ? $"{termCount} 件" : "未確認")}");
        sb.AppendLine();

        sb.AppendLine("--- AI機能・モデル状態 ---");
        if (aiStatus is not null)
        {
            var available = aiStatus["available"]?.GetValue<bool>() ?? false;
            var state = aiStatus["state"]?.GetValue<string>() ?? "unknown";
            var statusCode = aiStatus["status_code"]?.GetValue<string>() ?? (available ? "ready" : "model_missing");
            var model = aiStatus["model"]?.GetValue<string>() ?? "未選択";
            var modelId = aiStatus["model_id"]?.GetValue<string>() ?? "none";
            var resident = aiStatus["resident"]?.GetValue<bool>() ?? false;
            var device = aiStatus["device"]?.GetValue<string>() ?? "";
            var modalities = aiStatus["modalities"] is JsonArray arr
                ? string.Join(", ", arr.Select(m => m?.GetValue<string>() ?? ""))
                : "none";

            sb.AppendLine($"AI利用可否: {(available ? "利用可能" : "未導入・無効")}");
            sb.AppendLine($"状態コード: {statusCode} (内部状態: {state})");
            sb.AppendLine($"モデル: {model} (ID: {modelId})");
            sb.AppendLine($"対応モダリティ: {modalities}");
            sb.AppendLine($"常駐プロセス: {(resident ? "メモリ常駐中" : "待機中/未ロード")}{(string.IsNullOrEmpty(device) ? "" : $" (Device: {device})")}");

            var error = aiStatus["error"]?.GetValue<string>();
            if (!string.IsNullOrWhiteSpace(error))
            {
                sb.AppendLine($"直近エラー: {RedactText(error)}");
            }
        }
        else
        {
            sb.AppendLine("AI機能情報: 取得できませんでした (バックエンド未接続または無効)");
        }
        sb.AppendLine();

        sb.AppendLine("--- 検索対象スコープ ---");
        if (aiScope is not null)
        {
            var rootsArr = aiScope["root_ids"] as JsonArray;
            var scopeRootCount = rootsArr?.Count ?? 0;
            sb.AppendLine($"AI対象フォルダ設定: {(scopeRootCount == 0 ? "すべての登録フォルダ" : $"{scopeRootCount} フォルダに制限")}");
        }
        else
        {
            sb.AppendLine("AI対象スコープ: 未設定または全フォルダ");
        }
        sb.AppendLine();

        sb.AppendLine("--- 機密保護・プライバシー注記 ---");
        sb.AppendLine("※ 認証トークンとユーザー名は伏字にしています。実行場所やAI状態など、共有前に内容を確認してください。");
        sb.AppendLine("※ この診断情報は外部サーバーへ自動送信されません。クリップボードへのコピーのみ可能です。");
        sb.AppendLine("====================================================");

        return sb.ToString();
    }
}
