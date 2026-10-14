using Aredoko.Core;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.Foundation;
using Windows.Storage.Streams;

namespace Aredoko_WinUI;

// Native codec cursors are independent; only the view owns the range source.
[WinRT.GeneratedWinRTExposedType]
internal sealed partial class VideoRandomAccessStream : IRandomAccessStream
{
    private readonly VideoRangeSource source;
    private readonly object sync=new();
    private readonly SemaphoreSlim reads=new(1);
    private ulong position;
    private bool disposed;
    public VideoRandomAccessStream(VideoRangeSource source,ulong position=0){this.source=source;Seek(position);}
    public bool CanRead=>!disposed;
    public bool CanWrite=>false;
    public ulong Size{get=>(ulong)source.Manifest.SizeBytes;set=>throw new NotSupportedException();}
    public ulong Position{get{lock(sync)return position;}}
    public void Seek(ulong value){ObjectDisposedException.ThrowIf(disposed,this);if(value>Size)throw new ArgumentOutOfRangeException(nameof(value));lock(sync)position=value;}
    public IRandomAccessStream CloneStream()=>new VideoRandomAccessStream(source,Position);
    public IInputStream GetInputStreamAt(ulong value)=>new VideoRandomAccessStream(source,value);
    public IOutputStream GetOutputStreamAt(ulong value)=>throw new NotSupportedException();
    public IAsyncOperationWithProgress<IBuffer,uint> ReadAsync(IBuffer buffer,uint count,InputStreamOptions options)=>AsyncInfo.Run<IBuffer,uint>(async(token,progress)=>
    {
        ObjectDisposedException.ThrowIf(disposed,this);
        if(count>buffer.Capacity||count>8*VideoManifest.ChunkBytes)throw new ArgumentOutOfRangeException(nameof(count));
        await reads.WaitAsync(token).ConfigureAwait(false);
        try
        {
            var start=Position;var wanted=(int)Math.Min((ulong)count,Size-start);
            if((options&InputStreamOptions.Partial)!=0)wanted=Math.Min(wanted,VideoManifest.ChunkBytes);
            using var writer=new DataWriter();var done=0;
            while(done<wanted)
            {
                var bytes=await source.ReadAsync((long)start+done,Math.Min(VideoManifest.ChunkBytes,wanted-done),token).ConfigureAwait(false);
                writer.WriteBytes(bytes);done+=bytes.Length;progress.Report((uint)done);
            }
            ObjectDisposedException.ThrowIf(disposed,this);
            lock(sync){if(position==start)position+=(uint)done;}
            return writer.DetachBuffer();
        }
        finally{reads.Release();}
    });
    public IAsyncOperationWithProgress<uint,uint> WriteAsync(IBuffer buffer)=>throw new NotSupportedException();
    public IAsyncOperation<bool> FlushAsync()=>Task.FromResult(true).AsAsyncOperation();
    public void Dispose(){disposed=true;}
}
