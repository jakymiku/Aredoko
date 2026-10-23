"""Transactional multi-shelf storage. Product activation waits for query/scan adapters.

No filesystem/media access. Migration preserves legacy scalar names and writes
version1 so older binaries (version0 maximum) refuse to open the migrated DB.
"""
from contextlib import contextmanager

VERSION=1
DDL=(
    "CREATE TABLE shelves(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE CHECK(length(name) BETWEEN 1 AND 80))",
    "CREATE TABLE item_shelves(item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,shelf_id INTEGER NOT NULL REFERENCES shelves(id) ON DELETE CASCADE,PRIMARY KEY(item_id,shelf_id))",
    "CREATE TABLE root_shelves(root_id INTEGER NOT NULL REFERENCES library_roots(id) ON DELETE CASCADE,shelf_id INTEGER NOT NULL REFERENCES shelves(id) ON DELETE CASCADE,PRIMARY KEY(root_id,shelf_id))",
    "CREATE INDEX item_shelves_by_shelf ON item_shelves(shelf_id,item_id)",
    "CREATE INDEX root_shelves_by_shelf ON root_shelves(shelf_id,root_id)",
)
TABLES={'shelves','item_shelves','root_shelves'}

def identity(value):
    if type(value) is not int or not 1<=value<=9223372036854775807:raise ValueError('Invalid shelf identity')
    return value

