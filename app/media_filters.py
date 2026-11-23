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


def normalize_tag_filter(tag):
    """Validate an optional confirmed-tag filter without partial or word splitting."""
    if tag is None:
        return None
    if type(tag) is not str:
        raise ValueError('Invalid tag filter')
    value = tag.strip()
    if not 1 <= len(value) <= 60:
        raise ValueError('Tag filter must contain 1 to 60 characters')
    return value


def tag_clause(tag=None):
    """Exact SQL predicate against confirmed i.tags JSON array."""
    value = normalize_tag_filter(tag)
    if value is None:
        return [], []
    return ['json_valid(i.tags) AND EXISTS(SELECT 1 FROM json_each(i.tags) jt WHERE jt.value=?)'], [value]
