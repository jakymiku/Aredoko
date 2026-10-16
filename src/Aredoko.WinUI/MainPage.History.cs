using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;

public sealed partial class MainPage
{
    private int historyReturnMode;
    private async void RecordContentOpened(int itemId)
    {
        try{await api.PostAsync("api/library/history",new JsonObject{{"item_id",itemId}});}
        catch(Exception ex){AppLog.Error(ex);}
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
