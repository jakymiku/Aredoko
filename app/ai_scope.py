"""Explicit registered-library scope; no paths, SQL, or model-space changes."""
from library_index import TYPES
from shelves import shelf_clause

MAX_ROOTS = 256


def validate_scope(value):
    if not isinstance(value, dict) or set(value) - {'root_ids', 'kind', 'shelf', 'shelf_ids'}:
        raise ValueError('Invalid AI scope')
    roots = value.get('root_ids')
    if roots is not None:
        if (not isinstance(roots, list) or len(roots) > MAX_ROOTS
                or any(type(root) is not int or not 1<=root<=9223372036854775807 for root in roots)
                or len(set(roots)) != len(roots)):
            raise ValueError('Invalid registered root selection')
        roots = sorted(roots)  # Copy before an asynchronous job begins.
    kind = value.get('kind', '')
    shelf = value.get('shelf')
    if not isinstance(kind, str) or kind and kind not in TYPES:
        raise ValueError('Invalid scope kind')
    if shelf is not None and (not isinstance(shelf, str) or len(shelf) > 80):
        raise ValueError('Invalid scope shelf')
    shelf_clause(shelf,value.get('shelf_ids'))
    result={'root_ids': roots, 'kind': kind, 'shelf': shelf}
    if 'shelf_ids' in value:result['shelf_ids']=None if value['shelf_ids'] is None else sorted(value['shelf_ids'])
    return result


def scope_clause(scope):
    """Only called with a validated scope. Values are always SQL parameters."""
    where, values = [], []
    if scope is None:
        return where, values
    roots = scope['root_ids']
    if roots is not None:
        if roots:
            where.append('l.root_id IN (' + ','.join('?' for _ in roots) + ')')
            values.extend(roots)
        else:
            where.append('0=1')
    if scope['kind']:
        where.append('i.kind=?'); values.append(scope['kind'])
    clauses,parameters=shelf_clause(scope['shelf'],scope.get('shelf_ids'))
    where.extend(clauses);values.extend(parameters)
    return where, values
