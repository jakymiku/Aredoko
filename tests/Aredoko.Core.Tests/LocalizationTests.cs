using System.Globalization;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Aredoko.Core;

internal static class LocalizationTests
{
    private static readonly Regex JapaneseChar = new(@"[\u3040-\u30ff\u4e00-\u9fff]", RegexOptions.Compiled);
    private static readonly HashSet<string> TranslatableAttrs = new(StringComparer.Ordinal)
    {
        "Content", "Text", "Header", "PlaceholderText", "Title",
        "ToolTipService.ToolTip", "AutomationProperties.Name", "AutomationProperties.HelpText",
    };

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "src", "Aredoko.WinUI", "MainPage.xaml")))
                return dir.FullName;
            dir = dir.Parent;
        }
        throw new DirectoryNotFoundException("Repository root not found");
    }

    public static void Run(Action<bool, string> check)
    {
        var prev = AppText.CurrentLanguage;
        try
        {
            var tempDir = Path.Combine(Path.GetTempPath(), "aredoko-loc-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDir);
            try
            {
                var settingsPath = Path.Combine(tempDir, "viewer-settings.json");
                var enSettings = new ViewerInputSettings(Language: "en");
                enSettings.Save(settingsPath);
                var reloaded = ViewerInputSettings.Load(settingsPath);
                check(reloaded.Language == "en", "ViewerInputSettings roundtrips language=en");

                File.WriteAllText(settingsPath, """{"version":1,"wheel_up_advances":false,"language":"fr"}""");
                check(ViewerInputSettings.Load(settingsPath).Language == "system", "Invalid language normalizes to system");

                File.WriteAllText(settingsPath, """{"version":1,"wheel_up_advances":true}""");
                var legacy = ViewerInputSettings.Load(settingsPath);
                check(legacy.Language == "system" && legacy.WheelUpAdvances, "Legacy viewer-settings defaults language to system");
            }
            finally
            {
                try { Directory.Delete(tempDir, true); } catch { }
            }

            check(ViewerInputSettings.ResolveLanguage("system", new CultureInfo("ja-JP")) == "ja", "System resolves ja-JP to ja");
            check(ViewerInputSettings.ResolveLanguage("system", new CultureInfo("en-US")) == "en", "System resolves en-US to en");
            check(ViewerInputSettings.ResolveLanguage("system", new CultureInfo("de-DE")) == "en", "System resolves non-ja to en");
            check(ViewerInputSettings.ResolveLanguage("ja", new CultureInfo("en-US")) == "ja", "Explicit ja overrides OS culture");
            check(ViewerInputSettings.ResolveLanguage("en", new CultureInfo("ja-JP")) == "en", "Explicit en overrides OS culture");

            AppText.Apply("en");
            check(AppText.IsEnglish && AppText.L("あ", "A") == "A", "AppText.Apply(en) switches L() to English");
            check(AppText.TranslateBackend("AI索引を作成中です。") == "AI index build is in progress.", "AppText translates backend exact status");
            check(AppText.TranslateBackend("モデルを取得できませんでした。通信と空き容量を確認して再試行してください。途中までの取得は保持しています。 既存設定は保持しています。").EndsWith("Existing settings were preserved."), "AppText translates backend message with keep-existing suffix");
            check(AppText.TranslateBackend("追加できなかった本: 3冊。完了した範囲は保持しています。") == "Failed to add 3 book(s). Completed items were kept.", "AppText translates dynamic backend batch message");

            check(ErrorText.Localize("AI inference failed").StartsWith("AI inference failed."), "ErrorText.Localize uses English when active language is en");
            check(ErrorText.Localize("Use at most 16 search words") == "Use up to 16 search words.", "ErrorText.Localize uses English regex templates");
            check(ErrorText.AIWorkerFailure("ai_runtime_initialization_failed")!.Contains("memory"), "ErrorText.AIWorkerFailure returns English message");
            check(AISearchStatus.StatusLabel("complete") == "Ready", "AISearchStatus.StatusLabel returns English");
            check(AISearchStatus.Guidance(AISearchStatus.Unindexed, 10, 0, "").Contains("10 candidate"), "AISearchStatus.Guidance formats English");
            var settingsData = AISearchStatus.SettingsDataStatus("complete", 4, 10);
            check(settingsData.Step3Status.Contains("Ready"), "AISearchStatus.SettingsDataStatus returns English");
            var report = DiagnosticsReport.Generate(null, null, null, 2, 3, "Dark", "2026.1", 1, 1);
            check(report.Contains("App Version:") && !report.Contains("アプリ版:"), "DiagnosticsReport.Generate outputs English headers");
            var rootRow = new RegisteredRootRow(1, "C:/Comics", true, true, "", []);
            check(rootRow.StatusLabel.Contains("Active · Online") && rootRow.ShelfLabel == "Default shelf: None", "RegisteredRootRow labels translate cleanly");
            check(FolderScopeDescriber.DescribeSearchScope([rootRow], null, false, null).Summary.Contains("All registered folders"), "FolderScopeDescriber describes all folders in English");
            var plan = new AISetupPlan(false, 0, null, true, [], []);
            var guidanceText = AISetupGuidance.Describe(plan, 3, null, null);
            check(guidanceText.Contains("reopen Aredoko.exe"), "AISetupGuidance.Describe translates to English");
            var mediaRow = new MediaRow { Id = 1, Title = "Sample", Location = "./", Kind = "book", Tags = ["a", "b"], Match = "related" };
            check(mediaRow.LocationLabel == "Images directly in folder (as book)", "MediaRow.LocationLabel translates to English");
            check(mediaRow.MatchLabel == "Related term · ", "MediaRow.MatchLabel translates to English");

            var repo = FindRepoRoot();
            var missing = new List<string>();
            foreach (var rel in new[] { "MainPage.xaml", "TagSuggestionsView.xaml", "MainWindow.xaml" })
            {
                var doc = XDocument.Load(Path.Combine(repo, "src", "Aredoko.WinUI", rel));
                foreach (var el in doc.Descendants())
                {
                    foreach (var attr in el.Attributes())
                    {
                        var name = attr.Name.LocalName;
                        if (!TranslatableAttrs.Contains(name)) continue;
                        var val = attr.Value;
                        if (!JapaneseChar.IsMatch(val) || val == "日本語") continue;
                        if (!AppText.TryTranslateExact(val, out var en) || string.IsNullOrWhiteSpace(en))
                            missing.Add($"{rel}:{name}={val}");
                    }
                }
            }
            check(missing.Count == 0, missing.Count == 0 ? "All WinUI XAML Japanese strings have English translations" : "Missing XAML translations: " + string.Join("; ", missing.Take(5)));
        }
        finally
        {
            AppText.Apply(prev);
        }
    }
}
