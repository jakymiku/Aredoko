using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Net.Http;
using System.Text.Json;
namespace Aredoko_WinUI;
public sealed partial class MainPage : Page
{
    public MainPage() { InitializeComponent(); }
    private async void Page_Loaded(object sender, RoutedEventArgs e) => await ConnectAsync();
    private async void Retry_Click(object sender, RoutedEventArgs e) => await ConnectAsync();
    private async Task ConnectAsync() {
        try {
            using var api = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            using var json = JsonDocument.Parse(await api.GetStringAsync("http://127.0.0.1:8769/api/session"));
            Connection.Title = "API接続済み";
            Connection.Message = "起動骨格。ライブラリ統合は次の段階です。";
            Connection.Severity = InfoBarSeverity.Success;
        } catch (Exception ex) {
            Connection.Title = "バックエンドを起動してください";
            Connection.Message = ex.Message;
            Connection.Severity = InfoBarSeverity.Warning;
        }
    }
}
