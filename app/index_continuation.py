"""Explicit bounded library jobs. Planning never reads media or changes ai_state."""
import base64
import binascii
import copy
import hashlib
import json
import re
import secrets
import threading
import time
import zlib

from ai_process import AIUnavailable

JOB = 'library-continuation-v1'
TTL = 300
TERMINAL = ('cancelled', 'interrupted', 'failed')
INLINE_LIMIT = 1024
CHUNK_SIZE = 256
_UNSET = object()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _chunk_digest(entries):
    return hashlib.sha256(json.dumps(entries, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _append_varints(buf, ids, prev):
    for item in ids:
        delta = item - prev
        prev = item
        while delta >= 0x80:
            buf.append((delta & 0x7f) | 0x80)
            delta >>= 7
        buf.append(delta)
    return prev


def _decompress_ids(ids_b64, count):
    if type(ids_b64) is not str:
        raise ValueError('Invalid saved selection')
    try:
        compressed = base64.b64decode(ids_b64.encode('ascii'), validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error) as error:
        raise ValueError('Invalid saved selection') from error
    max_bytes = count * 10 + 16
    decomp = zlib.decompressobj()
    try:
        raw = decomp.decompress(compressed, max_bytes + 1)
    except zlib.error as error:
        raise ValueError('Invalid saved selection') from error
    if len(raw) > max_bytes or decomp.unconsumed_tail or not decomp.eof:
        raise ValueError('Invalid saved selection')
    return raw


def _iter_varint_chunks(raw, count, upper_id, after_id, expected_last_id, chunk_size=CHUNK_SIZE):
    pos = 0
    total = len(raw)
    prev = 0
    decoded = 0
    chunk_idx = 0
    chunk = []
    while pos < total:
        delta = 0
        shift = 0
        while True:
            if pos >= total or shift > 63:
                raise ValueError('Invalid saved item')
            byte = raw[pos]
            pos += 1
            delta |= (byte & 0x7f) << shift
            if not (byte & 0x80):
                break
            shift += 7
        item = prev + delta
        if item <= prev or item <= after_id or item > upper_id:
            raise ValueError('Invalid saved item order')
        prev = item
        decoded += 1
        chunk.append(item)
        if len(chunk) == chunk_size:
            yield chunk_idx, chunk
            chunk_idx += 1
            chunk = []
    if chunk:
        yield chunk_idx, chunk
    if decoded != count or prev != expected_last_id:
        raise ValueError('Invalid saved selection')


def public_state(state):
    value = copy.deepcopy({k: v for k, v in state.items() if k != 'continuation'})
    if state.get('job') == JOB:
        value['selected_total'] = state['total']
        value['unready_total'] = state['skipped']
    return value


class IndexContinuation:
    def __init__(self, ai, max_items):
        self.ai = ai
        self.max_items = max_items
        self._plan = None  # One bounded, expiring, process-local preview.

    def scope_profile(self, scope, profile):
        if type(profile) is not str or profile != self.ai.profile.key:
            raise ValueError('AI profile changed')
        scope = self.ai._scope(scope)
        if scope is None:
            raise ValueError('Explicit scope required')
        return scope

    def idle(self):
        from ai_search import AIBusy
        if self.ai._closed:
            raise AIUnavailable('AI is closing')
        if self.ai.worker and self.ai.worker.is_alive():
            raise AIBusy('AI索引を作成中です。')
        if self.ai.catalog.scan_state()['state'] in ('running', 'cancelling'):
            raise AIBusy('フォルダのスキャン完了後に実行してください。')

    def context(self, scope):
        roots = scope['root_ids']
        where = 'enabled=1'
        if roots is not None:
            where += ' AND id IN (' + ','.join('?' for _ in roots) + ')' if roots else ' AND 0=1'
        digest = hashlib.sha256()
        with self.ai.catalog.connect() as db:
            cursor = db.execute(
                'SELECT id,path,excludes_json,enabled,folder_books,recursive,default_shelf '
                'FROM library_roots WHERE ' + where + ' ORDER BY id', roots or [])
            while True:
                rows = cursor.fetchmany(256)
                if not rows: break
                for row in rows:
                    digest.update(json.dumps(tuple(row), ensure_ascii=False).encode())
                    digest.update(b'\n')
        return digest.hexdigest()

    def ready(self, rows, pending):
        regular = self.ai.store.fresh_ids(rows)
        return (regular - set(pending)) | (regular & self.ai.pending_tags.ready_ids(pending))

    def prepare(self, scope, profile, limit=_UNSET, after_id=0):
        from ai_search import AIBusy, revision
        scope = self.scope_profile(scope, profile)
        if limit is _UNSET:
            limit = self.max_items
        if type(limit) is not int or not 1 <= limit <= self.max_items:
            raise ValueError('Invalid continuation limit')
        if type(after_id) is not int or not 0 <= after_id <= 9223372036854775807:
            raise ValueError('Invalid continuation cursor')
        with self.ai.guard:
            self.idle()
            previous = fingerprint(self.ai.store.state())
        with self.ai.catalog.connect() as catalog_db, self.ai.store.connect() as vector_db:
            def versions():
                return (catalog_db.execute('PRAGMA data_version').fetchone()[0],
                        vector_db.execute('PRAGMA data_version').fetchone()[0])
            baseline = versions()
            root_context = self.context(scope)
            upper = catalog_db.execute('SELECT COALESCE(MAX(id),0) FROM items').fetchone()[0]
            def check():
                if self.ai._closed:
                    raise AIUnavailable('AI is closing')
                if versions() != baseline or self.ai.profile.key != profile:
                    raise AIBusy('索引の対象が変更されました。計画を確認し直してください。')
            total = fresh = remaining_after = 0
            selected_count = 0
            last_selected_id = after_id
            inline_entries = []
            compact = False
            varint_buf = bytearray()
            prev_id = 0
            current_chunk = []
            chunk_digests = []
            batch = []
            def flush_chunk(chunk):
                nonlocal prev_id
                prev_id = _append_varints(varint_buf, [entry[0] for entry in chunk], prev_id)
                chunk_digests.append(_chunk_digest(chunk))
            def consume(rows):
                nonlocal total, fresh, remaining_after, selected_count, last_selected_id, compact, current_chunk
                check()
                pending = self.ai.pending_tags.snapshots([r['id'] for r in rows])
                ready = self.ready(rows, pending)
                total += len(rows)
                fresh += len(ready)
                for row in rows:
                    if row['id'] <= after_id or row['id'] in ready:
                        continue
                    remaining_after += 1
                    if selected_count < limit:
                        entry = [row['id'], revision(row), pending.get(row['id'], {}).get('signature')]
                        selected_count += 1
                        last_selected_id = row['id']
                        if not compact:
                            inline_entries.append(entry)
                            if len(inline_entries) > INLINE_LIMIT:
                                compact = True
                                for offset in range(0, INLINE_LIMIT, CHUNK_SIZE):
                                    flush_chunk(inline_entries[offset:offset + CHUNK_SIZE])
                                current_chunk = inline_entries[INLINE_LIMIT:]
                                inline_entries.clear()
                        else:
                            current_chunk.append(entry)
                            if len(current_chunk) == CHUNK_SIZE:
                                flush_chunk(current_chunk)
                                current_chunk.clear()
                check()
            for row in self.ai._iter_rows(scope=scope, all_candidates=True, check=check):
                if row['id'] > upper:
                    continue
                batch.append(row)
                if len(batch) == CHUNK_SIZE:
                    consume(batch); batch = []
            if batch:
                consume(batch)
            if compact:
                if current_chunk:
                    flush_chunk(current_chunk)
                    current_chunk.clear()
                record = {
                    'version': 2,
                    'count': selected_count,
                    'ids_b64': base64.b64encode(zlib.compress(bytes(varint_buf), level=6)).decode('ascii'),
                    'chunks': chunk_digests,
                    'root_context': root_context,
                    'upper_id': upper,
                    'after_id': after_id,
                    'last_id': last_selected_id,
                }
            else:
                record = {
                    'version': 1,
                    'entries': inline_entries,
                    'root_context': root_context,
                    'upper_id': upper,
                    'after_id': after_id,
                }
            plan = {'plan_id': secrets.token_hex(16), 'expires_in_seconds': TTL,
                    'scope': scope, 'profile': profile, 'candidate_total': total,
                    'fresh_total': fresh, 'remaining_total': total-fresh,
                    'remaining_after_id': remaining_after, 'selected_total': selected_count,
                    'index_limit': limit, 'after_id': after_id, 'upper_id': upper,
                    'next_after_id': last_selected_id}
            with self.ai.guard:
                self.idle()
                with self.ai.catalog._guard:
                    self.ai.catalog._require_idle()
                    check()
                    if self.context(scope) != root_context or fingerprint(self.ai.store.state()) != previous:
                        raise AIBusy('索引の対象が変更されました。計画を確認し直してください。')
                    self._plan = {'public': copy.deepcopy(plan), 'expires': time.monotonic()+TTL,
                                  'previous': previous, 'record': record}
            return plan

    def iter_chunks(self, record):
        if record['version'] == 1:
            entries = record['entries']
            for idx, offset in enumerate(range(0, len(entries), CHUNK_SIZE)):
                yield idx, [entry[0] for entry in entries[offset:offset + CHUNK_SIZE]]
            return
        raw = _decompress_ids(record['ids_b64'], record['count'])
        yield from _iter_varint_chunks(raw, record['count'], record['upper_id'], record['after_id'], record['last_id'])

    def validate_record(self, record):
        if type(record) is not dict:
            raise ValueError('Invalid saved continuation')
        version = record.get('version')
        if type(version) is not int or version not in (1, 2):
            raise ValueError('Unsupported continuation version')
        if version == 1:
            if set(record) != {'version', 'entries', 'root_context', 'upper_id', 'after_id'}:
                raise ValueError('Invalid saved continuation')
            for key in ('upper_id', 'after_id'):
                if type(record[key]) is not int or not 0 <= record[key] <= 9223372036854775807:
                    raise ValueError('Invalid saved cursor')
            if type(record['root_context']) is not str or not re.fullmatch('[0-9a-f]{64}', record['root_context']):
                raise ValueError('Invalid saved context')
            entries = record['entries']
            if type(entries) is not list or not 1 <= len(entries) <= self.max_items:
                raise ValueError('Invalid saved selection')
            last = record['after_id']
            for entry in entries:
                if type(entry) is not list or len(entry) != 3:
                    raise ValueError('Invalid saved item')
                item, revision, signature = entry
                if type(item) is not int or not last < item <= record['upper_id']:
                    raise ValueError('Invalid saved item order')
                if type(revision) is not str or not re.fullmatch('[0-9a-f]{64}', revision):
                    raise ValueError('Invalid saved revision')
                if signature is not None and (type(signature) is not str or not re.fullmatch('[0-9a-f]{64}', signature)):
                    raise ValueError('Invalid saved tag signature')
                last = item
            return
        if set(record) != {'version', 'count', 'ids_b64', 'chunks', 'root_context', 'upper_id', 'after_id', 'last_id'}:
            raise ValueError('Invalid saved continuation')
        for key in ('upper_id', 'after_id', 'last_id'):
            if type(record[key]) is not int or not 0 <= record[key] <= 9223372036854775807:
                raise ValueError('Invalid saved cursor')
        count = record['count']
        if type(count) is not int or not 1 <= count <= self.max_items:
            raise ValueError('Invalid saved selection')
        if not record['after_id'] < record['last_id'] <= record['upper_id']:
            raise ValueError('Invalid saved cursor')
        if type(record['root_context']) is not str or not re.fullmatch('[0-9a-f]{64}', record['root_context']):
            raise ValueError('Invalid saved context')
        chunks = record['chunks']
        expected_chunks = (count + CHUNK_SIZE - 1) // CHUNK_SIZE
        if type(chunks) is not list or len(chunks) != expected_chunks:
            raise ValueError('Invalid saved selection')
        for digest in chunks:
            if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('Invalid saved revision')
        raw = _decompress_ids(record['ids_b64'], count)
        for _ in _iter_varint_chunks(raw, count, record['upper_id'], record['after_id'], record['last_id']):
            pass

    def check_chunk(self, state, chunk_idx, chunk_ids):
        """Catalog launch/publication guard is held by the caller; verify one 256-item chunk."""
        from ai_search import revision
        scope = self.scope_profile(state['scope'], state['profile'])
        record = state['continuation']
        self.ai.catalog._require_idle()
        if self.context(scope) != record['root_context']:
            raise ValueError('Registered roots changed; review a new plan')
        rows = self.ai._current_rows(chunk_ids, scope)
        pending = self.ai.pending_tags.snapshots(chunk_ids)
        chunk_entries = []
        pins = {}
        for item in chunk_ids:
            row = rows.get(item)
            if row is None:
                raise ValueError('Selected source or tags changed; review a new plan')
            rev = revision(row)
            sig = pending.get(item, {}).get('signature')
            chunk_entries.append([item, rev, sig])
            pins[item] = (rev, sig)
        if _chunk_digest(chunk_entries) != record['chunks'][chunk_idx]:
            raise ValueError('Selected source or tags changed; review a new plan')
        state['_pins'] = pins

    def check(self, state, ids):
        """Catalog launch/publication guard is held by the caller; no inference."""
        from ai_search import revision
        scope = self.scope_profile(state['scope'], state['profile'])
        record = state['continuation']
        self.ai.catalog._require_idle()
        if self.context(scope) != record['root_context']:
            raise ValueError('Registered roots changed; review a new plan')
        rows = self.ai._current_rows(ids, scope)
        pending = self.ai.pending_tags.snapshots(ids)
        expected = state['_pins']
        for item in ids:
            row = rows.get(item)
            if (row is None or revision(row) != expected[item][0]
                    or pending.get(item, {}).get('signature') != expected[item][1]):
                raise ValueError('Selected source or tags changed; review a new plan')

    def start(self, plan_id, scope, profile):
        with self.ai.guard:
            self.idle()
            plan = self._plan
            scope = self.scope_profile(scope, profile)
            if (type(plan_id) is not str or plan is None or plan_id != plan['public']['plan_id']
                    or time.monotonic() >= plan['expires'] or scope != plan['public']['scope']
                    or profile != plan['public']['profile'] or fingerprint(self.ai.store.state()) != plan['previous']):
                raise ValueError('Plan expired or changed; review a new plan')
            result = self._launch(plan['record'], scope, profile)
            self._plan = None
            return result

    def resume(self, job_id, scope, profile):
        with self.ai.guard:
            self.idle()
            scope = self.scope_profile(scope, profile)
            old = self.ai.store.state()
            if (type(job_id) is not str or re.fullmatch('[0-9a-f]{32}', job_id) is None
                    or old.get('job') != JOB or old.get('job_id') != job_id
                    or old.get('state') not in TERMINAL or scope != old.get('scope')
                    or profile != old.get('profile')):
                raise ValueError('Saved job unavailable; review a new plan')
            return self._launch(old.get('continuation'), scope, profile, resumed_from=job_id)

    def cancel(self, job_id):
        if type(job_id) is not str or not re.fullmatch('[0-9a-f]{32}', job_id):
            raise ValueError('Invalid job ID')
        with self.ai.guard:
            if self.ai._closed:
                return {'cancel_requested': False, 'job_id': job_id}
            state = self.ai.store.state()
            accepted = False
            if (state.get('job') == JOB and state.get('job_id') == job_id
                    and state.get('state') in ('running', 'cancelling')):
                self.ai.cancel.set()
                if state.get('state') == 'running':
                    self.ai.store.save_state({**state, 'state': 'cancelling'})
                accepted = True
            return {'cancel_requested': accepted, 'job_id': job_id}

    def _launch(self, record, scope, profile, resumed_from=None):
        if not self.ai.encoder.available:
            raise AIUnavailable('AI環境が未導入です。')
        self.validate_record(record)
        record = copy.deepcopy(record)
        if record['version'] == 1:
            ids = [entry[0] for entry in record['entries']]
            total = len(ids)
            next_after_id = ids[-1]
            pins = {item: (rev, sig) for item, rev, sig in record['entries']}
        else:
            ids = None
            total = record['count']
            next_after_id = record['last_id']
            pins = {}
        state = {'state': 'running', 'job': JOB, 'job_id': secrets.token_hex(16),
                 'scope': copy.deepcopy(scope), 'profile': profile, 'processed': 0,
                 'total': total, 'indexed': 0, 'skipped': 0, 'reused': 0, 'error': '',
                 'after_id': record['after_id'], 'upper_id': record['upper_id'],
                 'next_after_id': next_after_id, 'continuation': record}
        if resumed_from is not None:
            state['resumed_from'] = resumed_from
        state['_pins'] = pins
        with self.ai.catalog._guard:
            if record['version'] == 1:
                for offset in range(0, len(ids), CHUNK_SIZE):
                    self.check(state, ids[offset:offset+CHUNK_SIZE])
            else:
                for chunk_idx, chunk_ids in self.iter_chunks(record):
                    self.check_chunk(state, chunk_idx, chunk_ids)
        # Internal lookup is never persisted or returned. The compact source of
        # truth is continuation; _build reconstructs pins per batch/chunk.
        state['_pins'].clear()
        del state['_pins']
        self.ai.cancel.clear()
        self.ai.store.save_state(state)
        initial = public_state(state)
        self.ai.worker = threading.Thread(target=self.ai._build, args=(ids, scope, state), daemon=True)
        self.ai.worker.start()
        return initial
