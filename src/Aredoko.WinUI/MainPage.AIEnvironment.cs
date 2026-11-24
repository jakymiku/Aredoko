using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Windows.Storage.Pickers;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task OpenAIEnvironmentDialogAsync(AIDownloadSelection? acquired=null)
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        bool open=true,busy=false,openDownload=false;long revision=0;AIEnvironmentJob? current=null;Task? polling=null;string? operationError=null;string? savedJob=null;string? acquiredJob=null;AIEnvironmentStatus? locations=null;
        using var lifetime=new CancellationTokenSource();
        var timer=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(700)};
        try
        {
            dialogOpen=true;
            var panel=new StackPanel{Spacing=12};
            var modelScope=new ComboBox{Header="保存先を変える範囲",HorizontalAlignment=HorizontalAlignment.Stretch};
            foreach(var (label,role) in new (string,string?)[]{("すべてのモデル（共通）",null),("用途別：内容検索（文章・画像・動画・音声）","embedding"),("用途別：画像のタグ付け（WD Tagger）","tagger"),("用途別：検索意図の解析","intent")})
                modelScope.Items.Add(new ComboBoxItem{Content=label,Tag=role});
            var modelTargets=new Dictionary<string,AIModelTarget>();
            void AddModel(AIModelTarget target)
            {
                var key="model:"+modelTargets.Count;modelTargets.Add(key,target);
                // Only strings cross ComboBoxItem.Tag's WinRT ABI. Keep Core
                // records managed, including in trimmed Portable publication.
                modelScope.Items.Add(new ComboBoxItem{Content=$"{ModelLabel(target)}：{target.ModelId} ({target.Revision[..7]})",Tag=key});
            }
            if(acquired?.ModelTarget is {} acquiredTarget)AddModel(acquiredTarget);
            modelScope.SelectedIndex=acquired?.ModelTarget is not null?4:1;
            AutomationProperties.SetAutomationId(modelScope,"AIEnvironmentModelScope");
            var scopeNote=new TextBlock{TextWrapping=TextWrapping.Wrap};
            AutomationProperties.SetAutomationId(scopeNote,"AIEnvironmentModelScopeNote");
            AIModelTarget? SelectedTarget()=>(modelScope.SelectedItem as ComboBoxItem)?.Tag is string key&&modelTargets.TryGetValue(key,out var target)?target:null;
            string? SelectedRole()=>SelectedTarget()?.Role??(modelScope.SelectedItem as ComboBoxItem)?.Tag as string;
            static string ModelLabel(AIModelTarget? target)=>target?.Role=="tagger"?"タグ付けモデル":"検索モデル";
            var runtime=new TextBox{Header="AI実行環境",IsReadOnly=true,TextWrapping=TextWrapping.Wrap};
            var models=new TextBox{Header="モデルの保存先",IsReadOnly=true,TextWrapping=TextWrapping.Wrap};
            var chooseRuntime=new Button{Content="実行環境を選ぶ"};var resetRuntime=new Button{Content="標準に戻す"};
            var chooseModels=new Button{Content="モデルのフォルダを選ぶ"};var resetModels=new Button{Content="標準に戻す"};
            var diagnostic=new TextBlock{TextWrapping=TextWrapping.Wrap};var status=new TextBlock{Text="状態を確認しています。",TextWrapping=TextWrapping.Wrap};
            var setupArt=VisualAssets.Sticker();
            var progress=new ProgressBar{Minimum=0,Maximum=100,Visibility=Visibility.Collapsed};var refresh=new Button{Content="状態を更新"};
            foreach(var (control,id) in new (DependencyObject,string)[]{(runtime,"AIEnvironmentRuntime"),(models,"AIEnvironmentModels"),(chooseRuntime,"AIEnvironmentChooseRuntime"),(resetRuntime,"AIEnvironmentResetRuntime"),(chooseModels,"AIEnvironmentChooseModels"),(resetModels,"AIEnvironmentResetModels"),(diagnostic,"AIEnvironmentDiagnostic"),(status,"AIEnvironmentStatus"),(progress,"AIEnvironmentProgress"),(refresh,"AIEnvironmentRefresh")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(resetRuntime,"AI実行環境を標準に戻す");AutomationProperties.SetName(resetModels,"モデル保存先を標準に戻す");AutomationProperties.SetName(progress,"AI環境の検査進捗");
            var descTop=new TextBlock{Text="配置済みのフォルダを確認して設定します（ファイルは移動しません）",TextWrapping=TextWrapping.Wrap};
            ToolTipService.SetToolTip(descTop,"配置済みのフォルダを選ぶと内容を確認し、次回起動の設定として保存します。検査中も通常の閲覧・文字検索を利用できます。");
            panel.Children.Add(descTop);
            var acquiredLocation=new TextBox{Header=acquired?.Kind=="runtime"?"取得した実行環境":$"取得した{ModelLabel(acquired?.ModelTarget)}（{acquired?.ModelTarget?.ModelId}）",Text=acquired?.Root??"",IsReadOnly=true,TextWrapping=TextWrapping.Wrap,Visibility=acquired is not null?Visibility.Visible:Visibility.Collapsed};
            var useAcquired=new Button{Content=acquired?.Kind=="runtime"?"この実行環境を確認して使う":"このモデルの保存先を使う",Visibility=acquired is not null?Visibility.Visible:Visibility.Collapsed,IsEnabled=false};
            AutomationProperties.SetAutomationId(acquiredLocation,"AIEnvironmentAcquiredLocation");AutomationProperties.SetAutomationId(useAcquired,"AIEnvironmentUseAcquired");
            panel.Children.Add(acquiredLocation);panel.Children.Add(useAcquired);
            panel.Children.Add(runtime);
            var runtimeActions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};runtimeActions.Children.Add(chooseRuntime);runtimeActions.Children.Add(resetRuntime);panel.Children.Add(runtimeActions);
            var runtimeHint=new TextBlock{Text="aredoko-ai-runtime.json があるフォルダを指定",TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            ToolTipService.SetToolTip(runtimeHint,"Aredoko用のAI実行環境一式（aredoko-ai-runtime.jsonがあるフォルダ）を指定します。モデルとは別に用意します。");
            panel.Children.Add(runtimeHint);
            panel.Children.Add(modelScope);panel.Children.Add(models);panel.Children.Add(scopeNote);
            var modelActions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};modelActions.Children.Add(chooseModels);modelActions.Children.Add(resetModels);panel.Children.Add(modelActions);
            var modelHint=new TextBlock{Text="モデル群の親フォルダ（例：models）を指定",TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]};
            ToolTipService.SetToolTip(modelHint,"モデル別のフォルダをまとめた親フォルダを指定します。例：models の中に embeddinggemma-2 がある場合は models を選びます。");
            panel.Children.Add(modelHint);
            foreach(var control in new UIElement[]{diagnostic,setupArt,progress,status,refresh})panel.Children.Add(control);
            var download=new Button{Content="ダウンロード・進行状況"};AutomationProperties.SetAutomationId(download,"AIEnvironmentDownload");panel.Children.Add(download);
            var guide=new HyperlinkButton{Content="配置ガイド",NavigateUri=new Uri("https://github.com/jakymiku/Aredoko/blob/main/docs/ai-environment-guide.md")};AutomationProperties.SetAutomationId(guide,"AIEnvironmentGuide");panel.Children.Add(guide);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="手元のAIファイルを使う",SecondaryButtonText="確認を中止",IsSecondaryButtonEnabled=false,CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,
                Content=new ScrollViewer{Content=FormScrollContent.Wrap(panel),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled}};
            AutomationProperties.SetAutomationId(dialog,"AIEnvironmentDialog");
            void Render(AIEnvironmentJob job)
            {
                if(!open||disposed)return;
                current=job;var active=busy||job.Active;
                VisualAssets.State(setupArt,job.Active?"indexing":job.Saved?"completed":job.State=="failed"?"error":null);
                foreach(var control in new Control[]{chooseRuntime,chooseModels,resetRuntime,resetModels,modelScope})control.IsEnabled=!active;
                useAcquired.IsEnabled=!active&&acquired is not null&&(acquired.Kind=="runtime"||acquired.ModelTarget is not null)&&!(job.Saved&&job.Id==acquiredJob);
                useAcquired.Style=useAcquired.IsEnabled?(Style)Application.Current.Resources["AccentButtonStyle"]:Application.Current.Resources["DefaultButtonStyle"] as Style;
                useAcquired.Content=job.Saved&&job.Id==acquiredJob?"次回起動に設定済み":acquired?.Kind=="runtime"?"この実行環境を確認して使う":"このモデルの保存先を使う";
                dialog.IsSecondaryButtonEnabled=job.Active&&!busy&&job.State is not ("cancelling" or "saving");
                progress.Visibility=job.Active||job.Saved?Visibility.Visible:Visibility.Collapsed;
                progress.IsIndeterminate=job.Active&&job.BytesTotal is not >0;
                progress.Value=job.BytesTotal is >0?Math.Clamp(100d*job.BytesDone/job.BytesTotal.Value,0,100):job.Saved?100:0;
                status.Text=job.State=="idle"?"使用するフォルダを選んでください。":job.Message;
                if(job.Active&&job.BytesTotal is >0)status.Text+=$"\n{job.BytesDone/1048576d:N1} / {job.BytesTotal.Value/1048576d:N1} MB";
                if(job.Saved)
                {
                    var role=acquired?.ModelTarget?.Role??SelectedRole();
                    status.Text+=role=="tagger"
                        ?"\n✓ 設定を保存しました。画像タグ付け（WD Tagger）は再起動なしで今すぐ利用できます。"
                        :"\n✓ 設定を保存しました。反映するには Aredoko を一度閉じて再起動してください。";
                }
                if(operationError is not null)status.Text+="\n"+operationError;
            }
            void RenderModelLocation()
            {
                models.Text=locations?.ModelLocation(SelectedRole(),SelectedTarget())??"標準の場所";
                resetModels.Content=SelectedTarget() is not null?"このモデルの指定を解除":SelectedRole() is null?"すべて標準に戻す":"この対象を標準に戻す";
                scopeNote.Text=SelectedTarget() is not null?"このモデルだけ変更（ファイルは移動しません）":SelectedRole() is null?"すべてのモデルを変更（ファイルは移動しません）":"同じ用途のモデルを変更（ファイルは移動しません）";
            }
            modelScope.SelectionChanged+=(_,_)=>RenderModelLocation();
            RenderModelLocation();
            async Task LocationsAsync()
            {
                var requested=revision;
                var value=await api.AIEnvironment.StatusAsync(lifetime.Token);
                if(!open||disposed||requested!=revision||busy)return;
                locations=value;runtime.Text=value.RuntimeRoot??"標準の場所（または起動時に指定した環境）";
                // Keep existing native items/selection stable. Replacing the
                // selected item during refresh can reset ComboBox to common.
                // Only add bounded saved choices; reopening refreshes the set.
                foreach(var entry in value.ModelLocations??Array.Empty<AIModelLocation>())
                    if(!modelTargets.Values.Contains(entry.Target)&&modelTargets.Count<33)AddModel(entry.Target);
                RenderModelLocation();
                diagnostic.Text=(value.RuntimeFilesPresent?"✓ AI実行環境":"⚠ AI実行環境（要確認）")+"　"+(value.ModelFilesPresent?"✓ 検索モデル":"⚠ 検索モデル（要確認）");
                diagnostic.Text+=value.RestartRequired?"\n再起動後に反映されます":"\n設定変更は次回起動時に反映";
            }
            async Task RefreshAsync(bool locations=false)
            {
                var requested=revision;
                try
                {
                    var job=await api.AIEnvironment.JobAsync(lifetime.Token);
                    if(requested!=revision||busy)return;
                    operationError=null;Render(job);
                    if(locations||job.Saved&&savedJob!=job.Id){await LocationsAsync();savedJob=job.Id;}
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){if(open&&!disposed)status.Text="状態を確認できません。「状態を更新」で確認してください。\n"+ex.Message;}
            }
            async Task SelectAsync(bool forRuntime,bool reset,string? acquiredPath=null,AIModelTarget? target=null)
            {
                if(busy||current?.Active==true)return;
                busy=true;operationError=null;++revision;if(current is not null)Render(current);
                try
                {
                    string? path=acquiredPath;
                    if(!reset&&path is null)
                    {
                        path=await PickAIEnvironmentFolderAsync(forRuntime);
                        if(path is null||!open||disposed)return;
                    }
                    target??=SelectedTarget();
                    current=forRuntime?await api.AIEnvironment.SelectRuntimeAsync(path,lifetime.Token)
                        :target is not null?await api.AIEnvironment.SelectModelAsync(target,path,lifetime.Token)
                        :SelectedRole() is {} role?await api.AIEnvironment.SelectModelRoleAsync(role,path,lifetime.Token)
                        :await api.AIEnvironment.SelectModelsAsync(path,lifetime.Token);
                    if(acquiredPath is not null)acquiredJob=current.Id;
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError="開始を確認できません。「状態を更新」で確認してください。\n"+ex.Message;}
                finally{busy=false;if(current is not null)Render(current);}
            }
            useAcquired.Click+=async(_,_)=>{if(acquired is not null)await SelectAsync(acquired.Kind=="runtime",false,acquired.Root,acquired.ModelTarget);};
            chooseRuntime.Click+=async(_,_)=>await SelectAsync(true,false);resetRuntime.Click+=async(_,_)=>await SelectAsync(true,true);
            chooseModels.Click+=async(_,_)=>await SelectAsync(false,false);resetModels.Click+=async(_,_)=>await SelectAsync(false,true);
            refresh.Click+=async(_,_)=>{if(!busy&&(polling is null||polling.IsCompleted)){polling=RefreshAsync(true);await polling;}};
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy||current?.Id is not {} id)return;
                var deferral=args.GetDeferral();busy=true;operationError=null;++revision;Render(current);
                try{current=await api.AIEnvironment.CancelAsync(id,lifetime.Token);}
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError="中止を確認できません。「状態を更新」で確認してください。\n"+ex.Message;}
                finally{busy=false;deferral.Complete();if(current is not null)Render(current);}
            };
            download.Click+=(_,_)=>{if(busy)return;openDownload=true;dialog.Hide();};
            dialog.Closing+=(_,args)=>{if(busy)args.Cancel=true;};
            timer.Tick+=(_,_)=>{if(!busy&&current?.Active==true&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            dialog.Opened+=(_,_)=>{polling=RefreshAsync(true);timer.Start();};
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(openDownload&&!disposed)await OpenAIDownloadDialogAsync();
    }
    // Keep picker type resolution inside the caller's protected operation;
    // resetting preferences itself never needs to load a picker projection.
    private static async Task<string?> PickAIEnvironmentFolderAsync(bool forRuntime)
    {
        var picker=new FolderPicker(MainWindow.Current.AppWindow.Id){Title=forRuntime?"AI実行環境のフォルダ":"モデルをまとめた親フォルダ",CommitButtonText="このフォルダを確認"};
        return (await picker.PickSingleFolderAsync())?.Path;
    }

}
