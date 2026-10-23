using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Windows.Storage.Pickers;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task OpenAIEnvironmentDialogAsync()
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        bool open=true,busy=false;long revision=0;AIEnvironmentJob? current=null;Task? polling=null;string? operationError=null;string? savedJob=null;
        using var lifetime=new CancellationTokenSource();
        var timer=new DispatcherTimer{Interval=TimeSpan.FromMilliseconds(700)};
        try
        {
            dialogOpen=true;
            var panel=new StackPanel{Spacing=12};
            var runtime=new TextBox{Header="AI実行環境",IsReadOnly=true,TextWrapping=TextWrapping.Wrap};
            var models=new TextBox{Header="モデルの保存先",IsReadOnly=true,TextWrapping=TextWrapping.Wrap};
            var chooseRuntime=new Button{Content="実行環境を選ぶ"};var resetRuntime=new Button{Content="標準に戻す"};
            var chooseModels=new Button{Content="モデルのフォルダを選ぶ"};var resetModels=new Button{Content="標準に戻す"};
            var diagnostic=new TextBlock{TextWrapping=TextWrapping.Wrap};var status=new TextBlock{Text="状態を確認しています。",TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{Minimum=0,Maximum=100};var refresh=new Button{Content="状態を更新"};
            foreach(var (control,id) in new (DependencyObject,string)[]{(runtime,"AIEnvironmentRuntime"),(models,"AIEnvironmentModels"),(chooseRuntime,"AIEnvironmentChooseRuntime"),(resetRuntime,"AIEnvironmentResetRuntime"),(chooseModels,"AIEnvironmentChooseModels"),(resetModels,"AIEnvironmentResetModels"),(diagnostic,"AIEnvironmentDiagnostic"),(status,"AIEnvironmentStatus"),(progress,"AIEnvironmentProgress"),(refresh,"AIEnvironmentRefresh")})AutomationProperties.SetAutomationId(control,id);
            AutomationProperties.SetName(resetRuntime,"AI実行環境を標準に戻す");AutomationProperties.SetName(resetModels,"モデル保存先を標準に戻す");AutomationProperties.SetName(progress,"AI環境の検査進捗");
            panel.Children.Add(new TextBlock{Text="配置済みのフォルダを選ぶと内容を確認し、次回起動の設定として保存します。検査中も通常の閲覧・文字検索を利用できます。",TextWrapping=TextWrapping.Wrap});
            panel.Children.Add(runtime);
            var runtimeActions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};runtimeActions.Children.Add(chooseRuntime);runtimeActions.Children.Add(resetRuntime);panel.Children.Add(runtimeActions);
            panel.Children.Add(new TextBlock{Text="Aredoko用のAI実行環境一式（aredoko-ai-runtime.jsonがあるフォルダ）を指定します。モデルとは別に用意します。",TextWrapping=TextWrapping.Wrap});
            panel.Children.Add(models);
            var modelActions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};modelActions.Children.Add(chooseModels);modelActions.Children.Add(resetModels);panel.Children.Add(modelActions);
            panel.Children.Add(new TextBlock{Text="モデル別のフォルダをまとめた親フォルダを指定します。例：models の中に embeddinggemma-2 がある場合は models を選びます。",TextWrapping=TextWrapping.Wrap});
            foreach(var control in new UIElement[]{diagnostic,progress,status,refresh})panel.Children.Add(control);
            panel.Children.Add(new TextBlock{Text="アプリから取得できるAI環境は公開準備中です。配置済みの環境を指定して利用できます。",TextWrapping=TextWrapping.Wrap});
            var guide=new HyperlinkButton{Content="AI環境の配置ガイド",NavigateUri=new Uri("https://github.com/jakymiku/Aredoko/blob/feat/winui3-production-mvp-20261011/docs/ai-environment-guide.md")};AutomationProperties.SetAutomationId(guide,"AIEnvironmentGuide");panel.Children.Add(guide);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AI環境の追加と配置",SecondaryButtonText="検査を中止",IsSecondaryButtonEnabled=false,CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,
                Content=new ScrollViewer{Content=FormScrollContent.Wrap(panel),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled}};
            AutomationProperties.SetAutomationId(dialog,"AIEnvironmentDialog");
            void Render(AIEnvironmentJob job)
            {
                if(!open||disposed)return;
                current=job;var active=busy||job.Active;
                foreach(var control in new Control[]{chooseRuntime,chooseModels,resetRuntime,resetModels})control.IsEnabled=!active;
                dialog.IsSecondaryButtonEnabled=job.Active&&!busy&&job.State is not ("cancelling" or "saving");
                progress.IsIndeterminate=job.Active&&job.BytesTotal is not >0;
                progress.Value=job.BytesTotal is >0?Math.Clamp(100d*job.BytesDone/job.BytesTotal.Value,0,100):job.Saved?100:0;
                status.Text=job.State=="idle"?"使用するフォルダを選んでください。":job.Message;
                if(job.Active&&job.BytesTotal is >0)status.Text+=$"\n{job.BytesDone/1048576d:N1} / {job.BytesTotal.Value/1048576d:N1} MB";
                if(operationError is not null)status.Text+="\n"+operationError;
            }
            async Task LocationsAsync()
            {
                var requested=revision;
                var value=await api.AIEnvironment.StatusAsync(lifetime.Token);
                if(!open||disposed||requested!=revision||busy)return;
                runtime.Text=value.RuntimeRoot??"標準の場所（または起動時に指定した環境）";models.Text=value.ModelsRoot??"標準の場所";
                diagnostic.Text="実行環境："+(value.RuntimeFilesPresent?"ファイルあり":"未導入または要確認")+"　モデル："+(value.ModelFilesPresent?"ファイルあり":"未導入または要確認");
                diagnostic.Text+=value.RestartRequired?"\n保存した設定は、Aredokoを再起動すると反映されます。":"\n設定変更は次回起動時に反映します。AIの動作確認とは別です。";
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
            async Task SelectAsync(bool forRuntime,bool reset)
            {
                if(busy||current?.Active==true)return;
                busy=true;operationError=null;++revision;if(current is not null)Render(current);
                try
                {
                    string? path=null;
                    if(!reset)
                    {
                        var picker=new FolderPicker(MainWindow.Current.AppWindow.Id){Title=forRuntime?"AI実行環境のフォルダ":"モデルをまとめた親フォルダ",CommitButtonText="このフォルダを確認"};
                        var picked=await picker.PickSingleFolderAsync();
                        if(picked is null||!open||disposed)return;
                        path=picked.Path;
                    }
                    current=forRuntime?await api.AIEnvironment.SelectRuntimeAsync(path,lifetime.Token):await api.AIEnvironment.SelectModelsAsync(path,lifetime.Token);
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){operationError="開始を確認できません。「状態を更新」で確認してください。\n"+ex.Message;}
                finally{busy=false;if(current is not null)Render(current);}
            }
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
            dialog.Closing+=(_,args)=>{if(busy)args.Cancel=true;};
            timer.Tick+=(_,_)=>{if(!busy&&current?.Active==true&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            dialog.Opened+=(_,_)=>{polling=RefreshAsync(true);timer.Start();};
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;dialogOpen=false;transitions.Release();RestoreNavigation();}
    }
}
