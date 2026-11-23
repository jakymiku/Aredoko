"""One frozen P0 run; generated media and existing offline model only."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'app'))
from production import ProductionCatalog
from ai_search import AISearch
from ai_profiles import DEFAULT_PROFILE
from create_holdout_fixture import create
from search_quality import metrics
from test_index_gpu_scaling import MeasuredEncoder, source_digest
from test_index_gpu_api import vector_digest

MANIFEST = REPO / 'tests/fixtures/search-phase-v7.json'
SHA256 = '8212da5d4c146c8ac1086e04c95a3514d3564a1171cb3f9fe66498389f7e499b'


def load_manifest():
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('Frozen v7 input changed; do not edit observed inputs')
    value = json.loads(raw)
    items = {item['key']: item for item in value['items']}
    if len(items) != 24 or len(value['cases']) != 24:
        raise ValueError('Invalid fixed corpus')
    for case in value['cases']:
        if not set(case['relevance']) <= items.keys():
            raise ValueError('Unknown qrel')
        metrics([], case['relevance'])
    return raw, value


def aggregate(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['scope'], row['condition'], row['group']), []).append(row)
    result = []
    for (scope, condition, group), values in sorted(groups.items()):
        scored = [v['metrics'] for v in values if v['metrics'] is not None]
        probes = [v for v in values if v['no_answer_probe'] and v['eligible_count'] > 0]
        elapsed = sorted(v['elapsed_ms'] for v in values)
        result.append({'scope': scope, 'condition': condition, 'group': group,
                       'cases': len(values), 'scored_cases': len(scored),
                       'means': {key: statistics.mean(v[key] for v in scored) for key in scored[0]} if scored else None,
                       'no_answer_cases': len(probes),
                       'correct_empty_rate': sum(v['returned_count'] == 0 for v in probes) / len(probes) if probes else None,
                       'latency_median_ms': statistics.median(elapsed),
                       'latency_p95_ms': elapsed[math.ceil(.95 * len(elapsed)) - 1]})
    return result


def evaluate(target, encoder=None):
    raw, manifest = load_manifest()  # Fail before creating or reading media.
    target.mkdir(parents=True, exist_ok=False)
    (target / 'manifest.json').write_bytes(raw)
    report = {'runtime_pass': False, 'suite': 'phase-p0-v7', 'manifest_sha256': SHA256,
              'generated_only': True, 'profile': DEFAULT_PROFILE.identity(),
              'ranking': 'mean-rrf', 'actual_cuda': encoder is None,
              'quality_gate': 'diagnostic_only' if encoder is None else 'test_double_not_model_quality',
              'ui_time_to_find_ms': None, 'ui_interaction_count': None,
              'ui_measurement_note': 'No native UI run; retrieval latency is not time to find.',
              'cases': [], 'checks': []}
    catalog = ai = None
    folders = {}
    before = None
    def check(name, condition):
        report['checks'].append({'name': name, 'pass': bool(condition)})
        if not condition:
            raise RuntimeError(name)
    try:
        folders = {root: create(target / ('media-' + root), [i for i in manifest['items'] if i['root'] == root]) for root in ('A', 'B')}
        before = {root: source_digest(folder) for root, folder in folders.items()}
        catalog = ProductionCatalog(target / 'catalog.sqlite')
        roots = {}
        for root, folder in folders.items():
            roots[root] = catalog.add_root(str(folder))
            catalog.start_scan(roots[root]); catalog._worker.join(20)
            check('generated scan ' + root, not catalog._worker.is_alive() and catalog.scan_state()['state'] == 'complete')
        by_file = {row['title']: row for row in catalog.search()['items']}
        items = {i['key']: i for i in manifest['items']}
        check('exactly the frozen files', set(by_file) == {i['file'] for i in items.values()})
        by_id = {}
        for item in items.values():
            row = by_file[item['file']]; by_id[row['id']] = item['key']
            check('registered kind ' + item['key'], row['kind'] == item['kind'])
            if item['tags']:
                catalog.update([row['id']], {'tags': item['tags']})
        encoder = encoder or MeasuredEncoder()
        ai = AISearch(catalog, encoder)
        scope = {'root_ids': list(roots.values()), 'kind': '', 'shelf': None}
        started = time.perf_counter(); ai.start(scope=scope); ai.worker.join(240)
        report['index_seconds'] = round(time.perf_counter() - started, 3)
        check('fixture index complete', not ai.worker.is_alive() and ai.status()['state'] == 'complete' and ai.status()['indexed'] == 24)
        if report['actual_cuda']:
            check('actual CUDA used', encoder.device == 'cuda')
            check('real text/cover inference', encoder.calls['document'] == 24 and encoder.calls['image'] == 16)
        vectors = vector_digest(ai)
        for condition in manifest['conditions']:
            if condition == 'related':
                for entry in manifest['terms']:
                    catalog.terms.upsert(entry)
            for variant, selected in [('all-roots', ['A', 'B']), ('root-A', ['A'])]:
                ids = [roots[name] for name in selected]
                for case in manifest['cases']:
                    source = condition if condition in ('cover', 'text', 'all') else None
                    eligible = {key for key, item in items.items() if item['root'] in selected and item['kind'] == case['kind'] and (source != 'cover' or item['kind'] in ('image', 'book'))}
                    relevance = {key: grade for key, grade in case['relevance'].items() if key in eligible}
                    started = time.perf_counter()
                    if source:
                        response = ai.search(case['query'], kind=case['kind'], source=source, scope={'root_ids': ids, 'kind': '', 'shelf': None})
                    else:
                        response = catalog.search(case['query'], kind=case['kind'], root_ids=ids)
                    elapsed = time.perf_counter() - started
                    ranked = [by_id[row['id']] for row in response['items']]
                    check('result scope and modality', set(ranked) <= eligible)
                    report['cases'].append({'id': case['id'], 'query': case['query'], 'group': case['group'],
                        'evidence': case['evidence'], 'condition': condition, 'scope': variant,
                        'kind': case['kind'], 'eligible_count': len(eligible), 'relevance': relevance,
                        'no_answer_probe': case['group'] == 'no-answer',
                        'scope_excludes_relevance': bool(case['relevance']) and not relevance and bool(eligible),
                        'source_ineligible': not eligible, 'returned_count': len(ranked),
                        'top_5': ranked[:5], 'metrics': metrics(ranked, relevance),
                        'ranks': {key: ranked.index(key) + 1 if key in ranked else None for key in relevance},
                        'elapsed_ms': round(elapsed * 1000, 3)})
                print(json.dumps({'completed': condition, 'scope': variant}), flush=True)
        check('indexed vectors unchanged', vector_digest(ai) == vectors)
        check('frozen manifest unchanged', MANIFEST.read_bytes() == raw)
        report['summary'] = aggregate(report['cases'])
        report['telemetry'] = dict(getattr(encoder, 'telemetry', {}))
        report['index_status'] = ai.status()
        report['calls'] = dict(encoder.calls) if report['actual_cuda'] else 'test-double'
        report['runtime_pass'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        try:
            if ai:
                ai.close()
            elif encoder:
                encoder.close()
            if report['actual_cuda'] and encoder:
                report['owned_exits'] = encoder.observed_exits
                check('owned worker instances stopped', bool(encoder.observed_exits) and all(row['stopped'] for row in encoder.observed_exits))
        except Exception as error:
            report['runtime_pass'] = False; report['cleanup_error'] = type(error).__name__
        if catalog:
            catalog.close()
        if before is not None:
            report['source_unchanged'] = {root: source_digest(folder) for root, folder in folders.items()} == before
            if not report['source_unchanged']:
                report['runtime_pass'] = False
        (target / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); target = args.output.resolve()
    if os.name != 'nt' or not target.is_relative_to((REPO / 'data/ai-ui').resolve()):
        parser.error('New generated output under data/ai-ui on Windows required')
    if not DEFAULT_PROFILE.model_path(REPO).is_dir() or not (REPO / '.venv-ai/Scripts/python.exe').is_file():
        parser.error('Existing local weights/environment required; no download')
    report = evaluate(target)
    print(json.dumps({'runtime_pass': report['runtime_pass'], 'rows': len(report['cases']), 'error': report.get('error')}))
    return 0 if report['runtime_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
