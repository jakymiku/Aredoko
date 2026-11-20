using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using System.Text.Json.Nodes;

namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private sealed record PageLocation(string Key,string Screen,SearchBookmark Search,MediaRow? Origin,
        SearchBookmark? SimilarityReturn,bool DetailsOpen,(string Key,double Y)? Anchor,string FolderFilter,int FolderState,int[] CheckedRoots,bool DirectAudio,bool DirectVideo,bool DirectVideoAudio,string SettingsCategory="all");
    private sealed class LocationComparer:IEqualityComparer<PageLocation>
    {
        public bool Equals(PageLocation? left,PageLocation? right)=>left?.Key==right?.Key;
        public int GetHashCode(PageLocation value)=>StringComparer.Ordinal.GetHashCode(value.Key);
    }
    private readonly NavigationHistory<PageLocation> navigationHistory=new(64,new LocationComparer());
    private bool restoringNavigation;

    private PageLocation CaptureLocation()
    {
        var screen=settingsHubOpen?"settings":folderHubOpen?"folders":shelfHubOpen?"shelves":"library";
        var anchor=screen=="library"?CaptureBrowseAnchor():null;
        var selected=active?.Id??0;
        var targetPage=page;
        if(anchor is {} position && int.TryParse(position.Key,out var anchorId))
        {
            var index=rows.FindIndex(row=>row.Id==anchorId);
            if(index>=0)targetPage=(browseStart+index)/resultPageSize;
        }
        var search=new SearchBookmark(lastQuery,lastKind,lastMode,lastRoots?.ToArray(),lastLiteralOnly,lastBoundary,lastResultGroup,view,targetPage,selected,selectedShelfIds?.ToArray(),selectedTagScope,similarityOriginPage,similarityOriginMs);
        var identity=screen=="settings"
            ? new JsonObject{["screen"]="settings"}
            : new JsonObject{["screen"]=screen,["query"]=search.Query,["kind"]=search.Kind,["mode"]=search.Mode,
                ["roots"]=search.Roots is null?null:string.Join(",",search.Roots),["shelves"]=search.Shelves is null?null:string.Join(",",search.Shelves),["tag"]=search.Tag,
                ["literal"]=search.LiteralOnly,["boundary"]=search.Boundary,["group"]=search.Group,["view"]=search.View,["page"]=search.Page,["origin"]=similarityOrigin?.Id,["origin_page"]=similarityOriginPage,["origin_ms"]=similarityOriginMs,["audio_similarity"]=directAudioSimilarity,["video_similarity"]=directVideoSimilarity,["video_audio_similarity"]=directVideoAudioSimilarity};
        var origin=similarityOrigin is {} item?new MediaRow{Id=item.Id,Title=item.Title,Kind=item.Kind}:null;
        return new(identity.ToJsonString(),screen,search,origin,similarityReturn,Details.IsPaneOpen,anchor,FolderFilterBox.Text,FolderStateFilter.SelectedIndex,checkedFolderIds.ToArray(),directAudioSimilarity,directVideoSimilarity,directVideoAudioSimilarity,currentSettingsCategory);
    }
    private void RecordNavigationLocation()
    {
        if(disposed||restoringNavigation)return;
        navigationHistory.Track(CaptureLocation());UpdateNavigationHistoryButtons();
    }
    private void RememberCurrentLocation()
    {
        if(disposed||restoringNavigation||navigationHistory.Current is null)return;
        navigationHistory.ReplaceCurrent(CaptureLocation());UpdateNavigationHistoryButtons();
    }
    private void UpdateNavigationHistoryButtons()
    {
        if(NavigationBackButton is null)return;
        NavigationBackButton.IsEnabled=!restoringNavigation&&navigationHistory.CanBack;
        NavigationForwardButton.IsEnabled=!restoringNavigation&&navigationHistory.CanForward;
    }
    private async Task NavigateHistoryAsync(bool forward)
    {
        if(!ready||disposed||restoringNavigation||dialogOpen||saving||viewerWindow is not null)return;
        var target=navigationHistory.Peek(forward);if(target is null)return;
        RememberCurrentLocation();searchTimer.Stop();restoringNavigation=true;UpdateNavigationHistoryButtons();
        var moved=false;
        try
        {
            if(target.Screen=="settings")
            {
                await OpenSettingsAsync(target.SettingsCategory);
                moved=settingsHubOpen;
            }
            else if(target.Screen=="folders")
            {
                await OpenFolderHubAsync();
                if(folderHubOpen)
                {
                    folderPopulating=true;
                    try
                    {
                        FolderFilterBox.Text=target.FolderFilter;FolderStateFilter.SelectedIndex=target.FolderState;
                        checkedFolderIds.Clear();foreach(var id in target.CheckedRoots.Where(id=>knownRoots.Any(r=>r.Enabled&&r.Id==id)))checkedFolderIds.Add(id);
                    }
                    finally{folderPopulating=false;}
                    RenderFolderHub();moved=true;
                }
            }
            else if(target.Screen=="shelves")
            {
                await OpenShelfHubAsync();moved=shelfHubOpen;
            }
            else if(await transitions.WaitAsync(0))
            {
                try
                {
                    if(!await ConfirmDiscardAsync())return;
                    var bookmark=target.Search;CloseSettingsHubCore();CloseShelfHubCore();CloseFolderHubCore();
                    populating=true;
                    try
                    {
                        Query.Text=bookmark.Query;Kind.SelectedIndex=bookmark.Kind;SearchMode.SelectedIndex=bookmark.Mode;
                        RestoreSearchRoots(bookmark.Roots);SetShelfScope(bookmark.Shelves);SetTagScope(bookmark.Tag);AIMatchedOnly.IsChecked=bookmark.LiteralOnly;
                        SimilarityBoundary.Value=bookmark.Boundary??double.NaN;AIResultGroup.SelectedIndex=bookmark.Group;
                        view=bookmark.View;page=bookmark.Page;similarityOrigin=target.Origin;similarityOriginPage=bookmark.OriginPage;similarityOriginMs=bookmark.OriginMs;directAudioSimilarity=target.DirectAudio;directVideoSimilarity=target.DirectVideo;directVideoAudioSimilarity=target.DirectVideoAudio;similarityReturn=target.SimilarityReturn;UpdateSearchMethod();RestoreNavigation();
                    }
                    finally{populating=false;}
                    await LoadAsync();
                    if(!startupSearchSucceeded)return;
                    if(bookmark.Selection>0&&rows.FirstOrDefault(row=>row.Id==bookmark.Selection) is {} selected)
                    {ApplySelectedRow(selected);RestoreSelection();}
                    Items.UpdateLayout();await RestoreBrowseAnchorAsync(target.Anchor);Details.IsPaneOpen=target.DetailsOpen&&active is not null;
                    moved=true;
                }
                finally{transitions.Release();}
            }
            if(moved)
            {
                navigationHistory.Commit(forward,target);navigationHistory.ReplaceCurrent(CaptureLocation());
            }
        }
        catch(Exception ex){Failure(ex);}
        finally
        {
            restoringNavigation=false;UpdateNavigationHistoryButtons();
            if(PendingAutoSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void HistoryBack_Click(object sender,RoutedEventArgs args)=>await NavigateHistoryAsync(false);
    private async void HistoryForward_Click(object sender,RoutedEventArgs args)=>await NavigateHistoryAsync(true);
    private async void HistoryBackShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs args)
    {args.Handled=true;await NavigateHistoryAsync(false);}
    private async void HistoryForwardShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs args)
    {args.Handled=true;await NavigateHistoryAsync(true);}
}
