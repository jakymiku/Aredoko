"""Explicit multi-book page ranges. At most 8 books / 128 pages per job."""
import copy
import re
import secrets
import threading
import time

from ai_process import AIUnavailable
from page_index import identifier, token

MAX_BOOKS = 8
MAX_TOTAL = 128
TERMINAL = ('cancelled', 'interrupted', 'failed', 'partial')


def validate(items, page_limit):
    from page_semantics import MAX_PAGES
    if type(page_limit) is not int or not 1 <= page_limit <= MAX_TOTAL:
        raise ValueError('Invalid total page limit')
    if type(items) is not list or not 1 <= len(items) <= MAX_BOOKS:
        raise ValueError('Select 1..8 books')
    seen = set(); total = 0
    for item in items:
        if type(item) is not dict or set(item) != {'item_id', 'revision', 'page_ids'}:
            raise ValueError('Invalid book range')
        identifier(item['item_id']); token(item['revision'])
        ids = item['page_ids']
        if (type(ids) is not list or not 1 <= len(ids) <= MAX_PAGES or any(type(p) is not str for p in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError('Invalid page IDs')
        for pid in ids: token(pid)
        if item['item_id'] in seen: raise ValueError('Duplicate book')
        seen.add(item['item_id']); total += len(ids)
    if total > page_limit: raise ValueError('Total page limit exceeded')
    return total


def start_batch(ai, items, scope, page_limit, profile, expected_job=None):
    from ai_search import AIBusy
    total = validate(items, page_limit)
    scope = ai._scope(scope)
    if scope is None: raise ValueError('Explicit scope required')
    if type(profile) is not str or profile != ai.profile.key:
        raise ValueError('AI profile changed')
    if not ai.encoder.available or 'cover' not in ai.profile.modalities:
        raise AIUnavailable('選択中のモデルでは画像のAI検索を利用できません。')
    items = copy.deepcopy(items)
    with ai.guard:
        if ai._closed: raise AIUnavailable('AI is closing')
        if ai.worker and ai.worker.is_alive(): raise AIBusy('AI索引を作成中です。')
        if expected_job is not None:
            previous = ai.store.state()
            if (previous.get('job') != 'book-page-batch' or previous.get('job_id') != expected_job
                    or previous.get('state') not in TERMINAL):
                raise ValueError('Batch is no longer resumable')
            if scope != previous.get('scope'): raise ValueError('AI scope changed; review a new range')
        with ai.catalog._guard:
            ai.catalog._require_idle()
            for item in items:
                row = ai._current_rows([item['item_id']], scope).get(item['item_id'])
                if row is None or row['kind'] not in ('book', 'archive'):
                    raise KeyError('Page source unavailable')
                ai.pages.selection(item['item_id'], item['page_ids'], item['revision'])
        state = {'state':'running', 'job':'book-page-batch', 'job_id':secrets.token_hex(16),
            'processed':0, 'total':total, 'indexed':0, 'reused':0, 'skipped':0,
            'books_completed':0, 'books_failed':0, 'books_total':len(items), 'error':'',
            'scope':scope, 'page_limit':page_limit, 'profile':profile, 'selections':items,
            'books':[{'item_id':i['item_id'], 'revision':i['revision'], 'total':len(i['page_ids']),
                'state':'pending', 'processed':0, 'indexed':0, 'reused':0, 'error':''} for i in items]}
        if expected_job: state['resumed_from'] = expected_job
        initial = copy.deepcopy(state)
        ai.cancel.clear(); ai.store.save_state(state)
        ai.worker = threading.Thread(target=_build, args=(ai, state), daemon=True)
        ai.worker.start()
    return initial


def resume_batch(ai, job_id, scope, profile):
    if type(job_id) is not str or re.fullmatch('[0-9a-f]{32}', job_id) is None:
        raise ValueError('Invalid job ID')
    with ai.guard:
        previous = ai.store.state()
        if previous.get('job') != 'book-page-batch' or previous.get('job_id') != job_id:
            raise KeyError('Batch unavailable')
        items = previous.get('selections'); limit = previous.get('page_limit')
    return start_batch(ai, items, scope, limit, profile, expected_job=job_id)


def _build(ai, state):
    try:
        with ai.inference:
            for request, book in zip(state['selections'], state['books']):
                if ai.cancel.is_set(): break
                book['state'] = 'running'
                before = state['processed']; reused = state['reused']
                try:
                    with ai.catalog._guard:
                        ai.catalog._require_idle()
                        row = ai._current_rows([request['item_id']], state['scope']).get(request['item_id'])
                        if row is None: raise KeyError('Page source unavailable')
                        pages = ai.pages.selection(request['item_id'], request['page_ids'], request['revision'])
                    ai.pages._publish_range(pages, state, request['item_id'], request['revision'])
                    book['state'] = 'complete'; book['indexed'] = len(pages)
                    state['indexed'] += len(pages); state['books_completed'] += 1
                except InterruptedError:
                    book['state'] = 'cancelled'; break
                except Exception as ex:
                    book['state'] = 'failed'; state['books_failed'] += 1
                    book['error'] = '追加できませんでした（'+type(ex).__name__+'）。元ファイル・登録範囲を確認してください。'
                    state['skipped'] += book['total']
                finally:
                    book['processed'] = state['processed']-before
                    book['reused'] = state['reused']-reused
                    with ai.guard: ai.store.save_state(state)
            state['state'] = ('cancelled' if ai.cancel.is_set() else
                ('partial' if state['books_completed'] else 'failed') if state['books_failed'] else 'complete')
            if state['books_failed']: state['error'] = f"追加できなかった本: {state['books_failed']}冊。完了した範囲は保持しています。"
    except Exception as ex:
        state['state'] = 'failed'; state['error'] = '複数本の追加を終了できませんでした（'+type(ex).__name__+'）。'
    finally:
        ai._last_activity = time.monotonic()
        with ai.guard: ai.store.save_state(state)
