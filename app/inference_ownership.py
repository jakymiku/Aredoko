"""Explicit image/audio/video owners share one resident-worker budget.

No GPU API or process is started here. The image, audio and video paths
can keep their own namespaces while relinquishing the other idle worker before
loading. A failed release never grants the next owner permission to infer.
"""
import threading


class InferenceOwnership:
    def __init__(self):
        self.lock=threading.Lock()
        self.owners=[]
        self.registry=threading.Lock()

    def for_encoder(self,encoder,*,role=None):
        if not callable(getattr(encoder,'release',None)):
            raise ValueError('An explicitly releasable owned encoder is required')
        if role is not None and role not in ('image','audio','video'):
            raise ValueError('Invalid inference owner role')
        with self.registry:
            for owner in self.owners:
                if owner.encoder is encoder:
                    if role is not None and owner.role!=role:raise ValueError('Encoder already has another role')
                    return owner
            occupied={owner.role for owner in self.owners}
            # Old positional callers retain the two image/audio slots. Video
            # requires explicit registration, never an unbounded extra owner.
            if role is None:role=next((r for r in ('image','audio') if r not in occupied),None)
            if role is None or role in occupied:raise ValueError('Inference owner role is already occupied')
            if bool(getattr(encoder,'resident',False)):
                raise ValueError('Register an inactive encoder before loading its model')
            owner=_OwnerLock(self,encoder,role);self.owners.append(owner)
            return owner


class _OwnerLock:
    def __init__(self,group,encoder,role):
        self.group,self.encoder=group,encoder
        self.role=role
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
