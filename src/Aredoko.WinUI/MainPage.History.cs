using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private int historyReturnMode;
    private string? historyGeneration;
    private async Task RefreshHistoryGenerationAsync()
    {
        var status=await api.GetAsync("api/library/history");
        var generation=status["generation"]?.GetValue<string>();
        if(generation is null||!System.Text.RegularExpressions.Regex.IsMatch(generation,"\\A[0-9a-f]{32}\\z"))throw new InvalidDataException("Invalid history generation");
        historyGeneration=generation;
    }
    private async void RecordContentOpened(int itemId)
    {
        // Capture before the first await. Never retry this event after a clear.
        var generation=historyGeneration;
        if(generation is null)return;
        try{await api.PostAsync("api/library/history",new JsonObject{{"item_id",itemId},{"generation",generation}});}
        catch(Exception ex)
        {
            AppLog.Error(ex);
            try{if(!disposed)await RefreshHistoryGenerationAsync();}catch(Exception refresh){AppLog.Error(refresh);}
        }
    }
    private async Task DeleteHistoryAsync(int? itemId=null)
    {
        if(!ready||disposed||saving||dialogOpen||!await transitions.WaitAsync(0))return;
        try
        {
            if(!await ConfirmDiscardAsync())return;
            await RefreshHistoryGenerationAsync();var generation=historyGeneration;
            dialogOpen=true;
            var targetTitle=itemId is int id?(rowById.TryGetValue(id,out var found)?found.Title:"選択した作品"):null;
            var dialog=new ContentDialog{XamlRoot=XamlRoot,RequestedTheme=ActualTheme,Title=targetTitle is not null?"この作品の閲覧履歴を削除しますか？":"すべての閲覧履歴を削除しますか？",Content=(targetTitle is not null?$"対象：{targetTitle}\n":"")+"タグ・棚・お気に入り・本の読書位置・元ファイルは残ります。",PrimaryButtonText="履歴を削除",CloseButtonText="キャンセル",DefaultButton=ContentDialogButton.Close};
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetAutomationId(dialog,"HistoryDeleteDialog");
            var accepted=await dialog.ShowAsync()==ContentDialogResult.Primary;dialogOpen=false;
            if(!accepted||disposed)return;
            var request=new JsonObject{{"generation",generation},{"consent",true}};
            if(itemId is int selected)request["item_ids"]=new JsonArray((JsonNode?)JsonValue.Create(selected));
            var result=await api.PostAsync("api/library/history/delete",request);
            historyGeneration=result["generation"]?.GetValue<string>();
            page=0;await LoadAsync();
            Notice("閲覧履歴を削除しました",$"{result["removed"]?.GetValue<int>()??0:N0}件の履歴を削除しました。");
        }
        catch(Exception ex){if(!disposed)Failure(ex);}
        finally{dialogOpen=false;transitions.Release();if(PendingAutoSearch&&!disposed)searchTimer.Start();}
    }
    private async void UnreviewedOnly_Changed(object sender,RoutedEventArgs args)
    {
        if(!ready||populating||disposed)return;
        if(saving||dialogOpen||!await transitions.WaitAsync(0)){RestoreNavigation();return;}
        try
        {
            if(!await ConfirmDiscardAsync()){RestoreNavigation();return;}
            ClearSimilarity();view=UnreviewedOnly.IsChecked==true?"unreviewed":"all";
            page=0;RestoreNavigation();UpdateSearchMethod();await LoadAsync();SearchOptions.IsExpanded=true;
        }
        finally{transitions.Release();}
    }
}
