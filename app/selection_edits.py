"""Atomic metadata edits for a bounded, validated search selection."""
from shelves import ShelfStore,identity

MAX_SELECTION=256
OPERATIONS=('favorite_add','favorite_remove','shelves_add','shelves_remove')

def selection_ids(values):
    if not isinstance(values,list) or not 1<=len(values)<=MAX_SELECTION:raise ValueError('Select 1 to 256 items')
    if len({identity(value) for value in values})!=len(values):raise ValueError('Duplicate selection')
    return list(values)

def validate_edit(item_ids,operation,shelf_ids):
    ids=selection_ids(item_ids)
    if type(operation) is not str or operation not in OPERATIONS:raise ValueError('Invalid selection operation')
    if not isinstance(shelf_ids,list) or len(shelf_ids)>64 or len({identity(value) for value in shelf_ids})!=len(shelf_ids):raise ValueError('Invalid shelf selection')
    if operation.startswith('favorite_') and shelf_ids or operation.startswith('shelves_') and not shelf_ids:raise ValueError('Invalid shelves for operation')
    return ids

def apply(db,ids,operation,shelf_ids):
    # Caller owns the catalog transaction and has validated all frozen sources.
    if operation.startswith('favorite_'):
        db.executemany('UPDATE items SET favorite=? WHERE id=?',((int(operation=='favorite_add'),item) for item in ids))
        return
    for shelf in shelf_ids:
        if db.execute('SELECT 1 FROM shelves WHERE id=?',(shelf,)).fetchone() is None:raise KeyError(shelf)
    if operation=='shelves_add':
        for item in ids:
            present={row[0] for row in db.execute('SELECT shelf_id FROM item_shelves WHERE item_id=?',(item,))}
            if len(present|set(shelf_ids))>64:raise ValueError('An item would exceed the 64 shelf limit')
        db.executemany('INSERT OR IGNORE INTO item_shelves(item_id,shelf_id) VALUES(?,?)',((item,shelf) for item in ids for shelf in shelf_ids))
    else:
        db.executemany('DELETE FROM item_shelves WHERE item_id=? AND shelf_id=?',((item,shelf) for item in ids for shelf in shelf_ids))
    ShelfStore._sync(db,'item',ids)
