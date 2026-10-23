"""Per-launch restore handoff; never switches while an owned child is alive."""
import json
import os
from pathlib import Path
import re
from storage_lease import plain_path, identity, storage_lease
from storage_backup import validate_restored
from restore_switch import apply_restore_switch

class RestoreHandoff:
    def __init__(self, session_dir, instance, catalog):
        if not isinstance(instance,str) or re.fullmatch('[0-9a-f]{32}',instance) is None:
            raise ValueError('Invalid launcher instance')
        self.directory=plain_path(session_dir,directory=True)
        self.instance=instance
        self.catalog=plain_path(catalog,missing=True)
        self.request=self.directory/'restore-request.json'
        self.closed=self.directory/'restore-closed.json'

    def _write(self,path,value):
        plain_path(path,missing=True)
        with path.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False)
            stream.flush();os.fsync(stream.fileno())

    def _read(self,path):
        path=plain_path(path)
        if path.stat().st_size>16384:raise ValueError('Restore handoff exceeds limit')
        def unique(pairs):
            value={}
            for key,item in pairs:
                if key in value:raise ValueError('Duplicate handoff field')
                value[key]=item
            return value
        return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)

    def publish(self,job):
        if job.state!='completed' or job._thread.is_alive():raise ValueError('Restore preparation is not ready')
        staging=plain_path(job.staging_path,directory=True)
        if staging.parent!=self.catalog.parent/'restore-staging' or identity(staging)!=job._staging_identity:
            raise ValueError('Restore staging ownership changed')
        validate_restored(staging)
        self._write(self.request,{'instance':self.instance,'job_id':job.job_id,'catalog':str(self.catalog),
            'catalog_identity':list(identity(self.catalog)),'staging':str(staging),'staging_identity':list(identity(staging))})

    def mark_closed(self):
        # Called only after the backend's complete resource ExitStack succeeded.
        if self.request.exists():self._write(self.closed,{'instance':self.instance,'resources_closed':True})

    def finish(self,data,backend,frontend):
        if not self.request.exists():return None
        if backend is None or frontend is None or backend.poll()!=0 or frontend.poll()!=0:
            raise RuntimeError('Restore requires both owned children to exit normally')
        value=self._read(self.request);closed=self._read(self.closed)
        if not isinstance(value,dict) or set(value)!={'instance','job_id','catalog','catalog_identity','staging','staging_identity'} or value['instance']!=self.instance or value['catalog']!=str(self.catalog):
            raise ValueError('Restore handoff belongs to another launch')
        if closed!={'instance':self.instance,'resources_closed':True}:raise ValueError('Backend resource closure was not confirmed')
        if not isinstance(value['job_id'],str) or re.fullmatch('[0-9a-f]{32}',value['job_id']) is None:raise ValueError('Invalid restore job')
        staging=plain_path(value['staging'],directory=True)
        if staging.parent!=self.catalog.parent/'restore-staging' or list(identity(staging))!=value['staging_identity']:
            raise ValueError('Restore staging was replaced')
        # The old catalog's kernel owner lock must actually have been released.
        with storage_lease(self.catalog):
            if list(identity(self.catalog))!=value['catalog_identity']:raise ValueError('Source catalog was replaced')
            receipt=apply_restore_switch(data,staging,restore_id=value['job_id'])
        from restore_prepared import forget
        try:forget(staging.parent,value['job_id'])
        except (ValueError,OSError):pass  # Successful cutover remains authoritative.
        return {'restart':True,'receipt':receipt}
