"""Generated-only candidate-boundary audit; never opens an existing library.

The report separates an audit that ran correctly from a product completion gate
that can fail. Sparse 3D vectors are deterministic controls, not model quality.
"""
import argparse
from array import array
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
import ai_search
from ai_profiles import DEFAULT_PROFILE
from ai_search import AISearch, revision, source_contract
from create_preview_fixture import png
from page_semantics import CONTRACT as PAGE_CONTRACT
from production import ProductionCatalog
from tag_candidate_search import search_candidates
from tag_semantics import semantic_candidates
from tag_suggestions import TagSuggestions, TaggerInfo

FINAL_TAG = 'boundary_final_item'
FINAL_SHELF = 'boundary-final'
MAX_FIXTURE_ITEMS = 50_001


class QueryOnlyEncoder:
    profile = replace(DEFAULT_PROFILE, dimension=3)
    available = True
    resident = False

    def __init__(self):
        self.calls = []

    def encode(self, operation, value):
        if operation != 'query':
            raise AssertionError('No document/image inference in boundary audit')
        self.calls.append(operation)
        return [1., 0., 0.]

    def close(self):
        pass


def fingerprint(paths, base):
    return {path.relative_to(base).as_posix(): {
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'mtime_ns': path.stat().st_mtime_ns,
    } for path in paths}


def vector_digest(store):
    result = hashlib.sha256()
    with store.connect() as db:
        for table in ('ai_vectors', 'ai_source_contracts', 'ai_video_frames',
                      'ai_page_vectors', 'ai_proposal_vectors'):
            result.update(table.encode())
            for row in db.execute('SELECT * FROM ' + table + ' ORDER BY 1,2,3'):
                for value in row:
                    data = value if isinstance(value, bytes) else str(value).encode()
                    result.update(len(data).to_bytes(8, 'big')); result.update(data)
    return result.hexdigest()


def seed(folder, count, cap):
    """Synthetic catalog rows; only sparse controls have physical sources."""
    folder.mkdir(parents=True, exist_ok=False)
    media = folder / 'generated'; media.mkdir()
    catalog = ProductionCatalog(folder / 'catalog.sqlite')
    try:
        roots = []
        for n in range(3):
            path = media / f'root-{n}'; path.mkdir()
            roots.append(catalog.add_root(str(path.resolve())))
        controls = sorted({1, min(cap - 1, count), min(cap, count),
                           min(cap + 1, count), count - 1, count})
        books = {min(cap + 1, count - 1), count - 1}
        paths = []
        for start in range(1, count + 1, 256):
            locations = []; items = []; mappings = []
            for item in range(start, min(start + 256, count + 1)):
                root = roots[(item - 1) % 3]
                kind = 'book' if item in books else 'image'
                name = f'generated-{item:06d}' + ('.cbz' if kind == 'book' else '.png')
                size = 0; mtime = 1
                if item in controls:
                    path = media / f'root-{(item - 1) % 3}' / name
                    if kind == 'book':
                        with zipfile.ZipFile(path, 'w') as archive:
                            archive.writestr('1.png', png(16, 16, (20, 40, 80)))
                    else:
                        path.write_bytes(png(16, 16, (20, 40, 80)))
                    paths.append(path); size = path.stat().st_size; mtime = path.stat().st_mtime_ns
                tags = [FINAL_TAG] if item == count else []
                shelf = FINAL_SHELF if item == count else ''
                locations.append((item, root, name, kind, size, mtime,
                                  'present', '2026-10-18', '2026-10-18'))
                items.append((item, name, kind, json.dumps(tags), shelf, int(item == count)))
                mappings.append((item, item))
            with catalog.connect() as db:
                db.executemany('INSERT INTO library_locations(id,root_id,relative_path,kind,size_bytes,mtime_ns,status,discovered_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?)', locations)
                db.executemany('INSERT INTO items(id,title,kind,tags,shelf,favorite) VALUES(?,?,?,?,?,?)', items)
                db.executemany('INSERT INTO item_locations VALUES(?,?)', mappings)
        return catalog, roots, controls, books, paths
    except BaseException:
        catalog.close()
        raise


