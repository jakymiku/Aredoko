using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AredokoWinUiBench;

public sealed class MediaRow
{
    [JsonPropertyName("id")] public int Id { get; set; }
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";
    [JsonPropertyName("tags")] public string[] Tags { get; set; } = [];
    [JsonPropertyName("shelf")] public string Shelf { get; set; } = "";
    [JsonPropertyName("favorite")] public bool Favorite { get; set; }
    [JsonPropertyName("reviewed")] public bool Reviewed { get; set; }
    public string KindAndTags => $"{Kind} · {string.Join("、", Tags)}";
}

public sealed class SearchResponse
{
    [JsonPropertyName("total")] public int Total { get; set; }
    [JsonPropertyName("items")] public List<MediaRow> Items { get; set; } = [];
}

public sealed class SessionResponse
{
    [JsonPropertyName("token")] public string Token { get; set; } = "";
}

public sealed partial class MainWindow : Window
{
    private const string RootUrl = "http://127.0.0.1:8768/";
    private readonly HttpClient _api = new() { BaseAddress = new Uri(RootUrl) };
    private readonly DispatcherQueueTimer _searchDelay;
    public ObservableCollection<MediaRow> Items { get; } = [];
    private MediaRow? _active;
    private string _token = "";
    private int _page;
    private int _total;
    private int _searchVersion;
    private bool _settingFields;
    private bool _ready;
    private bool _dirty;

    public MainWindow()
    {
        InitializeComponent();
        _searchDelay = DispatcherQueue.CreateTimer();
        _searchDelay.Interval = TimeSpan.FromMilliseconds(220);
        _searchDelay.Tick += async (_, _) => {
            _searchDelay.Stop();
            _page = 0;
            await LoadAsync();
        };
        _ready = true;
        _ = InitializeAsync();
    }

    private async Task InitializeAsync()
    {
        try {
            _token = (await _api.GetFromJsonAsync<SessionResponse>("api/session"))?.Token ?? "";
            await LoadAsync();
        } catch (Exception ex) { TxtStatus.Text = $"起動に失敗: {ex.Message}"; }
    }

    private async Task LoadAsync()
    {
        var requestId = ++_searchVersion;
        var watch = Stopwatch.StartNew();
        TxtStatus.Text = "検索中…";
        var kind = CmbKind.SelectedIndex switch { 1 => "book", 2 => "image", 3 => "video", 4 => "audio", _ => "" };
        var url = $"api/items?q={Uri.EscapeDataString(TxtQuery.Text)}&kind={kind}&page={_page}";
        try {
            var result = await _api.GetFromJsonAsync<SearchResponse>(url) ?? throw new Exception("応答が空です");
            if (requestId != _searchVersion) return;
            _total = result.Total;
            Items.Clear();
            foreach (var item in result.Items) Items.Add(item);
            TxtCount.Text = $"{_total:N0} 件";
            TxtPage.Text = $"{_page + 1} / {Math.Max(1, (_total + 59) / 60)}";
            BtnPrev.IsEnabled = _page > 0;
            BtnNext.IsEnabled = (_page + 1) * 60 < _total;
            TxtStatus.Text = $"読み込み {watch.Elapsed.TotalMilliseconds:F1} ms · 60件ずつ · ListView仮想化";
        } catch (Exception ex) {
            if (requestId == _searchVersion) { Items.Clear(); TxtStatus.Text = $"読み込み失敗: {ex.Message}"; }
        }
    }

    private void Query_Changed(object sender, TextChangedEventArgs args) { if (!_ready) return; _searchDelay.Stop(); _searchDelay.Start(); }
    private async void Kind_Changed(object sender, SelectionChangedEventArgs args) { if (!_ready) return; _page = 0; await LoadAsync(); }
    private async void Prev_Click(object sender, RoutedEventArgs args) { if (_page > 0) { _page--; await LoadAsync(); } }
    private async void Next_Click(object sender, RoutedEventArgs args) { if ((_page + 1) * 60 < _total) { _page++; await LoadAsync(); } }

    private async void ItemList_SelectionChanged(object sender, SelectionChangedEventArgs args)
    {
        if (ItemList.SelectedItem is not MediaRow row) return;
        if (_dirty) { TxtStatus.Text = "未保存の変更があります。保存してから別の項目を選んでください。"; return; }
        try {
            var item = await _api.GetFromJsonAsync<MediaRow>($"api/items/{row.Id}");
            if (item is null) return;
            _settingFields = true;
            _active = item;
            TxtTitle.Text = item.Title;
            TxtTags.Text = string.Join(", ", item.Tags);
            TxtShelf.Text = item.Shelf;
            ChkFavorite.IsChecked = item.Favorite;
            ChkReviewed.IsChecked = item.Reviewed;
            _dirty = false;
            BtnSave.IsEnabled = false;
        } catch (Exception ex) { TxtStatus.Text = $"詳細の取得に失敗: {ex.Message}"; }
        finally { _settingFields = false; }
    }

    private void Editor_Changed(object sender, TextChangedEventArgs args) => MarkDirty();
    private void Editor_Checked(object sender, RoutedEventArgs args) => MarkDirty();
    private void MarkDirty() {
        if (_settingFields || _active is null || BtnSave is null) return;
        _dirty = true;
        BtnSave.IsEnabled = true;
    }

    private async void Save_Click(object sender, RoutedEventArgs args)
    {
        if (!_dirty || _active is null || string.IsNullOrEmpty(_token)) return;
        var tags = TxtTags.Text.Split(new[]{',','、'}, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries).Distinct().ToArray();
        if (tags.Length > 30 || tags.Any(t => t.Length > 60) || TxtShelf.Text.Length > 80) {
            TxtStatus.Text = "タグは30個・各60文字、棚は80文字以内にしてください。"; return;
        }
        BtnSave.IsEnabled = false;
        try {
            var payload = new { ids = new[]{_active.Id}, changes = new {
                tags, shelf = TxtShelf.Text, favorite = ChkFavorite.IsChecked == true,
                reviewed = ChkReviewed.IsChecked == true
            }};
            using var req = new HttpRequestMessage(HttpMethod.Post, "api/items/update");
            req.Headers.TryAddWithoutValidation("Origin", RootUrl.TrimEnd('/'));
            req.Headers.TryAddWithoutValidation("X-Aredoko-Token", _token);
            req.Content = JsonContent.Create(payload);
            using var response = await _api.SendAsync(req);
            response.EnsureSuccessStatusCode();
            _dirty = false;
            TxtStatus.Text = "保存しました";
            await LoadAsync();
        } catch (Exception ex) { TxtStatus.Text = $"保存または再読込に失敗: {ex.Message}"; }
        finally { BtnSave.IsEnabled = _dirty; }
    }
}
