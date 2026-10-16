using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private async void Navigation_ItemInvoked(NavigationView sender,NavigationViewItemInvokedEventArgs args)
    {
        if(args.InvokedItemContainer is NavigationViewItem {Tag:"settings"})await OpenSettingsAsync();
    }
    private async Task OpenSettingsAsync()
    {
        if(!ready||disposed||dialogOpen||saving||!await transitions.WaitAsync(0))return;
        dialogOpen=true;string? destination=null;
        try
        {
            var panel=new StackPanel{Spacing=16};
            var wheel=new ComboBox{Header="ホイールで次の画像・ページへ",HorizontalAlignment=HorizontalAlignment.Stretch};
            wheel.Items.Add("下に回す（上で戻る）");wheel.Items.Add("上に回す（下で戻る）");wheel.SelectedIndex=ViewerOptions.Value.WheelUpAdvances?1:0;
            AutomationProperties.SetAutomationId(wheel,"SettingsWheel");
            var hint=new TextBlock{Text="拡大中は画像のスクロールを優先します。マウスの進む・戻るも使えます。",TextWrapping=TextWrapping.Wrap};
            var savedText=new TextBlock{TextWrapping=TextWrapping.Wrap};AutomationProperties.SetAutomationId(savedText,"SettingsStatus");
            var save=new Button{Content="ビューワー設定を保存"};AutomationProperties.SetAutomationId(save,"SettingsSave");
            save.Click+=(_,_)=>{try{ViewerOptions.Save(wheel.SelectedIndex==1);savedText.Text="保存しました。開いているビューワーにも適用します。";}catch(Exception ex){savedText.Text="保存できません: "+ex.Message;}};
            panel.Children.Add(wheel);panel.Children.Add(hint);panel.Children.Add(save);panel.Children.Add(savedText);
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title="設定",CloseButtonText="閉じる",Content=panel};
            AutomationProperties.SetAutomationId(dialog,"SettingsDialog");
            foreach(var (label,id,target) in new[]{("AI検索の準備","BtnAIIndex","ai"),("関連語を編集","BtnRelatedTerms","terms")})
            {
                var button=new Button{Content=label,HorizontalAlignment=HorizontalAlignment.Stretch};AutomationProperties.SetAutomationId(button,id);
                button.Click+=(_,_)=>{destination=target;dialog.Hide();};panel.Children.Add(button);
            }
            await dialog.ShowAsync();
        }
        catch(Exception ex){Failure(ex);}
        finally{dialogOpen=false;transitions.Release();RestoreNavigation();}
        if(destination=="ai")AI_Click(this,new RoutedEventArgs());
        else if(destination=="terms")RelatedTerms_Click(this,new RoutedEventArgs());
    }
}
