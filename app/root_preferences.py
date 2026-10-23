"""Registered-root metadata, independent of media items and physical paths."""
from shelves import identity

VERSION=2
TABLE='registered_root_preferences'
DDL="CREATE TABLE registered_root_preferences(root_id INTEGER PRIMARY KEY REFERENCES library_roots(id) ON DELETE CASCADE,favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite IN (0,1)))"

class RootPreferences:
    def __init__(self,connect):self.connect=connect
    def migrate(self):
        with self.connect() as db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            version=db.execute('PRAGMA user_version').fetchone()[0]
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version==VERSION:
                if TABLE not in tables:raise ValueError('Incomplete registered-root preferences schema')
                return
            if version!=1 or TABLE in tables or not {'shelves','item_shelves','root_shelves'}<=tables:raise ValueError('Unsupported registered-root preferences migration')
            self._create(db)
            db.execute('PRAGMA user_version=2')
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
