using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task OpenAIAutoEnvironmentDialogAsync(bool fromSettings=false)
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;bool open=true,busy=false,returnToSettings=false;Task? polling=null;
        using var lifetime=new CancellationTokenSource();
        var timer=new DispatcherTimer{Interval=TimeSpan.FromSeconds(1)};
        try
        {
            JsonNode? summary=null,current=null;string? operationError=null;
            var description=new TextBlock{Text="取得内容を確認しています…",TextWrapping=TextWrapping.Wrap};
            var licenses=new StackPanel{Spacing=4};
            var consent=new CheckBox{Content="提供元・ライセンス・容量を確認し、ダウンロードと動作確認に同意する",IsEnabled=false};
            var speed=new NumberBox{Header="速度上限（MB/秒、0で無制限）",Value=0,Minimum=0,Maximum=1000000,SmallChange=1};
            AutomationProperties.SetAutomationId(speed,"AIAutoEnvironmentSpeed");
            var speedSettings=new Expander{Header="速度制限（既定は制限なし）",Content=speed,HorizontalAlignment=HorizontalAlignment.Stretch};
            var status=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{IsIndeterminate=true,Visibility=Visibility.Collapsed};
            var panel=new StackPanel{Spacing=12,MaxWidth=650};
            var overviewStack=new StackPanel{Spacing=8};
            overviewStack.Children.Add(description);
            overviewStack.Children.Add(new TextBlock{Text="• 画面を閉じても続行します\n• 中止しても元の設定は残ります\n• NVIDIA GPU（上限4 GB）またはCPUで自動動作（Radeon等はCPU／手元のDirectML・ROCm環境に対応）",TextWrapping=TextWrapping.Wrap,Style=(Style)Resources["MediaMetadataStyle"]});
            panel.Children.Add(new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=overviewStack});
            var licensesCard=new Border{Style=(Style)Application.Current.Resources["AredokoSurfaceStyle"],Child=licenses,Visibility=Visibility.Collapsed};
            panel.Children.Add(licensesCard);
            var autoArt=VisualAssets.Sticker(64);
            var progressRow=new Grid{ColumnSpacing=12};
            progressRow.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            progressRow.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            var progressStack=new StackPanel{Spacing=6,VerticalAlignment=VerticalAlignment.Center};
            progressStack.Children.Add(progress);progressStack.Children.Add(status);
            Grid.SetColumn(progressStack,1);
            progressRow.Children.Add(autoArt);progressRow.Children.Add(progressStack);
            panel.Children.Add(consent);panel.Children.Add(speedSettings);panel.Children.Add(progressRow);
            Button? backToSettings=fromSettings?new Button{Content="設定へ戻る",HorizontalAlignment=HorizontalAlignment.Left}:null;
            if(backToSettings is not null){AutomationProperties.SetAutomationId(backToSettings,"BtnBackToSettings");panel.Children.Add(backToSettings);}
            var scroll=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),Padding=new Thickness(0,0,16,0),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AIの自動セットアップ",PrimaryButtonText="ダウンロードして設定",SecondaryButtonText="中止",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,Content=scroll,IsPrimaryButtonEnabled=false,IsSecondaryButtonEnabled=false};
            AutomationProperties.SetAutomationId(dialog,"AIAutoEnvironmentDialog");AutomationProperties.SetAutomationId(consent,"AIAutoEnvironmentConsent");AutomationProperties.SetAutomationId(status,"AIAutoEnvironmentStatus");
            AutomationProperties.SetLiveSetting(status,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
            bool Active()=>current?["state"]?.GetValue<string>() is "waiting" or "checking_runtime" or "checking_base" or "downloading_runtime" or "building" or "checking_model" or "downloading_model" or "probing" or "saving" or "cancelling";
            void Render()
            {
                if(!open||disposed)return;
                var active=Active();var supported=summary?["supported"]?.GetValue<bool>()??false;
                consent.IsEnabled=supported&&!busy&&!active;
                if(backToSettings is not null)backToSettings.IsEnabled=!busy;
                speed.IsEnabled=!busy&&!active;
                if(active)speed.Value=(current?["bytes_per_second"]?.GetValue<long>()??0)/1_000_000d;
                dialog.IsPrimaryButtonEnabled=supported&&!busy&&!active&&consent.IsChecked==true;
                dialog.IsSecondaryButtonEnabled=!busy&&active&&!(current?["saved"]?.GetValue<bool>()??false)&&current?["state"]?.GetValue<string>()!="cancelling";
                progress.Visibility=active?Visibility.Visible:Visibility.Collapsed;
                var total=current?["bytes_total"]?.GetValue<long>()??0;var done=current?["bytes_done"]?.GetValue<long>()??0;
                progress.IsIndeterminate=total<=0;progress.Value=total>0?Math.Clamp(100d*done/total,0,100):0;
                status.Text=current?["message"]?.GetValue<string>()??"";
                if(active&&total>0)status.Text+=$"\n{done/1_000_000d:N1} / {total/1_000_000d:N1} MB";
                if(operationError is not null)status.Text+="\n"+operationError;
                VisualAssets.State(autoArt,active?"indexing":(current?["saved"]?.GetValue<bool>()==true)?"completed":(current?["state"]?.GetValue<string>()=="failed"||operationError is not null)?"error":null);
            }
            async Task RefreshAsync()
            {
                try
                {
                    summary=await api.GetAsync("api/library/ai/setup/build",lifetime.Token);current=summary["job"];
                    if(licenses.Children.Count==0)
                    {
                        description.Text=summary["supported"]?.GetValue<bool>()==true?$"対象モデル：{""}EmbeddingGemma 2\n最大取得量：{(summary["download_bytes"]?.GetValue<long>()??0)/1_000_000_000d:N2} GB\n必要な空き：約15 GB以上\n提供元：Python / PyTorch / PyPI / Google (HF)":"このモデルは自動セットアップ非対応です。「手元のファイルを使う」から指定してください";
                        if(summary["licenses"] is JsonArray entries)foreach(var entry in entries)
                            if(Uri.TryCreate(entry?["url"]?.GetValue<string>(),UriKind.Absolute,out var uri))
                            {
                                licenses.Children.Add(new TextBlock{Text=entry?["name"]?.GetValue<string>()??"ライセンス",TextWrapping=TextWrapping.Wrap});
                                licenses.Children.Add(new HyperlinkButton{Content="提供元のライセンスを確認",NavigateUri=uri});
                            }
                        licensesCard.Visibility=licenses.Children.Count>0?Visibility.Visible:Visibility.Collapsed;
                    }
                    operationError=null;Render();
                }
                catch(OperationCanceledException)when(lifetime.IsCancellationRequested){}
                catch(Exception ex){if(open&&!disposed){status.Text="準備状態を確認できません。閉じてから開き直してください。\n"+ex.Message;dialog.IsPrimaryButtonEnabled=false;}}
            }
            consent.Checked+=(_,_)=>Render();consent.Unchecked+=(_,_)=>Render();
            dialog.PrimaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(!dialog.IsPrimaryButtonEnabled)return;var deferral=args.GetDeferral();busy=true;operationError=null;Render();
                try
                {
                    if(!double.IsFinite(speed.Value)||speed.Value<0||speed.Value>1000000)throw new ArgumentException("速度上限を確認してください。0は無制限です。");
                    long? rate=speed.Value==0?null:checked((long)Math.Round(speed.Value*1000000));
                    current=await api.PostAsync("api/library/ai/setup/build/start",new JsonObject{["consent"]=true,["bytes_per_second"]=rate});consent.IsChecked=false;
                }
                catch(Exception ex){operationError="準備を開始できませんでした。\n"+ex.Message;}
                finally{busy=false;deferral.Complete();Render();}
            };
            dialog.SecondaryButtonClick+=async(_,args)=>
            {
                args.Cancel=true;if(busy)return;var deferral=args.GetDeferral();busy=true;Render();
                try{current=await api.PostAsync("api/library/ai/setup/build/cancel",new JsonObject());}
                catch(Exception ex){operationError="中止の状態を確認できませんでした。\n"+ex.Message;}
                finally{busy=false;deferral.Complete();Render();}
            };
            if(backToSettings is not null)backToSettings.Click+=(_,_)=>{if(!busy){returnToSettings=true;dialog.Hide();}};
            dialog.Closing+=(_,args)=>{if(busy)args.Cancel=true;};
            dialog.Opened+=(_,_)=>{polling=RefreshAsync();timer.Start();};
            timer.Tick+=(_,_)=>{if(Active()&&!busy&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            var closedTcs=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            dialog.Closed+=(_,_)=>closedTcs.TrySetResult(true);
            await dialog.ShowAsync();
            await Task.WhenAny(closedTcs.Task,Task.Delay(500));
        }
        catch(Exception ex){Failure(ex);}
        finally{open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(returnToSettings&&!disposed)await OpenSettingsAsync();
    }
}
