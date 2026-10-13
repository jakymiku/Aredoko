"""Forgiving literal search terms for the production catalog.

Users type short, vague Japanese queries ("東方 巫女", "ﾚｲﾑ", "REIMU").
The literal (non-AI) search therefore:

* normalizes both the query and stored text with NFKC + casefold and maps
  katakana to hiragana, so full/half width, letter case and kana script
  differences do not hide a file;
* splits the query on any whitespace (including the ideographic space) and
  requires every term (AND), so word order and separators do not matter.

Ordinary queries that matched before still match: an old contiguous
substring match is normally also an all-terms match of the normalized text
(rare NFKC composition edge cases at a substring boundary are the exception). This module is pure
stdlib and never reads files or models.
"""
import functools
import unicodedata

MAX_TERMS = 16
_KATAKANA = {code: code - 0x60 for code in range(0x30A1, 0x30F7)}  # ァ..ヶ -> ぁ..ゖ


@functools.lru_cache(maxsize=200_000)
def _normalize(text):
    return unicodedata.normalize('NFKC', text).casefold().translate(_KATAKANA)


def normalize(text):
    if not isinstance(text, str):
        return ''
    return _normalize(text)


def split_terms(query):
    """Normalized, de-duplicated terms in input order; empty for a blank query."""
    terms = list(dict.fromkeys(t for t in normalize(query).split() if t))
    if len(terms) > MAX_TERMS:
        raise ValueError(f'Use at most {MAX_TERMS} search words')
    return terms


def _scorer(alternatives):
    """One pass per row: (direct, covered, specific), memoized per search."""
    memo = {}

    def score(title, tags):
        key = (title, tags)
        found = memo.get(key)
        if found is None:
            hay = normalize(title) + '\x1f' + normalize(tags)
            direct = covered = specific = 0
            for options in alternatives:
                lengths = [len(option) for option in options if option in hay]
                if not lengths:
                    continue
                covered += 1
                typed = options[0] in hay
                direct += typed
                # The typed word itself outweighs any alternative (queries are
                # at most 300 characters), so direct matches rank first.
                specific += (1000 if typed else 0) + max(lengths)
            found = memo[key] = (direct if covered == len(alternatives) else -1, covered, specific)
        return found
    return score


def matcher(alternatives):
    """SQLite scalar aredoko_match(title, tags) for one search.

    alternatives: per query word, a list of normalized options (the word
    itself first). Returns -1 when some word has no option in the title or
    tags, otherwise how many words matched through the typed word itself
    (used to rank direct hits before related-term candidates).
    """
    score = _scorer(alternatives)
    return lambda title, tags: score(title, tags)[0]


def register(db, alternatives):
    """Expose this search's matchers to SQLite on this connection.

    aredoko_match: -1 or direct-word count (filter + rank).
    aredoko_cover: words matched by any option (partial fallback filter).
    aredoko_specific: ranking hint; a candidate matched through a full
    headword ("朝霧なぎ") ranks above one matched only through a short alias
    inside another name ("なぎ" in "なぎさ"). Never a filter.
    All three share one normalization and scan per row.
    """
    score = _scorer(alternatives)
    db.create_function('aredoko_match', 2, lambda t, g: score(t, g)[0], deterministic=True)
    db.create_function('aredoko_cover', 2, lambda t, g: score(t, g)[1], deterministic=True)
    db.create_function('aredoko_specific', 2, lambda t, g: score(t, g)[2], deterministic=True)
