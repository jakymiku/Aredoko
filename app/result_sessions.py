"""Short-lived disk-backed, fixed-order search results shared by native clients.

Providers emit existing bounded pages exactly once (AI providers keep one score
spool alive for this consumer). Subsequent range/neighbor reads never rerank.
No source bytes, model weights or all-result metadata lists live in memory.
"""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import threading
import time

from library_index import _excluded, is_folder_book
from previews import _safe_path, IMAGE_MIME, PreviewReader, PreviewUnavailable, ReaderChanged

MAX_SESSIONS = 3
MAX_BYTES = 512 * 1024 * 1024
IDLE_SECONDS = 15 * 60
_MISSING = object()


class ResultUnavailable(ValueError):
    def __init__(self, message='Result session unavailable', *, conditions=None, expired=False):
        super().__init__(message)
        self.conditions, self.expired = conditions, expired


class ResultCapacity(ValueError):
    pass


class IndexStamp:
    """Connection-relative index change monitor, with no retained read transaction."""
    def __init__(self, ai):
        self.ai = ai
        self.db = None
        self.lock = threading.Lock()
        self.closed = False

    def __call__(self):
        with self.lock:
            if self.closed:
                return None
            if self.db is None:
                self.db = sqlite3.connect(self.ai.store.path, check_same_thread=False)
            return self.ai.profile.key, self.db.execute('PRAGMA data_version').fetchone()[0]

    def close(self):
        with self.lock:
            if not self.closed:
                self.closed = True
                if self.db is not None: self.db.close()


