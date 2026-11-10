using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async Task OpenAIAutoEnvironmentDialogAsync()
    {
        if(!ready||disposed||dialogOpen||!await transitions.WaitAsync(0))return;
        dialogOpen=true;bool open=true,busy=false;Task? polling=null;
        using var lifetime=new CancellationTokenSource();
        var timer=new DispatcherTimer{Interval=TimeSpan.FromSeconds(1)};
        try
        {
            JsonNode? summary=null,current=null;string? operationError=null;
            var description=new TextBlock{Text="取得内容を確認しています…",TextWrapping=TextWrapping.Wrap};
            var licenses=new StackPanel{Spacing=4};
            var consent=new CheckBox{Content="提供元・ライセンス・容量を確認し、取得とAIの動作確認に同意します。",IsEnabled=false};
            var speed=new NumberBox{Header="速度上限（MB/秒、0で無制限）",Value=0,Minimum=0,Maximum=1000000,SmallChange=1};
            AutomationProperties.SetAutomationId(speed,"AIAutoEnvironmentSpeed");
            var speedSettings=new Expander{Header="速度制限（既定は制限なし）",Content=speed,HorizontalAlignment=HorizontalAlignment.Stretch};
            var status=new TextBlock{TextWrapping=TextWrapping.Wrap};
            var progress=new ProgressBar{IsIndeterminate=true,Visibility=Visibility.Collapsed};
            var panel=new StackPanel{Spacing=12,MaxWidth=650};
            panel.Children.Add(description);panel.Children.Add(licenses);
            panel.Children.Add(new TextBlock{Text="初回は数GBのダウンロードと構築を行います。途中で閉じても処理は続きます。中止した場合は前の設定を保持します。\n既存のモデル・環境は再利用し、変更・削除しません。GPUが利用できる場合は動作確認に使用します（上限4GB）。",TextWrapping=TextWrapping.Wrap});
            panel.Children.Add(consent);panel.Children.Add(speedSettings);panel.Children.Add(progress);panel.Children.Add(status);
            var scroll=new ScrollViewer{Content=panel,MaxHeight=Math.Max(160,ActualHeight-240),Padding=new Thickness(0,0,16,0),VerticalScrollBarVisibility=ScrollBarVisibility.Auto,HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="AI環境を自動構築",PrimaryButtonText="取得・構築して確認",SecondaryButtonText="中止",CloseButtonText="閉じる",DefaultButton=ContentDialogButton.None,Content=scroll,IsPrimaryButtonEnabled=false,IsSecondaryButtonEnabled=false};
            AutomationProperties.SetAutomationId(dialog,"AIAutoEnvironmentDialog");AutomationProperties.SetAutomationId(consent,"AIAutoEnvironmentConsent");AutomationProperties.SetAutomationId(status,"AIAutoEnvironmentStatus");
            AutomationProperties.SetLiveSetting(status,Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
            bool Active()=>current?["state"]?.GetValue<string>() is "waiting" or "checking_runtime" or "checking_base" or "downloading_runtime" or "building" or "checking_model" or "downloading_model" or "probing" or "saving" or "cancelling";
            void Render()
            {
                if(!open||disposed)return;
                var active=Active();var supported=summary?["supported"]?.GetValue<bool>()??false;
                consent.IsEnabled=supported&&!busy&&!active;
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
            }
            async Task RefreshAsync()
            {
                try
                {
                    summary=await api.GetAsync("api/library/ai/setup/build",lifetime.Token);current=summary["job"];
                    if(licenses.Children.Count==0)
                    {
                        description.Text=summary["supported"]?.GetValue<bool>()==true?$"EmbeddingGemma 2：公式の固定版パッケージとモデルを取得し、整合性と実推論を確認してから設定を保存します。\n最大取得量の目安 {(summary["download_bytes"]?.GetValue<long>()??0)/1_000_000_000d:N2} GB、構築時の空き容量目安15 GB。\n取得元：Python Software Foundation / PyTorch / PyPI / Google（Hugging Face）":"現在のモデルは自動構築の対象外です。AI環境の手動選択を利用してください。";
                        if(summary["licenses"] is JsonArray entries)foreach(var entry in entries)
                            if(Uri.TryCreate(entry?["url"]?.GetValue<string>(),UriKind.Absolute,out var uri))
                            {
                                licenses.Children.Add(new TextBlock{Text=entry?["name"]?.GetValue<string>()??"ライセンス",TextWrapping=TextWrapping.Wrap});
                                licenses.Children.Add(new HyperlinkButton{Content="提供元のライセンスを確認",NavigateUri=uri});
                            }
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
            dialog.Closing+=(_,args)=>{if(busy)args.Cancel=true;};
            dialog.Opened+=(_,_)=>{polling=RefreshAsync();timer.Start();};
            timer.Tick+=(_,_)=>{if(Active()&&!busy&&(polling is null||polling.IsCompleted))polling=RefreshAsync();};
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{open=false;timer.Stop();lifetime.Cancel();if(polling is not null)await polling;dialogOpen=false;transitions.Release();RestoreNavigation();}
    }
}
