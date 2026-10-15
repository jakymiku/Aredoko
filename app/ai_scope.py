"""Explicit registered-library scope; no paths, SQL, or model-space changes."""
from library_index import TYPES

MAX_ROOTS = 256


def validate_scope(value):
    if not isinstance(value, dict) or set(value) - {'root_ids', 'kind', 'shelf'}:
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
    return {'root_ids': roots, 'kind': kind, 'shelf': shelf}


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
    if scope['shelf'] is not None:
        where.append('i.shelf=?'); values.append(scope['shelf'])
    return where, values
