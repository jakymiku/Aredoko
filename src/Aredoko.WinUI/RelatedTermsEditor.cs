using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

// User-owned related-term dictionary. Saving changes only the dictionary;
// files, tags and AI indexes are untouched. Literal search reads it at once.
public sealed class RelatedTermsEditor
{
    private const int ShownEntries = 200;
    private readonly LibraryApi api;
    private readonly StackPanel panel = new() { Spacing = 12, MinWidth = 280 };
    private readonly TextBox term = new() { Header = AppText.L("作品名・タグにある言葉", "Headword in titles or tags"), PlaceholderText = AppText.L("例: 博麗霊夢", "e.g., Reimu Hakurei"), MaxLength = RelatedTerms.MaxWordChars };
    private readonly TextBox aliases = new() { Header = AppText.L("別の呼び名（、区切り）", "Aliases (comma-separated)"), PlaceholderText = AppText.L("例: 霊夢、reimu", "e.g., Reimu, hakurei_reimu") };
    private readonly TextBox related = new() { Header = AppText.L("探すときに思い浮かぶ言葉（、区切り）", "Related terms to search with (comma-separated)"), PlaceholderText = AppText.L("例: 東方、巫女", "e.g., Touhou, shrine_maiden") };
    private readonly Button save = new() { Content = AppText.L("保存", "Save"), Style = (Style)Application.Current.Resources["AccentButtonStyle"] };
    private readonly Button newEntry = new() { Content = AppText.L("＋ 新規", "+ New") };
    private readonly Button delete = new() { Content = AppText.L("削除", "Delete"), IsEnabled = false };
    private readonly Button export = new() { Content = AppText.L("書き出し…", "Export...") };
    private readonly Button import = new() { Content = AppText.L("読み込み…", "Import...") };
    private readonly ComboBox entries = new() { Header = AppText.L("登録済みの語", "Saved Entries"), HorizontalAlignment = HorizontalAlignment.Stretch };
    private readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap };
    private List<RelatedTermEntry> loaded = [];
    private bool busy;

    public RelatedTermsEditor(LibraryApi api)
    {
        this.api = api;
        AutomationProperties.SetAutomationId(term, "RelatedTerm");
        AutomationProperties.SetAutomationId(aliases, "RelatedAliases");
        AutomationProperties.SetAutomationId(related, "RelatedWords");
        AutomationProperties.SetAutomationId(save, "SaveRelatedTerm");
        AutomationProperties.SetAutomationId(newEntry, "NewRelatedTerm");
        AutomationProperties.SetAutomationId(delete, "DeleteRelatedTerm");
        AutomationProperties.SetAutomationId(entries, "RelatedTermList");
        AutomationProperties.SetAutomationId(export, "ExportRelatedTerms");
        AutomationProperties.SetAutomationId(import, "ImportRelatedTerms");
        AutomationProperties.SetAutomationId(status, "RelatedTermStatus");
        AutomationProperties.SetLiveSetting(status, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        var help = new TextBlock { TextWrapping = TextWrapping.Wrap, Text = AppText.L("言い換えを登録すると検索で一緒に探します（例：巫女 → 霊夢）", "Register synonyms and related words to search together (e.g., shrine_maiden → Reimu)") };
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Children = { save, newEntry, delete } };
        var editStack = new StackPanel { Spacing = 10, Children = { entries, term, aliases, related, actions } };
        var editCard = new Border { Style = (Style)Application.Current.Resources["AredokoSurfaceStyle"], Child = editStack };
        var filesHeading = new TextBlock { Text = AppText.L("辞書の書き出し・読み込み", "Export / Import Dictionary"), Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] };
        var files = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Children = { export, import } };
        var filesCard = new Border { Style = (Style)Application.Current.Resources["AredokoSurfaceStyle"], Child = new StackPanel { Spacing = 8, Children = { filesHeading, files } } };
        foreach (var element in new UIElement[] { help, editCard, filesCard, status }) panel.Children.Add(element);
        term.TextChanged += (_, _) => UpdateDeleteEnabled();
        newEntry.Click += (_, _) =>
        {
            if (busy) return;
            entries.SelectedIndex = -1;
            term.Text = aliases.Text = related.Text = "";
            UpdateDeleteEnabled();
            term.Focus(FocusState.Programmatic);
        };
        // Files are touched only through the pickers the user opens here.
        export.Click += async (_, _) => await RunAsync(async () =>
        {
            var picker = new Windows.Storage.Pickers.FileSavePicker { SuggestedFileName = "aredoko-related-terms" };
            picker.FileTypeChoices.Add("JSON", [".json"]);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(MainWindow.Current));
            var file = await picker.PickSaveFileAsync();
            if (file is null) return;
            var document = await api.ExportRelatedTermsAsync();
            await Windows.Storage.FileIO.WriteTextAsync(file, document, Windows.Storage.Streams.UnicodeEncoding.Utf8);
            // Count what was written, not the possibly stale list in this dialog.
            status.Text = AppText.L($"{RelatedTerms.CountExport(document):N0}件を書き出しました。", $"Exported {RelatedTerms.CountExport(document):N0} entries.");
        });
        import.Click += async (_, _) => await RunAsync(async () =>
        {
            var picker = new Windows.Storage.Pickers.FileOpenPicker();
            picker.FileTypeFilter.Add(".json");
            WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(MainWindow.Current));
            var file = await picker.PickSingleFileAsync();
            if (file is null) return;
            if ((await file.GetBasicPropertiesAsync()).Size > (ulong)RelatedTerms.MaxImportBytes) { status.Text = AppText.L("ファイルが大きすぎます（16MiBまで）。", "File is too large (max 16 MiB)."); return; }
            var text = await Windows.Storage.FileIO.ReadTextAsync(file, Windows.Storage.Streams.UnicodeEncoding.Utf8);
            var error = RelatedTerms.CheckImport(text);
            if (error is not null) { status.Text = error; return; }
            var result = await api.ImportRelatedTermsAsync(text);
            await RefreshAsync(null);
            status.Text = RelatedTerms.DescribeImport(result) + AppText.L("同じ見出し語は置き換え、他の登録は残します。", " Matching headwords were replaced; other entries were kept.");
        });
        entries.SelectionChanged += (_, _) =>
        {
            if (entries.SelectedItem is ComboBoxItem { Tag: RelatedTermEntry entry })
            {
                var sep = AppText.L("、", ", ");
                term.Text = entry.Term; aliases.Text = string.Join(sep, entry.Aliases); related.Text = string.Join(sep, entry.Related);
            }
        };
        save.Click += async (_, _) => await RunAsync(async () =>
        {
            var aliasWords = RelatedTerms.SplitWords(aliases.Text);
            var relatedWords = RelatedTerms.SplitWords(related.Text);
            var error = RelatedTerms.Validate(term.Text.Trim(), aliasWords, relatedWords);
            if (error is not null) { status.Text = error; return; }
            await api.PostAsync("api/library/terms", RelatedTerms.Upsert(term.Text, aliasWords, relatedWords));
            await RefreshAsync(term.Text.Trim());
            status.Text = AppText.L("✓ 保存しました", "✓ Saved");
        });
        delete.Click += async (_, _) => await RunAsync(async () =>
        {
            if (term.Text.Trim().Length == 0) { status.Text = AppText.L("削除する見出し語を選んでください。", "Select a headword to delete."); return; }
            await api.PostAsync("api/library/terms/delete", RelatedTerms.Delete(term.Text));
            term.Text = aliases.Text = related.Text = "";
            await RefreshAsync(null);
            status.Text = AppText.L("削除しました。", "Deleted.");
        });
    }

    public UIElement Content => panel;
    public bool IsBusy => busy;

    public Task LoadAsync() => RunAsync(() => RefreshAsync(null));

    private void UpdateDeleteEnabled() => delete.IsEnabled = !busy && !string.IsNullOrWhiteSpace(term.Text);

    private async Task RunAsync(Func<Task> action)
    {
        if (busy) return;
        busy = true;
        save.IsEnabled = newEntry.IsEnabled = delete.IsEnabled = entries.IsEnabled = export.IsEnabled = import.IsEnabled = false;
        term.IsEnabled = aliases.IsEnabled = related.IsEnabled = false;
        var busyText = AppText.L("処理しています…", "Processing...");
        status.Text = busyText;
        try
        {
            await action();
            if(status.Text == busyText)status.Text = AppText.L($"{loaded.Count:N0}件の登録があります。", $"{loaded.Count:N0} registered entry(ies).");
        }
        catch (Exception ex) { status.Text = ex.Message; }
        finally
        {
            busy = false;
            save.IsEnabled = newEntry.IsEnabled = entries.IsEnabled = export.IsEnabled = import.IsEnabled = true;
            term.IsEnabled = aliases.IsEnabled = related.IsEnabled = true;
            UpdateDeleteEnabled();
        }
    }

    private async Task RefreshAsync(string? select)
    {
        loaded = RelatedTerms.ParseList(await api.GetAsync("api/library/terms"));
        entries.Items.Clear();
        foreach (var entry in loaded.Take(ShownEntries))
            entries.Items.Add(new ComboBoxItem { Content = entry.Summary, Tag = entry });
        var index = select is null ? -1 : loaded.Take(ShownEntries).ToList().FindIndex(entry => entry.Term == select);
        entries.SelectedIndex = index;
        entries.PlaceholderText = loaded.Count == 0 ? AppText.L("まだ登録はありません", "No entries yet") : loaded.Count > ShownEntries ? AppText.L($"{loaded.Count:N0}件中、先頭{ShownEntries}件を表示", $"Showing first {ShownEntries} of {loaded.Count:N0}") : AppText.L($"{loaded.Count:N0}件", $"{loaded.Count:N0} entry(ies)");
    }
}
