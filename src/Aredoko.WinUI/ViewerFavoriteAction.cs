using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace Aredoko_WinUI;

// Shared by image, book and media viewers. The owner controls when media is ready
// and waits for FlushAsync before disposing this action.
internal sealed class ViewerFavoriteAction(ResultSession? session,Action<string> notice) : IDisposable
{
    public Button Button {get;}=new(){Content=new SymbolIcon(Symbol.OutlineStar),MinWidth=36,Padding=new Thickness(8),Visibility=session is null?Visibility.Collapsed:Visibility.Visible};
    private readonly CancellationTokenSource lifetime=new();
    private int itemId,version;
    private bool? value;
    private Task save=Task.CompletedTask;
    private bool disposed;
    public bool IsSaving {get;private set;}
    public event Action? StateChanged;
    public event Action<int,bool,bool>? Changed;
    public event Action? ReturnRequested;
    public Task FlushAsync()=>save;
    public void Attach()=>Button.Click+=async(_,_)=>{save=SaveAsync();await save;};
    public void UpdateAvailability(bool ready)=>Button.IsEnabled=ready&&!disposed&&!IsSaving&&value is not null;
    public void Refresh(int id,int ordinal)
    {
        itemId=id;var currentVersion=++version;value=null;
        Button.Content=new SymbolIcon(Symbol.OutlineStar);
        Label("お気に入りを読み込み中");
        if(session is not null)_=LoadAsync(id,ordinal,currentVersion);
    }
    private void Label(string text){AutomationProperties.SetName(Button,text);ToolTipService.SetToolTip(Button,text);}
    private void Update()
    {
        Button.Content=new SymbolIcon(value==true?Symbol.SolidStar:Symbol.OutlineStar);
        Label(value==true?"お気に入りを解除":"お気に入りに登録");StateChanged?.Invoke();
    }
    private async Task LoadAsync(int id,int ordinal,int currentVersion)
    {
        try
        {
            var result=await session!.RangeAsync(ordinal,1,lifetime.Token);
            if(disposed||version!=currentVersion)return;
            if(result.Items.Count!=1||result.Items[0].Id!=id)throw new InvalidDataException("表示中の作品を確認できません。");
            value=result.Items[0].Favorite;Update();
        }
        catch(OperationCanceledException) when(lifetime.IsCancellationRequested){}
        catch(Exception ex){if(!disposed&&version==currentVersion){Label("お気に入りの状態を取得できません。一覧で確認してください。");AppLog.Error(ex);}}
    }
    private async Task SaveAsync()
    {
        if(disposed||IsSaving||value is null||session is null||!Button.IsEnabled)return;
        var id=itemId;var target=!value.Value;IsSaving=true;StateChanged?.Invoke();
        try
        {
            var kept=await session.EditFavoriteAsync(id,target,CancellationToken.None);
            value=target;Changed?.Invoke(id,target,kept);Update();
            notice(target?"お気に入りに登録しました。":"お気に入りを解除しました。");
            if(!kept){notice("保存しました。検索結果を更新するため一覧へ戻ります。");ReturnRequested?.Invoke();}
        }
        catch(Exception ex){notice("お気に入りを保存できませんでした。一覧で状態を確認してください。");AppLog.Error(ex);}
        finally{IsSaving=false;if(!disposed)StateChanged?.Invoke();}
    }
    public void Dispose(){if(disposed)return;disposed=true;lifetime.Cancel();lifetime.Dispose();}
}
