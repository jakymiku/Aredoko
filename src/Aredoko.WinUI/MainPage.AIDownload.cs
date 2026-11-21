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
            var panel=new StackPanel{Spacing=12};
            var choice=new ComboBox{Header="取得するAI環境",HorizontalAlignment=HorizontalAlignment.Stretch};
            var information=new TextBlock{Text="取得できる環境を確認しています。",TextWrapping=TextWrapping.Wrap};
            var license=new HyperlinkButton{Content="ライセンスを確認",Visibility=Visibility.Collapsed};
            var speed=new NumberBox{Header="速度上限（MB/秒、0で無制限）",Value=0,Minimum=0,Maximum=1000000,SmallChange=1};
            var consent=new CheckBox{Content="容量とライセンスを確認し、選択したファイルを取得する"};
            var status=new TextBlock{TextWrapping=TextWrapping.Wrap};var progress=new ProgressBar{Minimum=0,Maximum=100,Visibility=Visibility.Collapsed};
            var destination=new TextBox{Header="取得した環境",IsReadOnly=true,TextWrapping=TextWrapping.Wrap,Visibility=Visibility.Collapsed};
            var select=new Button{Content="配置済みの環境を指定",Visibility=Visibility.Collapsed};var refresh=new Button{Content="状態を更新"};
            foreach(var (control,id) in new (DependencyObject,string)[]{(choice,"AIDownloadCatalog"),(information,"AIDownloadInformation"),(license,"AIDownloadLicense"),(speed,"AIDownloadSpeed"),(consent,"AIDownloadConsent"),(status,"AIDownloadStatus"),(progress,"AIDownloadProgress"),(destination,"AIDownloadDestination"),(select,"AIDownloadSelect"),(refresh,"AIDownloadRefresh")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(progress,"AI環境の取得進捗");
            var downloadSettings=new Expander{Header="速度制限（既定は制限なし）",Content=speed,HorizontalAlignment=HorizontalAlignment.Stretch};
            AutomationProperties.SetAutomationId(downloadSettings,"AIDownloadSettings");
            var introduction=new TextBlock{Text="取得後に使う環境を指定し、再起動して反映します",TextWrapping=TextWrapping.Wrap};
            ToolTipService.SetToolTip(introduction,"AI検索には検索モデルと実行環境が必要です。画像タグ付けモデルは追加機能です。");
            AutomationProperties.SetAutomationId(introduction,"AIDownloadIntroduction");panel.Children.Add(introduction);
            foreach(var control in new UIElement[]{choice,information,license,consent,downloadSettings,progress,status,destination,select,refresh})panel.Children.Add(control);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AI環境の取得",PrimaryButtonText="取得・再開",IsPrimaryButtonEnabled=false,SecondaryButtonText="中止",IsSecondaryButtonEnabled=false,CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,
                Content=new ScrollViewer{Content=FormScrollContent.Wrap(panel),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled}};
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
                status.Text=current?.State is null or "idle"?"取得する環境を選んでください。":current.Message;
                if(current is {State:not "idle"} job)status.Text+=$"\n取得 {job.BytesReceived/1000000d:N1} MB / "+(job.BytesTotal is {} total?$"{total/1000000d:N1} MB":"確認中")+$"　検証済み {job.BytesVerified/1000000d:N1} MB";
                if(operationError is not null)status.Text+="\n"+operationError;
                destination.Text=current?.Root??"";destination.Visibility=current?.Published==true&&current.Root is not null?Visibility.Visible:Visibility.Collapsed;
                var candidate=AIDownloadSelection.FromPublished(current,knownCatalogs);
                select.Visibility=candidate is not null?Visibility.Visible:Visibility.Collapsed;select.IsEnabled=!busy;
                select.Content=candidate?.Kind=="runtime"?"この実行環境を設定する":"このモデルの保存先を設定する";
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
                    var scope=selected.Kind=="model"?"モデルのみ（実行環境が別途必要）\n":"";
                    var capacity=selected.UnpackedBytes is {} expanded?$"サイズ：{selected.Bytes/1000000d:N1} MB ／ 展開後：{expanded/1000000d:N1} MB（{selected.UnpackedFiles:N0}件）\n⚠ 必要な空き：{(selected.Bytes+expanded)/1000000d:N1} MB以上":$"容量：{selected.Bytes/1000000d:N1} MB";
                    information.Text=scope+capacity+$"\n提供元：{string.Join(", ",selected.SourceHosts)}\nライセンス：{selected.License}\n版：{selected.Revision}";
                    license.NavigateUri=selected.LicenseUri;license.Visibility=Visibility.Visible;
                }
                else license.Visibility=Visibility.Collapsed;
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
