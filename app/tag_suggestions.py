"""Reviewable proposals, kept separate from user-confirmed catalog metadata.

Adapters are trusted local code, not client-supplied model names or paths. The
adapters remain optional and never download implicitly: embeddings are not a
generative tagger and synthetic adapter tests are not model-quality evidence.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import threading
import time

from ai_process import AIUnavailable
from ai_search import AIBusy
from catalog import validate_tags
from previews import PreviewReader, PreviewUnavailable, PreviewBusyError, ReaderChanged


class SuggestionConflict(AIBusy):
    """Refresh the source/candidate rather than overwriting a decision."""


def identifier(value):
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        raise ValueError('Invalid identifier')
    return value


def text(value, limit):
    if type(value) is not str or not 1 <= len(value.strip()) <= limit or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid proposal text')
    return value.strip()


@dataclass(frozen=True)
class TaggerInfo:
    adapter: str
    version: str
    model: str
    model_revision: str
    preprocessing: str

    def record(self):
        return {key: text(value, 256) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class TagProposal:
    tag: str
    explanation: str
    page: int = 0  # Zero-based; this first slice supplies only image/cover page 0.


SCHEMA = '''
CREATE TABLE IF NOT EXISTS tag_proposal_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    source_revision TEXT NOT NULL,
    producer_key TEXT NOT NULL,
    producer_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(item_id, source_revision, producer_key));
CREATE TABLE IF NOT EXISTS tag_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES tag_proposal_batches(id),
    tag TEXT NOT NULL,
    explanation TEXT NOT NULL,
    page INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','accepted','rejected')),
    accepted_tag TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    reviewed_at REAL,
    UNIQUE(batch_id,tag));
CREATE INDEX IF NOT EXISTS tag_batches_item ON tag_proposal_batches(item_id,id);
CREATE INDEX IF NOT EXISTS tag_proposals_batch ON tag_proposals(batch_id,id);
'''


class TagSuggestions:
    """One cancellable generation at a time; atomic publication and review.

    Optional adapter contract: .info: TaggerInfo and
    .suggest(source, cancelled) -> list[TagProposal] (at most 30).
    source contains bounded bytes/mime and an opaque physical revision, never a
    filesystem path. The adapter must honor cancellation and own/release its
    inference resources. Public clients cannot inject an adapter or proposals.
    """
    def __init__(self, catalog, adapter=None, previews=None):
        self.catalog = catalog
        self.adapter = adapter
        self.previews = previews or PreviewReader(catalog)
        self._job_guard = threading.Lock()
        self._active = None
        with catalog.connect() as db:
            db.executescript(SCHEMA)

    def status(self):
        if self.adapter is not None:
            status=getattr(self.adapter,'status',None)
            return status() if status else {'available':True,'reason':''}
        return {'available':False,'reason':'タグ生成モデルは未接続です。既存の検索・手動タグは利用できます。'}

    def _source(self, item_id):
        try:
            return self.previews.tag_source(identifier(item_id))
        except PreviewBusyError as error:
            raise AIBusy('Preview workers busy; retry later') from error
        except ReaderChanged as error:
            raise SuggestionConflict('Source changed; rescan before reviewing') from error
        except PreviewUnavailable as error:
            raise KeyError('Tag source unavailable') from error

    @staticmethod
    def _same(expected, actual):
        if expected != actual:
            raise SuggestionConflict('Source changed; regenerate proposals')

    @staticmethod
    def _batch(db, batch_id):
        row = db.execute('SELECT * FROM tag_proposal_batches WHERE id=?', (batch_id,)).fetchone()
        result = dict(row)
        result['producer'] = json.loads(result.pop('producer_json'))
        result['evidence'] = json.loads(result.pop('evidence_json'))
        result.pop('producer_key')
        result['proposals'] = [dict(r) for r in db.execute(
            'SELECT id,tag,explanation,page,state,accepted_tag,version,reviewed_at '
            'FROM tag_proposals WHERE batch_id=? ORDER BY id', (batch_id,))]
        return result

    def list(self, item_id, before=None, limit=10):
        identifier(item_id)
        if before is not None: identifier(before)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('Invalid history limit')
        # Keep the physical source and root state stable against catalog edits.
        with self.catalog._guard:
            source = self._source(item_id)
            with self.catalog.connect() as db:
                rows = db.execute('SELECT id FROM tag_proposal_batches WHERE item_id=? '
                    'AND id<? ORDER BY id DESC LIMIT ?',
                    (item_id, before or 9223372036854775807, limit + 1)).fetchall()
                batches = [self._batch(db, r['id']) for r in rows[:limit]]
            for batch in batches:
                batch['stale'] = batch['source_revision'] != source['revision']
            return {'item_id': item_id, 'source_revision': source['revision'],
                    'batches': batches, 'next_before': rows[limit-1]['id'] if len(rows) > limit else None,
                    **self.status()}

    @staticmethod
    def _request(value):
        if type(value) is not str or re.fullmatch(r'[0-9a-f]{32}', value) is None:
            raise ValueError('Expected a fresh 32-character request ID')
        return value

    def cancel(self, request_id):
        self._request(request_id)
        with self._job_guard:
            active = self._active
            matched = active is not None and active[0] == request_id
            if matched: active[1].set()
        return {'cancel_requested': matched}

    def generate(self, item_id, request_id):
        identifier(item_id)
        self._request(request_id)
        if not self.status()['available']: raise AIUnavailable(self.status()['reason'])
        try:
            producer = self.adapter.info.record()
        except Exception as error:
            raise AIUnavailable('Invalid tagger configuration; no proposals saved') from error
        producer_json = json.dumps(producer, sort_keys=True, ensure_ascii=False)
        key = hashlib.sha256(producer_json.encode()).hexdigest()
        cancelled = threading.Event()
        with self._job_guard:
            if self._active is not None: raise AIBusy('Tag generation in progress')
            self._active = request_id, cancelled
        try:
            with self.catalog._guard:
                self.catalog._require_idle()
                source = self._source(item_id)
                with self.catalog.connect() as db:
                    existing = db.execute('SELECT id FROM tag_proposal_batches WHERE '
                        'item_id=? AND source_revision=? AND producer_key=?',
                        (item_id, source['revision'], key)).fetchone()
                    if existing:
                        return {'batch': self._batch(db, existing['id']), 'reused': True}
            # No catalog guard held during inference; manual edits remain usable.
            try:
                payload = self.previews.tag_input(item_id)
            except PreviewBusyError as error:
                raise AIBusy('Preview workers busy; retry later') from error
            except ReaderChanged as error:
                raise SuggestionConflict('Source changed before analysis') from error
            except PreviewUnavailable as error:
                raise KeyError('Tag source unavailable') from error
            self._same(source, payload['source'])
            try:
                proposals = self.adapter.suggest(payload, cancelled.is_set)
            except (AIUnavailable, AIBusy):
                raise
            except Exception as error:
                raise AIUnavailable('Tagger failed; no proposals saved') from error
            if cancelled.is_set(): raise SuggestionConflict('Tag generation cancelled; no proposals saved')
            try:
                validated = self._validate(proposals)
                if self.adapter.info.record() != producer:
                    raise SuggestionConflict('Tagger changed during analysis; retry')
            except (ValueError, AttributeError, TypeError) as error:
                raise AIUnavailable('Invalid tagger output; no proposals saved') from error
            with self.catalog._guard:
                self.catalog._require_idle()
                self._same(source, self._source(item_id))
                # Serialize cancellation with the publication boundary. A cancel
                # received after commit correctly reports no active generation.
                with self._job_guard:
                    if cancelled.is_set(): raise SuggestionConflict('Tag generation cancelled; no proposals saved')
                    with self.catalog.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        db.execute('INSERT OR IGNORE INTO tag_proposal_batches '
                            '(item_id,source_revision,producer_key,producer_json,evidence_json,created_at) '
                            'VALUES(?,?,?,?,?,?)', (item_id, source['revision'], key, producer_json,
                            json.dumps(source, sort_keys=True), time.time()))
                        batch = db.execute('SELECT id FROM tag_proposal_batches WHERE '
                            'item_id=? AND source_revision=? AND producer_key=?',
                            (item_id, source['revision'], key)).fetchone()['id']
                        # A second service/process may already have published it.
                        # Never replace its decisions, including an empty batch.
                        fresh = db.execute('SELECT changes()').fetchone()[0] == 1
                        if fresh:
                            db.executemany("INSERT INTO tag_proposals(batch_id,tag,explanation,page,state) "
                                "VALUES(?,?,?,?,'pending')", [(batch, *p) for p in validated])
                        self._same(source, self._source(item_id))
                        result = self._batch(db, batch)
                    self._active = None
            return {'batch': result, 'reused': not fresh}
        finally:
            with self._job_guard:
                if self._active is not None and self._active[1] is cancelled:
                    self._active = None

    @staticmethod
    def _validate(proposals):
        if type(proposals) is not list or len(proposals) > 30:
            raise ValueError('Invalid adapter output')
        validated, seen = [], set()
        for proposal in proposals:
            if not isinstance(proposal, TagProposal) or type(proposal.page) is not int or proposal.page != 0:
                raise ValueError('Only the supplied image/cover page may be cited')
            tag = text(proposal.tag, 60)
            explanation = text(proposal.explanation, 500)
            if tag in seen: raise ValueError('Duplicate proposed tag')
            seen.add(tag)
            validated.append((tag, explanation, proposal.page))
        return validated

    def review(self, item_id, proposal_id, version, decision, tag=None):
        identifier(item_id)
        identifier(proposal_id)
        if type(version) is not int or not 0 <= version <= 9223372036854775807 or decision not in ('accept', 'reject'):
            raise ValueError('Invalid review')
        if decision == 'reject' and tag is not None: raise ValueError('Reject takes no edited tag')
        if tag is not None: tag = text(tag, 60)
        with self.catalog._guard:
            self.catalog._require_idle()
            source = self._source(item_id)
            with self.catalog.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT p.*,b.source_revision FROM tag_proposals p '
                    'JOIN tag_proposal_batches b ON b.id=p.batch_id WHERE p.id=? AND b.item_id=?',
                    (proposal_id, item_id)).fetchone()
                if row is None: raise KeyError('Proposal unavailable')
                if row['version'] != version or row['state'] != 'pending':
                    raise SuggestionConflict('Proposal already reviewed; refresh before saving')
                if row['source_revision'] != source['revision']:
                    raise SuggestionConflict('Proposal source is stale; regenerate before reviewing')
                accepted = (tag or row['tag']) if decision == 'accept' else None
                if accepted is not None:
                    current = db.execute('SELECT tags FROM items WHERE id=?', (item_id,)).fetchone()
                    # Union with the latest saved manual tags inside this same
                    # transaction. Never replace shelf/favorite/reviewed/progress.
                    tags = list(dict.fromkeys([*json.loads(current['tags']), accepted]))
                    tags = validate_tags(tags)
                    db.execute('UPDATE items SET tags=? WHERE id=?', (json.dumps(tags, ensure_ascii=False), item_id))
                db.execute('UPDATE tag_proposals SET state=?,accepted_tag=?,version=version+1,reviewed_at=? WHERE id=?',
                    ('accepted' if decision == 'accept' else 'rejected', accepted, time.time(), proposal_id))
                self._same(source, self._source(item_id))
                return {'proposal_id': proposal_id, 'state': 'accepted' if accepted else 'rejected',
                        'accepted_tag': accepted, 'version': version + 1}
