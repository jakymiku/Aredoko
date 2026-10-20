namespace Aredoko.Core;

// One in-flight save and one latest pending visible page. Close waits for both.
public sealed class ReaderProgressWriter(Func<ArchiveManifest,ReaderProgress,Task> save)
{
    private sealed record Pending(ArchiveManifest Book,ReaderProgress Progress,long Version);
    private readonly object sync=new();
    private Pending? pending;
    private Task drain=Task.CompletedTask;
    private bool running;
    private long version;
    public Exception? LastError {get;private set;}
    public event Action<Exception?>? StateChanged;
    public bool HasPending {get{lock(sync)return running;}}
    public void Queue(ArchiveManifest book,int page,ReaderDisplayMode mode)
    {
        book.Validate();var progress=new ReaderProgress(book.Revision,page,mode);progress.Validate();
        if(page>=book.PageCount)throw new ArgumentOutOfRangeException(nameof(page));
        lock(sync)
        {
            pending=new(book,progress,++version);
            if(!running){running=true;drain=DrainAsync();}
        }
    }
    public Task FlushAsync(){lock(sync)return drain;}
    private async Task DrainAsync()
    {
        while(true)
        {
            Pending current;
            lock(sync)
            {
                if(pending is null){running=false;return;}
                current=pending;pending=null;
            }
            Exception? error=null;
            try{await save(current.Book,current.Progress);}
            catch(Exception ex){error=ex;}
            bool notify;
            lock(sync){notify=current.Version==version;if(notify)LastError=error;}
            if(notify)StateChanged?.Invoke(error);
        }
    }
}