def name(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=80:raise ValueError('Shelf name must contain1 to80 characters')
    return value.strip()

class ShelfStore:
    def __init__(self,connect):self.connect=connect
    @contextmanager
    def transaction(self,require=True):
        with self.connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            if require and db.execute('PRAGMA user_version').fetchone()[0]not in (1,2):raise ValueError('Shelf migration required')
            yield db
    def migrate(self):
        with self.transaction(False) as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version in (1,2):
                if not TABLES<=tables:raise ValueError('Incomplete shelf schema')
                return
            if version!=0 or not {'production_marker','items','library_roots'}<=tables or TABLES&tables:raise ValueError('Unsupported shelf migration source')
            for statement in DDL:db.execute(statement)
            self._migrate_rows(db)
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:raise ValueError('Invalid shelf migration relationships')
            db.execute('PRAGMA user_version=1')
    @staticmethod
    def _migrate_rows(db):
        # Names are kept byte-for-byte, including old whitespace/case variants.
        db.execute("INSERT INTO shelves(name) SELECT shelf FROM items WHERE shelf<>'' UNION SELECT default_shelf FROM library_roots WHERE default_shelf<>'' ORDER BY 1")
        db.execute('INSERT INTO item_shelves SELECT i.id,s.id FROM items i JOIN shelves s ON s.name=i.shelf')
        db.execute('INSERT INTO root_shelves SELECT r.id,s.id FROM library_roots r JOIN shelves s ON s.name=r.default_shelf')
    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT s.id,s.name,(SELECT count(*) FROM item_shelves m WHERE m.shelf_id=s.id) item_count FROM shelves s ORDER BY s.name,s.id')]
    def create(self,value):
        value=name(value)
        with self.transaction() as db:
            sid=db.execute('INSERT INTO shelves(name) VALUES(?)',(value,)).lastrowid
        return sid
    def rename(self,sid,value):
        sid=identity(sid);value=name(value)
        with self.transaction() as db:
            old=db.execute('SELECT name FROM shelves WHERE id=?',(sid,)).fetchone()
            if old is None:raise KeyError(sid)
            db.execute('UPDATE shelves SET name=? WHERE id=?',(value,sid))
            db.execute('UPDATE items SET shelf=? WHERE shelf=?',(value,old[0]))
            db.execute('UPDATE library_roots SET default_shelf=? WHERE default_shelf=?',(value,old[0]))
    @staticmethod
    def _sync(db,entity,ids):
        table,key,relation,scalar=('items','item_id','item_shelves','shelf') if entity=='item' else ('library_roots','root_id','root_shelves','default_shelf')
        for oid in ids:
            row=db.execute(f'SELECT s.name FROM shelves s JOIN {relation} m ON m.shelf_id=s.id WHERE m.{key}=? ORDER BY s.id LIMIT 1',(oid,)).fetchone()
            db.execute(f'UPDATE {table} SET {scalar}=? WHERE id=?',(row[0] if row else '',oid))
    def replace(self,entity,object_ids,shelf_ids):
        if entity not in ('item','root'):raise ValueError('Invalid shelf entity')
        if not isinstance(object_ids,list) or not 1<=len(object_ids)<=256 or len(set(map(identity,object_ids)))!=len(object_ids):raise ValueError('Invalid shelf objects')
        if not isinstance(shelf_ids,list) or len(shelf_ids)>64 or len(set(map(identity,shelf_ids)))!=len(shelf_ids):raise ValueError('Invalid shelf selection')
        table,key,relation=('items','item_id','item_shelves') if entity=='item' else ('library_roots','root_id','root_shelves')
        with self.transaction() as db:
            self.replace_in_transaction(db,entity,object_ids,shelf_ids)
    @staticmethod
    def replace_in_transaction(db,entity,object_ids,shelf_ids):
        if entity not in ('item','root'):raise ValueError('Invalid shelf entity')
        if not isinstance(object_ids,list) or not 1<=len(object_ids)<=256 or len(set(map(identity,object_ids)))!=len(object_ids):raise ValueError('Invalid shelf objects')
        if not isinstance(shelf_ids,list) or len(shelf_ids)>64 or len(set(map(identity,shelf_ids)))!=len(shelf_ids):raise ValueError('Invalid shelf selection')
        table,key,relation=('items','item_id','item_shelves') if entity=='item' else ('library_roots','root_id','root_shelves')
        for sid in shelf_ids:
            if db.execute('SELECT 1 FROM shelves WHERE id=?',(sid,)).fetchone() is None:raise KeyError(sid)
        for oid in object_ids:
            if db.execute(f'SELECT id FROM {table} WHERE id=?',(oid,)).fetchone() is None:raise KeyError(oid)
        for oid in object_ids:
            db.execute(f'DELETE FROM {relation} WHERE {key}=?',(oid,))
            db.executemany(f'INSERT INTO {relation} VALUES(?,?)',[(oid,sid) for sid in shelf_ids])
        ShelfStore._sync(db,entity,object_ids)
    @staticmethod
    def scalar_in_transaction(db,entity,object_ids,value):
        table,key,relation=('items','item_id','item_shelves') if entity=='item' else ('library_roots','root_id','root_shelves')
        if not isinstance(value,str) or len(value)>80:raise ValueError('Invalid shelf name')
        for oid in object_ids:
            if db.execute(f'SELECT id FROM {table} WHERE id=?',(oid,)).fetchone() is None:raise KeyError(oid)
            count=db.execute(f'SELECT count(*) FROM {relation} WHERE {key}=?',(oid,)).fetchone()[0]
            if count>1:raise ValueError('Legacy scalar update would lose multiple shelves')
        sid=None
        if value:
            db.execute('INSERT OR IGNORE INTO shelves(name) VALUES(?)',(value,))
            sid=db.execute('SELECT id FROM shelves WHERE name=?',(value,)).fetchone()[0]
        for oid in object_ids:
            db.execute(f'DELETE FROM {relation} WHERE {key}=?',(oid,))
            if sid is not None:db.execute(f'INSERT INTO {relation} VALUES(?,?)',(oid,sid))
        ShelfStore._sync(db,entity,object_ids)

    def legacy_replace(self,item_ids,value):
        value='' if value=='' else name(value)
        if not isinstance(item_ids,list) or not 1<=len(item_ids)<=256 or len(set(map(identity,item_ids)))!=len(item_ids):raise ValueError('Invalid shelf objects')
        with self.transaction() as db:
            for oid in item_ids:
                if db.execute('SELECT id FROM items WHERE id=?',(oid,)).fetchone() is None:raise KeyError(oid)
                if db.execute('SELECT count(*) FROM item_shelves WHERE item_id=?',(oid,)).fetchone()[0]>1:raise ValueError('Legacy scalar update would lose multiple shelves')
            sid=None
            if value:
                db.execute('INSERT OR IGNORE INTO shelves(name) VALUES(?)',(value,));sid=db.execute('SELECT id FROM shelves WHERE name=?',(value,)).fetchone()[0]
            for oid in item_ids:
                db.execute('DELETE FROM item_shelves WHERE item_id=?',(oid,))
                if sid is not None:db.execute('INSERT INTO item_shelves VALUES(?,?)',(oid,sid))
            self._sync(db,'item',item_ids)
    def delete(self,sid):
        sid=identity(sid)
        with self.transaction() as db:
            if db.execute('SELECT id FROM shelves WHERE id=?',(sid,)).fetchone() is None:raise KeyError(sid)
            items=[r[0] for r in db.execute('SELECT item_id FROM item_shelves WHERE shelf_id=?',(sid,))]
            roots=[r[0] for r in db.execute('SELECT root_id FROM root_shelves WHERE shelf_id=?',(sid,))]
            db.execute('DELETE FROM shelves WHERE id=?',(sid,))
            self._sync(db,'item',items);self._sync(db,'root',roots)


def shelf_clause(shelf=None,shelf_ids=None):
    """OR within shelf IDs, AND with other backend conditions; no row fanout."""
    if shelf is not None and shelf_ids is not None:raise ValueError('Choose shelf names or IDs, not both')
    if shelf_ids is not None:
        if not isinstance(shelf_ids,list) or len(shelf_ids)>64 or len(set(map(identity,shelf_ids)))!=len(shelf_ids):raise ValueError('Invalid shelf selection')
        if not shelf_ids:return ['0=1'],[]
        return ['EXISTS(SELECT 1 FROM item_shelves sm WHERE sm.item_id=i.id AND sm.shelf_id IN ('+','.join('?' for _ in shelf_ids)+'))'],list(shelf_ids)
    if shelf is None:return [],[]
    if not isinstance(shelf,str) or len(shelf)>80:raise ValueError('Invalid shelf name')
    if shelf=='':return ["i.shelf=''"],[]
    return ['EXISTS(SELECT 1 FROM item_shelves sm JOIN shelves ss ON ss.id=sm.shelf_id WHERE sm.item_id=i.id AND ss.name=?)'],[shelf]
