using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private static string DownloadCatalogLabel(AIDownloadCatalog item)=>item.Kind=="runtime"
        ?item.Name+"（実行環境）"
        :item.ModelTarget?.Role switch
        {
            "tagger"=>"画像タグ付けモデル（"+item.Name+"）",
            "embedding"=>"内容検索モデル（"+item.Name+"）",
            _=>item.Name+"（モデル）"
        };

    private async Task OpenAIDownloadDialogAsync(string? preferRole = null)
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        bool open=true,busy=false;AIDownloadSelection? applySelection=null;IReadOnlyList<AIDownloadCatalog> knownCatalogs=Array.Empty<AIDownloadCatalog>();long revision=0;AIDownloadJob? current=null;Task? polling=null;string? operationError=null;
        using var lifetime=new CancellationTokenSource();var timer=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(700)};
        try
        {
            dialogOpen=true;
            var panel=new StackPanel{Spacing=12,MaxWidth=540};
            var choice=new ComboBox{Header="取得するモデル・環境",HorizontalAlignment=HorizontalAlignment.Stretch};
            var information=new TextBlock{Text="取得できる環境を確認しています。",TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            var license=new HyperlinkButton{Content="ライセンスを確認",Visibility=Visibility.Collapsed,Padding=new Thickness(0,2,0,2)};
            var speed=new NumberBox{Header="速度上限（MB/秒、0で無制限）",Value=0,Minimum=0,Maximum=1000000,SmallChange=1};
            var consent=new CheckBox{Content="容量とライセンスを確認し、選択したファイルを取得する"};
            var status=new TextBlock{TextWrapping=TextWrapping.Wrap};var progress=new ProgressBar{Minimum=0,Maximum=100,Visibility=Visibility.Collapsed};
            var destination=new TextBox{Header="保存先フォルダ",IsReadOnly=true,TextWrapping=TextWrapping.Wrap,Visibility=Visibility.Collapsed};
            var select=new Button{Content="配置済みの環境を指定",Visibility=Visibility.Collapsed};var refresh=new Button{Content="⟳ 状態を更新"};
            foreach(var (control,id) in new (DependencyObject,string)[]{(choice,"AIDownloadCatalog"),(information,"AIDownloadInformation"),(license,"AIDownloadLicense"),(speed,"AIDownloadSpeed"),(consent,"AIDownloadConsent"),(status,"AIDownloadStatus"),(progress,"AIDownloadProgress"),(destination,"AIDownloadDestination"),(select,"AIDownloadSelect"),(refresh,"AIDownloadRefresh")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(progress,"AI環境の取得進捗");
            var downloadSettings=new Expander{Header="速度制限（既定は制限なし）",Content=speed,HorizontalAlignment=Microsoft.UI.Xaml.HorizontalAlignment.Stretch,HorizontalContentAlignment=Microsoft.UI.Xaml.HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(downloadSettings,"AIDownloadSettings");
            var introduction=new TextBlock{Text="取得したいモデルを選んでダウンロードします（追加機能は後からでも設定できます）。",TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            ToolTipService.SetToolTip(introduction,"AI検索には検索モデルと実行環境が必要です。画像タグ付けモデルは追加機能です。");
            AutomationProperties.SetName(introduction,"AI検索には検索モデルと実行環境が必要です。画像タグ付けモデルは追加機能です。");
            AutomationProperties.SetAutomationId(introduction,"AIDownloadIntroduction");panel.Children.Add(introduction);

            var infoBox=new Border{Background=(Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources["SubtleFillColorSecondaryBrush"],CornerRadius=new CornerRadius(6),Padding=new Thickness(10,8,10,8),Child=new StackPanel{Spacing=4,Children={information,license}}};
            var card1=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=new StackPanel{Spacing=10,Children={choice,infoBox,consent}}};
            panel.Children.Add(card1);

            var downloadArt=VisualAssets.Sticker(64);
            var statusHeader=new Grid{ColumnSpacing=12};
            statusHeader.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            statusHeader.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            var statusStack=new StackPanel{Spacing=6,VerticalAlignment=VerticalAlignment.Center,Children={progress,status}};
            Grid.SetColumn(statusStack,1);
            statusHeader.Children.Add(downloadArt);statusHeader.Children.Add(statusStack);
            var actionRow=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8,Children={select,refresh}};
            var card2=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=new StackPanel{Spacing=8,Children={statusHeader,destination,actionRow}}};
            panel.Children.Add(card2);
            panel.Children.Add(downloadSettings);

            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AI環境の取得",PrimaryButtonText="取得・再開",IsPrimaryButtonEnabled=false,SecondaryButtonText="中止",IsSecondaryButtonEnabled=false,CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,
                Content=new ScrollViewer{Content=FormScrollContent.Wrap(panel),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled}};
            dialog.Resources["ContentDialogMaxWidth"]=580d;
            AutomationProperties.SetAutomationId(dialog,"AIDownloadDialog");
            AIDownloadCatalog? Selected()=>(choice.SelectedItem as ComboBoxItem)?.Tag as AIDownloadCatalog;
            void Render()
            {
                if(!open||disposed)return;
                var active=busy||current?.Active==true;choice.IsEnabled=!active;speed.IsEnabled=!active;consent.IsEnabled=!active;
                dialog.IsPrimaryButtonEnabled=!active&&Selected() is {} selectedCatalog&&consent.IsChecked==true&&!(current?.Published==true&&current.CatalogId==selectedCatalog.Id);
                dialog.IsSecondaryButtonEnabled=!busy&&current?.Active==true&&current.State is not ("publishing" or "cancelling");
                progress.Visibility=current?.Active==true||current?.Published==true?Visibility.Visible:Visibility.Collapsed;
                progress.IsIndeterminate=current?.State=="extracting"||current?.Active==true&&current.BytesTotal is not >0;
                progress.Value=current?.BytesTotal is >0?Math.Clamp(100d*current.BytesReceived/current.BytesTotal.Value,0,100):current?.Published==true?100:0;
                var candidate=AIDownloadSelection.FromPublished(current,knownCatalogs);
                if(candidate is not null&&current is {State:not "idle"} verifiedJob)
                {
                    status.Text=candidate.ModelTarget?.Role=="tagger"
                        ?$"✓ 準備完了（{verifiedJob.BytesVerified/1000000d:N1} MB 検証済み）\nこのまま閉じて、作品詳細の「✨ AI候補」からすぐ使えます。"
                        :$"✓ ダウンロード完了（{verifiedJob.BytesVerified/1000000d:N1} MB 検証済み）\n下の青いボタンから設定を保存し、Aredoko を再起動すると反映されます。";
                }
                else
                {
                    status.Text=current?.State is null or "idle"?"取得するモデルを選んでください。":current.Message;
                    if(current is {State:not "idle"} job)status.Text+=$"\n取得 {job.BytesReceived/1000000d:N1} MB / "+(job.BytesTotal is {} total?$"{total/1000000d:N1} MB":"確認中")+$"（検証済み {job.BytesVerified/1000000d:N1} MB）";
                }
                if(operationError is not null)status.Text+="\n"+operationError;
                VisualAssets.State(downloadArt,active?"indexing":current?.Published==true?"completed":(current?.State=="failed"||operationError is not null)?"error":null);
                destination.Text=current?.Root??"";destination.Visibility=current?.Published==true&&current.Root is not null?Visibility.Visible:Visibility.Collapsed;
                select.Visibility=candidate is not null?Visibility.Visible:Visibility.Collapsed;select.IsEnabled=!busy;
                var needsExplicitActivation=candidate is not null&&candidate.ModelTarget?.Role!="tagger";
                select.Style=needsExplicitActivation&&!busy?(Style)Application.Current.Resources["AccentButtonStyle"]:Application.Current.Resources["DefaultButtonStyle"] as Style;
                select.Content=candidate?.Kind=="runtime"?"この実行環境を有効化する →":candidate?.ModelTarget?.Role=="tagger"?"保存先を明示設定…":"このモデルを有効化する →";
            }
            async Task RefreshAsync(bool catalogs=false)
            {
                var requested=revision;
                try
                {
                    var items=catalogs?await api.AIDownloads.CatalogsAsync(lifetime.Token):null;
                    var job=await api.AIDownloads.JobAsync(lifetime.Token);
                    if(!open||disposed||busy||requested!=revision)return;
                    if(items is not null)
                    {
                        var selected=Selected()?.Id;knownCatalogs=items;choice.Items.Clear();
                        foreach(var item in items)choice.Items.Add(new ComboBoxItem{Content=DownloadCatalogLabel(item),Tag=item});
                        var preferredIndex=(!job.Active&&selected is null&&!string.IsNullOrEmpty(preferRole))?items.ToList().FindIndex(item=>item.ModelTarget?.Role==preferRole):-1;
                        var index=preferredIndex>=0?preferredIndex:items.ToList().FindIndex(item=>item.Id==(job.Active?job.CatalogId:selected??job.CatalogId));choice.SelectedIndex=index>=0?index:items.Count>0?0:-1;
                        if(items.Count==0)information.Text="ダウンロードできるモデルはありません（「自動セットアップ」または「手元のファイルを使う」を利用できます）";
                    }
                    current=job;operationError=null;Render();
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){if(open&&!disposed){operationError="状態を確認できません。「状態を更新」で確認してください。\n"+ex.Message;Render();}}
            }
            choice.SelectionChanged+=(_,_)=>
            {
                consent.IsChecked=false;
                if(Selected() is {} selected)
                {
                    var note=selected.Kind=="model"
                        ?(selected.ModelTarget?.Role=="tagger"?" · 同梱ランタイムで動作（追加の実行環境は不要）":" · AI検索用の実行環境と組み合わせて使います")
                        :"";
                    var capacity=selected.UnpackedBytes is {} expanded
                        ?$"容量：{selected.Bytes/1000000d:N1} MB ／ 展開後：{expanded/1000000d:N1} MB（{selected.UnpackedFiles:N0}件）· 必要な空き：{(selected.Bytes+expanded)/1000000d:N1} MB以上"
                        :$"容量：{selected.Bytes/1000000d:N1} MB{note}";
                    information.Text=capacity+$"\nライセンス：{selected.License} · 提供元：{string.Join(", ",selected.SourceHosts)}";
                    ToolTipService.SetToolTip(information,$"版（Revision）: {selected.Revision}");
                    license.NavigateUri=selected.LicenseUri;license.Visibility=Visibility.Visible;
                }
                else
                {
                    ToolTipService.SetToolTip(information,null);
                    license.Visibility=Visibility.Collapsed;
                }
                Render();
            };
            consent.Checked+=(_,_)=>Render();consent.Unchecked+=(_,_)=>Render();
            refresh.Click+=async(_,_)=>{if(!busy&&(polling is null||polling.IsCompleted)){polling=RefreshAsync(true);await polling;}};
            dialog.PrimaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy||current?.Active==true||Selected() is not {} selected||consent.IsChecked!=true)return;
                var deferral=args.GetDeferral();busy=true;operationError=null;++revision;Render();
                try
                {
                    if(!double.IsFinite(speed.Value)||speed.Value<0||speed.Value>1000000)throw new ArgumentException("速度上限を確認してください。0は無制限です。");
                    long? rate=speed.Value==0?null:checked((long)Math.Round(speed.Value*1000000));
                    current=await api.AIDownloads.StartAsync(selected.Id,rate,lifetime.Token);
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError="開始を確認できません。「状態を更新」で確認してください。\n"+ex.Message;}
                finally{busy=false;deferral.Complete();Render();}
            };
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy||current?.Id is not {} id)return;
                var deferral=args.GetDeferral();busy=true;operationError=null;++revision;Render();
                try{current=await api.AIDownloads.CancelAsync(id,lifetime.Token);}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError="中止を確認できません。「状態を更新」で確認してください。\n"+ex.Message;}
                finally{busy=false;deferral.Complete();Render();}
            };
            select.Click+=(_,_)=>
            {
                if(busy||AIDownloadSelection.FromPublished(current,knownCatalogs) is not {} candidate)return;
                applySelection=candidate;dialog.Hide();
            };
            dialog.Closing+=(_,args)=>{if(busy)args.Cancel=true;};
            timer.Tick+=(_,_)=>{if(!busy&&current?.Active==true&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            dialog.Opened+=(_,_)=>{polling=RefreshAsync(true);timer.Start();};
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(applySelection is not null&&!disposed)await OpenAIEnvironmentDialogAsync(applySelection);
    }
}
