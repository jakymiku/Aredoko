"""Kernel-owned catalog lease, shared by the production host and offline recovery."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat

class StorageBusyError(RuntimeError):pass
class StoragePathError(ValueError):pass

def plain_path(value, *, missing=False, directory=False):
    path=Path(os.path.abspath(value))
    # Check lexical ancestors before any resolve(): junctions must not disappear.
    for entry in reversed((path,*path.parents)):
        try:info=entry.lstat()
        except FileNotFoundError:
            if entry==path and missing:return path
            raise StoragePathError('Storage parent does not exist')
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise StoragePathError('Linked storage paths are not supported')
        folder=entry!=path or directory
        if folder and not stat.S_ISDIR(info.st_mode) or not folder and not stat.S_ISREG(info.st_mode):
            raise StoragePathError('Expected ordinary storage file or directory')
        if not folder and info.st_nlink!=1:raise StoragePathError('Hardlinked storage files are not supported')
    return path

def storage_parent(catalog):
    parent=Path(os.path.abspath(catalog)).parent;pending=[];current=parent
    while not current.exists():
        if current.parent==current:raise StoragePathError('Storage root unavailable')
        pending.append(current);current=current.parent
    plain_path(current,directory=True)
    for entry in reversed(pending):
        plain_path(entry.parent,directory=True)
        try:entry.mkdir(mode=0o700)
        except FileExistsError:pass
        plain_path(entry,directory=True)
    return parent

def identity(path):
    info=path.lstat();return info.st_dev,info.st_ino

@contextmanager
def storage_lease(catalog):
    catalog=plain_path(catalog,missing=True)
    lock=plain_path(str(catalog)+'.owner.lock',missing=True)
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    held=False
    try:
        plain_path(lock)
        info=os.fstat(fd)
        if (info.st_dev,info.st_ino)!=identity(lock):raise StoragePathError('Storage lease changed')
        os.lseek(fd,0,os.SEEK_SET)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(fd,msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            held=True
            if info.st_size==0:os.write(fd,b'0')
        except OSError as error:raise StorageBusyError('Close Aredoko before backup or recovery') from error
        yield
    finally:
        try:
            if held:
                os.lseek(fd,0,os.SEEK_SET)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(fd,msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(fd,fcntl.LOCK_UN)
        finally:os.close(fd)
        # Never unlink: another process could already hold this same lock inode.
