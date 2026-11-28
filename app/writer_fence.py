"""Cooperative write boundary shared by catalog, vectors and app settings.

Reads remain available. A pause waits for existing logical writes, then blocks
new writers until all pinned snapshots have been copied and released.
"""
from contextlib import contextmanager
import sqlite3,threading

class WriterFence:
    def __init__(self):
        self.condition=threading.Condition(threading.RLock());self.local=threading.local()
        self.active=0;self.pausing=False;self.owner=None
    @property
    def paused(self):
        with self.condition:return self.pausing
    @contextmanager
    def write(self,*,cancelled=None):
        with self.condition:
            depth=getattr(self.local,'depth',0)
            if depth==0:
                while self.pausing:
                    if cancelled is not None and cancelled():raise InterruptedError('Write cancelled while waiting for snapshot')
                    if self.owner==threading.get_ident():raise RuntimeError('Cannot write from the snapshot owner')
                    self.condition.wait(.05)
                if cancelled is not None and cancelled():raise InterruptedError('Write cancelled before publication')
                self.active+=1
            self.local.depth=depth+1
        try:yield
        finally:
            with self.condition:
                self.local.depth-=1
                if self.local.depth==0:self.active-=1;self.condition.notify_all()
    @contextmanager
    def pause(self,*,cancelled=None):
        def check():
            if cancelled is not None and cancelled():raise InterruptedError('Backup cancelled while waiting for writers')
        acquired=False
        try:
            with self.condition:
                if getattr(self.local,'depth',0):raise RuntimeError('Cannot pause inside a writer operation')
                while self.pausing:check();self.condition.wait(.05)
                check();self.pausing=True;self.owner=threading.get_ident();acquired=True
                while self.active:check();self.condition.wait(.05)
                check()
            yield
        finally:
            if acquired:
                with self.condition:self.pausing=False;self.owner=None;self.condition.notify_all()

class ConnectionWriteFence:
    def __init__(self,fence,observe=None):self.fence=fence;self.observe=observe;self.scope=None
    _WRITE_ACTIONS=tuple(getattr(sqlite3,name) for name in (
        'SQLITE_INSERT','SQLITE_UPDATE','SQLITE_DELETE',
        'SQLITE_CREATE_TABLE','SQLITE_CREATE_INDEX','SQLITE_CREATE_TRIGGER','SQLITE_CREATE_VIEW',
        'SQLITE_DROP_TABLE','SQLITE_DROP_INDEX','SQLITE_DROP_TRIGGER','SQLITE_DROP_VIEW',
        'SQLITE_ALTER_TABLE','SQLITE_REINDEX','SQLITE_ANALYZE',
    ) if hasattr(sqlite3,name))
    def authorize(self,action,first,second,database,trigger):
        writing=action in self._WRITE_ACTIONS or action==sqlite3.SQLITE_TRANSACTION and first=='BEGIN' or action==sqlite3.SQLITE_PRAGMA and second is not None
        if writing and self.scope is None:
            scope=self.fence.write();scope.__enter__();self.scope=scope
        return self.observe(action,first,second,database,trigger) if self.observe is not None else sqlite3.SQLITE_OK
    def close(self):
        if self.scope is not None:self.scope.__exit__(None,None,None);self.scope=None
