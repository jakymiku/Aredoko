using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

// A single, modal, read-only page. No file paths, prefetch or persistent cache.
internal sealed class ArchiveReaderView : Grid, IDisposable
{
    private readonly LibraryApi api;
    private readonly int itemId;
    private readonly CancellationTokenSource lifetime = new();
    private readonly CancellationToken cancellation;
    private readonly Image image = new() { Stretch = Stretch.Uniform };
    private readonly ScrollViewer viewport = new()
    {
        ZoomMode = ZoomMode.Enabled, MinZoomFactor = 1, MaxZoomFactor = 4,
        HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    };
    private readonly Button previous = new() { Content = "前へ" };
    private readonly Button next = new() { Content = "次へ" };
    private readonly Button retry = new() { Content = "再試行" };
    private readonly Button reopen = new() { Content = "最初から開き直す" };
    private readonly TextBlock count = new() { Text = "—", VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
    private readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap };
    private ArchiveManifest? manifest;
    private int page;
    private bool busy, disposed, failed;

    public ArchiveReaderView(LibraryApi api, int itemId)
    {
        this.api = api; this.itemId = itemId; cancellation = lifetime.Token;
        RowSpacing = 12;
        for (var i = 0; i < 4; i++) RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        viewport.Content = image;
        viewport.SizeChanged += (_, _) =>
        {
            image.Width = Math.Max(1, viewport.ActualWidth);
            image.Height = Math.Max(1, viewport.ActualHeight);
        };
        Children.Add(viewport);
        var navigation = new Grid { ColumnSpacing = 12 };
        navigation.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        navigation.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        navigation.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        navigation.Children.Add(previous); navigation.Children.Add(count); navigation.Children.Add(next);
        SetColumn(count, 1); SetColumn(next, 2); SetRow(navigation, 1); Children.Add(navigation);
        SetRow(status, 2); Children.Add(status);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        actions.Children.Add(retry); actions.Children.Add(reopen);
        SetRow(actions, 3); Children.Add(actions);
        Identify(viewport, "ReaderViewport", "ページ表示。拡大してスクロールできます");
        Identify(image, "ReaderImage", "本のページ");
        Identify(previous, "ReaderPrevious", "前のページ");
        Identify(next, "ReaderNext", "次のページ");
        // TextBlock exposes its current text as the accessible name. A fixed
        // Name here would hide updated page numbers and live error feedback.
        AutomationProperties.SetAutomationId(count, "ReaderPageNumber");
        AutomationProperties.SetAutomationId(status, "ReaderStatus");
        Identify(retry, "ReaderRetry", "現在のページを再試行");
        Identify(reopen, "ReaderReopen", "本を最初から開き直す");
        AutomationProperties.SetLiveSetting(status, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        previous.Click += async (_, _) => await LoadAsync(page - 1);
        next.Click += async (_, _) => await LoadAsync(page + 1);
        retry.Click += async (_, _) => { if (manifest is null) await OpenAsync(); else await LoadAsync(page); };
        reopen.Click += async (_, _) => await OpenAsync();
        UpdateActions();
    }

    private static void Identify(DependencyObject control, string id, string name)
    {
        AutomationProperties.SetAutomationId(control, id); AutomationProperties.SetName(control, name);
    }

    public void FitViewport(Windows.Foundation.Size size)
    {
        Width = Math.Clamp(size.Width - 120, 240, 840);
        viewport.Height = Math.Clamp(size.Height - 320, 100, 640);
    }

    public async Task OpenAsync()
    {
        if (busy || disposed) return;
        busy = true; failed = false; manifest = null; page = 0;
        image.Source = null; count.Text = "—"; status.Text = "本を開いています…"; UpdateActions();
        try
        {
            var result = await api.ReaderManifestAsync(itemId, cancellation);
            cancellation.ThrowIfCancellationRequested(); manifest = result;
        }
        catch (Exception ex) { ReportFailure(ex); }
        finally { busy = false; if (!disposed) UpdateActions(); }
        if (manifest is not null && !disposed) await LoadAsync(0);
    }

    private async Task LoadAsync(int requestedPage)
    {
        var book = manifest;
        if (busy || disposed || book is null || requestedPage < 0 || requestedPage >= book.PageCount) return;
        busy = true; failed = false; page = requestedPage; image.Source = null;
        viewport.ChangeView(0, 0, 1, true);
        count.Text = $"{page + 1} / {book.PageCount}";
        status.Text = "ページを読み込んでいます…"; UpdateActions();
        try
        {
            var source = await api.ReaderPageAsync(book, requestedPage, cancellation);
            var png = await ThumbnailCodec.ResizeAsync(source, cancellation, PreviewPolicy.ReaderEdge);
            using var stream = new InMemoryRandomAccessStream();
            using (var writer = new DataWriter(stream))
            {
                writer.WriteBytes(png); await writer.StoreAsync(); writer.DetachStream();
            }
            stream.Seek(0);
            var bitmap = new BitmapImage(); await bitmap.SetSourceAsync(stream);
            cancellation.ThrowIfCancellationRequested();
            if (disposed || manifest != book || page != requestedPage) return;
            image.Source = bitmap;
            AutomationProperties.SetName(image, $"{page + 1}ページ");
            status.Text = "表示しました。拡大すると細部を確認できます。";
        }
        catch (Exception ex) { ReportFailure(ex); }
        finally { busy = false; if (!disposed) UpdateActions(); }
    }

    private void ReportFailure(Exception ex)
    {
        if (disposed || cancellation.IsCancellationRequested) return;
        image.Source = null; failed = true;
        if (ex is ArchiveReadException { RequiresReopen: true })
        {
            manifest = null; count.Text = "—";
        }
        status.Text = ex switch
        {
            ArchiveReadException => ex.Message,
            OperationCanceledException => "読み込みがタイムアウトしました。再試行してください。",
            HttpRequestException => "接続できません。閉じてライブラリから再接続してください。",
            _ => "このページを表示できません。未対応形式・破損・画像サイズを確認してください。"
        };
        // Do not log source filenames or response bytes.
    }

    private void UpdateActions()
    {
        previous.IsEnabled = !busy && manifest is not null && page > 0;
        next.IsEnabled = !busy && manifest is not null && page + 1 < manifest.PageCount;
        retry.IsEnabled = !busy && failed;
        reopen.IsEnabled = !busy;
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true; lifetime.Cancel(); image.Source = null; manifest = null;
        lifetime.Dispose();
    }
}
