"""Explicit bounded library jobs. Planning never reads media or changes ai_state."""
import copy
import hashlib
import json
import re
import secrets
import threading
import time

from ai_process import AIUnavailable

JOB = 'library-continuation-v1'
TTL = 300
TERMINAL = ('cancelled', 'interrupted', 'failed')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


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

    def prepare(self, scope, profile, limit=1000, after_id=0):
        from ai_search import AIBusy, revision
        scope = self.scope_profile(scope, profile)
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
            entries = []
            batch = []
            def consume(rows):
                nonlocal total, fresh, remaining_after
                check()
                pending = self.ai.pending_tags.snapshots([r['id'] for r in rows])
                ready = self.ready(rows, pending)
                total += len(rows)
                fresh += len(ready)
                for row in rows:
                    if row['id'] <= after_id or row['id'] in ready:
                        continue
                    remaining_after += 1
                    if len(entries) < limit:
                        entries.append([row['id'], revision(row), pending.get(row['id'], {}).get('signature')])
                check()
            for row in self.ai._iter_rows(scope=scope, all_candidates=True, check=check):
                if row['id'] > upper:
                    continue
                batch.append(row)
                if len(batch) == 256:
                    consume(batch); batch = []
            if batch:
                consume(batch)
            plan = {'plan_id': secrets.token_hex(16), 'expires_in_seconds': TTL,
                    'scope': scope, 'profile': profile, 'candidate_total': total,
                    'fresh_total': fresh, 'remaining_total': total-fresh,
                    'remaining_after_id': remaining_after, 'selected_total': len(entries),
                    'index_limit': limit, 'after_id': after_id, 'upper_id': upper,
                    'next_after_id': entries[-1][0] if entries else after_id}
            with self.ai.guard:
                self.idle()
                with self.ai.catalog._guard:
                    self.ai.catalog._require_idle()
                    check()
                    if self.context(scope) != root_context or fingerprint(self.ai.store.state()) != previous:
                        raise AIBusy('索引の対象が変更されました。計画を確認し直してください。')
                    self._plan = {'public': copy.deepcopy(plan), 'expires': time.monotonic()+TTL,
                                  'previous': previous, 'record': {'version': 1, 'entries': entries,
                                  'root_context': root_context, 'upper_id': upper, 'after_id': after_id}}
            return plan

    def validate_record(self, record):
        if type(record) is not dict or set(record) != {'version', 'entries', 'root_context', 'upper_id', 'after_id'}:
            raise ValueError('Invalid saved continuation')
        if type(record['version']) is not int or record['version'] != 1:
            raise ValueError('Unsupported continuation version')
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
        ids = [entry[0] for entry in record['entries']]
        state = {'state': 'running', 'job': JOB, 'job_id': secrets.token_hex(16),
                 'scope': copy.deepcopy(scope), 'profile': profile, 'processed': 0,
                 'total': len(ids), 'indexed': 0, 'skipped': 0, 'reused': 0, 'error': '',
                 'after_id': record['after_id'], 'upper_id': record['upper_id'],
                 'next_after_id': ids[-1], 'continuation': record}
        if resumed_from is not None:
            state['resumed_from'] = resumed_from
        state['_pins'] = {item: (rev, sig) for item, rev, sig in record['entries']}
        with self.ai.catalog._guard:
            for offset in range(0, len(ids), 256):
                self.check(state, ids[offset:offset+256])
        # Internal lookup is never persisted or returned. The compact source of
        # truth is entries; _build reconstructs its own dictionary after launch.
        del state['_pins']
        self.ai.cancel.clear()
        self.ai.store.save_state(state)
        initial = public_state(state)
        self.ai.worker = threading.Thread(target=self.ai._build, args=(ids, scope, state), daemon=True)
        self.ai.worker.start()
        return initial
