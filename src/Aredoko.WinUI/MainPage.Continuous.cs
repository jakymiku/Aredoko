using Aredoko.Core;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Collections.ObjectModel;
using Windows.Foundation;

namespace Aredoko_WinUI;
public sealed partial class MainPage
{
    private readonly ObservableCollection<string> resultKeys=new();
    private ResultBuffer? browseBuffer;
    private int browseStart;
    private bool browseFailed,extending,browseReflowing;
    private ScrollViewer? resultScroll;

    private int PreviousBrowsePage()=>Math.Max(0,(browseStart-1)/resultPageSize);
    private int NextBrowsePage()=>browseBuffer?.End/resultPageSize??page+1;
    private void ResetBrowse(int start,SearchResponse result)
    {
        browseBuffer=new ResultBuffer(start,result);browseStart=start;browseFailed=false;
    }
    private static T? Descendant<T>(DependencyObject parent) where T:DependencyObject
    {
        for(var i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++)
        {
            var child=VisualTreeHelper.GetChild(parent,i);
            if(child is T match)return match;
            if(Descendant<T>(child) is T nested)return nested;
        }
        return null;
    }
    private void Items_Loaded(object sender,RoutedEventArgs args)
    {
        var scroll=Descendant<ScrollViewer>(Items);
        if(ReferenceEquals(resultScroll,scroll))return;
        if(resultScroll is not null)resultScroll.ViewChanged-=ResultScroll_Changed;
        resultScroll=scroll;
        if(scroll is not null)scroll.ViewChanged+=ResultScroll_Changed;
    }
    private async void ResultScroll_Changed(object? sender,ScrollViewerViewChangedEventArgs args)
    {
        if(!ready||!Items.IsEnabled||args.IsIntermediate||disposed||extending||browseReflowing||browseFailed||saving||dialogOpen||PendingSearch||folderHubOpen)return;
        if(resultScroll is not ScrollViewer scroll||browseBuffer is not ResultBuffer buffer||resultWindow is not ResultWindow window)return;
        var forward=scroll.VerticalOffset+scroll.ViewportHeight*2>=scroll.ExtentHeight&&buffer.End<buffer.Total;
        var backward=!forward&&scroll.VerticalOffset<scroll.ViewportHeight&&buffer.Start>0;
        if(!forward&&!backward||!await transitions.WaitAsync(0))return;
        extending=true;var session=resultSession;var token=renderCancellation.Token;
        try
        {
            var offset=forward?buffer.End:Math.Max(0,buffer.Start-ResultWindow.BlockSize);
            var count=forward?Math.Min(ResultWindow.BlockSize,buffer.Total-offset):buffer.Start-offset;
            var result=await window.ReadAsync(offset,count,token);
            if(disposed||token.IsCancellationRequested||!ReferenceEquals(session,resultSession)||!ReferenceEquals(buffer,browseBuffer))return;
            var anchor=CaptureBrowseAnchor();
            buffer.Extend(offset,result);browseStart=buffer.Start;rows=buffer.Items.ToList();
            var wanted=rows.Select(row=>RowKey(row.Id)).ToArray();var keep=wanted.ToHashSet();
            var wasPopulating=populating;populating=true;
            try
            {
                for(var i=resultKeys.Count-1;i>=0;i--)if(!keep.Contains(resultKeys[i]))resultKeys.RemoveAt(i);
                for(var i=0;i<wanted.Length;i++)if(i>=resultKeys.Count||resultKeys[i]!=wanted[i])resultKeys.Insert(i,wanted[i]);
                RestoreSelection();
            }
            finally{populating=wasPopulating;}
            Items.UpdateLayout();await RestoreBrowseAnchorAsync(anchor);
            if(disposed||token.IsCancellationRequested)return;
            UpdateBrowseFooter(FormatLoadedPageRange(browseStart,buffer.End-browseStart,buffer.Total),browseStart>0,buffer.End<buffer.Total);
        }
        catch(OperationCanceledException){}
        catch(Exception ex){if(!disposed){browseFailed=true;Failure(ex);}}
        finally
        {
            extending=false;transitions.Release();
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private async void BrowseEdgeShortcut(KeyboardAccelerator sender,KeyboardAcceleratorInvokedEventArgs args)
    {
        if(!ready||disposed||dialogOpen||saving||viewerWindow is not null||folderHubOpen||shelfHubOpen)return;
        // Preserve Ctrl+Home/End for caret movement and native editor selection.
        for(var node=FocusManager.GetFocusedElement(XamlRoot) as DependencyObject;node is not null&&node!=this;node=VisualTreeHelper.GetParent(node))
            if(node is TextBox or RichEditBox or PasswordBox or ComboBox or NumberBox or Slider)return;
        args.Handled=true;await JumpBrowseEdgeAsync(sender.Key==Windows.System.VirtualKey.End);
    }
    private async Task JumpBrowseEdgeAsync(bool last)
    {
        if(extending||browseReflowing||PendingSearch||resultSession is not {} session||resultWindow is not {} window||session.Total==0||!await transitions.WaitAsync(0))return;
        extending=true;var token=renderCancellation.Token;
        try
        {
            var start=last?Math.Max(0,session.Total-ResultWindow.BlockSize):0;
            var result=await window.ReadAsync(start,Math.Min(ResultWindow.BlockSize,session.Total-start),token);
            if(disposed||token.IsCancellationRequested||PendingSearch||!ReferenceEquals(session,resultSession))return;
            ResetBrowse(start,result);rows=browseBuffer!.Items.ToList();page=start/resultPageSize;
            RenderRows();RestoreSelection();Items.UpdateLayout();await YieldBrowseLayoutAsync();
            if(disposed||!ReferenceEquals(session,resultSession))return;
            resultScroll?.ChangeView(null,last?resultScroll.ScrollableHeight:0,null,true);
            await YieldBrowseLayoutAsync();
            UpdateBrowseFooter(FormatLoadedPageRange(start,rows.Count,browseBuffer.Total),start>0,browseBuffer.End<browseBuffer.Total);
        }
        catch(OperationCanceledException){}
        catch(Exception error){if(!disposed)Failure(error);}
        finally
        {
            extending=false;transitions.Release();
            if(PendingSearch&&!disposed){searchTimer.Stop();searchTimer.Start();}
        }
    }
    private (string Key,double Y)? CaptureBrowseAnchor()
    {
        (string Key,double Y,int Index)? first=null;
        foreach(var container in containerCleanup.Keys)
        {
            if(!container.IsLoaded||container.Tag is not int id)continue;
            var y=container.TransformToVisual(Items).TransformPoint(new Point()).Y;
            if(!double.IsFinite(y)||y+container.ActualHeight<=0||y>=Items.ActualHeight)continue;
            var index=rows.FindIndex(row=>row.Id==id);if(index<0)continue;
            // Recycled container insertion order is not visual order. Preserve
            // the leading visible row, and the first result within a tile row.
            if(first is null||y<first.Value.Y||y==first.Value.Y&&index<first.Value.Index)
                first=(RowKey(id),y,index);
        }
        return first is {} value?(value.Key,value.Y):null;
    }
    private void ReflowBrowse(Action change)
    {
        if(browseReflowing||extending||!ready||disposed||folderHubOpen||shelfHubOpen||Items.Visibility!=Visibility.Visible)
        {change();return;}
        var anchor=CaptureBrowseAnchor();
        var atEnd=resultScroll is not null&&resultScroll.ScrollableHeight>2&&browseBuffer is not null&&browseBuffer.End==browseBuffer.Total
            &&Math.Abs(resultScroll.ScrollableHeight-resultScroll.VerticalOffset)<2;
        if(anchor is null&&!atEnd){change();return;}
        var session=resultSession;var buffer=browseBuffer;var start=buffer?.Start;var end=buffer?.End;
        browseReflowing=true;
        try{change();Items.UpdateLayout();_ = FinishBrowseReflowAsync(anchor,atEnd,session,buffer,start,end);}
        catch{browseReflowing=false;throw;}
    }
    private async Task FinishBrowseReflowAsync((string Key,double Y)? anchor,bool atEnd,object? session,ResultBuffer? buffer,int? start,int? end)
    {
        try
        {
            await YieldBrowseLayoutAsync();
            if(disposed||!ReferenceEquals(session,resultSession)||!ReferenceEquals(buffer,browseBuffer)||buffer?.Start!=start||buffer?.End!=end)return;
            Items.UpdateLayout();
            if(atEnd&&resultScroll is not null)
            {
                resultScroll.ChangeView(null,resultScroll.ScrollableHeight,null,true);
                await YieldBrowseLayoutAsync();
            }
            else await RestoreBrowseAnchorAsync(anchor);
        }
        catch(Exception error){if(!disposed)Failure(error);}
        finally{browseReflowing=false;}
    }
    private Task YieldBrowseLayoutAsync()
    {
        var completion=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if(!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low,()=>completion.TrySetResult()))completion.TrySetResult();
        return completion.Task;
    }
    private async Task RestoreBrowseAnchorAsync((string Key,double Y)? anchor)
    {
        if(anchor is not {} value||resultScroll is null)return;
        // ScrollIntoView and native collection anchoring can finish after this
        // callback. Keep extending=true through layout so those transient offsets
        // cannot start a reverse fetch and immediately restore evicted rows.
        Items.ScrollIntoView(value.Key,ScrollIntoViewAlignment.Leading);
        await YieldBrowseLayoutAsync();if(disposed)return;Items.UpdateLayout();
        if(Items.ContainerFromItem(value.Key) is ListViewItem container)
        {
            var y=container.TransformToVisual(Items).TransformPoint(new Point()).Y;
            resultScroll.ChangeView(null,resultScroll.VerticalOffset+y-value.Y,null,true);
        }
        await YieldBrowseLayoutAsync();
    }
}