class FrozenResult:
    def __init__(self, catalog, conditions, stamp, budget, *, parent=None):
        self.catalog, self.conditions, self.stamp = catalog, conditions, stamp
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.resources = ExitStack()
        self.directory = tempfile.TemporaryDirectory(prefix='aredoko-results-', dir=parent)
        self.resources.callback(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'results.sqlite'
        try:
            self.db = sqlite3.connect(self.path, check_same_thread=False)
            self.resources.callback(self.db.close)
            self.db.execute('PRAGMA journal_mode=MEMORY')
            self.db.execute('PRAGMA cache_size=-2048')
            self.db.execute('PRAGMA temp_store=FILE')
            self.db.execute('PRAGMA max_page_count=' + str(budget // 4096))
            self.db.executescript('CREATE TABLE results(ordinal INTEGER PRIMARY KEY,item_id INTEGER UNIQUE,image INTEGER NOT NULL,payload TEXT NOT NULL);'
                                 'CREATE INDEX result_images ON results(image,ordinal);')
            self.db.set_progress_handler(lambda: int(self.stop.is_set()), 1000)
        except BaseException:
            self.resources.close()
            raise
        self.total = 0
        self.metadata = {}
        self.origin = None
        self.state = 'building'
        self.progress_lock = threading.Lock()
        self.expected_total = None
        self.processed = 0
        self.last_used = time.monotonic()
        self.capture_executor = None

    def check(self):
        if self.stop.is_set():
            raise ResultUnavailable(conditions=self.conditions)
        if self.stamp() != self.initial_stamp:
            raise ResultUnavailable('Search conditions or index changed; refresh results', conditions=self.conditions)

    def materialize(self, provider):
        self.initial_stamp = self.stamp()
        with self.lock:
            def consume(page):
                number = 0
                expected = None
                while True:
                    self.check()
                    result = page(number)
                    self.check()
                    if expected is None:
                        expected = result['total']
                        if type(expected) is not int or expected < 0:
                            raise ValueError('Invalid result count')
                        with self.progress_lock:
                            self.expected_total = expected
                        self.metadata = {k: v for k, v in result.items() if k not in ('items', 'page', 'limit')}
                        if self.metadata.get('origin_id') is not None:
                            self.origin = self._current(self.catalog.get(self.metadata['origin_id']), capture=True)
                    if result['total'] != expected or result['page'] != number:
                        raise ResultUnavailable('Search changed during creation', conditions=self.conditions)
                    items = result['items']
                    if len(items) > 120 or (not items and self.total != expected):
                        raise ResultUnavailable('Incomplete search results', conditions=self.conditions)
                    for item in self._currents(items,capture=True):
                        payload = json.dumps(item, ensure_ascii=False, separators=(',', ':'))
                        if len(payload.encode('utf-8')) > 512 * 1024:
                            raise ResultCapacity('Result evidence exceeds workspace limit')
                        image = (item.get('kind') == 'image' and item.get('availability') == 'present'
                                 and Path(item.get('relative_path', '')).suffix.casefold() in IMAGE_MIME)
                        self.db.execute('INSERT INTO results VALUES(?,?,?,?)', (self.total, item['id'], int(image), payload))
                        self.total += 1
                    self.db.commit()
                    if self.total > expected:
                        raise ResultUnavailable('Invalid result count', conditions=self.conditions)
                    with self.progress_lock:
                        self.processed = self.total
                    if self.total == expected:
                        break
                    number += 1
                return self.metadata
            try:
                # Overlap bounded source I/O; publish only after every owned
                # check has joined. The original physical guards stay intact.
                with ThreadPoolExecutor(max_workers=4, thread_name_prefix='result-source') as executor:
                    self.capture_executor = executor
                    try:
                        provider(consume)
                    finally:
                        self.capture_executor = None
                self.check()
                with self.progress_lock:
                    self.state = 'ready'
            except sqlite3.Error as error:
                if self.stop.is_set():
                    raise ResultUnavailable(conditions=self.conditions) from error
                raise ResultCapacity('Result workspace unavailable or full; no partial results published') from error
            finally:
                self.last_used = time.monotonic()

    def bytes(self):
        return self.path.stat().st_size

    def _currents(self,items,*,capture=False):
        # One bounded page connection/query, no persistent access cache. The
        # generation is checked before/after and every physical source is probed.
        self.check()
        if not items:return
        with self.catalog.connect() as db:
            ids=[item['id'] for item in items]
            rows=db.execute('SELECT '+self.catalog.FIELDS+',r.path,r.excludes_json,r.enabled'+self.catalog.JOIN+
                'JOIN library_roots r ON r.id=l.root_id WHERE i.id IN ('+','.join('?' for _ in ids)+')',ids).fetchall()
            grouped={}
            for row in rows:grouped.setdefault(row['id'],[]).append(row)
            prepared=[]
            for item in items:
                choices=grouped.get(item['id'],[])
                if len(choices)>1:
                    # Preserve the exact legacy representative-location query
                    # for the uncommon multiple-location case.
                    row=db.execute('SELECT '+self.catalog.FIELDS+',r.path,r.excludes_json,r.enabled'+self.catalog.JOIN+
                        'JOIN library_roots r ON r.id=l.root_id WHERE i.id=?',(item['id'],)).fetchone()
                else:row=choices[0] if choices else None
                prepared.append((item,row))
            roots=threading.local() if capture else None
            def validate(pair):
                item,row=pair
                cache=None
                if roots is not None:
                    if not hasattr(roots,'paths'):roots.paths={}
                    cache=roots.paths
                return self._current(item,capture=capture,row=row,root_cache=cache)
            if capture and len(prepared)>=16 and self.capture_executor is not None:
                # At most one provider page (120) is queued; map keeps rank.
                yield from self.capture_executor.map(validate,prepared)
            else:
                for pair in prepared:yield validate(pair)
        self.check()

    def _current(self, payload, *, capture=False, for_viewer=False, row=_MISSING, root_cache=None):
        # No access cache: registration/exclusion/ancestors/physical version are
        # checked even when the frozen metadata/rank was already read before.
        if self.stop.is_set():raise ResultUnavailable(conditions=self.conditions)
        item_id = payload['id']
        if row is _MISSING:
            with self.catalog.connect() as db:
                row = db.execute('SELECT ' + self.catalog.FIELDS + ',r.path,r.excludes_json,r.enabled' + self.catalog.JOIN +
                    'JOIN library_roots r ON r.id=l.root_id WHERE i.id=?', (item_id,)).fetchone()
        if row is None or not row['enabled'] or row['availability'] == 'excluded' or _excluded(row['relative_path'], tuple(json.loads(row['excludes_json']))):
            raise ResultUnavailable('Result scope changed; refresh results', conditions=self.conditions)
        current = self.catalog.item(row)
        for field in ('id', 'title', 'kind', 'tags', 'shelf', 'favorite', 'reviewed', 'root_id', 'relative_path', 'size_bytes', 'mtime_ns', 'availability'):
            if current.get(field) != payload.get(field):
                raise ResultUnavailable('Result metadata changed; refresh results', conditions=self.conditions)
        signature = None
        if current['availability'] == 'present':
            try:
                if is_folder_book(current['relative_path']):
                    signature = PreviewReader(self.catalog).tag_source(item_id)['revision']
                else:
                    # Only parsed/resolved root paths are reused, per thread and
                    # provider page. _safe_path still stats every ancestor and
                    # leaf on every item; no access/identity decision is cached.
                    _, info = _safe_path(row['path'], row['relative_path'], root_cache=root_cache,return_info=True)
                    if not stat.S_ISREG(info.st_mode) or (info.st_size, info.st_mtime_ns) != (row['size_bytes'], row['mtime_ns']):
                        signature = 'unavailable'
                    else:
                        signature = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
            except (OSError, PreviewUnavailable, ReaderChanged):
                # A disconnected source must not prevent an ordinary metadata
                # listing from being created. No source bytes are served here.
                signature = 'unavailable'
        if capture:
            return {**payload, '_source_identity': signature}
        if signature != payload.get('_source_identity'):
            raise ResultUnavailable('Result source identity changed; refresh results', conditions=self.conditions)
        if for_viewer and (signature == 'unavailable' or current['availability'] != 'present'):
            raise ResultUnavailable('Result source unavailable; refresh results', conditions=self.conditions)
        result = {key: value for key, value in payload.items() if key != '_source_identity'}
        if signature == 'unavailable':
            result.update(availability='unavailable', source_state='unavailable')
        return result

    def locate(self,item_ids):
        from selection_edits import selection_ids
        ids=selection_ids(item_ids)
        with self.lock:
            self.check()
            if self.state!='ready':raise ResultUnavailable(conditions=self.conditions)
            # Only IDs/ordinals are returned; source bytes and editing rights
            # still require the full guard at read/edit time.
            rows=self.db.execute('SELECT item_id,ordinal FROM results WHERE item_id IN ('+','.join('?' for _ in ids)+') ORDER BY ordinal',ids).fetchall()
            self.check();self.last_used=time.monotonic()
            return {'positions':[{'id':row[0],'ordinal':row[1]} for row in rows], 'conditions':self.conditions}

    def edit(self,item_ids,operation,shelf_ids):
        from selection_edits import validate_edit
        ids=validate_edit(item_ids,operation,shelf_ids)
        with self.lock:
            self.check()
            if self.state!='ready':raise ResultUnavailable(conditions=self.conditions)
            def validate():
                self.check()
                if self.origin is not None:self._current(self.origin,for_viewer=True)
                for offset in range(0,len(ids),120):
                    group=ids[offset:offset+120]
                    rows=self.db.execute('SELECT payload FROM results WHERE item_id IN ('+','.join('?' for _ in group)+')',group).fetchall()
                    if len(rows)!=len(group):raise ResultUnavailable('Selection left the search scope',conditions=self.conditions)
                    for item in self._currents([json.loads(row[0]) for row in rows]):
                        if item.get('availability')!='present':raise ResultUnavailable('Selection source unavailable',conditions=self.conditions)
                self.check()
            result=self.catalog.edit_result_selection(ids,operation,shelf_ids,validate,self.check)
            self.last_used=time.monotonic()
            return result

    def read(self, offset, limit):
        if type(offset) is not int or not 0 <= offset <= 9223372036854775807 or type(limit) is not int or not 1 <= limit <= 120:
            raise ValueError('Invalid result range')
        with self.lock:
            self.check()
            if self.state != 'ready':
                raise ResultUnavailable('Result session is still building', conditions=self.conditions)
            if self.origin is not None: self._current(self.origin, for_viewer=True)
            rows = self.db.execute('SELECT payload FROM results WHERE ordinal>=? ORDER BY ordinal LIMIT ?', (offset, limit)).fetchall()
            items = list(self._currents([json.loads(row[0]) for row in rows]))
            self.check()
            self.last_used = time.monotonic()
            return {**self.metadata, 'offset': offset, 'limit': limit, 'items': items,
                    'conditions': self.conditions, 'state': 'ready'}

    def neighbor(self, item_id, direction):
        if type(item_id) is not int or not 1 <= item_id <= 9223372036854775807 or type(direction) is not int or direction not in (-1, 1):
            raise ValueError('Invalid result neighbor')
        with self.lock:
            self.check()
            if self.origin is not None: self._current(self.origin, for_viewer=True)
            origin = self.db.execute('SELECT ordinal,payload FROM results WHERE item_id=?', (item_id,)).fetchone()
            if origin is None:
                raise ResultUnavailable('Current item is outside this result session', conditions=self.conditions)
            self._current(json.loads(origin[1]), for_viewer=True)
            sign, order = ('>', 'ASC') if direction == 1 else ('<', 'DESC')
            row = self.db.execute(f'SELECT ordinal,payload FROM results WHERE image=1 AND ordinal{sign}? ORDER BY ordinal {order} LIMIT 1', (origin[0],)).fetchone()
            target = None if row is None else {'ordinal': row[0], 'item': self._current(json.loads(row[1]), for_viewer=True)}
            self.check()
            self.last_used = time.monotonic()
            return {'neighbor': target, 'current_id': item_id, 'conditions': self.conditions}

    def close(self):
        self.stop.set()
        if not self.lock.acquire(blocking=False):
            return False
        try:
            self.resources.close()
        finally:
            self.lock.release()
        return True


class ResultSessions:
    def __init__(self, catalog, provider, *, index_stamp=None, index_stamp_for=None, parent=None, max_bytes=MAX_BYTES):
        if type(max_bytes) is not int or not 65536 <= max_bytes <= MAX_BYTES:
            raise ValueError('Invalid result workspace limit')
        self.catalog, self.provider, self.index_stamp = catalog, provider, index_stamp
        if index_stamp_for is not None and not callable(index_stamp_for):raise ValueError('Invalid result namespace stamp')
        self.index_stamp_for=index_stamp_for
        self.parent, self.max_bytes = parent, max_bytes
        self.sessions, self.retired = {}, {}
        self.lock, self.build_lock = threading.Lock(), threading.Lock()
        self.builder=None
        self.stopped = threading.Event()
        self.reaper = None

    @staticmethod
    def identifier(value):
        if type(value) is not str or re.fullmatch('[0-9a-f]{32}', value) is None:
            raise ValueError('Invalid result session ID')

    def _retire(self, key, conditions=None):
        now = time.monotonic()
        self.retired = {sid: old for sid, old in self.retired.items() if now - old[0] <= IDLE_SECONDS}
        if len(self.retired) >= 4096 and key not in self.retired and key not in self.sessions:
            raise ResultCapacity('Too many recently closed searches')
        self.retired[key] = (now, conditions)

    def _expire(self):
        now = time.monotonic()
        self.retired = {sid: old for sid, old in self.retired.items() if now - old[0] <= IDLE_SECONDS}
        for key, session in list(self.sessions.items()):
            if time.monotonic() - session.last_used > IDLE_SECONDS:
                self._retire(key, session.conditions)
                self.sessions.pop(key)
                session.close()

    def _reap(self):
        while not self.stopped.wait(5):
            with self.lock:
                self._expire()

    def create(self, session_id, conditions):
        self.identifier(session_id)
        if type(conditions) is not dict or len(json.dumps(conditions).encode()) > 16384:
            raise ValueError('Invalid result conditions')
        # JSON copy severs caller references; callers cannot mutate a live scope.
        conditions = json.loads(json.dumps(conditions))
        if not self.build_lock.acquire(blocking=False):
            raise ResultCapacity('A result session is already building')
        self.builder=threading.get_ident()
        session = None
        try:
            with self.lock:
                self._expire()
                if self.stopped.is_set() or session_id in self.retired or session_id in self.sessions:
                    raise ResultUnavailable(conditions=conditions)
                if len(self.sessions) >= MAX_SESSIONS or len(self.retired) >= 4096:
                    raise ResultCapacity('Close a result session before creating another')
                reserve = 256 * 1024 * 1024 if conditions.get('mode') in ('semantic', 'similar', 'pending-proposals-semantic','audio-direct') else 0
                budget = self.max_bytes - reserve - sum(s.bytes() for s in self.sessions.values())
                if budget < 65536:
                    raise ResultCapacity('Result workspace is full')
                def stamp():
                    base = self.catalog.result_generation()
                    return base, (self.index_stamp_for(conditions) if self.index_stamp_for is not None else
                                  self.index_stamp() if self.index_stamp is not None else None)
                session = FrozenResult(self.catalog, conditions, stamp, budget, parent=self.parent)
                self.sessions[session_id] = session
                if self.reaper is None:
                    self.reaper = threading.Thread(target=self._reap, daemon=True, name='result-session-owner')
                    self.reaper.start()
            session.materialize(lambda consume: self.provider(conditions, consume, session.stop.is_set))
            with self.lock:
                if self.stopped.is_set() or session_id not in self.sessions:
                    raise ResultUnavailable(conditions=conditions)
            return {'session_id': session_id, 'state': 'ready', 'total': session.total, 'conditions': conditions,
                    'range_limit': 120, 'idle_seconds': IDLE_SECONDS}
        except BaseException:
            if session is not None:
                self.cancel(session_id)
                session.close()
            raise
        finally:
            self.builder=None
            self.build_lock.release()

    def _get(self, session_id, *, allow_building=False):
        self.identifier(session_id)
        with self.lock:
            self._expire()
            result = self.sessions.get(session_id)
            if result is None:
                old = self.retired.get(session_id)
                raise ResultUnavailable(conditions=old[1] if old else None, expired=True)
            if result.state != 'ready' and not (allow_building and result.state == 'building'):
                raise ResultUnavailable('Result session is still building', conditions=result.conditions)
            return result

    def status(self, session_id):
        session = self._get(session_id, allow_building=True)
        # The owner can become visible immediately before materialize starts.
        # That initial zero-count state exposes no result metadata or rights.
        if hasattr(session, 'initial_stamp'):
            session.check()
        elif session.stop.is_set():
            raise ResultUnavailable(conditions=session.conditions)
        with session.progress_lock:
            return {'session_id': session_id, 'state': session.state,
                    'total': session.expected_total, 'processed': session.processed,
                    'conditions': session.conditions}

    def read(self, session_id, offset=0, limit=120):
        session = self._get(session_id)
        try:
            return {'session_id': session_id, **session.read(offset, limit)}
        except (OSError, PreviewUnavailable, ReaderChanged) as error:
            raise ResultUnavailable('Result source unavailable; refresh results', conditions=session.conditions) from error
        finally:
            if session.stop.is_set(): session.close()

    def neighbor(self, session_id, item_id, direction):
        session = self._get(session_id)
        try:
            return {'session_id': session_id, **session.neighbor(item_id, direction)}
        except (OSError, PreviewUnavailable, ReaderChanged) as error:
            raise ResultUnavailable('Result source unavailable; refresh results', conditions=session.conditions) from error
        finally:
            if session.stop.is_set(): session.close()

    def locate(self,session_id,item_ids):
        session=self._get(session_id)
        return {'session_id':session_id,**session.locate(item_ids)}

    def edit(self,session_id,item_ids,operation,shelf_ids):
        session=self._get(session_id)
        try:return {'session_id':session_id,**session.edit(item_ids,operation,shelf_ids)}
        except (OSError,PreviewUnavailable,ReaderChanged) as error:
            raise ResultUnavailable('Selection source unavailable; refresh search',conditions=session.conditions) from error
        finally:
            if session.stop.is_set():session.close()

    def cancel(self, session_id):
        self.identifier(session_id)
        with self.lock:
            session = self.sessions.get(session_id)
            self._retire(session_id, session.conditions if session else None)
            self.sessions.pop(session_id, None)
        if session is not None: session.close()
        return {'closed': True}

    def close(self,timeout=5):
        self.stopped.set()
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions: session.close()
        finished=True
        if self.builder!=threading.get_ident():
            finished=self.build_lock.acquire(timeout=timeout)
            if finished:self.build_lock.release()
        for session in sessions:finished=session.close() and finished
        if self.reaper is not None and self.reaper is not threading.current_thread():self.reaper.join(timeout=timeout)
        close_index = getattr(self.index_stamp, 'close', None)
        if close_index is not None: close_index()
        return finished
