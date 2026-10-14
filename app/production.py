"""Production catalog: read-only locations + separately editable metadata."""
import json
import threading
from contextlib import closing
from pathlib import Path
from catalog import Catalog
from library_index import LibraryIndex, TYPES
from search_terms import register as register_search_terms, split_terms
from term_relations import TermRelations


class ScanBusyError(ValueError):
    """A mutation should be retried after the atomic scan completes."""


class ProductionCatalog(Catalog):
    def __init__(self, path):
        # Never reinterpret an existing fictional demo database as a real library.
        import sqlite3
        if Path(path).exists():
            with closing(sqlite3.connect(path)) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'items' in tables and 'production_marker' not in tables:
                    raise ValueError('Use a separate production database, not the demo database')
        super().__init__(path)
        self.index = LibraryIndex(path)
        self.terms = TermRelations(self.connect)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS production_marker(version INTEGER);
                CREATE TABLE IF NOT EXISTS item_locations (
                    item_id INTEGER PRIMARY KEY REFERENCES items(id),
                    location_id INTEGER NOT NULL UNIQUE REFERENCES library_locations(id));
                CREATE TABLE IF NOT EXISTS scan_jobs (
                    id INTEGER PRIMARY KEY, root_id INTEGER NOT NULL, state TEXT NOT NULL,
                    discovered INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '');
                UPDATE scan_jobs SET state='interrupted',error='Restart the scan to resume safely'
                    WHERE state IN ('running','cancelling');
            ''')
        self._guard = threading.Lock()
        self._cancel = threading.Event()
        self._worker = None
        self._progress = 0
        # Recover a crash between index commit and catalog publication.
        self.sync_index()

    def seed(self, count=0):
        raise ValueError('Synthetic seeding is not available in production')

    def sync_index(self):
        with self.connect() as db:
            rows = db.execute('SELECT l.id,l.relative_path,l.kind,m.item_id,r.default_shelf FROM library_locations l '
                              'JOIN library_roots r ON r.id=l.root_id '
                              'LEFT JOIN item_locations m ON m.location_id=l.id').fetchall()
            for row in rows:
                if row['item_id'] is None:
                    item_id = db.execute('INSERT INTO items(title,kind,tags,shelf) VALUES(?,?,?,?)',
                                         (Path(row['relative_path']).name,row['kind'],'[]',row['default_shelf'])).lastrowid
                    db.execute('INSERT INTO item_locations VALUES(?,?)',(item_id,row['id']))
                else:
                    # Only source-derived fields; never overwrite user tags/favorites.
                    db.execute('UPDATE items SET title=?,kind=? WHERE id=?',
                               (Path(row['relative_path']).name,row['kind'],row['item_id']))

    @staticmethod
    def item(row):
        result = Catalog.item(row)
        result['synthetic'] = False
        return result

    JOIN = (' FROM items i JOIN item_locations m ON m.item_id=i.id '
            'JOIN library_locations l ON l.id=m.location_id ')
    FIELDS = 'i.*,l.root_id,l.relative_path,l.status AS availability,l.size_bytes,l.mtime_ns'

    def search(self, query='', kind='', view='all', page=0, limit=60, root_id=None):
        if kind and kind not in TYPES or view not in ('all','favorites','unreviewed','shelf'):
            raise ValueError('Invalid filter')
        if type(page) is not int or page<0 or not 1<=limit<=120 or len(query)>300:
            raise ValueError('Invalid paging')
        if root_id is not None and (type(root_id) is not int or not 1<=root_id<=9223372036854775807):
            raise ValueError('Invalid root filter')
        terms=split_terms(query)
        with self.connect() as db:
            if root_id is not None and not db.execute('SELECT 1 FROM library_roots WHERE id=? AND enabled=1',(root_id,)).fetchone():
                raise ValueError('Unknown registered root')
            # Every normalized word must appear in the title or tags (AND), so
            # "巫女 東方", "東方　巫女", "ﾚｲﾑ" and "REIMU" variants still find a
            # file. The user's related-term dictionary may add OR alternatives
            # to a word; it never removes the word or relaxes the filters.
            alternatives,expansions=self.terms.expand(terms,db)
            where, values = ["l.status<>'excluded'",'l.root_id IN (SELECT id FROM library_roots WHERE enabled=1)'], []
            if terms:
                register_search_terms(db,alternatives)
                where.append('aredoko_match(i.title,i.tags)>=0')
            if root_id is not None:
                where.append('l.root_id=?'); values.append(root_id)
            if kind:
                where.append('i.kind=?'); values.append(kind)
            where.extend({'favorites':['i.favorite=1'],'unreviewed':['i.reviewed=0'],
                          'shelf':["i.shelf<>''"],'all':[]}[view])
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
                                ' ORDER BY aredoko_specific(i.title,i.tags) DESC, i.id LIMIT ? OFFSET ?',
                                values+[limit,page*limit]).fetchall() if total else []
            elif expansions:
                # Items matching the typed words themselves come before
                # related-only candidates, then more specific matches (longer
                # spellings); ties keep the stable id order.
                rows=db.execute(f'SELECT {self.FIELDS},aredoko_match(i.title,i.tags) AS direct_hits'+clause+
                                ' ORDER BY direct_hits DESC, aredoko_specific(i.title,i.tags) DESC, i.id LIMIT ? OFFSET ?',
                                values+[limit,page*limit]).fetchall()
            else:
                rows=db.execute('SELECT '+self.FIELDS+clause+' ORDER BY i.id LIMIT ? OFFSET ?',
                                values+[limit,page*limit]).fetchall()
        items=[self.item(r) for r in rows]
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
            return super().update(ids, changes)

    def set_root_shelf(self,root_id,shelf,fill_unset=False):
        if type(root_id) is not int or not 1<=root_id<=9223372036854775807:raise ValueError('Invalid root ID')
        if not isinstance(shelf,str) or len(shelf)>80:raise ValueError('Shelf must be 80 characters or less')
        if type(fill_unset) is not bool:raise ValueError('Expected a boolean')
        shelf=shelf.strip()
        with self._guard:
            self._require_idle()
            with self.connect() as db:
                if not db.execute('UPDATE library_roots SET default_shelf=? WHERE id=? AND enabled=1',(shelf,root_id)).rowcount:
                    raise ValueError('Unknown registered root')
                changed=0
                if fill_unset and shelf:
                    changed=db.execute("UPDATE items SET shelf=? WHERE shelf='' AND id IN (SELECT m.item_id FROM item_locations m JOIN library_locations l ON l.id=m.location_id WHERE l.root_id=? AND l.status='present')",(shelf,root_id)).rowcount
        return {'default_shelf':shelf,'updated':changed}

    def unregister_root(self,root_id):
        with self._guard:
            self._require_idle()
            return self.index.unregister(root_id)

    def set_excludes(self, root_id, patterns):
        with self._guard:
            self._require_idle()
            return self.index.set_excludes(root_id, patterns)

    def shelves(self):
        with self.connect() as db:
            return [row[0] for row in db.execute("SELECT shelf FROM items WHERE shelf<>'' UNION SELECT default_shelf FROM library_roots WHERE default_shelf<>'' AND enabled=1 ORDER BY 1")]

    def add_root(self,path,excludes=None,default_shelf=''):
        if not isinstance(path,str) or not path or not Path(path).is_absolute():
            raise ValueError('Choose an absolute folder path')
        source=Path(path).resolve()
        if self.path.resolve().is_relative_to(source):
            raise ValueError('The library must not contain the application database')
        with self._guard:
            self._require_idle()
            return self.index.add_root(path,excludes,default_shelf)

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
