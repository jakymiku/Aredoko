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


def matcher(alternatives):
    """SQLite scalar aredoko_match(title, tags) for one search.

    alternatives: per query word, a list of normalized options (the word
    itself first). Returns -1 when some word has no option in the title or
    tags, otherwise how many words matched through the typed word itself
    (used to rank direct hits before related-term candidates). Each row's
    text is normalized once, whatever the number of words or options.
    """
    memo = {}

    def match(title, tags):
        key = (title, tags)
        if key not in memo:
            hay = normalize(title) + '\x1f' + normalize(tags)
            direct = 0
            for options in alternatives:
                if options[0] in hay:
                    direct += 1
                elif not any(option in hay for option in options[1:]):
                    direct = -1
                    break
            memo[key] = direct
        return memo[key]
    return match


def coverage(alternatives):
    """SQLite scalar aredoko_cover(title, tags): words matched by any option.

    Used only for the partial fallback when no item has every word.
    """
    memo = {}

    def cover(title, tags):
        key = (title, tags)
        if key not in memo:
            hay = normalize(title) + '\x1f' + normalize(tags)
            memo[key] = sum(any(option in hay for option in options) for options in alternatives)
        return memo[key]
    return cover


def register(db, alternatives):
    """Expose this search's matchers to SQLite on this connection."""
    db.create_function('aredoko_match', 2, matcher(alternatives), deterministic=True)
    db.create_function('aredoko_cover', 2, coverage(alternatives), deterministic=True)