def run(output, count):
    if type(count) is not int or not 8 <= count <= MAX_FIXTURE_ITEMS:
        raise ValueError('Fixture count must be an integer from 8 to 50001')
    cap = ai_search.MAX_ITEMS
    if cap < 3:
        raise ValueError('Audit requires candidate cap >= 3')
    output = Path(output)
    catalog, roots, controls, books, paths = seed(output, count, cap)
    encoder = QueryOnlyEncoder(); ai = None
    started = time.perf_counter()
    try:
        ai = AISearch(catalog, encoder)
        service = TagSuggestions(catalog)
        before_sources = fingerprint(paths, output)
        producer = TaggerInfo('boundary-fixture', '1', 'test-only', 'generated', 'cover-v1')
        rows = ai._current_rows(controls)
        for item in controls:
            row = rows[item]
            vector = [1., 0., 0.] if item in (1, count) else [.6, .8, 0.]
            vectors = {'text': vector}
            # Page-only books isolate the outer candidate gate from page rank.
            if item not in books:
                vectors['cover'] = vector
            ai.store.put(item, revision(row), vectors,
                         source_contract=source_contract(row, ai.profile) if 'cover' in vectors else None)
            source = service._source(item)
            if item in books:
                ai.pages.index.refresh(item)
                snapshot = ai.pages.index.list(item)
                page = snapshot['pages'][0]
                with ai.store.connect() as db:
                    db.execute('INSERT INTO ai_page_vectors VALUES(?,?,?,?,?,?)',
                               (item, source['revision'], page['page_id'], 0,
                                array('f', vector).tobytes(), PAGE_CONTRACT))
            with catalog.connect() as db:
                batch = db.execute('INSERT INTO tag_proposal_batches(item_id,source_revision,producer_key,producer_json,evidence_json,created_at) VALUES(?,?,?,?,?,?)',
                                   (item, source['revision'], hashlib.sha256(json.dumps(producer.record(), sort_keys=True).encode()).hexdigest(),
                                    json.dumps(producer.record()), '{}', 0.)).lastrowid
                db.execute("INSERT INTO tag_proposals(batch_id,tag,explanation,page,state) VALUES(?,?,?,0,'pending')",
                           (batch, FINAL_TAG if item == count else 'distractor', 'generated control'))
            snapshot = ai.pending_tags.snapshots([item])[item]
            with ai.store.connect() as db:
                db.execute('INSERT INTO ai_proposal_vectors VALUES(?,?,?,?,?)',
                           (item, batch, source['revision'], snapshot['signature'], array('f', vector).tobytes()))

        before_vectors = vector_digest(ai.store)
        checks = []
        observations = []

        def check(name, condition):
            checks.append({'name': name, 'passed': bool(condition)})
            if not condition:
                raise AssertionError('Audit control failed: ' + name)

        def observe(name, result, expected_ids, evidence=None):
            actual = [row['id'] for row in result['items']]
            expected = set(expected_ids)
            record = {'case': name, 'expected_indexed_total': len(expected),
                      'actual_total': result['total'], 'returned_ids': actual,
                      'expected_final': count in expected, 'returned_final': count in actual,
                      'gate_passed': result['total'] == len(expected) and set(actual) == expected}
            if evidence:
                record['page_evidence_ids'] = [row['id'] for row in result['items'] if 'ai_page_match' in row]
            observations.append(record)

        def expected(scope=None, view='all', source='all', origin=None):
            selected = []
            for item in controls:
                row = rows[item]
                if scope is not None:
                    if scope.get('root_ids') is not None and row['root_id'] not in scope['root_ids']: continue
                    if scope.get('shelf') is not None and row['shelf'] != scope['shelf']: continue
                if view == 'favorites' and not row['favorite']: continue
                if source == 'similar' and (item == origin or item in books): continue
                selected.append(item)
            return selected

        # Independent controls verify that absent tail results are not unindexed.
        literal = catalog.search(FINAL_TAG)
        check('literal reaches final item', literal['total'] == 1 and literal['items'][0]['id'] == count)
        raw_pending = search_candidates(service, FINAL_TAG)
        check('literal pending search reaches final item', raw_pending['total'] == 1 and raw_pending['items'][0]['id'] == count)
        check('final text vector is fresh', ai.store.text(rows[count]) is not None)
        check('unindexed metadata is distinct', ai.store.text(catalog.get(2)) is None)
        direct_page = ai.pages.rank([rows[item] for item in sorted(books)], [1., 0., 0.])
        check('late page vectors are current', set(direct_page) == books and all(value[1]['page'] == 0 for value in direct_page.values()))
        counts = ai.coverage({}, limit=cap)
        check('coverage counts full catalog', counts['candidate_total'] == count and counts['target_total'] == min(cap, count))
        final_root = rows[count]['root_id']
        other_root = next(root for root in roots if root != final_root)
        cases = [('all', {}), ('single-root', {'root_ids': [final_root]}),
                 ('multiple-roots', {'root_ids': [final_root, other_root]}),
                 ('shelf', {'shelf': FINAL_SHELF}), ('empty', {'root_ids': []})]
        for label, scope in cases:
            for source in ('text', 'cover', 'all'):
                observe(label + '/' + source, ai.search(FINAL_TAG, source=source, scope=scope),
                        expected(scope), evidence=source in ('cover', 'all'))
        observe('omitted-scope/text', ai.search(FINAL_TAG, source='text'), expected())
        observe('scoped-favorites/text', ai.search(FINAL_TAG, source='text', view='favorites', scope={}),
                expected({}, 'favorites'))
        observe('omitted-scope-favorites/text', ai.search(FINAL_TAG, source='text', view='favorites'),
                expected(None, 'favorites'))
        observe('scoped-kind-book/cover', ai.search(FINAL_TAG, source='cover', kind='book', scope={}),
                sorted(books), evidence=True)
        observe('scope-kind-book/cover', ai.search(FINAL_TAG, source='cover', scope={'kind': 'book'}),
                sorted(books), evidence=True)
        for label, scope in cases[:-1]:
            if scope.get('shelf') is not None: continue  # Origin must be in scope.
            candidates = expected(scope, source='similar')
            origin = min(candidates)
            observe(label + '/similar', ai.similar(origin, scope=scope),
                    expected(scope, source='similar', origin=origin))
        # A page-only origin is explicitly unindexed for cover similarity.
        check('page-only similarity fallback stays explicit', ai.similar(min(books), scope={})['similarity_status'] == 'unindexed')
        for label, kwargs in [('all', {}), ('single-root', {'root_ids': [final_root]}),
                              ('multiple-roots', {'root_ids': [final_root, other_root]}),
                              ('shelf', {'shelf': FINAL_SHELF})]:
            observe(label + '/pending', semantic_candidates(service, ai, FINAL_TAG, **kwargs), expected(kwargs))

        # Preserve sources; lifecycle changes apply only to this new synthetic DB.
        catalog.set_excludes(final_root, [rows[count]['relative_path']])
        check('excluded final is not eligible', count not in ai._current_rows([count]))
        observe('excluded-final/text', ai.search(FINAL_TAG, source='text', scope={}),
                [item for item in controls if item != count])
        catalog.set_excludes(final_root, [])
        catalog.unregister_root(final_root)
        check('unregistered final is not eligible', count not in ai._current_rows([count]))
        observe('unregistered-root/text', ai.search(FINAL_TAG, source='text', scope={}),
                [item for item in controls if rows[item]['root_id'] != final_root])
        try:
            ai.search(FINAL_TAG, source='text', scope={'root_ids': [final_root]})
        except ValueError:
            check('inactive explicit scope rejected', True)
        else:
            check('inactive explicit scope rejected', False)
        restore_path = output / 'generated' / f'root-{roots.index(final_root)}'
        restored = catalog.add_root(str(restore_path.resolve()))
        check('re-registration retains root and index', restored == final_root and ai.store.text(ai._current_rows([count])[count]) is not None)
        observe('re-registered/text', ai.search(FINAL_TAG, source='text', scope={}), expected())

        # Replace only the worker: exercise the real start selection twice,
        # with no document/image encoding or mutation of persisted vectors.
        plans = []
        def record_plan(ids, scope, *, upper_id=0, limit=0):
            selected = list(ids) if ids is not None else [r['id'] for r in ai._iter_rows(limit=limit, scope=scope, all_candidates=True) if r['id'] <= upper_id]
            plans.append(selected)
            ai.store.save_state({'state': 'complete', 'processed': 0, 'total': len(selected),
                                 'indexed': 0, 'skipped': 0, 'error': '', 'scope': scope})
        with patch.object(ai, '_build', side_effect=record_plan):
            for _ in range(2):
                ai.start(limit=cap, scope={}); ai.worker.join(10)
                check('plan worker stopped ' + str(len(plans)), not ai.worker.is_alive())
        check('repeated build selects same prefix', plans[0] == plans[1] and plans[0] == list(range(1, min(count, cap) + 1)))
        check('source bytes and mtime unchanged', before_sources == fingerprint(paths, output))
        check('saved vectors unchanged', before_vectors == vector_digest(ai.store))
        check('only deterministic query calls', all(call == 'query' for call in encoder.calls))
        try:
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            head = 'unavailable'
        report = {'protocol': 'candidate-boundary-v1', 'head': head, 'generated_only': True,
                  'metadata_count': count, 'dimension': 3, 'candidate_cap': cap,
                  'physical_control_files': len(paths), 'indexed_control_ids': controls,
                  'page_control_ids': sorted(books),
                  'filesystem_scan_run': False, 'real_model_calls': 0,
                  'deterministic_query_calls': len(encoder.calls), 'coverage': counts,
                  'checks': checks, 'cases': observations,
                  'build_selection': {'count': len(plans[0]), 'last_id': plans[0][-1],
                                      'same_on_repeat': plans[0] == plans[1], 'worker_mocked': True},
                  'sources': before_sources, 'vector_digest': before_vectors,
                  'elapsed_seconds': round(time.perf_counter() - started, 6),
                  'audit_passed': all(c['passed'] for c in checks),
                  'completion_gate_passed': all(c['gate_passed'] for c in observations),
                  'known_misses': [c['case'] for c in observations if not c['gate_passed']],
                  'limits': 'Sparse fake vectors and metadata only; not full-pool RRF, model quality, scan, 1TB, RAM or end-to-end GUI performance evidence.'}
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    finally:
        if ai is not None: ai.close()
        catalog.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New dedicated fixture directory; existing paths refused')
    parser.add_argument('--count', type=int, choices=(10_001, 50_001), required=True)
    parser.add_argument('--require-complete', action='store_true', help='Exit 2 if any indexed candidate is omitted')
    args = parser.parse_args()
    report = run(args.output, args.count)
    print(json.dumps({key: report[key] for key in ('metadata_count', 'audit_passed', 'completion_gate_passed', 'known_misses', 'elapsed_seconds')}, ensure_ascii=False))
    return 2 if args.require_complete and not report['completion_gate_passed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
