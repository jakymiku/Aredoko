using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private void UpdateGettingStarted()
    {
        var show=knownRoots.Count==0&&rows.Count==0&&view=="all"&&string.IsNullOrWhiteSpace(Query.Text)
            &&selectedSearchRoots is null&&selectedShelfIds is null&&similarityOrigin is null;
        GettingStarted.Visibility=show?Visibility.Visible:Visibility.Collapsed;
        if(show)Empty.Visibility=Visibility.Collapsed;
    }
    private async void GettingStartedFolders_Click(object sender,RoutedEventArgs args)
    {
        await OpenFolderHubAsync();
        if(folderHubOpen)FolderAddPanel.Visibility=Visibility.Visible;
    }
    private async void GettingStartedHelp_Click(object sender,RoutedEventArgs args)=>await OpenGettingStartedGuideAsync();
    private async Task OpenGettingStartedGuideAsync()
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;
        try
        {
            var panel=new StackPanel{Spacing=16};
            foreach(var (title,text) in new[]{
                ("1. フォルダを登録する","「登録フォルダ」→「フォルダを追加」から検索したい場所を選びます。サブフォルダを含めるかも選べます。登録後、詳細パネルの「選択フォルダをスキャン / 再開」を押すと一覧に読み込みます。元ファイルは移動・変換しません。"),
                ("2. 検索して開く","検索欄にファイル名やタグを入力します。画像・本・動画はダブルクリックで開けます。右クリックから既定のソフトやエクスプローラーでも開けます。"),
                ("3. AI検索を準備する（任意）","設定の「AI検索の準備」→「モデルをダウンロード」で容量とライセンスを確認して取得します。EmbeddingGemma 2は画像・文章の検索、WD Taggerは画像のタグ候補用です。モデルだけでは動かず対応する実行環境も必要です。実行環境の自動取得は準備中のため、現在は「配置済みを指定」で設定します。設定後は再起動し、AI索引の対象を確認して「索引を作成・更新」を実行します。"),
                ("4. 内容から探す・整理する","準備後は「画像の見た目」などのAI検索方法で、覚えている情景や特徴を入力します。右側の詳細でタグや棚を編集できます。タグ・棚は保存ボタンで保存し、お気に入りはすぐ反映します。AIタグは候補を確認してから承認します。"),
                ("閲覧・データ保護","画像や本は左右キー・ホイール・マウスの進む／戻るで送れます。ホイール方向、テーマ、小さい画像の拡大は設定で変更できます。バックアップと復元も設定から実行できます。フォルダ解除や棚の削除で元メディアは削除しません。"),
            })
            {
                panel.Children.Add(new TextBlock{Text=title,Style=(Style)Application.Current.Resources["SubtitleTextBlockStyle"],TextWrapping=TextWrapping.Wrap});
                panel.Children.Add(new TextBlock{Text=text,TextWrapping=TextWrapping.Wrap,IsTextSelectionEnabled=true});
            }
            var scroll=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled,Padding=new Thickness(0,0,16,0)};
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="使い方・初回設定",Content=scroll,CloseButtonText="閉じる"};
            AutomationProperties.SetAutomationId(dialog,"GettingStartedGuide");
            await dialog.ShowAsync();
        }
        catch(Exception error){Failure(error);}
        finally{dialogOpen=false;transitions.Release();}
    }
}
