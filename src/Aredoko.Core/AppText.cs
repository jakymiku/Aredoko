using System.Globalization;
using System.Text.RegularExpressions;

namespace Aredoko.Core;

public static partial class AppText
{
    public static string CurrentLanguage { get; private set; } = "ja";
    public static bool IsEnglish => CurrentLanguage == "en";

    public static string Apply(string? preference, CultureInfo? uiCulture = null)
    {
        CurrentLanguage = ViewerInputSettings.ResolveLanguage(preference, uiCulture);
        return CurrentLanguage;
    }

    public static string L(string ja, string en) => IsEnglish ? en : ja;

    public static string T(string ja) => IsEnglish && UiStrings.Exact.TryGetValue(ja, out var en) ? en : ja;

    public static bool TryTranslateExact(string ja, out string en) => UiStrings.Exact.TryGetValue(ja, out en!);

    [GeneratedRegex(@"^追加できなかった本: (\d+)冊。完了した範囲は保持しています。$")]
    private static partial Regex BatchFailedBooksRegex();

    [GeneratedRegex(@"^AI索引を作成できませんでした（([^）]+)）。ローカルログを確認してください。$")]
    private static partial Regex IndexFailedTypeRegex();

    [GeneratedRegex(@"^追加できませんでした（([^）]+)）。元ファイル・登録範囲を確認してください。$")]
    private static partial Regex BookAddFailedTypeRegex();

    [GeneratedRegex(@"^複数本の追加を終了できませんでした（([^）]+)）。$")]
    private static partial Regex BatchFinishFailedTypeRegex();

    [GeneratedRegex(@"^ページ索引を保存できませんでした（([^）]+)）。元ファイル・登録範囲を確認して再実行してください。$")]
    private static partial Regex PageIndexFailedTypeRegex();

    [GeneratedRegex(@"^モデル設定が無効です（([^）]+)）。設定を確認してください。文字検索は利用できます。$")]
    private static partial Regex InvalidProfileTypeRegex();

    [GeneratedRegex(@"^設定を読み込めません（([^）]+)）。JSON内容・場所を確認してください。$")]
    private static partial Regex ReadSettingsTypeRegex();

    [GeneratedRegex(@"^保存済みのモデル設定が無効です（([^）]+)）。$")]
    private static partial Regex SavedProfileTypeRegex();

    [GeneratedRegex(@"^画像分類の推定候補・(キャラクター|一般タグ)。分類出力 ([0-9.]+)（正解確率ではありません）。画像/表紙のみ、本文・人物関係は未確認。$")]
    private static partial Regex WdTaggerExplanationRegex();

    [GeneratedRegex(@"^音響特徴: (.+)$")]
    private static partial Regex AcousticSnippetRegex();

    public static string TranslateBackend(string? text)
    {
        if (string.IsNullOrEmpty(text) || !IsEnglish) return text ?? "";
        if (UiStrings.Exact.TryGetValue(text, out var exact)) return exact;
        const string keepExistingSuffix = " 既存設定は保持しています。";
        if (text.EndsWith(keepExistingSuffix, StringComparison.Ordinal))
        {
            var head = text[..^keepExistingSuffix.Length];
            return TranslateBackend(head) + " Existing settings were preserved.";
        }
        if (BatchFailedBooksRegex().Match(text) is { Success: true } m1)
            return $"Failed to add {m1.Groups[1].Value} book(s). Completed items were kept.";
        if (IndexFailedTypeRegex().Match(text) is { Success: true } m2)
            return $"Failed to build AI index ({m2.Groups[1].Value}). Check local logs.";
        if (BookAddFailedTypeRegex().Match(text) is { Success: true } m3)
            return $"Could not add item ({m3.Groups[1].Value}). Check the source files and folder scope.";
        if (BatchFinishFailedTypeRegex().Match(text) is { Success: true } m4)
            return $"Could not finish adding multiple books ({m4.Groups[1].Value}).";
        if (PageIndexFailedTypeRegex().Match(text) is { Success: true } m5)
            return $"Could not save page index ({m5.Groups[1].Value}). Check source files and scope, then retry.";
        if (InvalidProfileTypeRegex().Match(text) is { Success: true } m6)
            return $"Invalid model configuration ({m6.Groups[1].Value}). Check Settings. Text search remains available.";
        if (ReadSettingsTypeRegex().Match(text) is { Success: true } m7)
            return $"Cannot read configuration ({m7.Groups[1].Value}). Check JSON syntax and location.";
        if (SavedProfileTypeRegex().Match(text) is { Success: true } m8)
            return $"Saved model configuration is invalid ({m8.Groups[1].Value}).";
        if (WdTaggerExplanationRegex().Match(text) is { Success: true } m9)
        {
            var kind = m9.Groups[1].Value == "キャラクター" ? "character" : "general tag";
            return $"Estimated image tag ({kind}). Model score: {m9.Groups[2].Value} (not a ground-truth probability). Cover/image only; body text and context unverified.";
        }
        if (AcousticSnippetRegex().Match(text) is { Success: true } m10)
            return $"Acoustic cue: {m10.Groups[1].Value}";
        return text;
    }
}
