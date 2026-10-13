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
import unicodedata

MAX_TERMS = 16
_KATAKANA = {code: code - 0x60 for code in range(0x30A1, 0x30F7)}  # ァ..ヶ -> ぁ..ゖ


def normalize(text):
    if not isinstance(text, str):
        return ''
    return unicodedata.normalize('NFKC', text).casefold().translate(_KATAKANA)


def split_terms(query):
    """Normalized, de-duplicated terms in input order; empty for a blank query."""
    terms = list(dict.fromkeys(t for t in normalize(query).split() if t))
    if len(terms) > MAX_TERMS:
        raise ValueError(f'Use at most {MAX_TERMS} search words')
    return terms


def register(db):
    """Expose normalize() to SQLite as aredoko_norm(text) on this connection."""
    db.create_function('aredoko_norm', 1, normalize, deterministic=True)
