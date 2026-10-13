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
    private readonly TextBox term = new() { Header = "見出し語（ファイルやタグにある名前）", PlaceholderText = "例: 博麗霊夢", MaxLength = RelatedTerms.MaxWordChars };
    private readonly TextBox aliases = new() { Header = "別名・表記ゆれ（、区切り）", PlaceholderText = "例: 霊夢、reimu" };
    private readonly TextBox related = new() { Header = "思い出す手がかりの語（、区切り）", PlaceholderText = "例: 東方、巫女" };
    private readonly Button save = new() { Content = "保存" };
    private readonly Button delete = new() { Content = "この見出し語を削除" };
    private readonly ComboBox entries = new() { Header = "登録済み（選ぶと編集できます）", HorizontalAlignment = HorizontalAlignment.Stretch };
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
        AutomationProperties.SetAutomationId(status, "RelatedTermStatus");
        AutomationProperties.SetLiveSetting(status, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        var help = new TextBlock { TextWrapping = TextWrapping.Wrap, Text = "名前・タグ検索で、手がかりの語から見出し語と別名も候補に含めます。例:「東方 巫女」で博麗霊夢のタグやファイル名の作品も表示します。入力した語に一致する作品が先に並びます。" };
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Children = { save, delete } };
        foreach (var element in new UIElement[] { help, entries, term, aliases, related, actions, status }) panel.Children.Add(element);
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
            status.Text = "保存しました。次の名前・タグ検索から使われます。";
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

    public Task LoadAsync() => RunAsync(() => RefreshAsync(null));

    private async Task RunAsync(Func<Task> action)
    {
        if (busy) return;
        busy = true; save.IsEnabled = delete.IsEnabled = entries.IsEnabled = false;
        try { await action(); }
        catch (Exception ex) { status.Text = ex.Message; }
        finally { busy = false; save.IsEnabled = delete.IsEnabled = entries.IsEnabled = true; }
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
