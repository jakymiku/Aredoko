"""One explicitly selected book, <=128 pages, atomic chunks of <=16 pages."""
import copy
import re
import secrets
import threading
import time

from ai_process import AIUnavailable
from page_index import identifier, token
from previews import ReaderChanged

MAX_TOTAL = 128
JOB = 'book-pages-chunked'
TERMINAL = ('cancelled', 'interrupted', 'failed')


def _scope_profile(ai, scope, profile):
    if type(profile) is not str or profile != ai.profile.key:
        raise ValueError('AI profile changed')
    scope = ai._scope(scope)
    if scope is None:
        raise ValueError('Explicit scope required')
    return copy.deepcopy(scope)


def plan_chunked(ai, item_id, revision, scope, max_pages, profile):
    """CPU-only next-gap plan; no snapshot refresh, model load or job mutation."""
    scope = _scope_profile(ai, scope, profile)
    # coverage takes the non-reentrant AI guard itself. Do not nest it inside
    # the guard or acquire AI state while holding the catalog guard.
    gaps = ai.pages.next_gaps(item_id, revision, scope, max_pages=max_pages)
    with ai.guard:
        if ai._closed:
            raise AIUnavailable('AI is closing')
        with ai.catalog._guard:
            ai.catalog._require_idle()
            if ai._current_rows([item_id], scope).get(item_id) is None:
                raise KeyError('Page source unavailable')
            ids = []
            if gaps['total_gap_pages']:
                wanted = {page for chunk in gaps['chunks']
                          for page in range(chunk['start'], chunk['start']+chunk['count'])}
                with ai.catalog.connect() as db:
                    head = ai.pages.index._head(db, item_id)
                    if head is None or head['source_revision'] != revision:
                        raise ReaderChanged('Page source changed')
                    ids = [p['page_id'] for p in db.execute(
                        'SELECT page_id FROM page_entries WHERE snapshot_id=? AND page IN ('+
                        ','.join('?' for _ in wanted)+') ORDER BY page', [head['id'], *sorted(wanted)])]
                if len(ids) != gaps['total_gap_pages']:
                    raise ReaderChanged('Page index changed')
                ai.pages.selection(item_id, ids, revision)
    return {**gaps, 'page_ids':ids, 'scope':scope, 'chunks_total':(len(ids)+15)//16}


def start_chunked(ai, item_id, page_ids, revision, scope, profile, *, chunk_size=16, expected_job=None):
    from ai_search import AIBusy
    identifier(item_id); token(revision)
    if type(chunk_size) is not int or not 1 <= chunk_size <= 16:
        raise ValueError('Invalid chunk_size')
    if (type(page_ids) is not list or not 1 <= len(page_ids) <= MAX_TOTAL
            or any(type(pid) is not str for pid in page_ids) or len(set(page_ids)) != len(page_ids)):
        raise ValueError('Invalid page selection')
    for pid in page_ids:
        token(pid)
    page_ids = list(page_ids)
    scope = _scope_profile(ai, scope, profile)
    if not ai.encoder.available or 'cover' not in ai.profile.modalities:
        raise AIUnavailable('選択中のモデルでは画像のAI検索を利用できません。')
    with ai.guard:
        if ai._closed:
            raise AIUnavailable('AI is closing')
        if ai.worker and ai.worker.is_alive():
            raise AIBusy('AI索引を作成中です。')
        if expected_job is not None:
            previous = ai.store.state()
            if (previous.get('job') != JOB or previous.get('job_id') != expected_job
                    or previous.get('state') not in TERMINAL):
                raise ValueError('Chunked job is no longer resumable')
            if scope != previous.get('scope') or profile != previous.get('profile'):
                raise ValueError('Chunked scope or profile changed; review a new range')
            if (item_id, revision, page_ids, chunk_size) != (
                    previous.get('item_id'), previous.get('source_revision'),
                    previous.get('page_ids'), previous.get('chunk_size')):
                raise ValueError('Chunked selection changed; review a new range')
        with ai.catalog._guard:
            ai.catalog._require_idle()
            row = ai._current_rows([item_id], scope).get(item_id)
            if row is None or row['kind'] not in ('book', 'archive'):
                raise KeyError('Page source unavailable')
            pages = ai.pages.selection(item_id, page_ids, revision)
        state = {'state':'running', 'job':JOB, 'job_id':secrets.token_hex(16), 'item_id':item_id,
            'source_revision':revision, 'processed':0, 'total':len(pages),
            'indexed':0, 'reused':0, 'skipped':0, 'error':'', 'scope':scope, 'profile':profile,
            'page_ids':page_ids, 'chunk_size':chunk_size,
            'chunks_total':(len(pages)+chunk_size-1)//chunk_size, 'chunks_completed':0}
        if expected_job is not None:
            state['resumed_from'] = expected_job
        initial = copy.deepcopy(state)
        ai.cancel.clear(); ai.store.save_state(state)
        ai.worker = threading.Thread(target=_build, args=(ai, pages, state), daemon=True)
        ai.worker.start()
    # Return this job's own detached snapshot, not status of a replacement job.
    return initial


def resume_chunked(ai, job_id, scope, profile):
    if type(job_id) is not str or re.fullmatch('[0-9a-f]{32}', job_id) is None:
        raise ValueError('Invalid job ID')
    with ai.guard:
        previous = ai.store.state()
        if previous.get('job') != JOB or previous.get('job_id') != job_id:
            raise KeyError('Chunked job unavailable')
        saved = copy.deepcopy(previous)
    return start_chunked(ai, saved.get('item_id'), saved.get('page_ids'),
        saved.get('source_revision'), scope, profile, chunk_size=saved.get('chunk_size'), expected_job=job_id)


def _build(ai, pages, state):
    try:
        with ai.inference:
            for offset in range(0, len(pages), state['chunk_size']):
                if ai.cancel.is_set():
                    raise InterruptedError()
                chunk = pages[offset:offset+state['chunk_size']]
                # Recheck scope/source even for cached chunks before doing work.
                with ai.catalog._guard:
                    ai.catalog._require_idle()
                    if ai._current_rows([state['item_id']], state['scope']).get(state['item_id']) is None:
                        raise KeyError('Page source unavailable')
                    ai.pages.selection(state['item_id'], [p['page_id'] for p in chunk], state['source_revision'])
                # This existing publisher verifies again after inference and
                # commits one whole chunk; a cancelled partial chunk is invisible.
                ai.pages._publish_range(chunk, state, state['item_id'], state['source_revision'])
                state['indexed'] += len(chunk)
                state['chunks_completed'] += 1
                with ai.guard:
                    ai.store.save_state(state)
            state['state'] = 'complete'
    except InterruptedError:
        state['state'] = 'cancelled'
    except Exception as ex:
        state['state'] = 'failed'
        state['error'] = 'ページ索引を保存できませんでした（'+type(ex).__name__+'）。元ファイル・登録範囲を確認して再実行してください。'
    finally:
        ai._last_activity = time.monotonic()
        with ai.guard:
            ai.store.save_state(state)
