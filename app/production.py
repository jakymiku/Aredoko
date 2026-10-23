"""Production catalog: read-only locations + separately editable metadata."""
import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path
from catalog import Catalog
from shelves import ShelfStore, shelf_clause
from library_index import LibraryIndex, TYPES, is_folder_book, folder_title
from search_terms import register as register_search_terms, split_terms, explain_matches
from term_relations import TermRelations


class HistoryChanged(ValueError):
    """A delayed history operation belongs to an obsolete clear generation."""


class ScanBusyError(ValueError):
    """A mutation should be retried after the atomic scan completes."""


class ProductionCatalog(Catalog):
    def __init__(self, path):
        self._result_generation = 0
        self._result_generation_lock = threading.Lock()
        # Never reinterpret an existing fictional demo database as a real library.
        if Path(path).exists() and Path(path).stat().st_size > 0:
            with closing(sqlite3.connect(path)) as db:
                user_ver = db.execute("PRAGMA user_version").fetchone()[0]
                if user_ver > 1:
                    raise ValueError(f"Unsupported database schema user_version {user_ver} > 1; please update Aredoko.")
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'items' in tables and 'production_marker' not in tables:
                    raise ValueError('Use a separate production database, not the demo database')
        super().__init__(path,supported_schema=1)
        self.index = LibraryIndex(path)
        self.terms = TermRelations(self.connect)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS production_marker(version INTEGER);
                CREATE TABLE IF NOT EXISTS item_locations (
                    item_id INTEGER PRIMARY KEY REFERENCES items(id),
                    location_id INTEGER NOT NULL UNIQUE REFERENCES library_locations(id));
                CREATE TABLE IF NOT EXISTS reader_progress (
                    item_id INTEGER PRIMARY KEY REFERENCES items(id),
                    revision TEXT NOT NULL, page INTEGER NOT NULL CHECK(page>=0 AND page<10000),
                    mode TEXT NOT NULL CHECK(mode IN ('single','rtl','ltr')));
                CREATE TABLE IF NOT EXISTS view_history (
                    item_id INTEGER PRIMARY KEY REFERENCES items(id),
                    opened_ns INTEGER NOT NULL, open_count INTEGER NOT NULL DEFAULT 1);
                CREATE INDEX IF NOT EXISTS view_history_recent ON view_history(opened_ns DESC);
                CREATE TABLE IF NOT EXISTS scan_jobs (
                    id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL, state TEXT NOT NULL,
                    discovered INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '');
                UPDATE scan_jobs SET state='interrupted',error='Restart the scan to resume safely'
                    WHERE state IN ('running','cancelling');
            ''')
        self._guard = threading.Lock()
        import secrets
        self._history_generation = secrets.token_hex(16)
        self._history_requires_generation = False
        self._state_epoch = 0
        self._cancel = threading.Event()
        self._worker = None
        self._progress = 0
        self.shelf_store=ShelfStore(self.connect)
        self.shelf_store.migrate()
        # Recover a crash between index commit and catalog publication.
        self.sync_index()

    @contextmanager
    def connect(self):
        # Observe query-affecting writes at the shared connection boundary.
        # View/position writes deliberately leave frozen result order intact.
        changed = False
        def observe(action, table, column, database, trigger):
            nonlocal changed
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
                if database == 'main' and table not in ('view_history', 'reader_progress', 'scan_jobs'):
                    changed = True
            return sqlite3.SQLITE_OK
        with super().connect() as db:
            db.set_authorizer(observe)
            before = db.total_changes
            try:
                yield db
            except BaseException:
                # Conservatively invalidate even a rolled-back write attempt.
                if changed and db.total_changes != before:
                    with self._result_generation_lock:
                        self._result_generation += 1
                raise
            else:
                if changed and db.total_changes != before:
                    # Publish generation and commit together to session readers.
                    with self._result_generation_lock:
                        db.commit()
                        self._result_generation += 1
            finally:
                db.set_authorizer(None)

    def result_generation(self):
        with self._result_generation_lock:
            return self._state_epoch, self._result_generation

    def seed(self, count=0):
        raise ValueError('Synthetic seeding is not available in production')

    def sync_index(self):
        with self._guard:
            with self.connect() as db:
                rows = db.execute('SELECT l.id,l.relative_path,l.kind,m.item_id,r.default_shelf,r.path FROM library_locations l '
                                  'JOIN library_roots r ON r.id=l.root_id '
                                  'LEFT JOIN item_locations m ON m.location_id=l.id').fetchall()
                for row in rows:
                    title = (folder_title(row['path'], row['relative_path']) if is_folder_book(row['relative_path'])
                             else Path(row['relative_path']).name)
                    if row['item_id'] is None:
                        item_id = db.execute('INSERT INTO items(title,kind,tags,shelf) VALUES(?,?,?,?)',
                                             (title,row['kind'],'[]',row['default_shelf'])).lastrowid
                        db.execute('INSERT INTO item_locations VALUES(?,?)',(item_id,row['id']))
                        if row['default_shelf']:
                            db.execute('INSERT OR IGNORE INTO shelves(name) VALUES(?)',(row['default_shelf'],))
                            db.execute('INSERT OR IGNORE INTO root_shelves SELECT l.root_id,s.id FROM library_locations l JOIN shelves s ON s.name=? WHERE l.id=? AND NOT EXISTS(SELECT 1 FROM root_shelves rs WHERE rs.root_id=l.root_id)',(row['default_shelf'],row['id']))
                        db.execute('INSERT INTO item_shelves SELECT ?,shelf_id FROM root_shelves WHERE root_id=(SELECT root_id FROM library_locations WHERE id=?)',(item_id,row['id']))
                    else:
                        # Only source-derived fields; never overwrite user tags/favorites.
                        db.execute('UPDATE items SET title=?,kind=? WHERE id=?',
                                   (title,row['kind'],row['item_id']))
            self._state_epoch += 1

    @staticmethod
    def item(row):
        result = Catalog.item(row)
        result['synthetic'] = False
        if isinstance(result.get('shelf_ids'),str):result['shelf_ids']=json.loads(result['shelf_ids'])
        return result

    JOIN = (' FROM items i JOIN item_locations m ON m.item_id=i.id '
            'JOIN library_locations l ON l.id=m.location_id ')
    FIELDS = 'i.*,(SELECT json_group_array(shelf_id) FROM (SELECT shelf_id FROM item_shelves WHERE item_id=i.id ORDER BY shelf_id)) shelf_ids,l.root_id,l.relative_path,l.status AS availability,l.size_bytes,l.mtime_ns'

    def search(self, query='', kind='', view='all', page=0, limit=60, root_id=None, root_ids=None, shelf=None, shelf_ids=None):
        if kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf','history'):
            raise ValueError('Invalid filter')
        if type(page) is not int or page<0 or not 1<=limit<=120 or len(query)>300:
            raise ValueError('Invalid paging')
        if root_id is not None and root_ids is not None:
            raise ValueError('Invalid root filter')
        if root_id is not None:
            if type(root_id) is not int or not 1<=root_id<=9223372036854775807:
                raise ValueError('Invalid root filter')
            selected_roots = [root_id]
        elif root_ids is not None:
            if (not isinstance(root_ids, (list, tuple)) or not 1<=len(root_ids)<=256
                    or any(type(r) is not int or not 1<=r<=9223372036854775807 for r in root_ids)
                    or len(set(root_ids)) != len(root_ids)):
                raise ValueError('Invalid root filter')
            selected_roots = sorted(root_ids)
        else:
            selected_roots = None
        terms=split_terms(query)
        with self.connect() as db:
            if selected_roots is not None:
                placeholders = ','.join('?' for _ in selected_roots)
                active = {r[0] for r in db.execute(f'SELECT id FROM library_roots WHERE enabled=1 AND id IN ({placeholders})', selected_roots)}
                if len(active) != len(selected_roots):
                    raise ValueError('Unknown registered root')
            # Every normalized word must appear in the title or tags (AND), so
            # "巫女 東方", "東方　巫女", "ﾚｲﾑ" and "REIMU" variants still find a
            # file. The user's related-term dictionary may add OR alternatives
            # to a word; it never removes the word or relaxes the filters.
            alternatives,expansions=self.terms.expand(terms,db)
            where, values = ["l.status<>'excluded'",'l.root_id IN (SELECT id FROM library_roots WHERE enabled=1)'], []
            # Exclusions apply immediately, including before the next scan.
            from library_index import _excluded
            rules={r['id']:tuple(json.loads(r['excludes_json'])) for r in db.execute('SELECT id,excludes_json FROM library_roots WHERE enabled=1')}
            db.create_function('aredoko_location_visible',2,lambda root,path:int(root in rules and not _excluded(path,rules[root])),deterministic=True)
            where.append('aredoko_location_visible(l.root_id,l.relative_path)=1')
            if terms:
                register_search_terms(db,alternatives)
                where.append('aredoko_match(i.title,i.tags)>=0')
            if selected_roots is not None:
                if len(selected_roots) == 1:
                    where.append('l.root_id=?'); values.append(selected_roots[0])
                else:
                    where.append('l.root_id IN (' + ','.join('?' for _ in selected_roots) + ')')
                    values.extend(selected_roots)
            if kind:
                where.append('i.kind=?'); values.append(kind)
            shelf_where,shelf_values=shelf_clause(shelf,shelf_ids)
            where.extend(shelf_where);values.extend(shelf_values)
            where.extend({'favorites':['i.favorite=1'],'unreviewed':['i.reviewed=0'],
                          'shelf':["i.shelf<>''"],'history':['EXISTS(SELECT 1 FROM view_history h WHERE h.item_id=i.id)'],'all':[]}[view])
            clause=self.JOIN+' WHERE '+' AND '.join(where)
            total=db.execute('SELECT count(*)'+clause,values).fetchone()[0]
            partial=None
            if total==0 and len(terms)>=2:
                # Nothing has every word: offer items missing exactly one word
                # (e.g. a generic word like "キャラ"), clearly labelled partial.
                # Filters still apply unchanged; longer matched spellings first, then id.
                required=len(terms)-1
                where[where.index('aredoko_match(i.title,i.tags)>=0')]=f'aredoko_cover(i.title,i.tags)>={required}'
                clause=self.JOIN+' WHERE '+' AND '.join(where)
                total=db.execute('SELECT count(*)'+clause,values).fetchone()[0]
                # An empty fallback stays an ordinary empty result, so the UI
                # never claims to show partial matches it does not have.
                partial={'words':len(terms),'required':required} if total else None
                rows=db.execute('SELECT '+self.FIELDS+clause+
                                (' ORDER BY (SELECT opened_ns FROM view_history h WHERE h.item_id=i.id) DESC, i.id DESC LIMIT ? OFFSET ?' if view=='history' else ' ORDER BY aredoko_specific(i.title,i.tags) DESC, i.id LIMIT ? OFFSET ?'),
                                values+[limit,page*limit]).fetchall() if total else []
            elif expansions:
                # Items matching the typed words themselves come before
                # related-only candidates, then more specific matches (longer
                # spellings); ties keep the stable id order.
                rows=db.execute(f'SELECT {self.FIELDS},aredoko_match(i.title,i.tags) AS direct_hits'+clause+
                                (' ORDER BY (SELECT opened_ns FROM view_history h WHERE h.item_id=i.id) DESC, i.id DESC LIMIT ? OFFSET ?' if view=='history' else ' ORDER BY direct_hits DESC, aredoko_specific(i.title,i.tags) DESC, i.id LIMIT ? OFFSET ?'),
                                values+[limit,page*limit]).fetchall()
            else:
                rows=db.execute('SELECT '+self.FIELDS+clause+(' ORDER BY (SELECT opened_ns FROM view_history h WHERE h.item_id=i.id) DESC, i.id DESC LIMIT ? OFFSET ?' if view=='history' else ' ORDER BY i.id LIMIT ? OFFSET ?'),
                                values+[limit,page*limit]).fetchall()
        items=[self.item(r) for r in rows]
        if terms:
            for item in items:
                item['search_evidence']=explain_matches(item['title'],item['tags'],alternatives)
        result={'total':total,'page':page,'limit':limit,'items':items}
        if partial:
            for item in items:
                item['match']='partial'
            result['partial']=partial
            if expansions: result['expansions']=expansions
        elif expansions:
            for item,row in zip(items,rows):
                item.pop('direct_hits',None)
                item['match']='direct' if row['direct_hits']==len(terms) else 'related'
            result['expansions']=expansions
        return result

    def get(self,item_id):
        if type(item_id) is not int or not 1<=item_id<=9223372036854775807:
            raise ValueError('Invalid item')
        with self.connect() as db:
            row=db.execute('SELECT '+self.FIELDS+self.JOIN+' WHERE i.id=?',(item_id,)).fetchone()
        if row is None: raise KeyError(item_id)
        return self.item(row)

    def _require_idle(self):
        if self._worker and self._worker.is_alive():
            raise ScanBusyError('Scan in progress; retry after it completes')

    def update(self, ids, changes):
        # Share the launch guard so a scan cannot start between the check and
        # metadata commit. Fail promptly rather than waiting on SQLite's writer.
        with self._guard:
            self._require_idle()
            shelf_ids=None
            if isinstance(changes,dict) and 'shelf_ids' in changes:
                if 'shelf' in changes:raise ValueError('Choose shelf names or IDs, not both')
                changes=dict(changes);shelf_ids=changes.pop('shelf_ids')
                from shelves import identity
                if not isinstance(shelf_ids,list) or len(shelf_ids)>64 or len(set(map(identity,shelf_ids)))!=len(shelf_ids):raise ValueError('Invalid shelf selection')
                # Validate IDs and optional metadata with the established contract.
                if changes:changes=Catalog.prepare_update(ids,changes)
                else:
                    Catalog.prepare_update(ids,{'favorite':False});changes={}
            else:
                changes=Catalog.prepare_update(ids,changes)
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                marks=','.join('?' for _ in ids)
                count=db.execute(f'SELECT count(*) FROM items WHERE id IN ({marks})',ids).fetchone()[0]
                if count!=len(set(ids)):raise KeyError('Some items no longer exist')
                if shelf_ids is not None:ShelfStore.replace_in_transaction(db,'item',ids,shelf_ids)
                if 'shelf' in changes:ShelfStore.scalar_in_transaction(db,'item',ids,changes['shelf'])
                if changes:
                    assignments=','.join(f'{key}=?' for key in changes)
                    db.execute(f'UPDATE items SET {assignments} WHERE id IN ({marks})',list(changes.values())+ids)
            return {'updated':count}

    def history_status(self):
        with self._guard:
            with self.connect() as db:
                count = db.execute('SELECT count(*) FROM view_history').fetchone()[0]
            return {'generation': self._history_generation, 'count': count}

    def delete_history(self, *, generation, item_ids=None, consent=False):
        import secrets
        if consent is not True:
            raise ValueError('Explicit history deletion consent required')
        if item_ids is not None and (not isinstance(item_ids, list) or not 1 <= len(item_ids) <= 256 or
                any(type(value) is not int or not 1 <= value <= 9223372036854775807 for value in item_ids) or len(set(item_ids)) != len(item_ids)):
            raise ValueError('Invalid history item IDs')
        with self._guard, self._result_generation_lock:
            if type(generation) is not str or generation != self._history_generation:
                raise HistoryChanged('History generation changed')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if item_ids is None:
                    removed = db.execute('DELETE FROM view_history').rowcount
                else:
                    removed = db.execute('DELETE FROM view_history WHERE item_id IN (' + ','.join('?' for _ in item_ids) + ')', item_ids).rowcount
            # Keep commit + invalidation indivisible to frozen history readers.
            self._result_generation += 1
            self._history_generation = secrets.token_hex(16)
            self._history_requires_generation = True
            return {'removed': removed, 'generation': self._history_generation}

    def record_view(self, item_id, generation=None):
        import time
        from library_index import _excluded
        if type(item_id) is not int or not 1<=item_id<=9223372036854775807:raise ValueError('Invalid item')
        with self._guard:
            if generation is None and self._history_requires_generation or generation is not None and (type(generation) is not str or generation != self._history_generation):
                raise HistoryChanged('History generation changed')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row=db.execute('SELECT l.status,l.relative_path,r.enabled,r.excludes_json FROM item_locations m JOIN library_locations l ON l.id=m.location_id JOIN library_roots r ON r.id=l.root_id WHERE m.item_id=?',(item_id,)).fetchone()
                if row is None or not row['enabled'] or row['status']!='present' or _excluded(row['relative_path'],tuple(json.loads(row['excludes_json']))):raise KeyError(item_id)
                db.execute('INSERT INTO view_history(item_id,opened_ns) VALUES(?,?) ON CONFLICT(item_id) DO UPDATE SET opened_ns=excluded.opened_ns,open_count=view_history.open_count+1',(item_id,time.time_ns()))
        return {'recorded':item_id}

    def reader_progress(self, item_id):
        if type(item_id) is not int or not 1 <= item_id <= 9223372036854775807:
            raise ValueError('Invalid item')
        with self.connect() as db:
            row=db.execute('SELECT l.relative_path,l.status,r.enabled,r.excludes_json FROM item_locations m '
                'JOIN library_locations l ON l.id=m.location_id JOIN library_roots r ON r.id=l.root_id '
                'WHERE m.item_id=?',(item_id,)).fetchone()
            if row is None or not row['enabled'] or row['status'] != 'present' or not (is_folder_book(row['relative_path']) or Path(row['relative_path']).suffix.lower() in ('.cbz','.zip')):
                raise KeyError(item_id)
            from library_index import _excluded
            if _excluded(row['relative_path'],tuple(json.loads(row['excludes_json']))):raise KeyError(item_id)
            saved=db.execute('SELECT revision,page,mode FROM reader_progress WHERE item_id=?',(item_id,)).fetchone()
            return {'progress':dict(saved) if saved is not None else None}

    def save_reader_progress(self, item_id, value, previews):
        import re
        from previews import ReaderChanged
        if type(item_id) is not int or not 1 <= item_id <= 9223372036854775807:
            raise ValueError('Invalid item')
        if not isinstance(value,dict) or set(value) != {'revision','page','mode'}:
            raise ValueError('Invalid reading progress')
        revision,page,mode=value['revision'],value['page'],value['mode']
        if type(revision) is not str or re.fullmatch(r'[0-9a-f]{64}',revision) is None or type(page) is not int or not 0 <= page < 10000 or type(mode) is not str or mode not in ('single','rtl','ltr'):
            raise ValueError('Invalid reading progress')
        # Same guard as source-derived index publication/metadata changes.
        # A stale reader never overwrites a newer archive's saved position.
        with self._guard:
            self._require_idle()
            manifest=previews.manifest(item_id)
            if revision != manifest['revision']:raise ReaderChanged('Archive changed')
            if page >= manifest['page_count']:raise ValueError('Invalid reading page')
            with self.connect() as db:
                db.execute('INSERT INTO reader_progress(item_id,revision,page,mode) VALUES(?,?,?,?) '
                    'ON CONFLICT(item_id) DO UPDATE SET revision=excluded.revision,page=excluded.page,mode=excluded.mode',
                    (item_id,revision,page,mode))
        return {'saved':True}

    def set_root_shelf(self,root_id,shelf,fill_unset=False):
        if type(root_id) is not int or not 1<=root_id<=9223372036854775807:raise ValueError('Invalid root ID')
        if not isinstance(shelf,str) or len(shelf)>80:raise ValueError('Shelf must be 80 characters or less')
        if type(fill_unset) is not bool:raise ValueError('Expected a boolean')
        shelf=shelf.strip()
        with self._guard:
            self._require_idle()
            with self.connect() as db:
                ShelfStore.scalar_in_transaction(db,'root',[root_id],shelf)
                if not db.execute('UPDATE library_roots SET default_shelf=? WHERE id=? AND enabled=1',(shelf,root_id)).rowcount:
                    raise ValueError('Unknown registered root')
                changed=0
                if fill_unset and shelf:
                    targets=[r[0] for r in db.execute("SELECT m.item_id FROM item_locations m JOIN library_locations l ON l.id=m.location_id JOIN items i ON i.id=m.item_id WHERE l.root_id=? AND l.status='present' AND i.shelf=''",(root_id,))]
                    if targets:ShelfStore.scalar_in_transaction(db,'item',targets,shelf)
                    changed=len(targets)
                    db.execute("UPDATE items SET shelf=? WHERE shelf='' AND id IN (SELECT m.item_id FROM item_locations m JOIN library_locations l ON l.id=m.location_id WHERE l.root_id=? AND l.status='present')",(shelf,root_id)).rowcount
        return {'default_shelf':shelf,'updated':changed}

    def unregister_root(self,root_id):
        with self._guard:
            self._require_idle()
            res = self.index.unregister(root_id)
            self._state_epoch += 1
            return res

    def purge_inactive_root(self, root_id, consent=False):
        """Permanently delete an unregistered root's DB records while leaving files untouched.

        Active roots are rejected. Root IDs are never reused after purge so any
        previously saved scope referencing root_id stays invalid rather than
        silently matching a later registered folder.
        """
        if consent is not True:
            raise ValueError('Explicit folder purge consent required')
        if type(root_id) is not int or not 1 <= root_id <= 9223372036854775807:
            raise ValueError('Invalid root ID')
        with self._guard:
            self._require_idle()
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT id, enabled FROM library_roots WHERE id=?', (root_id,)).fetchone()
                if row is None:
                    raise KeyError(root_id)
                if row['enabled']:
                    raise ValueError('Unregister the root before purging database records')
                # Profile DBs are separate files, not tables in this catalog.
                # Remove derived data first; any failure keeps manual records
                # and the inactive root available for a safe retry.
                from ai_store_cleanup import purge_profile_stores
                try:
                    purge_profile_stores(self.path, root_id)
                except ValueError as error:
                    raise ValueError('AI index cleanup failed; library records were kept') from error
                db.execute('UPDATE library_root_seq SET max_id = max(max_id, ?) WHERE id=1', (root_id,))
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                item_subquery = ('SELECT m.item_id FROM item_locations m '
                                 'JOIN library_locations l ON l.id=m.location_id WHERE l.root_id=?')
                if 'page_text_heads' in tables and 'page_snapshots' in tables:
                    db.execute(f'DELETE FROM page_text_heads WHERE snapshot_id IN (SELECT id FROM page_snapshots WHERE item_id IN ({item_subquery}))', (root_id,))
                if 'page_texts' in tables and 'page_snapshots' in tables:
                    db.execute(f'DELETE FROM page_texts WHERE snapshot_id IN (SELECT id FROM page_snapshots WHERE item_id IN ({item_subquery}))', (root_id,))
                if 'page_heads' in tables:
                    db.execute(f'DELETE FROM page_heads WHERE item_id IN ({item_subquery})', (root_id,))
                if 'page_entries' in tables and 'page_snapshots' in tables:
                    db.execute(f'DELETE FROM page_entries WHERE snapshot_id IN (SELECT id FROM page_snapshots WHERE item_id IN ({item_subquery}))', (root_id,))
                if 'page_snapshots' in tables:
                    db.execute(f'DELETE FROM page_snapshots WHERE item_id IN ({item_subquery})', (root_id,))
                if 'tag_proposals' in tables and 'tag_proposal_batches' in tables:
                    db.execute(f'DELETE FROM tag_proposals WHERE batch_id IN (SELECT id FROM tag_proposal_batches WHERE item_id IN ({item_subquery}))', (root_id,))
                if 'tag_proposal_batches' in tables:
                    db.execute(f'DELETE FROM tag_proposal_batches WHERE item_id IN ({item_subquery})', (root_id,))
                for table in ('ai_vectors','ai_video_frames','ai_source_contracts','ai_proposal_vectors','ai_page_vectors','ai_audio_segments','ai_audio_acoustics'):
                    if table in tables:
                        db.execute(f'DELETE FROM {table} WHERE item_id IN ({item_subquery})', (root_id,))
                db.execute(f'DELETE FROM reader_progress WHERE item_id IN ({item_subquery})', (root_id,))
                db.execute(f'DELETE FROM view_history WHERE item_id IN ({item_subquery})', (root_id,))
                db.execute('CREATE TEMP TABLE purge_item_ids(id INTEGER PRIMARY KEY)')
                db.execute('INSERT INTO purge_item_ids '+item_subquery,(root_id,))
                removed_items=db.execute('SELECT count(*) FROM purge_item_ids').fetchone()[0]
                db.execute('DELETE FROM item_locations WHERE location_id IN (SELECT id FROM library_locations WHERE root_id=?)', (root_id,))
                db.execute('DELETE FROM item_shelves WHERE item_id IN (SELECT id FROM purge_item_ids)')
                db.execute('DELETE FROM root_shelves WHERE root_id=?',(root_id,))
                db.execute('DELETE FROM items WHERE id IN (SELECT id FROM purge_item_ids)')
                removed_locations = db.execute('DELETE FROM library_locations WHERE root_id=?', (root_id,)).rowcount
                db.execute('DELETE FROM scan_jobs WHERE root_id=?', (root_id,))
                db.execute('DELETE FROM library_roots WHERE id=? AND enabled=0', (root_id,))
            self._state_epoch += 1
        return {'purged': root_id, 'removed_items': removed_items, 'removed_locations': removed_locations}

    def set_excludes(self, root_id, patterns):
        with self._guard:
            self._require_idle()
            res = self.index.set_excludes(root_id, patterns)
            self._state_epoch += 1
            return res

    def change_shelf(self,operation,**values):
        with self._guard:
            self._require_idle()
            if operation=='create':return {'id':self.shelf_store.create(values['name'])}
            if operation=='rename':self.shelf_store.rename(values['shelf_id'],values['name']);return {'renamed':values['shelf_id']}
            if operation=='delete':self.shelf_store.delete(values['shelf_id']);return {'deleted':values['shelf_id']}
            if operation=='assign':self.shelf_store.replace(values['entity'],values['object_ids'],values['shelf_ids']);return {'updated':len(values['object_ids'])}
            raise ValueError('Invalid shelf operation')

    def shelf_descriptors(self):
        # Same registered-root/exclusion visibility as library search; no source I/O.
        from library_index import _excluded
        with self._guard, self.connect() as db:
            rules={r['id']:tuple(json.loads(r['excludes_json'])) for r in db.execute('SELECT id,excludes_json FROM library_roots WHERE enabled=1')}
            db.create_function('aredoko_shelf_visible',2,lambda root,path:int(root in rules and not _excluded(path,rules[root])),deterministic=True)
            rows=db.execute("WITH visible AS (SELECT sm.shelf_id,i.id,i.kind,l.status FROM item_shelves sm JOIN items i ON i.id=sm.item_id JOIN item_locations m ON m.item_id=i.id JOIN library_locations l ON l.id=m.location_id WHERE l.status<>'excluded' AND aredoko_shelf_visible(l.root_id,l.relative_path)=1) SELECT s.id,s.name,count(v.id) item_count,min(CASE WHEN v.status='present' AND v.kind IN ('image','book','archive','video') THEN v.id END) representative_id FROM shelves s LEFT JOIN visible v ON v.shelf_id=s.id GROUP BY s.id ORDER BY s.name,s.id").fetchall()
            result=[]
            for row in rows:
                entry=dict(row);representative=entry.pop('representative_id')
                sample=db.execute('SELECT '+self.FIELDS+self.JOIN+'WHERE i.id=?',(representative,)).fetchone() if representative is not None else None
                entry['representative']=self.item(sample) if sample is not None else None
                result.append(entry)
            return result

    def shelves(self):
        with self.connect() as db:
            return [row[0] for row in db.execute('SELECT name FROM shelves ORDER BY name,id')]

    def add_root(self,path,excludes=None,default_shelf='',folder_books=None,recursive=None):
        if not isinstance(path,str) or not path or not Path(path).is_absolute():
            raise ValueError('Choose an absolute folder path')
        source=Path(path).resolve()
        if self.path.resolve().is_relative_to(source):
            raise ValueError('The library must not contain the application database')
        with self._guard:
            self._require_idle()
            res = self.index.add_root(path,excludes,default_shelf,folder_books,recursive,metadata_hook=lambda db,rid: ShelfStore.scalar_in_transaction(db,'root',[rid],default_shelf.strip()))
            self._state_epoch += 1
            return res

    def scan_state(self):
        with self.connect() as db:
            row=db.execute('SELECT * FROM scan_jobs ORDER BY id DESC LIMIT 1').fetchone()
        result=dict(row) if row else {'id':0,'state':'idle','discovered':0,'error':''}
        if result['state'] in ('running','cancelling'):
            result['discovered']=self._progress
        return result

    def start_scan(self, root_id):
        if type(root_id) is not int or root_id<1: raise ValueError('Invalid root')
        with self._guard:
            if self._worker and self._worker.is_alive(): raise ValueError('A scan is already running')
            self.index.locations(root_id,limit=1)  # Validate before creating a job.
            self._cancel.clear(); self._progress=0
            with self.connect() as db:
                job=db.execute("INSERT INTO scan_jobs(root_id,state) VALUES(?,'running')",(root_id,)).lastrowid
            self._worker=threading.Thread(target=self._scan,args=(job,root_id),daemon=True)
            self._worker.start()
            return {'job_id':job}

    def _scan(self,job,root_id):
        state,error='complete',''
        try:
            result=self.index.scan(root_id,cancelled=self._cancel.is_set,
                                   progress=lambda n:setattr(self,'_progress',n))
            self.sync_index()
            self._progress=result['discovered']
        except InterruptedError: state='cancelled'
        except Exception as ex:
            # Store a concise local diagnostic, never returned with filesystem paths.
            state,error='failed',type(ex).__name__+': scan failed; check folder availability'
        with self.connect() as db:
            db.execute('UPDATE scan_jobs SET state=?,discovered=?,error=? WHERE id=?',
                       (state,self._progress,error,job))

    def cancel_scan(self):
        self._cancel.set()
        return {'cancel_requested':True}

    def close(self):
        self._cancel.set()
        if self._worker: self._worker.join(timeout=10)
        super().close()
