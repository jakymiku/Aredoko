"""Two explicit model owners share an inference lock and resident worker.

No GPU API or process is started here. The existing image and new audio paths
can keep their own namespaces while relinquishing the other idle worker before
loading. A failed release never grants the next owner permission to infer.
"""
import threading


class InferenceOwnership:
    def __init__(self):
        self.lock=threading.Lock()
        self.owners=[]
        self.registry=threading.Lock()

    def for_encoder(self,encoder):
        if not callable(getattr(encoder,'release',None)):
            raise ValueError('An explicitly releasable owned encoder is required')
        with self.registry:
            for owner in self.owners:
                if owner.encoder is encoder:return owner
            if len(self.owners)>=2:raise ValueError('Only the image and audio owners are supported')
            owner=_OwnerLock(self,encoder);self.owners.append(owner)
            return owner


class _OwnerLock:
    def __init__(self,group,encoder):
        self.group,self.encoder=group,encoder
        self.holder=None

    def acquire(self,blocking=True,timeout=-1):
        if not self.group.lock.acquire(blocking,timeout):return False
        try:
            with self.group.registry:peers=[peer.encoder for peer in self.group.owners if peer is not self]
            for peer in peers:
                if bool(getattr(peer,'resident',False)):
                    peer.release()
                    if bool(getattr(peer,'resident',False)):
                        raise RuntimeError('Previous model owner is still resident')
            self.holder=threading.get_ident()
            return True
        except BaseException:
            self.group.lock.release()
            raise

    def release(self):
        if self.holder!=threading.get_ident():raise RuntimeError('Inference lock is not owned by this thread')
        self.holder=None
        self.group.lock.release()

    def locked(self):return self.group.lock.locked()
    def __enter__(self):self.acquire();return self
    def __exit__(self,*exc):self.release()
