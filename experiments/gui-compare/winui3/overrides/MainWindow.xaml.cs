using System;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Linq;
using System.Text;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AredokoWinUiBench;

public sealed partial class MainWindow : Window
{
    private const string RootUrl = "http://127.0.0.1:8768/";
    private const string BuildTag = "LIST-v4";
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
        // Explicitly wire the data source instead of relying on the Window x:Bind lifecycle.
        // The API returned 50,000 records, but the former compiled binding left the list blank.
        ItemList.ItemsSource = Items;
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
            TxtStatus.Text = $"接続中 [{BuildTag}]";
            // JsonDocument avoids reflection serialization in trimmed/Native AOT WinUI builds.
            _token = BenchJson.ParseSession(await _api.GetStringAsync("api/session")).Token;
            if (string.IsNullOrEmpty(_token)) throw new InvalidOperationException("Session token missing");
            await LoadAsync();
        } catch (Exception ex) {
            TxtStatus.Text = $"起動に失敗 [{BuildTag}]: {ex.GetType().Name}: {ex.Message}";
            Debug.WriteLine(ex);
        }
    }

    private async Task LoadAsync()
    {
        var requestId = ++_searchVersion;
        var watch = Stopwatch.StartNew();
        TxtStatus.Text = "検索中…";
        var kind = CmbKind.SelectedIndex switch { 1 => "book", 2 => "image", 3 => "video", 4 => "audio", _ => "" };
        var url = $"api/items?q={Uri.EscapeDataString(TxtQuery.Text)}&kind={kind}&page={_page}";
        try {
            var result = BenchJson.ParseSearch(await _api.GetStringAsync(url));
            if (requestId != _searchVersion) return;
            _total = result.Total;
            Items.Clear();
            foreach (var item in result.Items) Items.Add(item);
            TxtCount.Text = $"{_total:N0} 件";
            TxtPage.Text = $"{_page + 1} / {Math.Max(1, (_total + 59) / 60)}";
            BtnPrev.IsEnabled = _page > 0;
            BtnNext.IsEnabled = (_page + 1) * 60 < _total;
            var fetched = result.Items.Count;
            var fetchMs = watch.Elapsed.TotalMilliseconds;
            TxtStatus.Text = $"読込 {fetchMs:F1}ms · API {fetched}件 / ListView {ItemList.Items.Count}件 [{BuildTag}]";
            // Diagnostics after layout: distinguishes an empty source from an unrealized template.
            DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Low, () => {
                if (requestId != _searchVersion) return;
                var realized = fetched == 0 ? "empty" :
                    ItemList.ContainerFromIndex(0) is null ? "not-realized" : "realized";
                TxtStatus.Text = $"読込 {fetchMs:F1}ms · API {fetched} / ListView {ItemList.Items.Count} · 高さ {ItemList.ActualHeight:F0} · {realized} [{BuildTag}]";
            });
        } catch (Exception ex) {
            if (requestId == _searchVersion) { Items.Clear(); TxtStatus.Text = $"読み込み失敗 [{BuildTag}]: {ex.GetType().Name}: {ex.Message}"; Debug.WriteLine(ex); }
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
            var item = BenchJson.ParseItem(await _api.GetStringAsync($"api/items/{row.Id}"));
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
            var body = BenchJson.CreateUpdate(_active.Id, tags, TxtShelf.Text,
                ChkFavorite.IsChecked == true, ChkReviewed.IsChecked == true);
            using var req = new HttpRequestMessage(HttpMethod.Post, "api/items/update");
            req.Headers.TryAddWithoutValidation("Origin", RootUrl.TrimEnd('/'));
            req.Headers.TryAddWithoutValidation("X-Aredoko-Token", _token);
            req.Content = new StringContent(body, Encoding.UTF8, "application/json");
            using var response = await _api.SendAsync(req);
            response.EnsureSuccessStatusCode();
            _dirty = false;
            TxtStatus.Text = "保存しました";
            await LoadAsync();
        } catch (Exception ex) { TxtStatus.Text = $"保存または再読込に失敗: {ex.Message}"; }
        finally { BtnSave.IsEnabled = _dirty; }
    }
}
