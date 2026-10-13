"""Evaluate literal (non-AI) search on the frozen literal-related-v3 manifest.

Runs entirely on generated placeholder files in a temporary directory with a
temporary production DB; no model, GPU, network or private folder is used.

Conditions (same items, same queries, same graded qrels):
  legacy      former contiguous LIKE over title/tags (emulated SQL, reference)
  normalized  current literal search, empty related-term dictionary
  dictionary  current literal search with the manifest's user dictionary

The dictionary and queries were written by the same evaluator, so the
dictionary condition shows mechanism behaviour, not real-library quality.

Usage: python tools/evaluate_literal_search.py [--output data/literal-eval/result.json]
"""
import argparse
import hashlib
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tools'))
from production import ProductionCatalog  # noqa: E402
from search_quality import metrics, summary  # noqa: E402

MANIFEST = ROOT / 'tests' / 'fixtures' / 'literal-related-v3.json'
SHA256 = 'c4fa0d94c6ebf4459bf4e9d593af759b39afd8a680404b999d0596f602385091'
CONDITIONS = ('legacy', 'normalized', 'dictionary')


def legacy_search(catalog, query, kind):
    """The pre-2026-10-13 ProductionCatalog literal SQL, kept only for comparison."""
    where, values = ["l.status<>'excluded'"], []
    if query.strip():
        q = query.strip().replace('!', '!!').replace('%', '!%').replace('_', '!_')
        where.append("(i.title LIKE ? ESCAPE '!' OR i.tags LIKE ? ESCAPE '!')")
        values.extend([f'%{q}%'] * 2)
    if kind:
        where.append('i.kind=?'); values.append(kind)
    with catalog.connect() as db:
        rows = db.execute('SELECT i.title' + catalog.JOIN + ' WHERE ' + ' AND '.join(where) +
                          ' ORDER BY i.id LIMIT 120', values).fetchall()
    return [row['title'] for row in rows]


def evaluate():
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise SystemExit('Frozen manifest changed; create a new version instead of editing it')
    manifest = json.loads(raw)
    by_title = {item['file']: item['key'] for item in manifest['items']}
    with tempfile.TemporaryDirectory(prefix='aredoko-literal-') as tmp:
        base = pathlib.Path(tmp); media = base / 'media'; media.mkdir()
        for item in manifest['items']:
            (media / item['file']).write_bytes(b'generated placeholder; literal search does not read content')
        catalog = ProductionCatalog(base / 'catalog.sqlite')
        try:
            root = catalog.add_root(str(media)); catalog.start_scan(root); catalog._worker.join(30)
            if catalog.scan_state()['state'] != 'complete':
                raise SystemExit('fixture scan did not complete')
            ids = {row['title']: row['id'] for row in catalog.search(limit=120)['items']}
            for item in manifest['items']:
                if item['tags']:
                    catalog.update([ids[item['file']]], {'tags': item['tags']})
            rows = []
            for condition in CONDITIONS:
                if condition == 'dictionary':
                    for entry in manifest['dictionary']:
                        catalog.terms.upsert(entry)
                for case in manifest['cases']:
                    if condition == 'legacy':
                        titles = legacy_search(catalog, case['query'], case['kind'])
                    else:
                        result = catalog.search(case['query'], kind=case['kind'], limit=120)
                        titles = [row['title'] for row in result['items']]
                    ranked = [by_title[title] for title in titles]
                    rows.append({'case': case['id'], 'group': case['group'], 'query': case['query'],
                                 'source': condition, 'filter': case['kind'] or 'all-kinds',
                                 'ranked': ranked, 'returned': len(ranked),
                                 'metrics': metrics(ranked, case['relevance'])})
        finally:
            catalog.close()
    grouped = summary([dict(row, filter='all-filters') for row in rows])
    return {'manifest': MANIFEST.name, 'sha256': SHA256, 'conditions': list(CONDITIONS),
            'rows': rows, 'summary': grouped}


def main():
    parser = argparse.ArgumentParser(description='Literal search evaluation on generated fixtures')
    parser.add_argument('--output', help='optional JSON path inside data/')
    args = parser.parse_args()
    result = evaluate()
    for entry in result['summary']:
        means = entry['means']
        text = ('no scored cases' if means is None else
                ' '.join(f"{key}={value:.3f}" for key, value in means.items()))
        print(f"{entry['group']:<14} {entry['source']:<10} cases={entry['cases']} scored={entry['scored_cases']} {text}")
    for row in result['rows']:
        if row['metrics'] is None or row['metrics']['recall_at_5'] < 1 or row['metrics']['best_grade_at_1'] < 1:
            print(f"  {row['source']:<10} {row['case']} {row['query']!r}: top={row['ranked'][:5]} returned={row['returned']}")
    if args.output:
        output = (ROOT / args.output).resolve()
        if (ROOT / 'data').resolve() not in output.parents:
            raise SystemExit('--output must be inside the ignored data/ folder')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
