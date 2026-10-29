"""Two bounded read-only validators; callbacks stay on the owning caller thread."""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import queue
import threading

WORKERS=2
QUEUE_LIMIT=64
PARALLEL_MIN_FILES=64


def verify_entries(entries,validate,cancelled,on_bytes,on_file):
    if len(entries)<PARALLEL_MIN_FILES:
        for entry in entries:validate(entry,cancelled,on_bytes);on_file()
        return
    stop=threading.Event();events=queue.Queue(QUEUE_LIMIT)
    def check():
        if cancelled():raise RuntimeError('Runtime validation cancelled')
    def emit(kind,value=0):
        while not stop.is_set():
            try:events.put((kind,value),timeout=.05);return
            except queue.Full:pass
        raise RuntimeError('Runtime validation cancelled')
    def work(entry):
        validate(entry,stop.is_set,lambda count:emit('bytes',count))
        emit('file')
    def drain():
        # Re-check failed futures between bounded batches even while a large
        # peer file continuously produces chunk progress.
        for _ in range(QUEUE_LIMIT):
            check()
            try:kind,value=events.get_nowait()
            except queue.Empty:return
            if kind=='bytes':on_bytes(value)
            else:on_file()
    check();pool=ThreadPoolExecutor(max_workers=WORKERS,thread_name_prefix='aredoko-runtime-verify')
    iterator=iter(entries);pending=set()
    try:
        for _ in range(WORKERS):
            entry=next(iterator,None)
            if entry is not None:pending.add(pool.submit(work,entry))
        while pending:
            check();drain();done,pending=wait(pending,timeout=.05,return_when=FIRST_COMPLETED)
            for future in done:
                future.result();entry=next(iterator,None)
                if entry is not None:pending.add(pool.submit(work,entry))
        drain();check()
    finally:
        # A failing observer, source change or owner cancellation stops all
        # readers before the owner's lease/cache/worker state can be released.
        stop.set();pool.shutdown(wait=True,cancel_futures=True)
