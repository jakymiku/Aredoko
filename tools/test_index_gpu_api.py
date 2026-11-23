"""Verify production HTTP paging/filters on a completed generated 10k GPU fixture.

Existing offline model/runtime only. No scans, downloads or native GUI. Accepts
only a completed generated benchmark below data/index-scaling; annotations are
restored in finally and source/vector digests are compared.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler
from test_index_gpu_scaling import MeasuredEncoder, source_digest, memory_bytes
from ai_search import AISearch


def vector_digest(ai):
    digest = hashlib.sha256()
    with ai.store.connect() as db:
        for item_id, revision, mode, vector in db.execute(
                'SELECT * FROM ai_vectors ORDER BY item_id,modality'):
            digest.update(f'{item_id}:{revision}:{mode}'.encode()); digest.update(vector)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    args = parser.parse_args(); target = args.fixture.resolve()
    if not target.is_relative_to((REPO / 'data/index-scaling').resolve()):
        parser.error('Fixture must be under data/index-scaling')
    evidence = target / 'result.json'; output = target / 'api-result.json'
    if not evidence.is_file() or output.exists(): parser.error('Completed fixture and fresh API result required')
    previous = json.loads(evidence.read_text(encoding='utf-8'))
    if not (previous.get('pass') and previous.get('actual_model') and
            previous.get('fixtures', {}).get('generated_sources_only') and
            previous.get('inference_calls', {}).get('document') == 10000):
        parser.error('Completed generated actual-GPU 10000 fixture required')
    database = target / 'catalog.sqlite'; media = target / 'generated'
    # Check declared roots read-only before creating product objects.
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        roots = [Path(row[0]).resolve() for row in db.execute('SELECT path FROM library_roots')]
    if roots != [media]: parser.error('Generated root mismatch')
    evidence_hash = hashlib.sha256(evidence.read_bytes()).hexdigest()
    source_before = source_digest(media)
    catalog = ProductionCatalog(database); encoder = MeasuredEncoder(); ai = AISearch(catalog, encoder)
    vectors_before = vector_digest(ai)
    report = {'pass': False, 'actual_model': True, 'native_gui_run': False, 'checks': [], 'requests': []}
    owned = [1, 10000]; favorites = {item_id: catalog.get(item_id)['favorite'] for item_id in owned}
    server = None; thread = None
    def check(label, condition):
        report['checks'].append({'name': label, 'pass': bool(condition)})
        if not condition: raise RuntimeError(label)
    try:
        settings = AIProfileSettings(REPO, target / 'api-settings.json')
        token = secrets.token_urlsafe(32)
        server = ThreadingHTTPServer(('127.0.0.1', 0), production_handler(catalog, token, ai=ai, profiles=settings))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        def search(label, **extra):
            body = {'query': '傘が必要な暗い都会の景色', **extra}
            started = time.perf_counter()
            request = urllib.request.Request(origin + '/api/library/ai/search', json.dumps(body).encode(),
                      {'Content-Type': 'application/json', 'Origin': origin, 'X-Aredoko-Token': token})
            with urllib.request.urlopen(request, timeout=180) as response:
                check(label + ' HTTP 200', response.status == 200)
                found = json.load(response)
            report['requests'].append({'label': label, 'seconds': time.perf_counter() - started,
                                       'total': found['total'], 'page': found['page'],
                                       'items': len(found['items'])})
            check(label + ' coverage limit', found['coverage_limit'] == 10000)
            return found
        first = search('first'); second = search('second', page=1)
        last = search('last', page=166); beyond = search('beyond', page=167)
        check('all pages total 10000', all(x['total'] == 10000 for x in [first, second, last, beyond]))
        check('60/60/40/0 paging', [len(x['items']) for x in [first, second, last, beyond]] == [60, 60, 40, 0])
        groups = [{x['id'] for x in page['items']} for page in [first, second, last]]
        check('separate page IDs', not any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)))
        images = search('images', kind='image')
        check('kind image filtering', images['total'] == 625 and all(x['kind'] == 'image' for x in images['items']))
        covers = search('covers', source='cover')
        check('cover-only total 938', covers['total'] == 938)
        update = urllib.request.Request(origin + '/api/items/update',
                 json.dumps({'ids': owned, 'changes': {'favorite': True}}).encode(),
                 {'Content-Type': 'application/json', 'Origin': origin, 'X-Aredoko-Token': token})
        with urllib.request.urlopen(update, timeout=15) as response:
            check('favorite HTTP update persisted', response.status == 200 and
                  json.load(response)['updated'] == 2 and all(catalog.get(i)['favorite'] for i in owned))
        favored = search('favorites', view='favorites')
        check('favorites filter includes distant generated IDs',
              favored['total'] == 2 and {x['id'] for x in favored['items']} == set(owned))
        check('real query only, no document/image inference', dict(encoder.calls) == {'query': 7} and encoder.device == 'cuda')
        report['controller_memory_bytes'] = memory_bytes(os.getpid())
        check('HTTP controller memory readable', bool(report['controller_memory_bytes']))
        report['memory_scope'] = 'Controller process lifetime peak includes HTTP server and all requests; GUI excluded. CUDA is torch max allocated, not whole-board VRAM.'
        report['max_cuda_allocated_mib'] = encoder.peak_cuda_allocated_mib
        report['pass'] = True
    except Exception as ex:
        report['error'] = type(ex).__name__ + ': ' + str(ex)
    finally:
        try:
            if server: server.shutdown(); server.server_close()
            if thread: thread.join(5)
            for item_id, favorite in favorites.items(): catalog.update([item_id], {'favorite': favorite})
            check('favorites restored', all(catalog.get(i)['favorite'] == value for i, value in favorites.items()))
            check('saved vectors unchanged', vector_digest(ai) == vectors_before)
            ai.close()
            check('owned model process instances stopped', bool(encoder.observed_exits) and
                  all(row['stopped'] for row in encoder.observed_exits))
            check('generated source bytes/size/mtime unchanged', source_digest(media) == source_before)
            check('benchmark evidence unchanged', hashlib.sha256(evidence.read_bytes()).hexdigest() == evidence_hash)
        except Exception as ex:
            report['pass'] = False; report['cleanup_error'] = str(ex)
        finally:
            ai.close(); catalog.close()
        report['observed_process_exits'] = encoder.observed_exits
        report['inference_calls'] = dict(encoder.calls)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'pass': report['pass'], 'checks': len(report['checks']),
                          'error': report.get('error'), 'cleanup_error': report.get('cleanup_error')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
