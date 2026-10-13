"""User-owned related-term dictionary for literal search expansion.

Vision case: the user types "東方 巫女" but the file is only tagged or named
"博麗霊夢". An entry such as

    {"term": "博麗霊夢", "aliases": ["霊夢", "reimu"], "related": ["東方", "巫女"]}

lets each query word also match the entry's term and aliases:

* a word equal to the term or an alias (an alternative spelling) adds the
  term and every alias;
* a word equal to a related word (a hint the user would remember) adds the
  term and aliases as additional *candidates*.

Expansion only adds OR alternatives to a word, never removes the original
word, never overrides kind/view filters, and is reported back so the UI can
show which related words were included. Entries live in the catalog DB and
are created only by the user; nothing is shipped or downloaded.
"""
import json
from search_terms import normalize

MAX_ENTRIES = 2000
MAX_WORDS = 16          # aliases or related words per entry
MAX_WORD_CHARS = 60
MAX_ALTERNATIVES = 256  # per query word, including the word itself

SCHEMA = '''
CREATE TABLE IF NOT EXISTS term_relations (
    id INTEGER PRIMARY KEY,
    term TEXT NOT NULL,
    term_key TEXT NOT NULL UNIQUE,
    aliases TEXT NOT NULL DEFAULT '[]',
    related TEXT NOT NULL DEFAULT '[]');
'''


def _word(value, field):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= MAX_WORD_CHARS:
        raise ValueError(f'{field} must contain 1 to {MAX_WORD_CHARS} characters')
    value = value.strip()
    if not normalize(value) or any(ch.isspace() for ch in normalize(value)):
        raise ValueError(f'{field} must be a single word without spaces')
    return value


def _words(values, field, exclude):
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > MAX_WORDS:
        raise ValueError(f'{field} must be a list of at most {MAX_WORDS} words')
    result, seen = [], set(exclude)
    for value in values:
        word = _word(value, field)
        if normalize(word) not in seen:
            seen.add(normalize(word)); result.append(word)
    return result


def validate_entry(body):
    if not isinstance(body, dict) or set(body) - {'term', 'aliases', 'related'} or 'term' not in body:
        raise ValueError('Expected term with optional aliases and related words')
    term = _word(body['term'], 'term')
    aliases = _words(body.get('aliases'), 'aliases', {normalize(term)})
    keys = {normalize(term)} | {normalize(a) for a in aliases}
    related = _words(body.get('related'), 'related', keys)
    return {'term': term, 'aliases': aliases, 'related': related}


class TermRelations:
    def __init__(self, connect):
        self.connect = connect
        with self.connect() as db:
            db.executescript(SCHEMA)

    @staticmethod
    def _row(row):
        return {'term': row['term'], 'aliases': json.loads(row['aliases']), 'related': json.loads(row['related'])}

    def entries(self):
        with self.connect() as db:
            rows = db.execute('SELECT term,aliases,related FROM term_relations ORDER BY term_key').fetchall()
        return [self._row(r) for r in rows]

    def upsert(self, body):
        entry = validate_entry(body)
        key = normalize(entry['term'])
        values = (entry['term'], key, json.dumps(entry['aliases'], ensure_ascii=False),
                  json.dumps(entry['related'], ensure_ascii=False))
        with self.connect() as db:
            exists = db.execute('SELECT 1 FROM term_relations WHERE term_key=?', (key,)).fetchone()
            if not exists and db.execute('SELECT count(*) FROM term_relations').fetchone()[0] >= MAX_ENTRIES:
                raise ValueError(f'At most {MAX_ENTRIES} related-term entries')
            db.execute('INSERT INTO term_relations(term,term_key,aliases,related) VALUES(?,?,?,?) '
                       'ON CONFLICT(term_key) DO UPDATE SET term=excluded.term,aliases=excluded.aliases,'
                       'related=excluded.related', values)
        return entry

    def delete(self, term):
        key = normalize(_word(term, 'term'))
        with self.connect() as db:
            removed = db.execute('DELETE FROM term_relations WHERE term_key=?', (key,)).rowcount
        if not removed:
            raise KeyError(term)
        return {'deleted': True}

    def expand(self, terms, db):
        """Map each normalized query word to its alternatives (word first).

        Returns (alternatives per word, expansions report). Uses the caller's
        connection so a search sees one consistent dictionary snapshot.
        """
        rows = db.execute('SELECT term,aliases,related FROM term_relations').fetchall() if terms else []
        groups = []
        for row in rows:
            entry = self._row(row)
            spellings = [entry['term']] + entry['aliases']
            groups.append(({normalize(w) for w in spellings}, {normalize(w) for w in entry['related']}, spellings))
        # Candidates related to more of the typed words come first, so with a
        # large dictionary "東方 巫女" keeps 博麗霊夢 (related to both) within
        # the per-word cap ahead of entries related to 東方 alone.
        wanted_words = set(terms)
        groups.sort(key=lambda group: -len((group[0] | group[1]) & wanted_words))
        alternatives, report = [], []
        for word in terms:
            options, added, truncated = [word], [], False
            # Alternative spellings of the word first, then related candidates.
            for wanted in ('spelling', 'related'):
                for keys, related, spellings in groups:
                    if (word in keys) if wanted == 'spelling' else (word in related and word not in keys):
                        for spelling in spellings:
                            key = normalize(spelling)
                            if key in options:
                                continue
                            if len(options) >= MAX_ALTERNATIVES:
                                truncated = True
                                continue
                            options.append(key); added.append(spelling)
            alternatives.append(options)
            if added:
                entry = {'term': word, 'added': added}
                if truncated:
                    entry['truncated'] = True
                report.append(entry)
        return alternatives, report
