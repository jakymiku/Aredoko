"""Registered-root metadata, independent of media items and physical paths."""
from shelves import identity

VERSION=3
STARTUP_MODES=('none','list','list_and_ai')
TABLE='registered_root_preferences'
DDL="CREATE TABLE registered_root_preferences(root_id INTEGER PRIMARY KEY REFERENCES library_roots(id) ON DELETE CASCADE,favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite IN (0,1)),startup_scan TEXT NOT NULL DEFAULT 'none' CHECK(startup_scan IN ('none','list','list_and_ai')))"

class RootPreferences:
    def __init__(self,connect):self.connect=connect
    def migrate(self):
        with self.connect() as db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            version=db.execute('PRAGMA user_version').fetchone()[0]
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version==VERSION:
                if TABLE not in tables or [r[1] for r in db.execute('PRAGMA table_info('+TABLE+')')]!=['root_id','favorite','startup_scan']:raise ValueError('Incomplete registered-root preferences schema')
                return
            if version==2:
                if TABLE not in tables or [r[1] for r in db.execute('PRAGMA table_info('+TABLE+')')]!=['root_id','favorite']:raise ValueError('Invalid legacy root preferences')
                db.execute("ALTER TABLE registered_root_preferences ADD COLUMN startup_scan TEXT NOT NULL DEFAULT 'none' CHECK(startup_scan IN ('none','list','list_and_ai'))")
            elif version==1 and TABLE not in tables and {'shelves','item_shelves','root_shelves'}<=tables:self._create(db)
            else:raise ValueError('Unsupported registered-root preferences migration')
            db.execute('PRAGMA user_version=3')
    @staticmethod
    def _create(db):db.execute(DDL)
    def set_favorite(self,root_id,favorite):
        root_id=identity(root_id)
        if type(favorite) is not bool:raise ValueError('Expected a boolean')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT id FROM library_roots WHERE id=?',(root_id,)).fetchone() is None:raise KeyError(root_id)
            db.execute('INSERT INTO registered_root_preferences(root_id,favorite) VALUES(?,?) ON CONFLICT(root_id) DO UPDATE SET favorite=excluded.favorite',(root_id,int(favorite)))
        return {'root_id':root_id,'favorite':favorite}
    def set_startup_scan(self,root_ids,mode):
        if type(mode) is not str or mode not in STARTUP_MODES:raise ValueError('Invalid startup scan mode')
        if not isinstance(root_ids,list) or not 1<=len(root_ids)<=256 or len(set(map(identity,root_ids)))!=len(root_ids):raise ValueError('Invalid root selection')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for root in root_ids:
                if db.execute('SELECT id FROM library_roots WHERE id=?',(root,)).fetchone() is None:raise KeyError(root)
            db.executemany('INSERT INTO registered_root_preferences(root_id,startup_scan) VALUES(?,?) ON CONFLICT(root_id) DO UPDATE SET startup_scan=excluded.startup_scan',((root,mode) for root in root_ids))
        return {'root_ids':root_ids,'mode':mode}
