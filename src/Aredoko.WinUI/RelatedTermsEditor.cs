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
    private readonly TextBox term = new() { Header = "作品名・タグにある言葉", PlaceholderText = "例: 博麗霊夢", MaxLength = RelatedTerms.MaxWordChars };
    private readonly TextBox aliases = new() { Header = "別の呼び名（、区切り）", PlaceholderText = "例: 霊夢、reimu" };
    private readonly TextBox related = new() { Header = "探すときに思い浮かぶ言葉（、区切り）", PlaceholderText = "例: 東方、巫女" };
    private readonly Button save = new() { Content = "保存" };
    private readonly Button delete = new() { Content = "削除" };
    private readonly Button export = new() { Content = "書き出し…" };
    private readonly Button import = new() { Content = "読み込み…" };
    private readonly ComboBox entries = new() { Header = "登録済みの語", HorizontalAlignment = HorizontalAlignment.Stretch };
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
        AutomationProperties.SetAutomationId(delete, "DeleteRelatedTerm");
        AutomationProperties.SetAutomationId(entries, "RelatedTermList");
        AutomationProperties.SetAutomationId(export, "ExportRelatedTerms");
        AutomationProperties.SetAutomationId(import, "ImportRelatedTerms");
        AutomationProperties.SetAutomationId(status, "RelatedTermStatus");
        AutomationProperties.SetLiveSetting(status, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        var help = new TextBlock { TextWrapping = TextWrapping.Wrap, Text = "言い換えを登録すると検索で一緒に探します（例：巫女 → 霊夢）" };
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Children = { save, delete } };
        var files = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Children = { export, import } };
        foreach (var element in new UIElement[] { help, entries, term, aliases, related, actions, files, status }) panel.Children.Add(element);
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
            status.Text = $"{RelatedTerms.CountExport(document):N0}件を書き出しました。";
        });
        import.Click += async (_, _) => await RunAsync(async () =>
        {
            var picker = new Windows.Storage.Pickers.FileOpenPicker();
            picker.FileTypeFilter.Add(".json");
            WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(MainWindow.Current));
            var file = await picker.PickSingleFileAsync();
            if (file is null) return;
            if ((await file.GetBasicPropertiesAsync()).Size > (ulong)RelatedTerms.MaxImportBytes) { status.Text = "ファイルが大きすぎます（16MiBまで）。"; return; }
            var text = await Windows.Storage.FileIO.ReadTextAsync(file, Windows.Storage.Streams.UnicodeEncoding.Utf8);
            var error = RelatedTerms.CheckImport(text);
            if (error is not null) { status.Text = error; return; }
            var result = await api.ImportRelatedTermsAsync(text);
            await RefreshAsync(null);
            status.Text = RelatedTerms.DescribeImport(result) + "同じ見出し語は置き換え、他の登録は残します。";
        });
        entries.SelectionChanged += (_, _) =>
        {
            if (entries.SelectedItem is ComboBoxItem { Tag: RelatedTermEntry entry })
            {
                term.Text = entry.Term; aliases.Text = string.Join("、", entry.Aliases); related.Text = string.Join("、", entry.Related);
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
            status.Text = "✓ 保存しました";
        });
        delete.Click += async (_, _) => await RunAsync(async () =>
        {
            if (term.Text.Trim().Length == 0) { status.Text = "削除する見出し語を選んでください。"; return; }
            await api.PostAsync("api/library/terms/delete", RelatedTerms.Delete(term.Text));
            term.Text = aliases.Text = related.Text = "";
            await RefreshAsync(null);
            status.Text = "削除しました。";
        });
    }

    public UIElement Content => panel;
    public bool IsBusy => busy;

    public Task LoadAsync() => RunAsync(() => RefreshAsync(null));

    private async Task RunAsync(Func<Task> action)
    {
        if (busy) return;
        busy = true;
        save.IsEnabled = delete.IsEnabled = entries.IsEnabled = export.IsEnabled = import.IsEnabled = false;
        term.IsEnabled = aliases.IsEnabled = related.IsEnabled = false;
        status.Text = "処理しています…";
        try
        {
            await action();
            if(status.Text == "処理しています…")status.Text = $"{loaded.Count:N0}件の登録があります。";
        }
        catch (Exception ex) { status.Text = ex.Message; }
        finally
        {
            busy = false;
            save.IsEnabled = delete.IsEnabled = entries.IsEnabled = export.IsEnabled = import.IsEnabled = true;
            term.IsEnabled = aliases.IsEnabled = related.IsEnabled = true;
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
        entries.PlaceholderText = loaded.Count == 0 ? "まだ登録はありません" : loaded.Count > ShownEntries ? $"{loaded.Count:N0}件中、先頭{ShownEntries}件を表示" : $"{loaded.Count:N0}件";
    }
}
