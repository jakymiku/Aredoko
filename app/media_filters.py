"""Query categories are independent of persistent media classifications."""
from library_index import TYPES

QUERY_KINDS=frozenset(TYPES)|{'compressed'}

def kind_clause(kind):
    if not isinstance(kind,str) or kind and kind not in QUERY_KINDS:raise ValueError('Invalid media filter')
    if kind=='compressed':
        # Retain book=CBZ/PDF/EPUB and legacy archive=ZIP in storage/API rows.
        # Exact suffix comparison handles upper-case CBZ without wildcard paths.
        return ["(i.kind='archive' OR (i.kind='book' AND lower(substr(l.relative_path,-4))='.cbz'))"],[]
    return (['i.kind=?'],[kind]) if kind else ([],[])
